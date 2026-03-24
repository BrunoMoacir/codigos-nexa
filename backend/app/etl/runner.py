"""
app/etl/runner.py - Orquestrador Principal do Pipeline ETL

Pipeline Completo (8 STEPS):
    1. Data Ingestor (Polars normalization + BankStrategy)
    2. Transaction Classifier (CatBoost/Rules - categorias)
    3. Recurring Detector (Subscriptions + Installments)
    4. 🆕 PF/PJ Context Classifier (ML + Fallback) ← F4
    5. Shadow Invoice Detection (Subscription + Installment)
    6. Data Quality Validator
    7. User Profile Analyzer
    8. Save to Database

Uso:
    from app.etl.runner import run_etl_pipeline
    
    result_df = run_etl_pipeline(
        transactions_df=raw_transactions,
        user_id="user_123",
        account_id="acc_001"
    )
"""

import polars as pl
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS DOS MÓDULOS ETL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Módulos existentes
# Step 1 (Ingestor) não é chamado aqui: TransactionIngestor.process() espera
# list[TransactionWebhook], não um DataFrame. Ele é chamado antes da pipeline,
# na rota POST /transactions/webhook, que converte o payload para DataFrame
# e só então chama run_etl_pipeline().
from app.etl.classifier import TransactionClassifier
from app.etl.recurring_detector import RecurringDetector
from app.etl.data_quality import DataQualityValidator
from app.etl.profiles import UserProfileAnalyzer

# Shadow Invoice Detection (já implementado)
from app.etl.shadow_invoices.runner import run_shadow_invoice_detection

# 🆕 F4: PF/PJ Classifier
from app.etl.pf_pj_classifier import PFPJClassifier

# Persistência
from app.db.queries import save_transactions_clean


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÃO PRINCIPAL: ETL Pipeline Completo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from sqlalchemy.orm import Session

def run_etl_pipeline(
    db: Session,
    transactions_df: pl.DataFrame,
    user_id: str,
    account_id: str | None = None,
    skip_steps: list[str] | None = None
) -> pl.DataFrame:
    """
    Executa pipeline ETL completo com todas as transformações.
    
    Args:
        transactions_df: DataFrame com transações brutas (pós-webhook validation)
        user_id: ID do usuário (para buscar overrides)
        account_id: ID da conta (opcional, para contexto)
        skip_steps: Lista de steps para pular (útil para testes/debug)
    
    Returns:
        DataFrame processado com todas as features calculadas
    
    Pipeline Steps:
        1. Data Ingestion        - Normalização, dedupe, BankStrategy
        2. Category Classification - CatBoost/Rules para categorias
        3. Recurring Detection   - Assinaturas e parcelamentos
        4. PF/PJ Classification  - Contexto pessoal vs empresarial (F4)
        5. Shadow Invoice        - Obrigações futuras
        6. Data Quality          - Validação e confidence scoring
        7. Profile Analysis      - Financial health, savings rate
        8. Database Persistence  - Salvar em transactions_clean
    
    Example:
        >>> from app.schemas.transaction import TransactionBatchResult
        >>> 
        >>> # Validar batch com Pydantic
        >>> batch = TransactionBatchResult.from_raw_batch(raw_data, ...)
        >>> valid_txns_df = pl.DataFrame([txn.dict() for txn in batch.valid_transactions])
        >>> 
        >>> # Rodar ETL completo
        >>> processed_df = run_etl_pipeline(
        ...     valid_txns_df,
        ...     user_id="user_123",
        ...     account_id="acc_001"
        ... )
        >>> 
        >>> # DataFrame agora tem todas as features:
        >>> # - category (Step 2)
        >>> # - is_recurring, is_installment (Step 3)
        >>> # - context_type, context_confidence (Step 4) ← F4
        >>> # - shadow_invoice_id (Step 5)
        >>> # - data_status, confidence (Step 6)
    """
    
    skip_steps = skip_steps or []
    
    logger.info(f"🚀 Iniciando ETL Pipeline")
    logger.info(f"   User: {user_id}")
    logger.info(f"   Account: {account_id or 'N/A'}")
    logger.info(f"   Transações: {len(transactions_df)}")
    
    df = transactions_df
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 1: DATA INGESTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Step 1 (Ingestor) é executado antes desta função, na rota de webhook.
    # O DataFrame já chega normalizado.
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 2: CATEGORY CLASSIFICATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "classifier" not in skip_steps:
        logger.info("🏷️  Step 2: Category Classification")
        try:
            df = TransactionClassifier().predict(df)
            logger.info("   ✅ Step 2 concluído")
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 2: {e}", exc_info=True)
            logger.warning("   Continuando sem classificação de categorias")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 3: RECURRING DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "recurring" not in skip_steps:
        logger.info("🔄 Step 3: Recurring Detection")
        try:
            df = RecurringDetector().detect(df)
            logger.info("   ✅ Step 3 concluído")
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 3: {e}", exc_info=True)
            logger.warning("   Continuando sem detecção de recorrências")
    
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
            
            # Aplica user overrides (se disponíveis no banco)
            df = apply_user_overrides(db, df, user_id)
            
            # Log de resultados
            pf_count = len(df.filter(pl.col("pf_pj_label") == "PF")) if "pf_pj_label" in df.columns else 0
            pj_count = len(df.filter(pl.col("pf_pj_label") == "PJ")) if "pf_pj_label" in df.columns else 0
            uncertain_count = len(df.filter(pl.col("pf_pj_label") == "UNCERTAIN")) if "pf_pj_label" in df.columns else 0
            
            logger.info(f"   ✅ Step 4 concluído: PF={pf_count}, PJ={pj_count}, UNCERTAIN={uncertain_count}")
            
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 4: {e}", exc_info=True)
            logger.warning("   Continuando sem classificação PF/PJ")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 5: SHADOW INVOICE DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "shadow_invoices" not in skip_steps:
        logger.info("📌 Step 5: Shadow Invoice Detection")
        
        try:
            # Detecta obrigações futuras (Subscription + Installment)
            shadow_df = run_shadow_invoice_detection(df)
            
            if not shadow_df.is_empty():
                logger.info(f"   ✅ Detectadas {len(shadow_df)} shadow invoices")
                
                # TODO: Salvar shadow invoices em tabela separada
                # await save_shadow_invoices(shadow_df, user_id)
            else:
                logger.info("   ℹ️  Nenhuma shadow invoice detectada")
        
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 5: {e}", exc_info=True)
            logger.warning("   Continuando sem shadow invoices")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 6: DATA QUALITY VALIDATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "data_quality" not in skip_steps:
        logger.info("✅ Step 6: Data Quality Validation")
        try:
            quality_report = DataQualityValidator().validate(df)
            logger.info(f"   ✅ Step 6 concluído: confidence={quality_report.overall_confidence:.2f}, "
                        f"level={quality_report.quality_level}, anomalias={quality_report.anomaly_count}")
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 6: {e}", exc_info=True)
            logger.warning("   Continuando sem validação de qualidade")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 7: USER PROFILE ANALYSIS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "profile_analysis" not in skip_steps:
        logger.info("📊 Step 7: User Profile Analysis")
        try:
            # MI.2: rodar IncomeProfiler primeiro para filtrar renda real (sem transferências)
            from app.etl.income_profiler import IncomeProfiler
            income_profile = IncomeProfiler().build(df)
            logger.info(
                f"   ℹ️  IncomeProfiler: renda=R$ {income_profile.monthly_net_income:,.0f}/mês, "
                f"padrão={income_profile.income_pattern.value}, "
                f"confiança={income_profile.confidence:.0%}"
            )
            profile = UserProfileAnalyzer().analyze(df, income_profile=income_profile)
            logger.info(f"   ✅ Step 7 concluído: perfil={profile.profile_type}, "
                        f"score={profile.score}")
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 7: {e}", exc_info=True)
            logger.warning("   Continuando sem análise de perfil")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 8: SAVE TO DATABASE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "save_db" not in skip_steps:
        logger.info("💾 Step 8: Save to Database")
        try:
            rows_saved = save_transactions_clean(db, df, user_id=user_id, account_id=account_id)
            logger.info(f"   ✅ Step 8 concluído: {rows_saved} linhas salvas em transactions_clean")
        except Exception as e:
            logger.error(f"   ❌ Erro no Step 8: {e}", exc_info=True)
            logger.warning("   Continuando sem persistência")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONCLUSÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    logger.info(f"✅ ETL Pipeline concluído: {len(df)} transações processadas")
    
    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPER: Aplicar User Overrides (F4)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def apply_user_overrides(db: Session, df: pl.DataFrame, user_id: str) -> pl.DataFrame:
    """
    Aplica correções manuais do usuário sobre classificações PF/PJ.
    
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
    # from app.db.queries import get_context_overrides
    # 
    # 1. BUSCAR OVERRIDES DO BANCO:
    #    overrides = await get_context_overrides(user_id)
    #    # SELECT transaction_id, corrected_context
    #    # FROM context_overrides
    #    # WHERE user_id = $1
    # 
    # 2. CRIAR LOOKUP DICT:
    #    override_map = {
    #        row['transaction_id']: row['corrected_context']
    #        for row in overrides
    #    }
    # 
    # 3. APLICAR OVERRIDES NO DATAFRAME:
    #    if override_map:
    #        df = df.with_columns([
    #            # Substituir pf_pj_label com override
    #            pl.when(pl.col('transaction_id').is_in(override_map.keys()))
    #            .then(pl.col('transaction_id').map_dict(override_map))
    #            .otherwise(pl.col('pf_pj_label'))
    #            .alias('pf_pj_label'),
    #            
    #            # Marcar como override
    #            pl.when(pl.col('transaction_id').is_in(override_map.keys()))
    #            .then(pl.lit(True))
    #            .otherwise(pl.lit(False))
    #            .alias('context_override_by_user'),
    #            
    #            # Remover confidence de overrides
    #            pl.when(pl.col('transaction_id').is_in(override_map.keys()))
    #            .then(pl.lit(None))
    #            .otherwise(pl.col('pf_pj_confidence'))
    #            .alias('pf_pj_confidence')
    #        ])
    # 
    # 4. LOG:
    #    logger.info(f"   ✅ {len(override_map)} overrides aplicados")
    # 
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # IMPLEMENTAÇÃO REAL (Integrada com DB)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    from app.db.queries import get_context_overrides
    
    try:
        # 1. BUSCAR OVERRIDES DO BANCO
        # get_context_overrides retorna list[dict] com keys: transaction_id, corrected_context, ...
        overrides = get_context_overrides(db, user_id)
        
        if not overrides:
            logger.info("   ℹ️  Nenhum override encontrado no banco para este usuário")
            return df
            
        # 2. CRIAR LOOKUP DICT
        override_map = {
            row['transaction_id']: row['corrected_context']
            for row in overrides
        }
        
        # 3. APLICAR OVERRIDES NO DATAFRAME
        # Verifica se as colunas necessárias existem, cria se não
        if "pf_pj_label" not in df.columns:
            logger.warning("   ⚠️  Coluna pf_pj_label não existe - criando vazia para overrides")
            df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias("pf_pj_label"))
            
        if "pf_pj_confidence" not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Float64).alias("pf_pj_confidence"))
            
        # Lógica de aplicação
        df = df.with_columns([
            # Substituir pf_pj_label com override, manter original se não houver
            pl.when(pl.col('transaction_id').is_in(override_map.keys()))
            .then(pl.col('transaction_id').map_dict(override_map))
            .otherwise(pl.col('pf_pj_label'))
            .alias('pf_pj_label'),
            
            # Marcar como override
            pl.when(pl.col('transaction_id').is_in(override_map.keys()))
            .then(pl.lit(True))
            .otherwise(pl.lit(False))
            .alias('context_override_by_user'),
            
            # Definir confidence como 1.0 para overrides (firmeza total)
            pl.when(pl.col('transaction_id').is_in(override_map.keys()))
            .then(pl.lit(1.0))
            .otherwise(pl.col('pf_pj_confidence'))
            .alias('pf_pj_confidence')
        ])
        
        applied_count = len([tid for tid in override_map.keys() if tid in df['transaction_id'].to_list()])
        if applied_count > 0:
            logger.info(f"   ✅ {applied_count} overrides aplicados com sucesso")
            
    except Exception as e:
        logger.error(f"   ❌ Erro ao aplicar overrides: {e}")
        # Retorna DF original em caso de erro para não quebrar pipeline
        return df

    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXEMPLO DE USO EM API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
# backend/app/api/v1/routes/transactions.py

from app.etl.runner import run_etl_pipeline
from app.schemas.transaction import TransactionBatchResult
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import polars as pl

router = APIRouter(prefix="/transactions", tags=["Transactions"])

@router.post("/webhook")
async def process_transaction_webhook(webhook_data: dict):
    '''
    Webhook da Pluggy/Belvo - Processa batch de transações.
    
    Fluxo completo:
        1. Validação Pydantic (TransactionBatchResult)
        2. ETL completo (8 steps incluindo F4)
        3. Persistência no banco
        4. Retorno de resumo
    '''
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 1: Validação Pydantic
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    batch = TransactionBatchResult.from_raw_batch(
        raw_data=webhook_data['results'],
        institution_id=webhook_data['connector']['id'],
        item_id=webhook_data['item']['id'],
        fetched_at=datetime.utcnow()
    )
    
    # Log rejection rate
    if batch.rejection_rate > 0.5:
        logger.warning(f"Alto rejection rate: {batch.rejection_rate:.1%}")
    
    if batch.total_valid == 0:
        raise HTTPException(
            status_code=422,
            detail=f"Nenhuma transação válida. Rejection rate: {batch.rejection_rate:.1%}"
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 2: Converter para DataFrame Polars
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    valid_txns_df = pl.DataFrame([
        txn.dict() for txn in batch.valid_transactions
    ])
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 3: Rodar ETL completo (incluindo F4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    processed_df = run_etl_pipeline(
        transactions_df=valid_txns_df,
        user_id="user_123",  # TODO: Pegar do auth context
        account_id=webhook_data.get('account_id')
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 4: Extrair métricas do resultado
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Contadores PF/PJ (F4)
    pf_count = 0
    pj_count = 0
    uncertain_count = 0
    
    if "pf_pj_label" in processed_df.columns:
        pf_count = len(processed_df.filter(pl.col("pf_pj_label") == "PF"))
        pj_count = len(processed_df.filter(pl.col("pf_pj_label") == "PJ"))
        uncertain_count = len(processed_df.filter(pl.col("pf_pj_label") == "UNCERTAIN"))
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STEP 5: Retornar resumo
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    return {
        "status": "success",
        "total_received": batch.total_received,
        "total_valid": batch.total_valid,
        "total_rejected": batch.total_rejected,
        "total_processed": len(processed_df),
        "rejection_rate": batch.rejection_rate,
        
        # Métricas F4
        "context_classification": {
            "pf_count": pf_count,
            "pj_count": pj_count,
            "uncertain_count": uncertain_count
        }
    }
"""