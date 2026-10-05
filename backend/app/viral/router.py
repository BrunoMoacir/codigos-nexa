"""
app/viral/router.py — V1/V2: Viral & Wrapped

GET  /api/v1/viral/savings-card/{user_id}         — JSON com economia consolidada
GET  /api/v1/viral/savings-card/{user_id}/svg     — cartão SVG privado
GET  /api/v1/viral/savings-card/{user_id}/png     — exportação PNG (stub)
GET  /api/v1/viral/wrapped/{user_id}/{year}       — JSON do wrapped anual
GET  /api/v1/viral/wrapped/{user_id}/{year}/svg   — cartão SVG do wrapped
POST /api/v1/viral/shares                         — registra evento de compartilhamento
DELETE /api/v1/viral/shares/{share_id}            — revoga compartilhamento
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response

from app.core.security import require_owner
from app.viral.models import SavingsCard, ShareEvent, ShareResponse, WrappedReport
from app.viral.services.card_renderer import CardRenderer
from app.viral.services.savings_consolidator import SavingsConsolidator
from app.viral.services.wrapped_generator import WrappedGenerator
from app.core.formatacao import brl

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/viral", tags=["Viral (V1/V2 — Savings Card & Wrapped)"])

_consolidator = SavingsConsolidator()
_wrapped_gen = WrappedGenerator()
_renderer = CardRenderer()


@router.get("/savings-card/{user_id}", response_model=SavingsCard)
def get_savings_card(
    user_id: str = Depends(require_owner),
) -> SavingsCard:
    """
    **Cartão de Economia Consolidada (V1)**

    Consolida potencial de economia de 4 módulos Nexa. Todos os valores são
    estimativas (potencial_estimado) salvo indicação de `amount_type=actual_fee`.

    | Módulo | Fonte |
    |--------|-------|
    | F2 Optimizer | `net_gain_expected` do melhor cartão recomendado |
    | F5 Costs | `savings_opportunity` × 12 (tarifas evitáveis) |
    | F13 Negotiator | soma de `potential_gain` em negociações não recusadas |
    | OPP | `top_gain_brl` × 12 (dinheiro parado que poderia render) |
    """
    sources, total = _consolidator.consolidate(user_id)
    months_active = _get_months_active(user_id)

    if total > 0:
        tagline = (
            f"A Nexa identificou até {brl(total)} em oportunidades anuais "
            f"em {months_active} mês(es) de uso. Potencial estimado."
        )
    else:
        tagline = "Continue usando a Nexa — identificaremos suas oportunidades de economia em breve."

    logger.info("[viral] savings-card user=%s sources=%d total=%.2f", user_id, len(sources), total)

    return SavingsCard(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc),
        total_annual_savings_brl=total,
        sources=sources,
        months_active=months_active,
        tagline=tagline,
    )


@router.get("/savings-card/{user_id}/svg")
def get_savings_card_svg(
    user_id: str = Depends(require_owner),
) -> Response:
    """Retorna o cartão de economia (V1) como SVG privado (sem cache público)."""
    card = get_savings_card(user_id=user_id)
    svg = _renderer.render_savings_card(card)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store, private"},
    )


@router.get("/savings-card/{user_id}/png")
def get_savings_card_png(
    user_id: str = Depends(require_owner),
) -> Response:
    """
    Exportação PNG do cartão V1.
    A conversão SVG→PNG é feita no frontend (canvas API).
    Este endpoint retorna o SVG com Content-Type adequado para download.
    """
    card = get_savings_card(user_id=user_id)
    svg = _renderer.render_savings_card(card)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="nexa-savings-{card.user_id[:8]}.svg"',
            "Cache-Control": "no-store, private",
        },
    )


@router.get("/wrapped/{user_id}/{year}", response_model=WrappedReport)
def get_wrapped(
    user_id: str = Depends(require_owner),
    year: int = Path(..., ge=2020, le=2100, description="Ano do wrapped (ex: 2026)"),
) -> WrappedReport:
    """
    **Wrapped Anual "Banco vs. Você" (V2)**

    Gera até 5 highlights do ano:

    | Categoria | Descrição |
    |-----------|-----------|
    | `biggest_waste` | Categoria de tarifa com maior gasto total no ano |
    | `worst_fee` | Tarifa individual mais alta paga em um único mês |
    | `best_card_missed` | Cartão que mais renderia vs. o atual |
    | `idle_money` | Dinheiro parado na conta que poderia ter rendido |
    | `score_evolution` | Evolução do Health Score no ano (jan vs dez) |
    """
    try:
        report = _wrapped_gen.generate(user_id, year)
    except Exception as exc:
        logger.error("[viral] wrapped user=%s year=%s: %s", user_id, year, exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar wrapped.")

    logger.info(
        "[viral] wrapped user=%s year=%d highlights=%d", user_id, year, len(report.highlights)
    )
    return report


@router.get("/wrapped/{user_id}/{year}/svg")
def get_wrapped_svg(
    user_id: str = Depends(require_owner),
    year: int = Path(..., ge=2020, le=2100),
) -> Response:
    """Retorna o wrapped anual (V2) como SVG privado."""
    report = get_wrapped(user_id=user_id, year=year)
    svg = _renderer.render_wrapped_card(report)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store, private"},
    )


@router.post("/shares", response_model=ShareResponse, status_code=201)
def register_share(
    event: ShareEvent,
    user_id: str = Depends(require_owner),
) -> ShareResponse:
    """
    Registra um evento de compartilhamento voluntário do cartão V1 ou V2.
    Salvo em viral_share_log para analytics de CAC viral e badge VIRAL_SHARE.
    """
    if event.user_id != user_id:
        raise HTTPException(status_code=403, detail="user_id não corresponde ao token.")

    share_id = str(uuid.uuid4())
    utm_link: str | None = None

    if event.utm_campaign:
        utm_link = (
            f"https://nexa.app/?utm_source=viral"
            f"&utm_medium={event.utm_medium or 'share'}"
            f"&utm_campaign={event.utm_campaign}"
            f"&ref={share_id[:8]}"
        )

    _log_share(user_id=user_id, share_id=share_id, event=event)
    logger.info("[viral] share registered user=%s id=%s channel=%s", user_id, share_id, event.channel)

    return ShareResponse(share_id=share_id, utm_link=utm_link)


@router.delete("/shares/{share_id}", status_code=204)
def revoke_share(
    share_id: str,
    user_id: str = Depends(require_owner),
) -> None:
    """Revoga um compartilhamento (marca como revoked no log)."""
    _revoke_share_log(user_id=user_id, share_id=share_id)
    logger.info("[viral] share revoked user=%s id=%s", user_id, share_id)


def _log_share(user_id: str, share_id: str, event: ShareEvent) -> None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO viral_share_log "
                    "(id, user_id, card_type, channel, card_version, utm_campaign, utm_medium, shared_at) "
                    "VALUES (:id, :uid, :ct, :ch, :cv, :uc, :um, NOW())"
                ),
                {
                    "id": share_id,
                    "uid": user_id,
                    "ct": event.card_type,
                    "ch": event.channel,
                    "cv": event.card_version,
                    "uc": event.utm_campaign,
                    "um": event.utm_medium,
                },
            )
            db.commit()
    except Exception as exc:
        logger.warning("[viral] _log_share user=%s: %s", user_id, exc)


def _revoke_share_log(user_id: str, share_id: str) -> None:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(
                text(
                    "UPDATE viral_share_log SET revoked_at = NOW() "
                    "WHERE id = :sid AND user_id = :uid"
                ),
                {"sid": share_id, "uid": user_id},
            )
            db.commit()
    except Exception as exc:
        logger.warning("[viral] _revoke_share user=%s id=%s: %s", user_id, share_id, exc)


def _get_months_active(user_id: str) -> int:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text("SELECT created_at FROM users WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()

        if not row or not row[0]:
            return 1

        created_at = row[0]
        today = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        months = (today.year - created_at.year) * 12 + today.month - created_at.month
        return max(1, months)
    except Exception:
        return 1
