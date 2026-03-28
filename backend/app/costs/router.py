"""
app/api/v1/routes/costs.py — F5: Raio-X de Custos Bancários

Endpoint: GET /costs/raio-x/{user_id}
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_owner
from app.costs.bank_fee_analyzer import BankFeeAnalyzer
from app.costs.models import BankCostReport

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/costs", tags=["Custos Bancários (F5)"])


@router.get("/raio-x/{user_id}", response_model=BankCostReport)
async def get_bank_cost_report(
    user_id: str = Depends(require_owner),
) -> BankCostReport:
    """
    **F5 — Raio-X de Custos Bancários**

    Analisa o histórico de transações do usuário e retorna:
    - Total pago em tarifas bancárias no período
    - Detalhamento por banco e por tipo de tarifa
    - Comparação com benchmarks de mercado (BACEN 2026)
    - Economia potencial ao migrar para bancos mais baratos
    - Projeção anual do Custo Bancário Total (CBT)

    **Categorias detectadas:**
    `ANUIDADE_CARTAO`, `TARIFA_MANUTENCAO`, `TED_DOC`, `SAQUE`,
    `JUROS_ROTATIVO`, `SEGURO_PRESTAMISTA`, `PACOTE_SERVICOS`, `IOF`
    """

    logger.info("[API] F5 costs/raio-x | user=%s", user_id)

    # ── 1. Buscar transações ──────────────────────────────────────
    try:
        from app.core.db.queries import get_transactions_for_user
        transactions_df = get_transactions_for_user(user_id)
    except Exception as exc:
        logger.error("[API] F5 erro ao buscar transações: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao acessar dados do usuário.")

    if transactions_df.is_empty():
        raise HTTPException(
            status_code=404,
            detail=f"Sem histórico de transações para user_id={user_id}. "
                   "Conecte sua conta bancária via Open Finance primeiro.",
        )

    # ── 2. Analisar custos ────────────────────────────────────────
    try:
        report = BankFeeAnalyzer().analyze(transactions_df, user_id=user_id)
        return report

    except Exception as exc:
        logger.error("[API] F5 erro na análise: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao analisar custos bancários.")
