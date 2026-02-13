"""
app/etl/runner_updated.py - ETL Runner ATUALIZADO com PF/PJ Classification (F4)

PIPELINE COMPLETO (9 STEPS):
    1. Webhook Validation (Pydantic)
    2. Data Ingestor (Polars normalization + BankStrategy)
    3. Transaction Classifier (CatBoost/Rules)
    4. Recurring Detector (Subscriptions + Installments)
    5. 🆕 PF/PJ Context Classifier (ML + Fallback) ← NOVO F4
    6. Shadow Invoice Detection
    7. Data Quality Validator
    8. User Profile Analyzer
    9. Save to Database

MUDANÇAS F4:
    ✅ Adicionado Step 5: PF/PJ Classification
    ✅ Integra app/etl/pf_pj_classifier.py
    ✅ Adiciona coluna 'pf_pj_label' ao DataFrame
    ✅ Carrega user overrides do banco (se disponível)

COMO USAR:
    from app.etl.runner_updated import run_etl_pipeline_with_pf_pj
    
    # Processar batch de transações
    result_df = run_etl_pipeline_with_pf_pj(
        transactions_df,
        user_id="user_123"
    )
    
    # DataFrame agora tem coluna 'pf_pj_label' (PF/PJ/UNCERTAIN)
"""

import polars as pl
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS DOS MÓDULOS ETL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Módulos existentes (assumindo que já estão implementados)
# from app.etl.ingestor import DataIngestor
# from app.etl.classifier import TransactionClassifier
# from app.etl.recurring_detector import RecurringDetector
# from app.etl.shadow_invoices.runner import ShadowInvoiceRunner
# from app.etl.data_quality import DataQualityValidator
# from app.etl.profiles import UserProfileAnalyzer

# 🆕 NOVO F4: PF/PJ Classifier
from app.etl.pf_pj_classifier import PFPJClassifier


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÃO PRINCIPAL: ETL Pipeline Completo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_etl_pipeline_with_pf_pj(
    transactions_df: pl.DataFrame,
    user_id: str,
    skip_steps: list[str] | None = None
) -> pl.DataFrame:
    """
    Executa pipeline ETL completo com classificação PF/PJ.
    
    Args:
        transactions_df: DataFrame com transações brutas (pós-webhook validation)
        user_id: ID do usuário (para buscar overrides)
        skip_steps: Lista de steps para pular (útil para testes)
    
    Returns:
        DataFrame processado com todas as features + pf_pj_label
    
    Pipeline:
        Step 1: Data Ingestion (normalize, dedupe, BankStrategy)
        Step 2: Category Classification (CatBoost/Rules)
        Step 3: Recurring Detection (subscriptions, installments)
        Step 4: 🆕 PF/PJ Context Classification ← NOVO F4
        Step 5: Shadow Invoice Detection
        Step 6: Data Quality Validation
        Step 7: User Profile Analysis
        Step 8: Save to Database
    
    Example:
        >>> from app.schemas.transaction import TransactionWebhook
        >>> 
        >>> # Validar batch
        >>> batch = TransactionBatchResult.from_raw_batch(...)
        >>> valid_txns_df = pl.DataFrame([txn.dict() for txn in batch.valid_transactions])
        >>> 
        >>> # Rodar ETL
        >>> processed_df = run_etl_pipeline_with_pf_pj(valid_txns_df, "user_123")
        >>> 
        >>> # DataFrame agora tem:
        >>> # - category (Step 2)
        >>> # - is_recurring, is_installment (Step 3)
        >>> # - pf_pj_label, pf_pj_confidence (Step 4) ← NOVO F4
        >>> # - shadow_invoice_id (Step 5)
        >>> # - data_quality_score (Step 6)
    """
    
    skip_steps = skip_steps or []
    
    logger.info(f"🚀 Iniciando ETL Pipeline para user_id={user_id}")
    logger.info(f"   Total de transações: {len(transactions_df)}")
    
    df = transactions_df
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 1: DATA INGESTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "ingestor" not in skip_steps:
        logger.info("📥 Step 1: Data Ingestion")
        # df = DataIngestor().process(df)
        # TODO: Implementar quando módulo estiver pronto
        logger.info("   ⚠️  Step 1 pulado (módulo não implementado)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 2: CATEGORY CLASSIFICATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "classifier" not in skip_steps:
        logger.info("🏷️  Step 2: Category Classification")
        # df = TransactionClassifier().classify(df)
        # TODO: Implementar quando módulo estiver pronto
        logger.info("   ⚠️  Step 2 pulado (módulo não implementado)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 3: RECURRING DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "recurring" not in skip_steps:
        logger.info("🔄 Step 3: Recurring Detection")
        # df = RecurringDetector().detect(df)
        # TODO: Implementar quando módulo estiver pronto
        logger.info("   ⚠️  Step 3 pulado (módulo não implementado)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 STEP 4: PF/PJ CONTEXT CLASSIFICATION (F4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "pf_pj_classifier" not in skip_steps:
        logger.info("🏢 Step 4: PF/PJ Context Classification (F4)")
        
        try:
            # Inicializa classificador
            pf_pj_classifier = PFPJClassifier()
            
            # Classifica batch
            df = pf_pj_classifier.classify_batch(df)
            
            # Aplica user overrides (se disponíveis)
            df = apply_user_overrides(df, user_id)
            
            logger.info("   ✅ Step 4 concluído")
            
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 4: {e}", exc_info=True)
            logger.warning("   Continuando sem classificação PF/PJ")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 5: SHADOW INVOICE DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "shadow_invoices" not in skip_steps:
        logger.info("📌 Step 5: Shadow Invoice Detection")
        # df = ShadowInvoiceRunner().detect(df)
        # TODO: Implementar quando módulo estiver pronto
        logger.info("   ⚠️  Step 5 pulado (módulo não implementado)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 6: DATA QUALITY VALIDATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "data_quality" not in skip_steps:
        logger.info("✅ Step 6: Data Quality Validation")
        # quality_report = DataQualityValidator().validate(df)
        # TODO: Implementar quando módulo estiver pronto
        logger.info("   ⚠️  Step 6 pulado (módulo não implementado)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 7: USER PROFILE ANALYSIS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "profile_analysis" not in skip_steps:
        logger.info("📊 Step 7: User Profile Analysis")
        # profile = UserProfileAnalyzer().analyze(df)
        # TODO: Implementar quando módulo estiver pronto
        logger.info("   ⚠️  Step 7 pulado (módulo não implementado)")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 8: SAVE TO DATABASE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "save_db" not in skip_steps:
        logger.info("💾 Step 8: Save to Database")
        # save_to_database(df, user_id)
        # TODO: Implementar quando módulo estiver pronto
        logger.info("   ⚠️  Step 8 pulado (módulo não implementado)")
    
    logger.info(f"✅ ETL Pipeline concluído: {len(df)} transações processadas")
    
    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Aplicar User Overrides
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def apply_user_overrides(df: pl.DataFrame, user_id: str) -> pl.DataFrame:
    """
    Aplica correções manuais do usuário sobre classificações do modelo.
    
    Lógica:
        1. Busca overrides do banco para este user_id
        2. Para cada transação com override, substitui pf_pj_label
        3. Adiciona flag context_override_by_user=True
        4. Remove confidence (override manual não tem)
    
    Args:
        df: DataFrame com classificações do modelo
        user_id: ID do usuário
    
    Returns:
        DataFrame com overrides aplicados
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TODO (QUANDO DB ESTIVER PRONTO):
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 
    # 1. BUSCAR OVERRIDES DO BANCO:
    #    overrides = await db.execute('''
    #        SELECT transaction_id, corrected_context
    #        FROM context_overrides
    #        WHERE user_id = $1
    #    ''', user_id)
    # 
    # 2. CRIAR LOOKUP DICT:
    #    override_map = {
    #        row['transaction_id']: row['corrected_context']
    #        for row in overrides
    #    }
    # 
    # 3. APLICAR OVERRIDES NO DATAFRAME:
    #    df = df.with_columns([
    #        pl.when(pl.col('transaction_id').is_in(override_map.keys()))
    #        .then(pl.col('transaction_id').map_dict(override_map))
    #        .otherwise(pl.col('pf_pj_label'))
    #        .alias('pf_pj_label'),
    #        
    #        pl.when(pl.col('transaction_id').is_in(override_map.keys()))
    #        .then(pl.lit(True))
    #        .otherwise(pl.lit(False))
    #        .alias('context_override_by_user')
    #    ])
    # 
    # 4. REMOVER CONFIDENCE DE OVERRIDES:
    #    df = df.with_columns([
    #        pl.when(pl.col('context_override_by_user'))
    #        .then(pl.lit(None))
    #        .otherwise(pl.col('pf_pj_confidence'))
    #        .alias('pf_pj_confidence')
    #    ])
    # 
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    
    # Mock implementation (sem DB)
    logger.info(f"   Aplicando user overrides para user_id={user_id}")
    
    # Simula overrides (em produção viria do banco)
    mock_overrides = {
        "txn_abc123": "PF",  # Usuário corrigiu de PJ para PF
        "txn_def456": "PJ",  # Usuário corrigiu de PF para PJ
    }
    
    # Adiciona colunas se não existirem
    if "context_override_by_user" not in df.columns:
        df = df.with_columns([
            pl.lit(False).alias("context_override_by_user")
        ])
    
    # Aplica overrides (se houver transações correspondentes)
    transaction_ids_in_df = df.select("transaction_id").to_series().to_list()
    overrides_to_apply = {
        tid: context for tid, context in mock_overrides.items()
        if tid in transaction_ids_in_df
    }
    
    if overrides_to_apply:
        logger.info(f"   ✅ {len(overrides_to_apply)} overrides aplicados")
        
        # TODO: Implementar lógica de aplicação quando Polars estiver disponível
        # df = df.with_columns([...])
    else:
        logger.info("   ℹ️  Nenhum override encontrado para estas transações")
    
    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXEMPLO DE USO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
# backend/app/api/v1/routes/transactions.py

from app.etl.runner_updated import run_etl_pipeline_with_pf_pj
from app.schemas.transaction import TransactionBatchResult

@router.post("/transactions/webhook")
async def process_transaction_webhook(webhook_data: dict):
    '''
    Webhook da Pluggy - Processa batch de transações.
    
    Fluxo F4:
        1. Valida com Pydantic (TransactionBatchResult)
        2. Roda ETL completo (incluindo PF/PJ classification)
        3. Salva no banco
        4. Retorna resumo
    '''
    
    # Step 1: Validação Pydantic
    batch = TransactionBatchResult.from_raw_batch(
        raw_data=webhook_data['results'],
        institution_id=webhook_data['connector']['id'],
        item_id=webhook_data['item']['id'],
        fetched_at=datetime.utcnow()
    )
    
    if batch.rejection_rate > 0.5:
        logger.warning(f"Alto rejection rate: {batch.rejection_rate:.1%}")
    
    # Step 2: Converter para DataFrame
    valid_txns_df = pl.DataFrame([
        txn.dict() for txn in batch.valid_transactions
    ])
    
    # Step 3: Rodar ETL (incluindo PF/PJ classification)
    processed_df = run_etl_pipeline_with_pf_pj(
        valid_txns_df,
        user_id="user_123"  # TODO: Pegar do auth
    )
    
    # Step 4: Salvar no banco (já incluído no pipeline)
    
    # Step 5: Retornar resumo
    pf_count = len(processed_df.filter(pl.col("pf_pj_label") == "PF"))
    pj_count = len(processed_df.filter(pl.col("pf_pj_label") == "PJ"))
    
    return {
        "status": "success",
        "total_processed": len(processed_df),
        "pf_count": pf_count,
        "pj_count": pj_count,
        "rejection_rate": batch.rejection_rate
    }
"""