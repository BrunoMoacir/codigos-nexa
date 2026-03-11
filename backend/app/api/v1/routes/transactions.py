"""
app/api/v1/routes/transactions.py - Webhook para receber transações da Pluggy

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Recebe webhooks da Pluggy com transações e:
1. Valida com TransactionBatchResult (tolerante a erros)
2. Salva JSON cru no storage (auditoria)
3. Processa com ETL (ingestor + classifier)
4. Retorna status de processamento

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO COMPLETO                                                       ║
╚══════════════════════════════════════════════════════════════════════╝

Pluggy → POST /api/v1/transactions/webhook
          ↓
    Valida (Pydantic TransactionBatchResult)
          ↓
    Salva JSON cru (storage/raw_events.py)
          ↓
    ETL Pipeline:
      1. Ingestor (limpa + normaliza)
      2. Classifier (categoriza)
          ↓
    Retorna status (200 OK)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.transaction import TransactionBatchResult
from app.etl import TransactionIngestor, TransactionClassifier

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/transactions", tags=["Transactions"])
logger = logging.getLogger(__name__)

# Mapeamento Pluggy connector_id → institution_id
# Adicionar novos bancos aqui conforme integração for expandida
_CONNECTOR_MAP: dict[str, str] = {
    "201": "nubank",
    "202": "itau",
    "203": "bradesco",
    "204": "inter",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEBHOOK: RECEBE TRANSAÇÕES DA PLUGGY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_transaction_webhook(
    payload: dict[str, Any],
    user_id: str = Query("golden_user_777", description="ID mapeado do item_id (mock para o MVP)")
):
    """
    Recebe webhook de transações da Pluggy.
    
    Payload esperado (Pluggy):
    {
        "connector": {"id": "201"},  # Nubank = 201
        "item": {"id": "item_abc123"},
        "results": [
            {
                "id": "txn_1",
                "amount": -50.00,
                "date": "2024-01-20T10:00:00Z",
                "description": "UBER VIAGEM",
                "accountId": "acc_123",
                ...
            }
        ]
    }
    
    Retorna:
    {
        "status": "processed",
        "batch_id": "batch_abc123",
        "total_received": 100,
        "total_valid": 95,
        "total_rejected": 5,
        "rejection_rate": 0.05
    }
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. EXTRAIR CONTEXTO DO WEBHOOK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    try:
        connector_id = str(payload.get("connector", {}).get("id", "unknown"))
        institution_id = _CONNECTOR_MAP.get(connector_id, "unknown")
        if institution_id == "unknown":
            logger.warning(
                "Webhook recebido com connector_id desconhecido: %s. "
                "Adicionar ao _CONNECTOR_MAP se for um banco válido.",
                connector_id,
            )
        
        item_id = payload.get("item", {}).get("id", "unknown")
        raw_transactions = payload.get("results", [])
        
        logger.info(
            "Webhook recebido",
            extra={
                "institution_id": institution_id,
                "item_id": item_id,
                "total_transactions": len(raw_transactions)
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao extrair contexto do webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload inválido: faltam campos obrigatórios (connector, item, results)"
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. VALIDAR BATCH (Pydantic - tolerante a erros)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    try:
        batch_result = TransactionBatchResult.from_raw_batch(
            raw_data=raw_transactions,
            institution_id=institution_id,
            item_id=item_id,
            fetched_at=datetime.now(timezone.utc)
        )
        
        logger.info(
            "Batch validado",
            extra={
                "total_valid": batch_result.total_valid,
                "total_rejected": batch_result.total_rejected,
                "rejection_rate": batch_result.rejection_rate
            }
        )
        
    except Exception as e:
        logger.error(f"Erro ao validar batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na validação do batch: {str(e)}"
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. SALVAR JSON CRU (Storage - auditoria)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # TODO: Implementar storage/raw_events.py
    # try:
    #     await save_raw_events(payload, institution_id)
    #     logger.info("JSON cru salvo no storage")
    # except Exception as e:
    #     logger.warning(f"Erro ao salvar JSON cru: {e}")
    #     # Não falha o webhook por causa disso (auditoria é opcional)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. PROCESSAR COM ETL (se houver transações válidas)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if batch_result.valid_transactions:
        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # PASSO 1: INGESTOR (Limpa + Normaliza)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            ingestor = TransactionIngestor()
            clean_df, metrics = ingestor.process(batch_result.valid_transactions)
            
            logger.info(
                "ETL Ingestor concluído",
                extra={
                    "records_processed": metrics.records_after_dedup,
                    "duplicates_removed": metrics.duplicates_removed,
                    "quality_score": metrics.quality_score
                }
            )
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # PASSO 2: CLASSIFIER (Categoriza)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            classifier = TransactionClassifier()
            categorized_df = classifier.predict(clean_df)
            
            logger.info("ETL Classifier concluído")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # PASSO 3: SALVAR NO DUCKDB
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            from app.db.queries import save_transactions_clean
            
            account_id = None
            if "account_id" in categorized_df.columns and not categorized_df.is_empty():
                account_id = categorized_df["account_id"][0]
                
            saved_rows = save_transactions_clean(
                df=categorized_df,
                user_id=user_id,
                account_id=account_id
            )
            
            logger.info(
                "ETL Pipeline completo",
                extra={
                    "final_records": len(categorized_df),
                    "saved_rows": saved_rows
                }
            )
            
        except Exception as e:
            logger.error(f"Erro no ETL Pipeline: {e}", exc_info=True)
            # Não falha o webhook (já salvamos os dados crus)
            # Mas loga erro para investigação
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. ALERTAR SE NECESSÁRIO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if batch_result.should_alert:
        logger.log(
            getattr(logging, batch_result.alert_level),  # WARNING ou CRITICAL
            batch_result.alert_message,
            extra={
                "institution_id": institution_id,
                "rejection_rate": batch_result.rejection_rate
            }
        )
        
        # TODO: Enviar alerta (Slack/PagerDuty)
        # if batch_result.alert_level == "CRITICAL":
        #     await send_slack_alert(batch_result.alert_message)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. RETORNAR STATUS (sempre 200 - webhook aceito)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    return {
        "status": "processed",
        "batch_id": batch_result.batch_id,
        "institution_id": institution_id,
        "total_received": batch_result.total_received,
        "total_valid": batch_result.total_valid,
        "total_rejected": batch_result.total_rejected,
        "rejection_rate": batch_result.rejection_rate,
        "alert_level": batch_result.alert_level
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: Buscar transações processadas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{user_id}", status_code=status.HTTP_200_OK)
async def get_user_transactions(
    user_id: str,
    start_date: Optional[str] = Query(
        default=None,
        description="Data inicial no formato YYYY-MM-DD. Sem filtro se omitido.",
    ),
    end_date: Optional[str] = Query(
        default=None,
        description="Data final no formato YYYY-MM-DD. Sem filtro se omitido.",
    ),
    category: Optional[str] = Query(
        default=None,
        description="Filtrar por categoria (ex: alimentacao, transporte).",
    ),
    transaction_type: Optional[str] = Query(
        default=None,
        description="Filtrar por tipo: 'debit' ou 'credit'.",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=1000,
        description="Máximo de transações retornadas (padrão: 200).",
    ),
) -> dict:
    """
    Retorna transações processadas de um usuário com filtros opcionais.

    Fonte primária: tabela `transactions_clean` no DuckDB.
    Fallback (dev): pipeline NexaRunner com dados mock Pluggy.

    **Campos por transação:**
    - `transaction_id`, `description`, `amount`, `date`, `category`,
      `transaction_type`, `is_recurring`, `is_installment`

    **Nota:** o campo `time` (hora da transação) não está disponível no schema
    atual — `date` é do tipo DATE. O agrupamento por hora no gráfico de colunas
    não pode ser feito com esses dados. Será suportado quando a Pluggy fornecer
    datetime completo e o ETL for atualizado.

    **Exemplo de resposta:**
    ```json
    {
      "user_id": "user_123",
      "total": 47,
      "debit_count": 38,
      "credit_count": 9,
      "filters": {"start_date": "2026-03-01", "end_date": "2026-03-06"},
      "transactions": [
        {
          "transaction_id": "txn_abc",
          "description": "UBER VIAGEM",
          "amount": -25.90,
          "date": "2026-03-05",
          "category": "transporte",
          "transaction_type": "debit",
          "is_recurring": false,
          "is_installment": false
        }
      ]
    }
    ```
    """
    import duckdb
    import polars as pl
    from app.db.queries import get_connection

    # ── 1. Tentar DuckDB (transactions_clean) ─────────────────────────
    try:
        con = get_connection()
        try:
            query = "SELECT * FROM transactions_clean WHERE user_id = ?"
            params: list = [user_id]

            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            if category:
                query += " AND lower(category) = lower(?)"
                params.append(category)
            if transaction_type:
                type_filter = "debit" if transaction_type.lower() == "debit" else "credit"
                amount_op = "<" if type_filter == "debit" else ">="
                query += f" AND amount {amount_op} 0"

            query += " ORDER BY date DESC LIMIT ?"
            params.append(limit)

            result_df = con.execute(query, params).pl()
        except (duckdb.CatalogException, duckdb.BinderException):
            result_df = pl.DataFrame()
        finally:
            con.close()
    except Exception as exc:
        logger.warning("Erro ao consultar DuckDB: %s", exc)
        result_df = pl.DataFrame()

    # ── 2. Fallback: NexaRunner (dev mode / tabela vazia) ─────────────
    if result_df.is_empty():
        logger.info("transactions_clean vazia para %s — usando pipeline", user_id)
        try:
            from app.runner import NexaRunner
            runner_mode = os.getenv("RUNNER_MODE", "dev")
            result = NexaRunner(mode=runner_mode).run(horizon_days=30)
            if result.get("status") == "success":
                txns: pl.DataFrame = result["transactions"]["pf_pj_classified_df"]
                if not txns.is_empty():
                    # Normalizar nomes de colunas para o schema de transactions_clean
                    rename = {
                        "predicted_category": "category",
                        "pf_pj_label": "context_type",
                        "transaction_date": "date",
                    }
                    for old, new in rename.items():
                        if old in txns.columns and new not in txns.columns:
                            txns = txns.rename({old: new})

                    # Aplicar filtros de data
                    if "date" in txns.columns:
                        txns = txns.with_columns(pl.col("date").cast(pl.Date))
                        if start_date:
                            from datetime import date as dt_date
                            txns = txns.filter(pl.col("date") >= dt_date.fromisoformat(start_date))
                        if end_date:
                            from datetime import date as dt_date
                            txns = txns.filter(pl.col("date") <= dt_date.fromisoformat(end_date))

                    if category and "category" in txns.columns:
                        txns = txns.filter(pl.col("category").str.to_lowercase() == category.lower())

                    if transaction_type and "amount" in txns.columns:
                        if transaction_type.lower() == "debit":
                            txns = txns.filter(pl.col("amount") < 0)
                        else:
                            txns = txns.filter(pl.col("amount") >= 0)

                    result_df = txns.head(limit)
        except Exception as exc:
            logger.error("Fallback pipeline falhou para %s: %s", user_id, exc)

    if result_df.is_empty():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nenhuma transação encontrada para user_id='{user_id}'.",
        )

    # ── 3. Serializar ──────────────────────────────────────────────────
    output_cols = [
        c for c in (
            "transaction_id", "description", "amount", "date",
            "category", "transaction_type", "is_recurring", "is_installment",
        )
        if c in result_df.columns
    ]
    serialized = result_df.select(output_cols).to_dicts()

    # Converter date para string
    for row in serialized:
        if "date" in row and hasattr(row["date"], "isoformat"):
            row["date"] = row["date"].isoformat()

    # ── 4. Estatísticas agregadas ──────────────────────────────────────
    debit_count = 0
    credit_count = 0
    if "amount" in result_df.columns:
        debit_count = result_df.filter(pl.col("amount") < 0).height
        credit_count = result_df.filter(pl.col("amount") >= 0).height

    logger.info(
        "GET /transactions/%s | total=%d | debit=%d | credit=%d",
        user_id, len(serialized), debit_count, credit_count,
    )

    return {
        "user_id": user_id,
        "total": len(serialized),
        "debit_count": debit_count,
        "credit_count": credit_count,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "category": category,
            "transaction_type": transaction_type,
        },
        "transactions": serialized,
    }