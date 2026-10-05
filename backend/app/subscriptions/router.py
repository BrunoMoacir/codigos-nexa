# app/api/v1/routes/subscriptions.py
# M1.5 — Detecção de Assinaturas Esquecidas

import logging
from fastapi import APIRouter, HTTPException, Query, Depends, status
from app.core.security import require_owner
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscriptions", tags=["Subscriptions (M1.5)"])


@router.get("/{user_id}")
def get_subscriptions(
    months: int = Query(
        default=6,
        ge=2,
        le=24,
        description="Janela de histórico em meses para detectar recorrência (mín: 2, máx: 24)",
    ),
    user_id: str = Depends(require_owner),   # IDOR fix (auditoria 2026-07)
):
    """
    M1.5 — Detecta assinaturas recorrentes e sinaliza as possivelmente esquecidas.

    Analisa o histórico de transações do usuário e identifica cobranças
    recorrentes (mesmo merchant, mesmo valor, meses seguidos). Aplica 3
    heurísticas de alerta:

    - **DUPLICATE_CATEGORY**: 3+ serviços na mesma categoria (ex: 3 streamings)
    - **LOW_VALUE**: assinatura < R$ 15/mês — valor fácil de esquecer
    - **PRICE_INCREASE**: reajuste > 10% desde a primeira cobrança detectada

    **Parâmetros:**
    - `user_id`: ID do usuário
    - `months`: janela de análise (padrão: 6 meses)

    **Exemplo de resposta:**
    ```json
    {
      "total_subscriptions": 6,
      "total_monthly_cost": 213.40,
      "alerted_count": 2,
      "summary_text": "Encontrei 6 assinaturas ativas totalizando R$ 213/mês...",
      "subscriptions": [...],
      "alerted": [
        {
          "merchant": "netflix",
          "monthly_amount": 55.90,
          "alerts": ["DUPLICATE_CATEGORY"],
          "alert_messages": ["Você tem 3 serviços de streaming video — R$ 104/mês no total."]
        }
      ]
    }
    ```
    """
    from app.core.db.queries import get_transactions_for_user
    from app.subscriptions.subscription_detector import detect_subscriptions
    import polars as pl

    # 1. Buscar transações do PostgreSQL
    try:
        transactions_df = get_transactions_for_user(user_id)
    except Exception as e:
        logger.error("[Subscriptions] Erro ao buscar transações: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao acessar dados do usuário.")


    if transactions_df.is_empty():
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum histórico de transações encontrado para user_id={user_id}.",
        )

    # 2. Filtrar pela janela de meses solicitada
    if "transaction_date" in transactions_df.columns:
        import datetime
        cutoff = datetime.date.today() - datetime.timedelta(days=months * 30)
        transactions_df = transactions_df.filter(
            pl.col("transaction_date").cast(pl.Date) >= cutoff
        )
    elif "date" in transactions_df.columns:
        import datetime
        cutoff = datetime.date.today() - datetime.timedelta(days=months * 30)
        transactions_df = transactions_df.filter(
            pl.col("date").cast(pl.Date) >= cutoff
        )

    if transactions_df.is_empty():
        raise HTTPException(
            status_code=422,
            detail=f"Sem transações nos últimos {months} meses para user_id={user_id}.",
        )

    # 3. Detectar assinaturas
    try:
        report = detect_subscriptions(transactions_df=transactions_df, user_id=user_id)
    except Exception as e:
        logger.error("[Subscriptions] Erro na detecção: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao processar assinaturas.")

    return report.to_dict()


@router.get("/{user_id}/simple")
def get_subscriptions_simple(
    user_id: str = Depends(require_owner),   # IDOR fix (auditoria 2026-07)
):
    """
    M1.5 — Lista enxuta das assinaturas, para o frontend.

    Lia a tabela `subscriptions`, que nenhuma migração cria: respondia sempre
    "Tabela de assinaturas não existe" com lista vazia, para todo usuário.
    Agora é o MESMO detector de GET /subscriptions/{user_id}, com a forma
    simplificada — uma fonte só para as duas telas.
    """
    relatorio = get_subscriptions(months=6, user_id=user_id)
    alertadas = {a.get("merchant") for a in relatorio.get("alerted", []) if isinstance(a, dict)}
    itens = [
        {
            "name": s.get("merchant"),
            "category": s.get("subscription_category"),
            "amount": s.get("monthly_amount"),
            "billing_cycle": "monthly",
            "first_seen": s.get("first_seen"),
            "last_seen": s.get("last_seen"),
            "price_changed": s.get("first_amount") not in (None, s.get("monthly_amount")),
            "needs_attention": s.get("merchant") in alertadas,
        }
        for s in relatorio.get("subscriptions", [])
    ]
    return {
        "user_id": user_id,
        "total": len(itens),
        "subscriptions": itens,
        "total_monthly_cost": relatorio.get("total_monthly_cost", 0.0),
        "summary_text": relatorio.get("summary_text"),
    }
