"""
app/core/notifications/fcm_sender.py — push nativo via Firebase Cloud Messaging (HTTP v1).

Sem SDK do Google: a API v1 é REST. A autenticação é a de conta de serviço:
um JWT assinado com a chave privada (RS256) é trocado por um access token
OAuth2 de 1 h, guardado em memória até perto de vencer.

Configuração: FCM_SERVICE_ACCOUNT_B64 — o JSON da conta de serviço do
Firebase (Configurações do projeto → Contas de serviço → Gerar nova chave),
em base64. É um SEGREDO: só no gerenciador de segredos do deploy.

Privacidade: a notificação Android sai com visibility=PRIVATE — na tela de
bloqueio protegida aparece só "conteúdo oculto"; valores em R$ não ficam
expostos para quem pega o celular.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_ESCOPO = "https://www.googleapis.com/auth/firebase.messaging"
_ENVIO = "https://fcm.googleapis.com/v1/projects/{projeto}/messages:send"
_TIMEOUT = 10.0

_cache_lock = threading.Lock()
_cache: dict[str, object] = {"token": None, "expira": 0.0}


def _credenciais() -> dict | None:
    from app.core.config import settings

    bruto = (getattr(settings, "FCM_SERVICE_ACCOUNT_B64", "") or "").strip()
    if not bruto:
        return None
    try:
        dados = json.loads(base64.b64decode(bruto).decode())
    except Exception:
        logger.error("[FCM] FCM_SERVICE_ACCOUNT_B64 não é um JSON em base64 válido")
        return None
    if dados.get("type") != "service_account" or not all(
        dados.get(k) for k in ("project_id", "private_key", "client_email")
    ):
        logger.error("[FCM] credencial sem type=service_account/project_id/private_key/client_email")
        return None
    return dados


def is_configured() -> bool:
    return _credenciais() is not None


def _access_token(cred: dict, transport: httpx.BaseTransport | None = None, forcar: bool = False) -> str:
    with _cache_lock:
        agora = time.time()
        if not forcar and _cache["token"] and float(_cache["expira"]) - 60 > agora:
            return str(_cache["token"])
        from jose import jwt

        claims = {
            "iss": cred["client_email"],
            "scope": _ESCOPO,
            "aud": _TOKEN_URI,
            "iat": int(agora),
            "exp": int(agora) + 3600,
        }
        headers = {"kid": cred["private_key_id"]} if cred.get("private_key_id") else None
        assertion = jwt.encode(claims, cred["private_key"], algorithm="RS256", headers=headers)
        with httpx.Client(timeout=_TIMEOUT, transport=transport) as client:
            resp = client.post(_TOKEN_URI, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            })
        resp.raise_for_status()
        dados = resp.json()
        _cache["token"] = dados["access_token"]
        _cache["expira"] = agora + float(dados.get("expires_in", 3600))
        return str(_cache["token"])


def _token_invalido(resp: httpx.Response) -> bool:
    """O token do aparelho morreu (app desinstalado, token trocado, outro projeto)."""
    if resp.status_code == 404:
        return True
    try:
        erro = resp.json().get("error") or {}
    except ValueError:
        return False
    codigos = {d.get("errorCode") for d in erro.get("details") or [] if isinstance(d, dict)}
    if codigos & {"UNREGISTERED", "SENDER_ID_MISMATCH"}:
        return True
    return resp.status_code == 400 and "registration token" in str(erro.get("message", "")).lower()


def montar_mensagem(token: str, title: str, body: str, url: str, tag: str) -> dict:
    return {
        "message": {
            "token": token,
            "notification": {"title": title[:120], "body": body[:500]},
            # data só aceita strings; a rota é lida pelo app ao tocar na notificação
            "data": {"url": url if url.startswith("/") else "/feed", "tag": tag or ""},
            "android": {
                "priority": "HIGH",
                "ttl": "21600s",  # o alerta perde valor depois de algumas horas
                "notification": {
                    "channel_id": "alertas",
                    "tag": tag or "hive",
                    "visibility": "PRIVATE",
                },
            },
            "apns": {
                "headers": {"apns-priority": "10", "apns-expiration": str(int(time.time()) + 21600)},
                "payload": {"aps": {"thread-id": tag or "hive", "sound": "default"}},
            },
        }
    }


def enviar(token: str, title: str, body: str, url: str = "/feed", tag: str = "",
           transport: httpx.BaseTransport | None = None) -> str:
    """'ok' | 'invalido' (revogar o aparelho) | 'falha' (tentar no próximo ciclo)."""
    cred = _credenciais()
    if cred is None:
        return "falha"
    corpo = montar_mensagem(token, title, body, url, tag)
    destino = _ENVIO.format(projeto=cred["project_id"])
    for tentativa in (1, 2):
        try:
            access = _access_token(cred, transport, forcar=tentativa == 2)
            with httpx.Client(timeout=_TIMEOUT, transport=transport) as client:
                resp = client.post(destino, json=corpo, headers={"Authorization": f"Bearer {access}"})
        except httpx.HTTPError as exc:
            logger.warning("[FCM] falha de rede: %s", exc)
            return "falha"
        if resp.status_code == 401 and tentativa == 1:
            continue  # access token revogado/expirado antes do previsto: renova uma vez
        if resp.is_success:
            return "ok"
        if _token_invalido(resp):
            return "invalido"
        logger.warning("[FCM] envio recusado HTTP %s", resp.status_code)
        return "falha"
    return "falha"


# ── aparelhos ────────────────────────────────────────────────────────────

def registrar_aparelho(user_id: str, token: str, platform: str, app_version: str | None) -> None:
    """Grava (ou transfere para este usuário) o token do aparelho."""
    from app.core.database import SessionLocal
    from app.notifications.models_orm import PushDevice

    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        row = db.query(PushDevice).filter(PushDevice.token == token).first()
        if row is None:
            db.add(PushDevice(
                id=str(uuid.uuid4()), user_id=user_id, token=token, platform=platform,
                app_version=app_version, created_at=agora, last_seen_at=agora,
            ))
        else:
            if row.user_id != user_id:
                logger.info("[FCM] aparelho passou de uma conta para outra — transferido")
            row.user_id = user_id
            row.platform = platform
            row.app_version = app_version
            row.last_seen_at = agora
            row.revoked_at = None
        db.commit()


def remover_aparelho(user_id: str, token: str | None = None) -> int:
    """Revoga um aparelho do usuário (ou todos, sem token)."""
    from app.core.database import SessionLocal
    from app.notifications.models_orm import PushDevice

    try:
        with SessionLocal() as db:
            q = db.query(PushDevice).filter(PushDevice.user_id == user_id, PushDevice.revoked_at.is_(None))
            if token:
                q = q.filter(PushDevice.token == token)
            n = q.update({PushDevice.revoked_at: datetime.now(timezone.utc)}, synchronize_session=False)
            db.commit()
            return int(n)
    except Exception as exc:
        logger.warning("[FCM] remoção de aparelho falhou user=%s: %s", user_id, exc)
        return 0


def aparelhos_ativos(user_id: str) -> list[tuple[str, str]]:
    """[(id, token)] dos aparelhos ativos do usuário."""
    try:
        from app.core.database import SessionLocal
        from app.notifications.models_orm import PushDevice

        with SessionLocal() as db:
            rows = (
                db.query(PushDevice.id, PushDevice.token)
                .filter(PushDevice.user_id == user_id, PushDevice.revoked_at.is_(None))
                .all()
            )
        return [(r[0], r[1]) for r in rows]
    except Exception as exc:
        logger.debug("[FCM] aparelhos_ativos user=%s: %s", user_id, exc)
        return []


def enviar_para_usuario(user_id: str, title: str, body: str, url: str = "/feed", tag: str = "") -> tuple[int, int]:
    """(enviados, falhados) para os aparelhos nativos do usuário."""
    if not is_configured():
        return 0, 0
    enviados = falhados = 0
    for device_id, token in aparelhos_ativos(user_id):
        resultado = enviar(token, title, body, url, tag)
        if resultado == "ok":
            enviados += 1
        else:
            falhados += 1
            if resultado == "invalido":
                _revogar_por_id(device_id)
    return enviados, falhados


def _revogar_por_id(device_id: str) -> None:
    try:
        from app.core.database import SessionLocal
        from app.notifications.models_orm import PushDevice

        with SessionLocal() as db:
            db.query(PushDevice).filter(PushDevice.id == device_id).update(
                {PushDevice.revoked_at: datetime.now(timezone.utc)}, synchronize_session=False
            )
            db.commit()
    except Exception as exc:
        logger.warning("[FCM] revogação do aparelho %s falhou: %s", device_id, exc)
