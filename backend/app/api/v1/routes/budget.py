"""
app/api/v1/routes/budget.py — Orçamento Inteligente (M1.3)

Endpoint: GET /budget/{user_id}?monthly_income=8000

Retorna sugestão de orçamento 50/30/20 baseada no histórico de transações.
"""

from __future__ import annotations

import logging
from typing import Optional

import polars as pl
from fastapi import APIRouter, HTTPException, Query, status, Depends
from app.core.security import get_current_user

from app.cashflow.budget_advisor import BudgetAdvisor, BudgetSuggestion
from app.db.queries import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budget", tags=["Budget"])

_advisor = BudgetAdvisor(history_months=3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /budget/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="M1.3 — Orçamento Inteligente por Categoria",
    description=(
        "Analisa o histórico de transações dos últimos 3 meses e sugere limites "
        "de gasto por categoria usando a regra 50/30/20 adaptada ao perfil real. "
        "Retorna alocações por grupo (essenciais/desejos/poupança), cortes sugeridos "
        "e texto explicativo em linguagem natural."
    ),
)
async def get_budget_advice(
    user_id: str,
    monthly_income: float = Query(
        ...,
        gt=0,
        description="Renda mensal líquida do usuário (R$). Obrigatório para calcular os percentuais 50/30/20.",
    ),
    history_months: int = Query(
        default=3,
        ge=1,
        le=12,
        description="Meses de histórico a considerar (padrão: 3, máximo: 12).",
    ),
    _: str = Depends(get_current_user),
) -> dict:
    """
    Retorna sugestão de orçamento 50/30/20 baseada no histórico real do usuário.

    **Como usar:**
    ```
    GET /api/v1/budget/{user_id}?monthly_income=8000
    ```

    **Resposta inclui:**
    - `group_summary`: resumo por grupo (essenciais / desejos / poupança)
    - `allocations`: detalhamento por categoria
    - `actionable_cuts`: cortes concretos ordenados por potencial de economia
    - `summary_text`: texto explicativo em português

    **Exemplo de summary_text:**
    > "Com base nos últimos 3 meses: Essenciais: 58% (ideal 50%) — acima do ideal
    > em 8 p.p. Desejos: 22% (ideal 30%) — dentro do esperado.
    > Poupança: 6% (ideal 20%) — abaixo do ideal. Faltam R$1.120/mês para atingir a meta."
    """
    logger.info("GET /budget/%s | income=R$%.0f | history=%dm", user_id, monthly_income, history_months)

    # ── 1. Buscar transações do DuckDB ────────────────────────────────
    try:
        con = get_connection()
        rows = con.execute(
            """
            SELECT date as transaction_date, amount, category
            FROM transactions_clean
            WHERE user_id = ?
            ORDER BY date DESC
            """,
            [user_id],
        ).fetchall()
        cols = ["transaction_date", "amount", "category"]
        con.close()
    except Exception as exc:
        logger.error("Erro ao buscar transações para budget/%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao acessar dados de transações.",
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma transação encontrada para user_id='{user_id}'.",
        )

    # ── 2. Montar DataFrame ─────────────────────────────────────────
    try:
        transactions_df = pl.DataFrame(
            {col: [r[i] for r in rows] for i, col in enumerate(cols)}
        )
    except Exception as exc:
        logger.error("Erro ao construir DataFrame: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar dados de transações.",
        )

    # ── 3. Gerar sugestão ──────────────────────────────────────────
    advisor = BudgetAdvisor(history_months=history_months)
    try:
        suggestion = advisor.suggest(transactions_df, monthly_income=monthly_income)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("BudgetAdvisor falhou para %s: %s", user_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao calcular sugestão de orçamento.",
        )

    logger.info(
        "GET /budget/%s | cortes=%d | conf=%.2f | gap_poupanca=R$%.0f",
        user_id, len(suggestion.actionable_cuts), suggestion.confidence, suggestion.savings_gap,
    )
    return suggestion.to_dict()
