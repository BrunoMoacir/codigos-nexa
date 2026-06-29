"""
app/viral/router.py — V1/V2: Viral & Wrapped

GET /api/v1/viral/savings-card/{user_id}      — JSON com economia consolidada
GET /api/v1/viral/savings-card/{user_id}/svg  — cartão SVG compartilhável
GET /api/v1/viral/wrapped/{user_id}/{year}    — JSON do wrapped anual
GET /api/v1/viral/wrapped/{user_id}/{year}/svg — cartão SVG do wrapped
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response

from app.core.security import require_owner
from app.viral.models import SavingsCard, WrappedReport
from app.viral.services.savings_consolidator import SavingsConsolidator
from app.viral.services.wrapped_generator import WrappedGenerator
from app.viral.services.card_renderer import CardRenderer

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

    Soma a economia identificada por 4 módulos Nexa:

    | Módulo | Fonte |
    |--------|-------|
    | F2 Optimizer | `net_gain_expected` do melhor cartão recomendado |
    | F5 Costs | `savings_opportunity` × 12 (tarifas evitáveis) |
    | F13 Negotiator | soma de `potential_gain` em negociações não recusadas |
    | OPP | `top_gain_brl` × 12 (dinheiro parado que poderia render) |
    """
    sources, total = _consolidator.consolidate(user_id)
    months_active = _get_months_active(user_id)

    tagline = (
        f"A Nexa te ajudou a guardar R$ {total:,.2f} em {months_active} mês(es)."
        if total > 0
        else "Continue usando a Nexa para identificar oportunidades de economia."
    )

    logger.info(
        "[viral] savings-card user=%s sources=%d total=%.2f", user_id, len(sources), total
    )

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
    """Retorna o cartão de economia (V1) como imagem SVG compartilhável."""
    card = get_savings_card(user_id=user_id)
    svg = _renderer.render_savings_card(card)
    return Response(content=svg, media_type="image/svg+xml")


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
    """Retorna o wrapped anual (V2) como imagem SVG compartilhável."""
    report = get_wrapped(user_id=user_id, year=year)
    svg = _renderer.render_wrapped_card(report)
    return Response(content=svg, media_type="image/svg+xml")


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
