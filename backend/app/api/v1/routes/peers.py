"""
app/api/v1/routes/peers.py — Comparação Anônima com Perfis Similares (MX.4)

Endpoint: GET /peers/compare/{user_id}?monthly_income=8000

Compara o perfil de gastos do usuário com benchmarks agregados da POF/IBGE
por faixa de renda, retornando posicionamento por categoria e percentil de poupança.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.db.queries import get_connection
from app.peers.peer_comparison import PeerComparator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/peers", tags=["Peers — MX.4"])

_comparator = PeerComparator()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /peers/compare/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get(
    "/compare/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="MX.4 — Comparação com Perfis Similares (IBGE/POF)",
    description=(
        "Compara o perfil de gastos do usuário com benchmarks da Pesquisa de "
        "Orçamentos Familiares (POF/IBGE) para sua faixa de renda. Retorna "
        "posicionamento por categoria ('acima', 'na_media', 'abaixo') e "
        "percentil estimado de poupança vs. perfis similares."
    ),
)
async def compare_peers(
    user_id: str,
    monthly_income: float = Query(
        ...,
        gt=0,
        description="Renda mensal líquida (R$). Determina a faixa de renda de referência.",
    ),
    history_months: int = Query(
        default=3,
        ge=1,
        le=12,
        description="Meses de histórico de transações a considerar (padrão: 3).",
    ),
) -> dict:
    """
    Compara o perfil de gastos do usuário com benchmarks da faixa de renda.

    **Como usar:**
    ```
    GET /api/v1/peers/compare/user_123?monthly_income=8000
    GET /api/v1/peers/compare/user_123?monthly_income=8000&history_months=6
    ```

    **Faixas de renda:**
    - BAIXA: até R$ 3.000/mês
    - MEDIA: R$ 3.001–R$ 8.000/mês
    - ALTA: R$ 8.001–R$ 20.000/mês
    - PREMIUM: acima de R$ 20.000/mês

    **Resposta:**
    ```json
    {
      "income_bracket": "MEDIA",
      "bracket_label": "renda média (R$ 3.001–R$ 8.000/mês)",
      "monthly_income": 8000,
      "user_savings_rate": 14.0,
      "benchmark_savings_rate": 13.0,
      "savings_percentile_label": "top 40%",
      "categories": [
        {
          "category": "moradia",
          "label": "Moradia",
          "user_pct": 35.0,
          "benchmark_pct": 30.0,
          "delta_pct": 5.0,
          "status": "acima",
          "insight": "Você gasta 35% da renda em moradia — 5 p.p. acima da média..."
        }
      ],
      "highlights_above": ["Moradia"],
      "highlights_below": ["Lazer"],
      "summary_text": "Gasta acima da média em: Moradia. Índice de poupança (14.0%) — top 40%..."
    }
    ```
    """
    logger.info(
        "GET /peers/compare/%s | income=R$%.0f | history=%dm",
        user_id, monthly_income, history_months,
    )

    # ── 1. Buscar transações de débito do DuckDB ───────────────────────
    try:
        con = get_connection()
        rows = con.execute(
            """
            SELECT amount, category
            FROM transactions
            WHERE user_id = ?
              AND amount < 0
              AND transaction_date >= current_date - INTERVAL (?) MONTH
            """,
            [user_id, history_months],
        ).fetchall()
        con.close()
    except Exception as exc:
        logger.error("Erro ao buscar transações para peers/compare/%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao acessar dados de transações.",
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma transação encontrada para user_id='{user_id}'.",
        )

    # ── 2. Agregar por categoria e calcular média mensal ──────────────
    raw: dict[str, float] = {}
    for amount, category in rows:
        cat = (category or "outros").lower().strip()
        raw[cat] = raw.get(cat, 0.0) + abs(float(amount))

    category_spending = (
        {k: v / history_months for k, v in raw.items()}
        if history_months > 1
        else raw
    )

    # ── 3. Comparar com benchmarks ────────────────────────────────────
    try:
        report = _comparator.compare(
            monthly_income=monthly_income,
            category_spending=category_spending,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("PeerComparator falhou para %s: %s", user_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao calcular comparação com pares.",
        )

    logger.info(
        "GET /peers/compare/%s | faixa=%s | poupanca=%.1f%% | percentil=%s",
        user_id,
        report.income_bracket,
        report.user_savings_rate * 100,
        report.savings_percentile_label,
    )
    return report.to_dict()
