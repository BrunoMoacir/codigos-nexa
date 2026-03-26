"""
app/api/v1/routes/purchase.py — F7: Modo Compra Inteligente

Endpoint: POST /purchase/analyze
"""

import logging
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.purchase.models import PurchaseRequest, PurchaseRecommendation
from app.purchase.purchase_advisor import PurchaseAdvisor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/purchase", tags=["Purchase Advisor (F7)"])


@router.post("/analyze", response_model=PurchaseRecommendation)
async def analyze_purchase(
    request: PurchaseRequest,
    _: str = Depends(get_current_user),
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
