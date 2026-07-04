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
    DISCLAIMER,
    BankComparisonResponse,
    CatalogProduct,
    OpportunitiesResponse,
    CompareRequest,
    CompareResponse,
    ProductCatalogResponse,
    SavingsVsCdiResult,
    TreasuryComparisonResponse,
)
from app.opportunities.services.opportunity_engine import OpportunityEngine
from app.opportunities.services.bank_comparator import BankComparator
from app.opportunities.services.bank_scorecard import BankScorecardService
from app.opportunities.services.savings_vs_cdi import SavingsVsCdiService
from app.opportunities.services.treasury_comparator import TreasuryComparatorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/opportunities", tags=["Opportunities (OPP)"])

_engine = OpportunityEngine()
_comparator = BankComparator()
_savings_vs_cdi = SavingsVsCdiService()
_treasury = TreasuryComparatorService(comparator=_comparator)
_scorecard = BankScorecardService(comparator=_comparator)


@router.get("/savings-vs-cdi", response_model=SavingsVsCdiResult)
def get_savings_vs_cdi(
    amount_reference_brl: float = Query(
        default=10_000.0,
        gt=0,
        description="Valor de referência (R$) para calcular a perda estimada. Não usa saldo real do usuário.",
    ),
    current_user: str = Depends(get_current_user),
) -> SavingsVsCdiResult:
    """
    **OPP.4 (Ticket OPP4-C) — Poupança vs. CDI**

    Comparação genérica, sem depender de saldo real do usuário (Opção A do
    plano OPP.4 — `docs/OPP4_POUPANCA_CDI_PLANO.md`): calcula a taxa oficial
    da poupança (SELIC + TR, `calculate_savings_rate`) e compara com o CDI
    atual para um valor de referência.

    **Importante:** esta rota é registrada ANTES de `/{user_id}` de propósito
    — `savings-vs-cdi` não pode ser interpretado como um `user_id`.

    - **status**: `BELOW_CDI` | `NEAR_CDI` | `NO_ADVANTAGE` | `DATA_UNAVAILABLE`
    - **severity**: `LOW` | `MEDIUM` | `HIGH` — usado por Feed/Notificações para decidir
      se vale gerar um card (ver seção 5.4/5.5 do plano).
    """
    try:
        return _savings_vs_cdi.analyze(amount_reference_brl=amount_reference_brl)
    except Exception as exc:
        logger.error("[opportunities] savings_vs_cdi user=%s: %s", current_user, exc)
        raise HTTPException(status_code=500, detail="Erro ao comparar poupança com CDI.")


@router.get("/treasury-vs-cdb-vs-savings", response_model=TreasuryComparisonResponse)
def get_treasury_vs_cdb_vs_savings(
    amount: float = Query(default=10_000.0, gt=0, description="Valor a simular (R$)."),
    holding_months: int = Query(default=12, ge=1, le=360, description="Prazo em meses."),
    current_user: str = Depends(get_current_user),
) -> TreasuryComparisonResponse:
    """
    **OPP.3 — Tesouro SELIC vs. CDB vs. Poupança**

    Compara as três alternativas clássicas de reserva em rendimento LÍQUIDO:
    Tesouro SELIC (IR regressivo + custódia B3 de 0,20% a.a. sobre o excedente
    de R$10k), o melhor CDB de liquidez diária do catálogo, e a poupança
    (taxa oficial SELIC + TR). Não depende de dados do usuário.

    Rota estática registrada ANTES de `/{user_id}` — mesma razão de
    `/savings-vs-cdi`.
    """
    try:
        return _treasury.compare(
            amount=amount, holding_months=holding_months, disclaimer=DISCLAIMER
        )
    except Exception as exc:
        logger.error("[opportunities] treasury_comparison user=%s: %s", current_user, exc)
        raise HTTPException(status_code=500, detail="Erro ao comparar Tesouro, CDB e poupança.")


@router.get("/products", response_model=ProductCatalogResponse)
def get_product_catalog() -> ProductCatalogResponse:
    """
    **V2 — Catálogo de produtos (transparência)**

    Catálogo completo usado pelo radar, com origem dos dados (curadoria ou
    Open Finance Dados Abertos). Público de propósito: a neutralidade do
    ranking é verificável por qualquer um.
    """
    try:
        meta = BankComparator.catalog_metadata()
        products = [
            CatalogProduct(
                **{
                    **p,
                    "is_tax_exempt": p.get(
                        "is_tax_exempt", p.get("product_type") in ("LCI", "LCA")
                    ),
                }
            )
            for p in meta["products"]
        ]
        return ProductCatalogResponse(
            updated_at=meta["updated_at"],
            source=meta["source"],
            institution_count=len({p.bank_name for p in products}),
            product_count=len(products),
            products=products,
        )
    except Exception as exc:
        logger.error("[opportunities] product_catalog: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao carregar o catálogo de produtos.")


@router.get("/{user_id}/banks", response_model=BankComparisonResponse)
def get_bank_scorecard(
    user_id: str = Depends(require_owner),
    amount: float = Query(default=0.0, ge=0, description="Valor a simular (R$). 0 = usa o dinheiro ocioso detectado."),
    holding_months: int = Query(default=12, ge=1, le=360),
) -> BankComparisonResponse:
    """
    **V2 (docs/OPP.md §8.2) — Scorecard por banco**

    Ranking agregado por instituição (não por produto): qual banco paga mais
    pelo seu perfil, onde seu dinheiro está hoje (via Pluggy) e quanto você
    perde por lealdade. Ajustado a risco por tier do emissor.

    Quando `amount` não é informado, usa o dinheiro ocioso detectado do
    usuário (mínimo R$ 1.000 para a simulação fazer sentido).
    """
    try:
        simulated_amount = amount
        if simulated_amount <= 0:
            idle = _engine.analyze(
                user_id=user_id, holding_months=holding_months, persist_snapshot=False
            )
            simulated_amount = max(idle.idle_amount, 1_000.0)

        cdi_annual = OpportunityEngine._get_cdi_annual()
        selic_annual = OpportunityEngine._get_selic_annual()
        return _scorecard.build(
            user_id=user_id,
            amount=simulated_amount,
            holding_months=holding_months,
            cdi_annual=cdi_annual,
            selic_annual=selic_annual,
            disclaimer=DISCLAIMER,
        )
    except Exception as exc:
        logger.error("[opportunities] bank_scorecard user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Erro ao montar o scorecard de bancos.")


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
        cdi_annual = OpportunityEngine._get_cdi_annual()
        ranked = _comparator.rank(
            amount=body.amount,
            holding_months=body.holding_months,
            cdi_annual=cdi_annual,
            selic_annual=OpportunityEngine._get_selic_annual(),
        )
    except Exception as exc:
        logger.error("[opportunities] compare user=%s: %s", current_user, exc)
        raise HTTPException(status_code=500, detail="Erro ao comparar oportunidades.")

    return CompareResponse(
        amount=body.amount,
        holding_months=body.holding_months,
        cdi_annual_pct=round(cdi_annual * 100, 4),
        opportunities=ranked,
        disclaimer=DISCLAIMER,
    )
