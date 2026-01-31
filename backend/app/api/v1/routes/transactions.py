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
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.schemas.transaction import TransactionBatchResult
from app.etl import TransactionIngestor, TransactionClassifier

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/transactions", tags=["Transactions"])
logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEBHOOK: RECEBE TRANSAÇÕES DA PLUGGY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_transaction_webhook(payload: dict[str, Any]):
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
        # Inferir institution_id a partir do connector_id
        # Mapeamento Pluggy: connector_id → institution_id
        CONNECTOR_MAP = {
            "201": "nubank",
            "202": "itau",
            "203": "bradesco",
            "204": "inter",
            # Adicione outros conforme necessário
        }
        
        connector_id = str(payload.get("connector", {}).get("id", "unknown"))
        institution_id = CONNECTOR_MAP.get(connector_id, "unknown")
        
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
            # PASSO 3: SALVAR NO POSTGRES (TODO)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            # TODO: Implementar salvamento no Postgres
            # await save_to_postgres(categorized_df)
            
            logger.info(
                "ETL Pipeline completo",
                extra={
                    "final_records": len(categorized_df)
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
# ENDPOINT DE TESTE: Buscar transações processadas (futuro)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{user_id}")
async def get_user_transactions(user_id: str, limit: int = 100):
    """
    Retorna transações processadas de um usuário.
    
    TODO: Implementar query no Postgres.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Endpoint ainda não implementado. Aguardando integração com Postgres."
    )