"""
app/core/notifications/push_sender.py — Canal Web Push (PWA, R1.d)

Envia notificações push para as inscrições (push_subscriptions) do
usuário via protocolo Web Push com VAPID (pywebpush).

Comportamento:
  - Sem VAPID configurado ou sem pywebpush instalado → canal desativado
    (is_configured() = False), tudo falha aberto.
  - Endpoint que responde 404/410 (inscrição expirada/revogada pelo
    navegador) é marcado revoked_at e não recebe mais tentativas.
  - Payload JSON: {title, body, url, tag} — interpretado pelo service
    worker do frontend (frontend-react/public/sw.js).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Serviços de push dos navegadores. O endpoint da inscrição vem do navegador do
# usuário e o servidor faz POST nele: sem esta lista, qualquer usuário logado
# registrava "http://169.254.169.254/..." ou um serviço interno e o backend
# passava a fazer requisições para lá (SSRF).
_HOSTS_DE_PUSH = (
    "fcm.googleapis.com",            # Chrome, Edge, Android
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "web.push.apple.com",            # Safari (macOS/iOS)
    "notify.windows.com",            # Edge legado (wns2-*.notify.windows.com)
)


def endpoint_permitido(endpoint: str) -> bool:
    """
    https, porta 443 e host de um serviço de push conhecido (ou subdomínio).

    O host passa por DOIS parsers que têm de concordar: o `urlparse` da stdlib
    e o do urllib3, que é o que o `requests` (dentro do pywebpush) usa para
    conectar. Eles divergem em URL ambígua. Em
    `https://evil.example\\@fcm.googleapis.com/x`, a stdlib lê o host depois do
    `@` (aprovaria), e o urllib3 corta a autoridade no `\\` e conecta em
    `evil.example`. Endpoint de push real nunca traz credencial, barra
    invertida, espaço, caractere de controle ou não-ASCII, então esses são
    recusados antes de qualquer parser.
    """
    from urllib.parse import urlparse

    from urllib3.util import parse_url

    if (
        not isinstance(endpoint, str)
        or not endpoint.isascii()
        or any(c in "\\@" or c <= " " or c == "\x7f" for c in endpoint)
    ):
        return False
    try:
        partes = urlparse(endpoint)
        conexao = parse_url(endpoint)
        porta = partes.port
    except Exception:
        return False
    host = (partes.hostname or "").lower()
    if (
        partes.scheme != "https"
        or not host
        or porta not in (None, 443)
        or partes.username is not None
        or partes.password is not None
        or partes.netloc.lower() not in (host, f"{host}:443")
    ):
        return False
    if (
        (conexao.scheme or "").lower() != "https"
        or (conexao.host or "").lower() != host
        or conexao.port not in (None, 443)
        or conexao.auth is not None
    ):
        return False
    return any(host == h or host.endswith("." + h) for h in _HOSTS_DE_PUSH)


def _sessao_sem_redirecionamento():
    """
    Sessão HTTP do envio que não segue redirecionamento.

    O `requests` segue 3xx por padrão. Se o servidor seguisse, um destino
    aprovado pela lista poderia mandar o backend para outro host ou porta, ou
    para HTTP puro. Serviço de push real responde 201, nunca 3xx.
    """
    import requests

    sessao = requests.Session()
    sessao.max_redirects = 0  # um 3xx vira TooManyRedirects antes do 2º pedido
    return sessao


@dataclass
class PushSubscription:
    id: str
    endpoint: str
    p256dh: str
    auth: str


def is_configured() -> bool:
    """True quando há chaves VAPID e a lib pywebpush está disponível."""
    from app.core.config import settings

    if not (settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY):
        return False
    try:
        import pywebpush  # noqa: F401
        return True
    except ImportError:
        return False


# ── CRUD de inscrições ───────────────────────────────────────────────

def save_subscription(
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str = "",
) -> bool:
    """Cria (ou reativa) uma inscrição. Idempotente por (user, endpoint)."""
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            updated = db.execute(
                text(
                    "UPDATE push_subscriptions"
                    " SET p256dh = :p, auth = :a, revoked_at = NULL"
                    " WHERE user_id = :uid AND endpoint = :ep"
                ),
                {"p": p256dh, "a": auth, "uid": user_id, "ep": endpoint},
            )
            if updated.rowcount == 0:
                db.execute(
                    text(
                        "INSERT INTO push_subscriptions"
                        " (id, user_id, endpoint, p256dh, auth, user_agent, created_at)"
                        " VALUES (:id, :uid, :ep, :p, :a, :ua, :now)"
                    ),
                    {
                        "id": str(uuid.uuid4()), "uid": user_id, "ep": endpoint,
                        "p": p256dh, "a": auth, "ua": user_agent[:255], "now": now,
                    },
                )
            db.commit()
        return True
    except Exception as exc:
        logger.warning("[PushSender] save_subscription user=%s: %s", user_id, exc)
        return False


def remove_subscription(user_id: str, endpoint: str) -> bool:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text(
                    "UPDATE push_subscriptions SET revoked_at = :now"
                    " WHERE user_id = :uid AND endpoint = :ep"
                ),
                {"now": datetime.now(timezone.utc), "uid": user_id, "ep": endpoint},
            )
            db.commit()
        return True
    except Exception as exc:
        logger.warning("[PushSender] remove_subscription user=%s: %s", user_id, exc)
        return False


def remover_inscricoes(user_id: str) -> int:
    """Revoga TODAS as inscrições de Web Push do usuário (corte de sessão)."""
    try:
        from sqlalchemy import text

        from app.core.database import SessionLocal

        with SessionLocal() as db:
            res = db.execute(
                text(
                    "UPDATE push_subscriptions SET revoked_at = :now"
                    " WHERE user_id = :uid AND revoked_at IS NULL"
                ),
                {"now": datetime.now(timezone.utc), "uid": user_id},
            )
            db.commit()
        return int(res.rowcount or 0)
    except Exception as exc:
        logger.warning("[PushSender] remover_inscricoes user=%s: %s", user_id, exc)
        return 0


def get_active_subscriptions(user_id: str) -> list[PushSubscription]:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT id, endpoint, p256dh, auth FROM push_subscriptions"
                    " WHERE user_id = :uid AND revoked_at IS NULL"
                ),
                {"uid": user_id},
            ).fetchall()
        return [PushSubscription(id=r[0], endpoint=r[1], p256dh=r[2], auth=r[3]) for r in rows]
    except Exception as exc:
        logger.debug("[PushSender] get_active_subscriptions user=%s: %s", user_id, exc)
        return []


def has_active_subscription(user_id: str) -> bool:
    return bool(get_active_subscriptions(user_id))


def tem_destino(user_id: str) -> bool:
    """Há para onde mandar push: navegador inscrito (Web Push) ou aparelho
    com o app nativo (FCM)."""
    from app.core.notifications import fcm_sender

    if is_configured() and has_active_subscription(user_id):
        return True
    return fcm_sender.is_configured() and bool(fcm_sender.aparelhos_ativos(user_id))


# ── Envio ────────────────────────────────────────────────────────────

def send_to_user(
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "",
) -> tuple[int, int]:
    """
    Envia push para todas as inscrições ativas do usuário.

    Inclui os aparelhos com o app nativo (FCM).

    Returns:
        (enviados, falhados)
    """
    from app.core.notifications import fcm_sender

    nativos_ok, nativos_falha = fcm_sender.enviar_para_usuario(user_id, title, body, url, tag)
    if not is_configured():
        return nativos_ok, nativos_falha

    subscriptions = get_active_subscriptions(user_id)
    if not subscriptions:
        return nativos_ok, nativos_falha

    from app.core.config import settings
    from pywebpush import WebPushException, webpush

    payload = json.dumps(
        {"title": title, "body": body, "url": url, "tag": tag},
        ensure_ascii=False,
    )

    sent, failed = nativos_ok, nativos_falha
    sessao = _sessao_sem_redirecionamento()
    try:
        for sub in subscriptions:
            ok = _enviar_web_push(webpush, WebPushException, sessao, sub, payload, settings)
            if ok:
                sent += 1
            else:
                failed += 1
    finally:
        sessao.close()

    return sent, failed


def _enviar_web_push(webpush, WebPushException, sessao, sub: PushSubscription, payload: str, settings) -> bool:
    """Uma inscrição: True se o serviço de push aceitou."""
    if not endpoint_permitido(sub.endpoint):
        # inscrição gravada antes da validação: nunca seguir um endpoint estranho
        _revoke(sub.id)
        logger.warning("[PushSender] inscrição %s com endpoint fora dos serviços de push — revogada", sub.id)
        return False
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            ttl=6 * 3600,   # o alerta perde valor depois de algumas horas
            requests_session=sessao,
        )
        _mark_success(sub.id)
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            # inscrição morta no push service — nunca mais tentar
            _revoke(sub.id)
            logger.info("[PushSender] inscrição %s revogada (HTTP %s)", sub.id, status)
        else:
            logger.warning("[PushSender] falha push sub=%s: %s", sub.id, exc)
        return False
    except Exception as exc:
        logger.warning("[PushSender] erro inesperado sub=%s: %s", sub.id, exc)
        return False



def _mark_success(subscription_id: str) -> None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text("UPDATE push_subscriptions SET last_success_at = :now WHERE id = :id"),
                {"now": datetime.now(timezone.utc), "id": subscription_id},
            )
            db.commit()
    except Exception:
        pass


def _revoke(subscription_id: str) -> None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text("UPDATE push_subscriptions SET revoked_at = :now WHERE id = :id"),
                {"now": datetime.now(timezone.utc), "id": subscription_id},
            )
            db.commit()
    except Exception:
        pass


__all__ = [
    "PushSubscription",
    "get_active_subscriptions",
    "has_active_subscription",
    "is_configured",
    "remove_subscription",
    "save_subscription",
    "send_to_user",
]
