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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.schemas.transaction import TransactionBatchResult
from app.forecast.etl import TransactionIngestor, TransactionClassifier
from app.core.database import get_db
from app.core.cache import cache_response, invalidate_user_cache

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
    user_id: str = Query("golden_user_777", description="ID mapeado do item_id (mock para o MVP)"),
    db: Session = Depends(get_db)
):
    """
    Recebe webhook de transações da Pluggy.
    """
    
    # 1. EXTRAIR CONTEXTO DO WEBHOOK
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
        logger.error("Erro ao extrair contexto do webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload inválido: faltam campos obrigatórios (connector, item, results)"
        )
    
    # 2. VALIDAR BATCH (Pydantic - tolerante a erros)
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
        logger.error("Erro ao validar batch de transações: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao validar transações. Verifique o formato dos dados.",
        )
    
    # 3. PROCESSAR COM ETL (se houver transações válidas)
    if batch_result.valid_transactions:
        try:
            # PASSO 1: INGESTOR (Limpa + Normaliza)
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
            
            # PASSO 2: CLASSIFIER (Categoriza)
            classifier = TransactionClassifier()
            categorized_df = classifier.predict(clean_df)
            
            logger.info("ETL Classifier concluído")
            
            # PASSO 3: SALVAR NO POSTGRES VIA SQLALCHEMY
            from app.core.db.queries import save_transactions_clean
            
            account_id = None
            if "account_id" in categorized_df.columns and not categorized_df.is_empty():
                account_id = categorized_df["account_id"][0]
                
            saved_rows = save_transactions_clean(
                db=db,
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

            # Invalidar cache após salvar transações
            invalidate_user_cache(user_id)
            logger.debug(f"Cache invalidado para user_id={user_id} após novas transações")
            
        except Exception as e:
            logger.error("Erro no ETL Pipeline: %s", e, exc_info=True)
    
    if batch_result.should_alert:
        logger.log(
            getattr(logging, batch_result.alert_level),  # WARNING ou CRITICAL
            batch_result.alert_message,
            extra={
                "institution_id": institution_id,
                "rejection_rate": batch_result.rejection_rate
            }
        )
    
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
@cache_response(prefix="transactions", ttl=300)
async def get_user_transactions(
    user_id: str,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    transaction_type: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db)
) -> dict:
    """Retorna transações processadas de um usuário com filtros opcionais."""
    import polars as pl
    from app.core.db.queries import get_transactions_for_user

    try:
        txns = get_transactions_for_user(user_id)
        if txns.is_empty():
            serialized = []
            debit_count = 0
            credit_count = 0
        else:
            # Normalizações esperadas pela API
            rename = {
                "predicted_category": "category",
                "pf_pj_label": "context_type",
                "transaction_date": "date",
            }
            for old, new in rename.items():
                if old in txns.columns and new not in txns.columns:
                    txns = txns.rename({old: new})

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

            # Ordena desc e limita
            if "date" in txns.columns:
                txns = txns.sort("date", descending=True)
            result_df = txns.head(limit)

            output_cols = [
                c
                for c in (
                    "transaction_id",
                    "description",
                    "amount",
                    "date",
                    "category",
                    "transaction_type",
                    "is_recurring",
                    "is_installment",
                    "context_type",
                )
                if c in result_df.columns
            ]
            serialized = result_df.select(output_cols).to_dicts()

            for row in serialized:
                if "date" in row and hasattr(row["date"], "isoformat"):
                    row["date"] = row["date"].isoformat()

            # Contar débito/crédito
            debit_count = 0
            credit_count = 0
            if "amount" in result_df.columns:
                debit_count = result_df.filter(pl.col("amount") < 0).height
                credit_count = result_df.filter(pl.col("amount") >= 0).height

        if not serialized:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nenhuma transação encontrada para user_id='{user_id}'.",
            )

        logger.info(
            "GET /transactions/%s | total=%d | debit=%d | credit=%d",
            user_id,
            len(serialized),
            debit_count,
            credit_count,
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Erro ao consultar transações: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar transações: {str(exc)}",
        )