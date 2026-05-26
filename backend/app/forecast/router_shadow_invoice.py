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
from datetime import date, datetime, timezone
from typing import Optional

import polars as pl
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
        
        from app.runner import get_runner
        import os

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"
        runner_result = get_runner(mode).run_from_db(user_id=user_id, horizon_days=days_ahead)

        if not runner_result or runner_result.get("status") != "success":
            logger.warning("⚠️ Nenhuma transação ou erro no runner para user_id=%s", user_id)
            # Não retornar cedo: prosseguir para tentar agregar assinaturas
            # Shadow data ficará vazio e preencheremos a partir da tabela `subscriptions` se existir.
            shadow_data = {}
        else:
            shadow_data = runner_result.get("projections", {}).get("shadow_events", {})
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: EXTRAIR SHADOW INVOICES DO RESULTADO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        invoices_list = []
        total_monthly_impact = 0.0
        total_count = 0
        subscriptions_count = 0
        installments_count = 0

        if hasattr(shadow_data, "filter") and not shadow_data.is_empty():
            for row in shadow_data.to_dicts():
                metadata = row.get("metadata") or {}
                description = metadata.get("description", "Desconhecido")
                next_due_date = row.get("next_due_date")
                if isinstance(next_due_date, date) and not isinstance(next_due_date, datetime):
                    next_due_date = datetime.combine(next_due_date, datetime.min.time(), tzinfo=timezone.utc)
                invoices_list.append({
                    "id": f"shadow_{row.get('type', 'unknown').lower()}_{len(invoices_list)}",
                    "next_due_date": next_due_date,
                    "merchant": description.upper(),
                    "description": description,
                    "amount": round(float(row.get("amount", 0)), 2),
                    "type": str(row.get("type", "unknown")).upper(),
                    "origin": "recurring_pattern",
                    "confidence": round(float(row.get("confidence", 0)), 2),
                    "occurrences": metadata.get("occurrences"),
                })

            total_count = shadow_data.height
            if "amount" in shadow_data.columns:
                total_monthly_impact = -round(abs(float(shadow_data.select("amount").sum().item())), 2)
            if "type" in shadow_data.columns:
                subscriptions_count = shadow_data.filter(pl.col("type") == "SUBSCRIPTION").height
                installments_count = shadow_data.filter(pl.col("type") == "INSTALLMENT").height
        elif isinstance(shadow_data, dict):
            invoices_list = shadow_data.get("invoices", [])
            total_count = shadow_data.get("total_count", 0)
            subscriptions_count = shadow_data.get("subscriptions_count", 0)
            installments_count = shadow_data.get("installments_count", 0)
            total_monthly_impact = shadow_data.get("total_monthly_impact", 0.0)

        # ── Incluir assinaturas presentes na tabela `subscriptions` (caso existam)
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                q = db.execute(text("""
                    SELECT name, amount, next_billing_date, status, billing_cycle
                    FROM subscriptions
                    WHERE user_id = :user_id
                """), {"user_id": user_id})

                subs_rows = q.fetchall()
                for row in subs_rows:
                    name, amt, next_billing, row_status, cycle = row[0], row[1], row[2], row[3], row[4]
                    if row_status == 'active' and (cycle is None or (isinstance(cycle, str) and cycle.lower() == 'monthly')):
                        due_date = next_billing
                        if isinstance(due_date, date) and not isinstance(due_date, datetime):
                            due_date = datetime.combine(due_date, datetime.min.time(), tzinfo=timezone.utc)
                        invoices_list.append({
                            "id": f"sub_tbl_{len(invoices_list)}",
                            "next_due_date": due_date,
                            "merchant": (name or "Desconhecido").upper(),
                            "description": name or "Desconhecido",
                            "amount": -abs(float(amt or 0.0)),
                            "type": "SUBSCRIPTION",
                            "origin": "subscriptions_table",
                            "confidence": 1.0,
                        })
                        subscriptions_count = subscriptions_count + 1
                        total_monthly_impact = total_monthly_impact - abs(float(amt or 0.0))
                        total_count = total_count + 1
            finally:
                db.close()
        except Exception:
            # Não falhar caso a tabela não exista ou haja erro de leitura
            pass
        
        logger.info(
            f"✅ Shadow invoices detectadas",
            extra={
                "total": total_count,
                "subscriptions": subscriptions_count,
                "installments": installments_count,
                "monthly_impact": total_monthly_impact
            }
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: CONSTRUIR RESPOSTA
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return ShadowInvoiceListResponse(
            invoices=invoices_list,
            total_count=total_count,
            total_monthly_impact=total_monthly_impact,
            subscriptions_count=subscriptions_count,
            installments_count=installments_count
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
        
        from app.runner import get_runner
        import os

        mode = "prod" if os.getenv("APP_MODE", "dev") == "prod" else "dev"
        runner_result = get_runner(mode).run_from_db(user_id=user_id, horizon_days=30)
        
        if not runner_result or runner_result.get("status") != "success":
            shadow_data = {}
        else:
            shadow_data = runner_result.get("projections", {}).get("shadow_events", {})
            if hasattr(shadow_data, "filter"):  # It's a dataframe!
                shadow_data = {
                    "total_monthly_impact": -round(abs(float(shadow_data.select("amount").sum().item())), 2) if "amount" in shadow_data.columns else 0.0,
                    "total_count": shadow_data.height,
                    "subscriptions_count": shadow_data.filter(pl.col("type") == "SUBSCRIPTION").height if "type" in shadow_data.columns else 0,
                    "installments_count": shadow_data.filter(pl.col("type") == "INSTALLMENT").height if "type" in shadow_data.columns else 0,
                }
            elif isinstance(shadow_data, dict):
                pass
            else:
                shadow_data = {}
        
        # Incluir assinaturas da tabela `subscriptions` no resumo (se existirem)
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                q = db.execute(text("""
                    SELECT amount, status, billing_cycle
                    FROM subscriptions
                    WHERE user_id = :user_id
                """), {"user_id": user_id})
                rows = q.fetchall()
                sub_count_tbl = 0
                sub_total_tbl = 0.0
                for r in rows:
                    amt, row_status, cycle = r[0], r[1], r[2]
                    if row_status == 'active' and (cycle is None or (isinstance(cycle, str) and cycle.lower() == 'monthly')):
                        sub_count_tbl += 1
                        sub_total_tbl += float(amt or 0.0)
                # Merge into shadow_data values
                total_monthly = shadow_data.get("total_monthly_impact", 0.0) - sub_total_tbl
                total_count = shadow_data.get("total_count", 0) + sub_count_tbl
                subscriptions_count = shadow_data.get("subscriptions_count", 0) + sub_count_tbl
            finally:
                db.close()
        except Exception:
            total_monthly = shadow_data.get("total_monthly_impact", 0.0)
            total_count = shadow_data.get("total_count", 0)
            subscriptions_count = shadow_data.get("subscriptions_count", 0)

        return {
            "total_monthly_committed": total_monthly,
            "total_count": total_count,
            "subscriptions": subscriptions_count,
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
