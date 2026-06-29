"""
app/opportunities/router.py — OPP: Radar de Oportunidades

GET  /api/v1/opportunities/{user_id}
    Detecta dinheiro parado e retorna ranking de investimentos ranqueados
    por taxa líquida (após IR). Persiste snapshot em opportunity_snapshots.

POST /api/v1/opportunities/compare
    Comparação ad hoc: informe um valor e prazo, receba o ranking completo.
    Não requer histórico de transações.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user, require_owner
from app.core.database import get_db
from sqlalchemy.orm import Session

from app.opportunities.models import (
    OpportunitiesResponse,
    CompareRequest,
    CompareResponse,
)
from app.opportunities.services.opportunity_engine import OpportunityEngine
from app.opportunities.services.bank_comparator import BankComparator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/opportunities", tags=["Opportunities (OPP)"])

_engine = OpportunityEngine()
_comparator = BankComparator()


@router.get("/{user_id}", response_model=OpportunitiesResponse)
def get_opportunities(
    user_id: str = Depends(require_owner),
    holding_months: int = Query(
        default=12,
        ge=1,
        le=360,
        description="Prazo de comparação em meses (padrão: 12). Afeta a alíquota de IR.",
    ),
) -> OpportunitiesResponse:
    """
    **OPP — Radar de Oportunidades**

    Detecta dinheiro parado na conta corrente e compara os melhores
    produtos de renda fixa disponíveis no mercado.

    - **idle_amount**: renda média 3m − despesas médias 3m
    - **monthly_loss_in_checking**: custo mensal de não investir (CDI atual)
    - **opportunities**: ranking por taxa líquida (após IR) — não taxa bruta
    - **top_opportunity**: melhor opção acessível para o saldo do usuário
    - Persiste snapshot em `opportunity_snapshots` para histórico (V2/Wrapped)

    **Ranking:** produtos elegíveis (min_amount ≤ idle_amount) aparecem primeiro,
    ordenados por `annual_rate_net_pct` decrescente. Produtos com valor mínimo
    acima do saldo aparecem ao final com `eligible: false`.
    """
    try:
        result = _engine.analyze(
            user_id=user_id,
            holding_months=holding_months,
            persist_snapshot=True,
        )
    except Exception as exc:
        logger.error("[opportunities] analyze user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao calcular oportunidades.")

    return result


@router.post("/compare", response_model=CompareResponse)
def compare_opportunities(
    body: CompareRequest,
    current_user: str = Depends(get_current_user),
) -> CompareResponse:
    """
    **Comparação ad hoc**

    Informe um valor e prazo para comparar todos os produtos disponíveis.
    Útil para simular um aporte específico (ex: "se eu investir R$ 20.000 por 2 anos").

    Não lê histórico de transações — usa apenas os dados informados.

    **Exemplo:**
    ```json
    { "amount": 20000, "holding_months": 24 }
    ```
    """
    if body.amount <= 0:
        raise HTTPException(status_code=422, detail="amount deve ser maior que zero.")

    try:
        from app.opportunities.services.opportunity_engine import OpportunityEngine
        cdi_annual = OpportunityEngine._get_cdi_annual()
        ranked = _comparator.rank(
            amount=body.amount,
            holding_months=body.holding_months,
            cdi_annual=cdi_annual,
        )
    except Exception as exc:
        logger.error("[opportunities] compare user=%s: %s", current_user, exc)
        raise HTTPException(status_code=500, detail="Erro ao comparar oportunidades.")

    return CompareResponse(
        amount=body.amount,
        holding_months=body.holding_months,
        cdi_annual_pct=round(cdi_annual * 100, 4),
        opportunities=ranked,
    )
