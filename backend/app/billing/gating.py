"""
app/billing/gating.py — Enforcement de planos e limites de uso.

Dark launch: TODO o gating fica atrás de BILLING_ENFORCEMENT_ENABLED.
  - False (default): nada é bloqueado; violações são apenas LOGADAS
    ("[Gating] would_block ...") — permite medir impacto antes de ligar.
  - True (produção pós-lançamento): 402 Payment Required com o plano
    necessário e o preço — o frontend converte em tela de upgrade.

Uso nos routers:
    @router.get("/defense/{user_id}", dependencies=[require_plan("total")])
    ...
    # limites de uso (Free 5 msgs IA/dia etc.):
    consume_usage(user_id, "chat_messages")

Contadores: Redis (INCR + EXPIRE por janela) com fallback em memória —
mesmo padrão do Job Guard. As janelas seguem o calendário de São Paulo: a
diária vira à meia-noite de Brasília (em UTC virava às 21h, e o "5 mensagens
por dia" do Free recomeçava no meio da noite); a mensal, no dia 1º.

Enforcement só vale com o Stripe pronto para cobrar (chave + segredo do
webhook). Pedido sem isso, ele NÃO bloqueia e loga erro: bloquear quem não tem
como pagar seria pior do que deixar de cobrar por algumas horas.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException

from app.billing.plans import (
    FREE_LIMITS,
    PLAN_FREE,
    PLAN_PRO,
    PLANS,
    PRO_LIMITS,
    UsageLimit,
    plan_satisfies,
)
from app.core.config import settings
from app.core.security import require_owner

logger = logging.getLogger(__name__)

# Fallback em memória: {chave: (contagem, expira_em_epoch)}
_memory_counters: dict[str, tuple[int, float]] = {}

_FUSO = ZoneInfo("America/Sao_Paulo")
_avisou_sem_stripe = False


def enforcement_enabled() -> bool:
    """Enforcement pedido E Stripe pronto para cobrar."""
    global _avisou_sem_stripe
    if not bool(getattr(settings, "BILLING_ENFORCEMENT_ENABLED", False)):
        return False
    from app.billing.stripe_client import StripeClient

    if StripeClient().is_ready:
        return True
    if not _avisou_sem_stripe:
        logger.error(
            "[Gating] BILLING_ENFORCEMENT_ENABLED=true sem STRIPE_SECRET_KEY/STRIPE_WEBHOOK_SECRET — "
            "enforcement NÃO aplicado (ninguém conseguiria assinar)."
        )
        _avisou_sem_stripe = True
    return False


def _get_plan(user_id: str) -> str:
    from app.billing.service import BillingService

    return BillingService().get_effective_plan(user_id)


def _upgrade_detail(required_plan: str, reason: str) -> dict:
    plan = PLANS.get(required_plan)
    return {
        "error": "upgrade_required",
        "reason": reason,
        "required_plan": required_plan,
        "price_brl_monthly": plan.price_brl_monthly if plan else None,
        "checkout_endpoint": "/api/v1/billing/checkout/{user_id}",
    }


def require_plan(required_plan: str):
    """Dependency factory: exige tier mínimo (pro|total) no endpoint.
    Retorna o user_id autenticado (substitui require_owner no endpoint)."""

    def _dependency(user_id: str = Depends(require_owner)) -> str:
        user_plan = _get_plan(user_id)
        if plan_satisfies(user_plan, required_plan):
            return user_id
        if not enforcement_enabled():
            logger.info(
                "[Gating] would_block user=%s plan=%s required=%s (enforcement off)",
                user_id, user_plan, required_plan,
            )
            return user_id
        raise HTTPException(
            status_code=402,
            detail=_upgrade_detail(
                required_plan,
                f"Este recurso faz parte do plano {required_plan.capitalize()}.",
            ),
        )

    return Depends(_dependency)


# ── Limites de uso ──────────────────────────────────────────────────


def _limit_for(user_plan: str, usage_key: str) -> UsageLimit | None:
    """Limite aplicável ao plano (None = ilimitado para este plano)."""
    if user_plan == PLAN_FREE:
        return FREE_LIMITS.get(usage_key)
    if user_plan == PLAN_PRO:
        return PRO_LIMITS.get(usage_key)
    return None  # Total: sem limites


def _window_bounds(window: str, now: datetime | None = None) -> tuple[str, int]:
    """(sufixo da chave, segundos até expirar) para a janela atual,
    no calendário de São Paulo."""
    now = (now or datetime.now(_FUSO)).astimezone(_FUSO)
    if window == "daily":
        suffix = now.strftime("%Y%m%d")
        proxima = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        suffix = now.strftime("%Y%m")
        if now.month == 12:
            proxima = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            proxima = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    ttl = max(int((proxima - now).total_seconds()), 60)
    return suffix, ttl


def _increment(key: str, ttl: int) -> int:
    """INCR com expiração — Redis primeiro, memória como fallback."""
    try:
        from app.core.cache import get_redis

        r = get_redis()
        if r is not None:
            value = r.incr(key)
            if value == 1:
                r.expire(key, ttl)
            return int(value)
    except Exception as exc:
        logger.debug("[Gating] redis indisponível (%s) — contador em memória", exc)

    now = time.monotonic()
    count, expires = _memory_counters.get(key, (0, now + ttl))
    if now > expires:
        count, expires = 0, now + ttl
    count += 1
    _memory_counters[key] = (count, expires)
    return count


def _current(key: str) -> int:
    try:
        from app.core.cache import get_redis

        r = get_redis()
        if r is not None:
            value = r.get(key)
            return int(value) if value else 0
    except Exception:
        pass
    count, expires = _memory_counters.get(key, (0, 0.0))
    return count if time.monotonic() <= expires else 0


def check_usage(user_id: str, usage_key: str) -> None:
    """
    Levanta 402 se o PRÓXIMO uso passaria do limite — sem consumir.

    Para recursos caros que podem falhar (o chat leva até 60 s e pode dar
    timeout): verifica antes, e `consume_usage` só depois do sucesso. Debitar
    antes cobrava do plano Free uma mensagem que nunca foi respondida.
    """
    user_plan = _get_plan(user_id)
    limit = _limit_for(user_plan, usage_key)
    if limit is None:
        return
    suffix, _ = _window_bounds(limit.window)
    used = _current(f"usage:{usage_key}:{user_id}:{suffix}")
    if used < limit.limit:
        return
    if not enforcement_enabled():
        logger.info(
            "[Gating] would_block_usage user=%s key=%s used=%d limit=%d (enforcement off)",
            user_id, usage_key, used, limit.limit,
        )
        return
    raise HTTPException(
        status_code=402,
        detail=_upgrade_detail(PLAN_PRO, limit.description),
    )


def consume_usage(user_id: str, usage_key: str) -> None:
    """Consome 1 uso do contador. Levanta 402 quando o limite do plano foi
    atingido (ou apenas loga, com enforcement desligado)."""
    user_plan = _get_plan(user_id)
    limit = _limit_for(user_plan, usage_key)
    if limit is None:
        return  # ilimitado neste plano

    suffix, ttl = _window_bounds(limit.window)
    key = f"usage:{usage_key}:{user_id}:{suffix}"
    used = _increment(key, ttl)

    if used <= limit.limit:
        return
    if not enforcement_enabled():
        logger.info(
            "[Gating] would_block_usage user=%s key=%s used=%d limit=%d (enforcement off)",
            user_id, usage_key, used, limit.limit,
        )
        return
    raise HTTPException(
        status_code=402,
        detail=_upgrade_detail(PLAN_PRO, limit.description),
    )


def contar_bancos_conectados(user_id: str) -> int:
    """Conexões Open Finance do usuário (itens Pluggy gravados)."""
    try:
        from app.core.database import SessionLocal
        from app.core.models.pluggy_item import PluggyItem

        with SessionLocal() as db:
            return int(db.query(PluggyItem).filter(PluggyItem.user_id == user_id).count())
    except Exception as exc:
        logger.warning("[Gating] contagem de bancos falhou user=%s: %s", user_id, exc)
        return 0


def check_bank_limit(user_id: str, conexoes_atuais: int | None = None) -> None:
    """
    "1 banco conectado no plano Free" — é uma CONTAGEM de conexões, não um
    contador por janela: o limite existia no catálogo, mas nenhuma rota o
    aplicava, e o Free conectava quantos bancos quisesse. Chamada antes de
    gravar uma conexão NOVA (renovar o consentimento de um banco já
    conectado não passa por aqui).
    """
    user_plan = _get_plan(user_id)
    limit = _limit_for(user_plan, "connected_banks")
    if limit is None:
        return
    atuais = contar_bancos_conectados(user_id) if conexoes_atuais is None else conexoes_atuais
    if atuais < limit.limit:
        return
    if not enforcement_enabled():
        logger.info(
            "[Gating] would_block_banks user=%s conexoes=%d limit=%d (enforcement off)",
            user_id, atuais, limit.limit,
        )
        return
    raise HTTPException(status_code=402, detail=_upgrade_detail(PLAN_PRO, limit.description))


def bloqueio_de_plano(user_id: str, required_plan: str) -> dict | None:
    """
    Para quem não é rota (as ferramentas do agente): None se o usuário pode
    usar o recurso; senão, o mesmo detalhe que o 402 das rotas carregaria.
    Com enforcement desligado, só loga — igual ao require_plan.
    """
    user_plan = _get_plan(user_id)
    if plan_satisfies(user_plan, required_plan):
        return None
    if not enforcement_enabled():
        logger.info(
            "[Gating] would_block_tool user=%s plan=%s required=%s (enforcement off)",
            user_id, user_plan, required_plan,
        )
        return None
    return _upgrade_detail(
        required_plan, f"Este recurso faz parte do plano {required_plan.capitalize()}."
    )


def usage_snapshot(user_id: str) -> list[dict]:
    """Uso atual dos contadores do plano do usuário (para o app exibir)."""
    user_plan = _get_plan(user_id)
    limits = FREE_LIMITS if user_plan == PLAN_FREE else (
        PRO_LIMITS if user_plan == PLAN_PRO else {}
    )
    snapshot = []
    for limit in limits.values():
        if limit.key == "connected_banks":
            usado = contar_bancos_conectados(user_id)
        else:
            suffix, _ = _window_bounds(limit.window)
            usado = _current(f"usage:{limit.key}:{user_id}:{suffix}")
        snapshot.append({
            "key": limit.key,
            "used": usado,
            "limit": limit.limit,
            "window": limit.window,
            "description": limit.description,
        })
    return snapshot


__all__ = [
    "require_plan", "check_usage", "consume_usage", "usage_snapshot", "enforcement_enabled",
    "check_bank_limit", "bloqueio_de_plano", "contar_bancos_conectados",
]
