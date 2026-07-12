"""
app/api/v1/routes/purchase.py — F7: Modo Compra Inteligente

Endpoints:
  POST /purchase/analyze                       — análise completa (pré-compra)
  GET  /purchase/checkout-context/{user_id}    — resposta compacta para o
                                                 momento da compra (R1.a)
  GET  /purchase/recent-review/{user_id}       — revisão retroativa das
                                                 compras grandes recentes (R1.a)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import get_current_user, require_owner
from app.purchase.models import PurchaseRequest, PurchaseRecommendation
from app.purchase.purchase_advisor import PurchaseAdvisor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/purchase", tags=["Purchase Advisor (F7)"])


# ── Schemas do checkout-context (R1.a) ─────────────────────────────

class CheckoutOption(BaseModel):
    label: str
    method: str
    net_cost: float
    monthly_cost: Optional[float] = None
    profile_fit: str


class CheckoutContext(BaseModel):
    """Resposta enxuta do F7 para o momento da compra — pensada para um
    modal/checkout que precisa responder em uma olhada."""
    user_id: str
    amount: float
    category: str
    verdict: str = Field(..., description="Frase única: como pagar e por quê")
    recommended_label: str
    recommended_method: str
    savings_vs_worst: float = Field(..., description="R$ economizados vs. a pior opção listada")
    affordable: bool
    risk_level: str
    safe_to_spend_after: float
    options: list[CheckoutOption]
    confidence_score: float


class RecentPurchaseReview(BaseModel):
    transaction_id: str
    merchant: str
    amount: float
    category: str
    purchase_date: str
    paid_method_label: str
    best_method_label: str
    potential_savings_brl: float


class RecentReviewResponse(BaseModel):
    user_id: str
    lookback_days: int
    total: int
    reviews: list[RecentPurchaseReview]
    total_savings_missed_brl: float


@router.post("/analyze", response_model=PurchaseRecommendation)
async def analyze_purchase(
    request: PurchaseRequest,
    current_user: str = Depends(get_current_user),
) -> PurchaseRecommendation:
    """
    **F7 — Modo Compra Inteligente**

    Analisa uma compra e recomenda a melhor forma de pagamento comparando:
    - PIX à vista
    - Cartão à vista (com cashback/pontos do melhor cartão via F2)
    - Cartão parcelado sem juros (se `installments > 1`)
    - Crédito pessoal CDC (se `amount >= R$1.000` e `installments > 6`)

    O ranqueamento usa **custo líquido** (total_cost − reward_value) e considera
    o impacto no safe-to-spend do usuário (F1).

    **Exemplo de request:**
    ```json
    {
      "user_id": "user_123",
      "amount": 3000.00,
      "category": "Eletrônicos",
      "installments": 12,
      "monthly_income": 8000.00
    }
    ```
    """
    if current_user != request.user_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    logger.info(
        "[API] F7 purchase/analyze | user=%s amount=%.2f category=%s",
        request.user_id, request.amount, request.category,
    )

    try:
        result = PurchaseAdvisor().analyze(request)
        return result

    except ValueError as exc:
        logger.warning("[API] F7 validação: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))

    except Exception as exc:
        logger.error("[API] F7 erro interno: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao analisar a compra.")


@router.get(
    "/checkout-context/{user_id}",
    response_model=CheckoutContext,
    summary="R1.a — Contexto compacto do F7 para o momento da compra",
)
async def get_checkout_context(
    user_id: str = Depends(require_owner),
    amount: float = Query(..., gt=0, description="Valor da compra (R$)"),
    category: str = Query(default="Outros", description="Categoria da compra"),
    installments: int = Query(default=1, ge=1, le=48, description="Parcelas em consideração"),
) -> CheckoutContext:
    """
    **R1.a — Modo Compra no momento da compra.**

    Mesma inteligência do POST /purchase/analyze, resposta desenhada para
    o checkout: um veredito em uma frase, a opção recomendada, o impacto
    na margem segura e a lista curta de opções por custo líquido. Ideal
    para modal de decisão rápida, share-sheet mobile ou extensão de navegador.
    """
    logger.info(
        "[API] F7 checkout-context | user=%s amount=%.2f category=%s",
        user_id, amount, category,
    )
    try:
        result = PurchaseAdvisor().analyze(PurchaseRequest(
            user_id=user_id,
            amount=amount,
            category=category,
            installments=installments,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("[API] F7 checkout-context erro: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao analisar a compra.")

    def _cost(o) -> float:
        return o.net_cost_real if o.net_cost_real is not None else o.net_cost

    worst = max(result.options, key=_cost) if result.options else None
    savings_vs_worst = (
        round(_cost(worst) - result.recommended_net_cost, 2) if worst else 0.0
    )

    # Veredito em uma frase: recomendação + situação de liquidez
    liquidity = result.liquidity_impact
    if not liquidity.affordable:
        caution = " Atenção: essa compra estoura sua margem segura do mês."
    elif liquidity.risk_level in ("HIGH", "CRITICAL"):
        caution = " Cabe no orçamento, mas aperta sua margem segura."
    else:
        caution = ""
    verdict = (
        f"Pague com {result.recommended_label} — custo líquido de "
        f"R$ {result.recommended_net_cost:,.2f}"
        + (f", R$ {savings_vs_worst:,.2f} mais barato que a pior opção" if savings_vs_worst > 0 else "")
        + f".{caution}"
    )

    return CheckoutContext(
        user_id=user_id,
        amount=amount,
        category=result.category,
        verdict=verdict,
        recommended_label=result.recommended_label,
        recommended_method=result.recommended_method.value,
        savings_vs_worst=savings_vs_worst,
        affordable=liquidity.affordable,
        risk_level=liquidity.risk_level,
        safe_to_spend_after=round(liquidity.safe_to_spend_after, 2),
        options=[
            CheckoutOption(
                label=o.label,
                method=o.method.value,
                net_cost=round(_cost(o), 2),
                monthly_cost=o.monthly_cost,
                profile_fit=o.profile_fit,
            )
            for o in result.options
        ],
        confidence_score=result.confidence_score,
    )


@router.get(
    "/recent-review/{user_id}",
    response_model=RecentReviewResponse,
    summary="R1.a — Revisão retroativa das compras grandes recentes",
)
async def get_recent_review(user_id: str = Depends(require_owner)) -> RecentReviewResponse:
    """
    **R1.a — o F7 olhando para trás.**

    Varre as compras à vista ≥ R$300 dos últimos 14 dias e calcula quanto
    o usuário teria economizado pagando de outra forma (mesmo motor do
    card PURCHASE_FOLLOWUP do feed).
    """
    logger.info("[API] F7 recent-review | user=%s", user_id)
    try:
        from app.purchase.post_purchase import _LOOKBACK_DAYS, get_post_purchase_analyzer

        # sob demanda: ignora o marcador de "já analisada" do scheduler
        followups = get_post_purchase_analyzer().detect(user_id, use_seen_marker=False)
    except Exception as exc:
        logger.error("[API] F7 recent-review erro: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao revisar compras recentes.")

    reviews = [
        RecentPurchaseReview(
            transaction_id=f.transaction_id,
            merchant=f.merchant,
            amount=f.amount,
            category=f.category,
            purchase_date=f.purchase_date,
            paid_method_label=f.paid_method_label,
            best_method_label=f.best_method_label,
            potential_savings_brl=f.potential_savings_brl,
        )
        for f in followups
    ]
    return RecentReviewResponse(
        user_id=user_id,
        lookback_days=_LOOKBACK_DAYS,
        total=len(reviews),
        reviews=reviews,
        total_savings_missed_brl=round(sum(r.potential_savings_brl for r in reviews), 2),
    )
