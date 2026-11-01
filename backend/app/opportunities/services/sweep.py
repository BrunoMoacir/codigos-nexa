"""F6 — prévia segura de sweep automático.

A iniciação de pagamento Open Finance ainda não está disponível. Este módulo
calcula apenas uma proposta auditável; nunca movimenta saldo nem chama
provedores de pagamento.
"""

from __future__ import annotations

from app.opportunities.models import (
    DISCLAIMER,
    OpportunitiesResponse,
    SweepPreviewRequest,
    SweepPreviewResponse,
)


def build_sweep_preview(
    user_id: str,
    opportunities: OpportunitiesResponse,
    request: SweepPreviewRequest,
) -> SweepPreviewResponse:
    """Monta uma proposta de sweep limitada ao valor ocioso confirmado."""
    requested = request.amount
    idle_amount = max(0.0, round(opportunities.idle_amount, 2))

    if requested is not None and requested <= 0:
        raise ValueError("amount deve ser maior que zero.")
    if requested is not None and requested > idle_amount:
        raise ValueError("amount não pode exceder o valor ocioso disponível.")

    amount = idle_amount if requested is None else round(requested, 2)
    source = "IDLE_AMOUNT" if requested is None else "REQUESTED_AMOUNT"
    top = next(
        (item for item in opportunities.opportunities if item.eligible),
        None,
    )

    if amount <= 0:
        return SweepPreviewResponse(
            user_id=user_id,
            status="NO_ELIGIBLE_AMOUNT",
            amount=0.0,
            source=source,
            holding_months=request.holding_months,
            reason=(
                "Nenhum valor está disponível após a proteção da reserva de emergência."
            ),
            disclaimer=DISCLAIMER,
        )

    if top is None:
        return SweepPreviewResponse(
            user_id=user_id,
            status="NO_ELIGIBLE_AMOUNT",
            amount=amount,
            source=source,
            holding_months=request.holding_months,
            reason="Nenhum produto do catálogo atende ao valor do sweep.",
            disclaimer=DISCLAIMER,
        )

    return SweepPreviewResponse(
        user_id=user_id,
        status="REQUIRES_CONSENT",
        amount=amount,
        source=source,
        holding_months=request.holding_months,
        top_opportunity=top,
        reason=(
            "Prévia calculada. A Nexa não movimentou o dinheiro: a execução "
            "depende de consentimento e da iniciação de pagamento Open Finance fase 4."
        ),
        disclaimer=DISCLAIMER,
    )


__all__ = ["build_sweep_preview"]
