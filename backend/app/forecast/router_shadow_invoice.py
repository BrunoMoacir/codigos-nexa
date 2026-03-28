"""
app/api/v1/routes/shadow_invoice.py - Endpoint de Shadow Invoices (Obrigações Futuras)

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE ESTE ARQUIVO FAZ                                               ║
╚══════════════════════════════════════════════════════════════════════╝

Expõe GET /shadow_invoice/{user_id} que retorna apenas as obrigações
futuras detectadas automaticamente:
    - Parcelamentos (detectados em descrições)
    - Assinaturas (recorrências detectadas)
    - Gastos variáveis (média + percentil de segurança)

╔══════════════════════════════════════════════════════════════════════╗
║ FLUXO                                                                ║
╚══════════════════════════════════════════════════════════════════════╝

GET /api/v1/shadow_invoice/user_123?days_ahead=60
        ↓
Buscar transações históricas (últimos 90 dias)
        ↓
Detectar padrões:
  1. Parcelamentos (01/10, 1/10, etc)
  2. Assinaturas (Netflix, Spotify, etc)
  3. Gastos variáveis (Uber, Mercado)
        ↓
Calcular próximas ocorrências até days_ahead
        ↓
Retornar ShadowInvoiceListResponse
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from app.core.security import require_owner

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS: Shadow Invoice Processing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.forecast.etl import (
    TransactionIngestor,
    TransactionClassifier,
    run_shadow_invoice_detection
)
from app.forecast.schemas_shadow_invoice import (
    ShadowInvoiceListResponse,
    ShadowInvoiceResponse,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

router = APIRouter(prefix="/shadow_invoice", tags=["Shadow Invoice"])
logger = logging.getLogger(__name__)

# TODO: Conectar com banco de dados para buscar transações por user_id


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /shadow_invoice/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{user_id}", response_model=ShadowInvoiceListResponse)
async def get_shadow_invoices(
    user_id: str = Depends(require_owner),
    days_ahead: int = 60,
) -> ShadowInvoiceListResponse:
    """
    Retorna obrigações financeiras futuras detectadas automaticamente.
    
    **O que é Shadow Invoice?**
    
    Shadow Invoice é a projeção matemática de compromissos financeiros futuros
    calculada a partir de padrões reais encontrados no histórico do usuário.
    
    Detecta automaticamente:
      1. **Parcelamentos**: "COMPRA 01/10", "1/10" (12 parcelas de R$ 100)
      2. **Assinaturas**: Netflix, Spotify, etc (padrão recorrente mensal)
      3. **Gastos Variáveis**: Uber, Mercado (média histórica + segurança)
    
    **Parâmetros:**
    - `user_id`: ID único do usuário
    - `days_ahead`: Quantos dias para frente projetar (padrão: 60)
    
    **Retorna:**
    ```json
    {
        "invoices": [
            {
                "id": "shadow_001",
                "date": "2025-02-15",
                "merchant": "MAGALU",
                "amount": -100.0,
                "type": "installment",
                "origin": "detected_parcel_01/10",
                "confidence": 0.95
            },
            {
                "id": "shadow_002",
                "date": "2025-02-20",
                "merchant": "NETFLIX",
                "amount": -21.90,
                "type": "subscription",
                "origin": "recurring_pattern",
                "confidence": 0.99
            }
        ],
        "total_count": 42,
        "total_monthly_impact": -1068.10,
        "subscriptions_count": 9,
        "installments_count": 33
    }
    ```
    
    **Fluxo Interno:**
    1. Buscar transações do usuário (últimos 90 dias)
    2. Normalizar com ETL Ingestor
    3. Executar ShadowInvoiceDetector
    4. Consolidar resultado em ShadowInvoiceListResponse
    
    **Notas importantes:**
    - Não usa dados bancários (que podem estar indisponíveis)
    - 100% determinístico (sem IA nesta etapa)
    - Sempre disponível mesmo quando Open Finance falha
    - Confidence score indica quantas vezes o padrão foi visto

    **Erros possíveis:**
    - 404: Usuário não encontrado
    - 500: Erro ao processar dados
    """
    try:
        logger.info("Processando shadow invoices para user=%s days_ahead=%d", user_id, days_ahead)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: BUSCAR TRANSAÇÕES HISTÓRICAS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # TODO: Query no Postgres para trazer transações do usuário
        # SELECT * FROM transactions_clean 
        # WHERE user_id = ? AND date >= now() - interval 90 days
        
        from app.runner import NexaRunner
        from app.core.config import settings
        import os

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"
        if mode == "prod" and (not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
            )

        runner = NexaRunner(mode=mode)
        runner_result = runner.run(horizon_days=days_ahead)
        
        if not runner_result:
            logger.warning(f"⚠️ Nenhuma transação encontrada para user_id={user_id}")
            # Retornar lista vazia (não é erro, apenas nenhum padrão detectado)
            return ShadowInvoiceListResponse(
                invoices=[],
                total_count=0,
                total_monthly_impact=0.0,
                subscriptions_count=0,
                installments_count=0
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: EXTRAIR SHADOW INVOICES DO RESULTADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        shadow_data = runner_result.get("shadow_invoices", {})
        
        logger.info(
            f"✅ Shadow invoices detectadas",
            extra={
                "total": shadow_data.get("total_count", 0),
                "subscriptions": shadow_data.get("subscriptions_count", 0),
                "installments": shadow_data.get("installments_count", 0),
                "monthly_impact": shadow_data.get("total_monthly_impact", 0)
            }
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CONSTRUIR RESPOSTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return ShadowInvoiceListResponse(
            invoices=shadow_data.get("invoices", []),
            total_count=shadow_data.get("total_count", 0),
            total_monthly_impact=shadow_data.get("total_monthly_impact", 0.0),
            subscriptions_count=shadow_data.get("subscriptions_count", 0),
            installments_count=shadow_data.get("installments_count", 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao processar shadow invoices para user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao detectar obrigações futuras. Tente novamente.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENDPOINT: GET /shadow_invoice/{user_id}/summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{user_id}/summary")
async def get_shadow_invoice_summary(user_id: str = Depends(require_owner)):
    """
    Retorna resumo das obrigações detectadas (apenas números chave).
    
    Útil para dashboards que querem informação rápida.
    
    Retorna:
    ```json
    {
        "total_monthly_committed": -1068.10,
        "total_count": 42,
        "subscriptions": 9,
        "installments": 33,
        "date_generated": "2025-02-11T15:30:00Z"
    }
    ```
    """
    
    try:
        logger.info("Gerando summary de shadow invoices para user=%s", user_id)
        
        from app.runner import NexaRunner
        from app.core.config import settings
        import os

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"
        if mode == "prod" and (not settings.PLUGGY_CLIENT_ID or not settings.PLUGGY_CLIENT_SECRET):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pluggy não configurada. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no backend/.env.",
            )

        runner = NexaRunner(mode=mode)
        runner_result = runner.run(horizon_days=30)
        
        shadow_data = runner_result.get("shadow_invoices", {})
        
        return {
            "total_monthly_committed": shadow_data.get("total_monthly_impact", 0.0),
            "total_count": shadow_data.get("total_count", 0),
            "subscriptions": shadow_data.get("subscriptions_count", 0),
            "installments": shadow_data.get("installments_count", 0),
            "date_generated": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error("Erro ao gerar summary de shadow invoices para user=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar resumo de obrigações. Tente novamente.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("", tags=["Health"])
async def shadow_invoice_health():
    """Health check do serviço."""
    return {
        "status": "ok",
        "service": "shadow_invoice",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
