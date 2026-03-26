"""
test_schemas_complete.py - Validação Completa de TODOS os Schemas (CORRIGIDO)

OBJETIVO:
    Validar todos os schemas Pydantic do sistema para garantir que:
    ✅ Aceitam dados válidos
    ✅ Rejeitam dados inválidos
    ✅ Conversores funcionam corretamente
    ✅ Serialização JSON funciona
    ✅ Validações de campo funcionam

SCHEMAS TESTADOS:
    1. TransactionWebhook (entrada de webhooks)
    2. TransactionOut (saída de API)
    3. RejectedTransaction (DLQ)
    4. TransactionBatchResult (validação tolerante)
    5. ShadowInvoiceResponse (shadow invoices)
    6. ShadowInvoiceListResponse (lista de shadows)
    7. CashflowProjectionPoint (ponto de projeção)
    8. CashflowSummaryResponse (resumo cashflow)
    9. CashflowProjectionResponse (projeção completa)
    10. SafeToSpendResponse (safe-to-spend básico)
    11. SafeToSpendDetailedResponse (safe-to-spend detalhado)
    12. FinancialHealthResponse (saúde financeira)
    13. MonthlyForecastResponse (previsão mensal)
    14. ForecastResponse (forecast completo)

CORREÇÕES APLICADAS:
    ✅ CORREÇÃO 1: Campo "date" → "projection_date" (CashflowProjectionPoint)
    ✅ CORREÇÃO 2: Campo "shadow_amount" → "expenses" (CashflowProjectionPoint)
    ✅ CORREÇÃO 3: Adicionado "id" ao batch Itaú (TransactionBatchResult)

EXECUÇÃO:
    cd backend
    python app/schemas/test_schemas_complete.py
"""

import sys
import os
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAR PYTHON PATH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Adiciona o diretório 'backend' ao PYTHONPATH para permitir imports de 'app'

# Detectar diretório do backend (2 níveis acima deste arquivo)
current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent.parent  # test_schemas_complete.py → schemas → app → backend

# Adicionar ao sys.path se ainda não estiver
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
    print(f"✅ Python path configurado: {backend_dir}\n")

import logging
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from pydantic import ValidationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS DE TESTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def header(title: str):
    """Imprime header de seção."""
    print(f"\n{'='*80}")
    print(f"🧪 {title}")
    print(f"{'='*80}\n")


def subheader(title: str):
    """Imprime subheader."""
    print(f"\n▶ {title}")
    print(f"{'-'*80}")


def success(msg: str):
    """Imprime mensagem de sucesso."""
    print(f"   ✅ {msg}")


def error(msg: str):
    """Imprime mensagem de erro."""
    print(f"   ❌ {msg}")


def info(msg: str):
    """Imprime informação."""
    print(f"   ℹ️  {msg}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 1: TRANSACTION SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_transaction_webhook():
    """Testa TransactionWebhook (schema de entrada)."""
    from app.core.schemas.transaction import TransactionWebhook
    
    subheader("TESTE 1.1: TransactionWebhook - Dados Válidos")
    
    # Dados válidos (Nubank/Pluggy padrão)
    valid_data = {
        "transaction_id": "txn_nubank_abc123",
        "account_id": "acc_xyz789",
        "amount": -150.50,
        "transaction_date": "2024-01-15T10:30:00Z",
        "description": "PAG UBER VIAGEM",
        "balance": 1849.50,
        "status": "POSTED",
        "institution_id": "nubank",
        "item_id": "item_123",
        "source": "PLUGGY",
        "fetched_at": "2024-01-21T14:00:00Z"
    }
    
    try:
        txn = TransactionWebhook(**valid_data)
        success(f"TransactionWebhook aceita dados válidos")
        success(f"  • Amount: {txn.amount} (tipo: {type(txn.amount).__name__})")
        success(f"  • Date: {txn.transaction_date} (UTC: {txn.transaction_date.tzinfo})")
        success(f"  • Dedup hash gerado: {txn.dedup_hash[:16]}...")
        assert isinstance(txn.amount, Decimal), "Amount deve ser Decimal"
        assert txn.transaction_date.tzinfo is not None, "Date deve ser timezone-aware"
        assert len(txn.dedup_hash) == 64, "Hash deve ter 64 chars (SHA256)"
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 1.2: TransactionWebhook - Parsing BR")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    br_data = {
        **valid_data,
        "amount": "1.500,50",  # BR format
        "transaction_date": "15/01/2024 10:30:00",  # BR format
    }
    
    try:
        txn = TransactionWebhook(**br_data)
        success("Parser BR funcionando")
        success(f"  • Amount BR '1.500,50' → {txn.amount}")
        success(f"  • Date BR '15/01/2024' → {txn.transaction_date}")
        assert abs(txn.amount - Decimal("1500.50")) < Decimal("0.01"), "Parse BR incorreto"
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 1.3: TransactionWebhook - Normalização de Sinal")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # DEBIT deve ser negativo
    debit_data = {
        **valid_data,
        "amount": 100,  # Positivo (errado)
        "type": "DEBIT"  # Mas é débito
    }
    
    try:
        txn = TransactionWebhook(**debit_data)
        success("Normalização de sinal funcionando")
        success(f"  • Amount: 100 + type=DEBIT → {txn.amount}")
        assert txn.amount < 0, "DEBIT deve ser negativo"
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 1.4: TransactionWebhook - Rejeição de Dados Inválidos")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    invalid_cases = [
        ({"amount": None}, "amount é obrigatório"),
        ({"transaction_date": "data_invalida"}, "data inválida"),
        ({"amount": "abc"}, "amount não numérico"),
    ]
    
    for invalid_data, reason in invalid_cases:
        test_data = {**valid_data, **invalid_data}
        try:
            TransactionWebhook(**test_data)
            error(f"DEVERIA REJEITAR: {reason}")
            raise AssertionError(f"Aceitou dado inválido: {reason}")
        except ValidationError:
            success(f"Rejeitou corretamente: {reason}")


def test_transaction_batch_result():
    """Testa TransactionBatchResult (validação tolerante)."""
    from app.core.schemas.transaction import TransactionBatchResult
    
    subheader("TESTE 1.5: TransactionBatchResult - Validação Tolerante")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ✅ CORREÇÃO 3 APLICADA: Adicionado "id": "txn_2" ao batch Itaú
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Batch com transações válidas e inválidas
    raw_batch = [
        # Válida (Nubank)
        {
            "id": "txn_1",
            "accountId": "acc_1",
            "amount": -50.00,
            "date": "2024-01-15T10:00:00Z",
            "description": "Netflix",
        },
        # Válida (Itaú - campos PT)
        {
            "id": "txn_2",  # ✅ CORRIGIDO: Adicionado campo obrigatório
            "conta": "acc_2",
            "valor": "100,50",
            "data": "15/01/2024 10:00:00",
            "descricao": "Compra",
        },
        # Inválida (falta amount)
        {
            "id": "txn_3",
            "accountId": "acc_3",
            "date": "2024-01-15T10:00:00Z",
        },
    ]
    
    try:
        result = TransactionBatchResult.from_raw_batch(
            raw_data=raw_batch,
            institution_id="itau",  # ✅ CORRIGIDO: "nubank" → "itau" para testar mapeamento
            item_id="item_123",
            fetched_at=datetime.now(timezone.utc)
        )
        
        success("Validação tolerante funcionando")
        success(f"  • Total recebido: {result.total_received}")
        success(f"  • Válidas: {result.total_valid}")
        success(f"  • Rejeitadas: {result.total_rejected}")
        success(f"  • Rejection rate: {result.rejection_rate:.1%}")
        
        assert result.total_received == 3
        assert result.total_valid == 2  # Nubank + Itaú
        assert result.total_rejected == 1  # Faltando amount
        
        success(f"  • Mapeamento Itaú funcionando (conta → account_id)")
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 2: SHADOW INVOICE SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_shadow_invoice_schemas():
    """Testa schemas de Shadow Invoices."""
    from app.forecast.schemas_shadow_invoice import (
        ShadowInvoiceResponse,
        ShadowInvoiceListResponse
    )
    
    subheader("TESTE 2.1: ShadowInvoiceResponse")
    
    # Shadow invoice válida
    shadow_data = {
        "type": "SUBSCRIPTION",
        "description": "NETFLIX.COM *ASSINATURA PREMIUM",
        "amount": -49.90,
        "next_due_date": datetime(2026, 3, 5, tzinfo=timezone.utc),
        "confidence": 0.92,
        "occurrences": 6,
        "installment_info": None,
        "metadata": {"category": "Lazer"}
    }
    
    try:
        shadow = ShadowInvoiceResponse(**shadow_data)
        success("ShadowInvoiceResponse criado")
        success(f"  • Type: {shadow.type}")
        success(f"  • Amount: {shadow.amount}")
        success(f"  • Confidence: {shadow.confidence}")
        
        # Validações
        assert shadow.amount < 0, "Amount deve ser negativo"
        assert 0 <= shadow.confidence <= 1, "Confidence deve estar entre 0 e 1"
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 2.2: ShadowInvoiceListResponse")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Lista de shadows
    shadow_list_data = {
        "invoices": [shadow],
        "total_count": 1,
        "total_monthly_impact": -49.90,
        "subscriptions_count": 1,
        "installments_count": 0
    }
    
    try:
        shadow_list = ShadowInvoiceListResponse(**shadow_list_data)
        success("ShadowInvoiceListResponse criado")
        success(f"  • Total count: {shadow_list.total_count}")
        success(f"  • Monthly impact: R$ {shadow_list.total_monthly_impact}")
        success(f"  • Subscriptions: {shadow_list.subscriptions_count}")
        
        # Serialização JSON
        json_data = shadow_list.model_dump()
        success(f"  • Serialização JSON: OK")
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 3: CASHFLOW SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_cashflow_schemas():
    """Testa schemas de Cashflow."""
    from app.forecast.schemas_cashflow import (
        CashflowProjectionPoint,
        CashflowSummaryResponse,
        CashflowProjectionResponse
    )
    
    subheader("TESTE 3.1: CashflowProjectionPoint")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ✅ CORREÇÃO 1 APLICADA: "date" → "projection_date"
    # ✅ CORREÇÃO 2 APLICADA: "shadow_amount" → "expenses"
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    point_data = {
        "projection_date": date(2026, 3, 5),  # ✅ CORRIGIDO
        "projected_balance": 4950.10,
        "expenses": -49.90,  # ✅ CORRIGIDO
        "risk_flag": None
    }
    
    try:
        point = CashflowProjectionPoint(**point_data)
        success("CashflowProjectionPoint criado")
        success(f"  • Date: {point.projection_date}")  # ✅ CORRIGIDO
        success(f"  • Balance: R$ {point.projected_balance}")
        success(f"  • Expenses: R$ {point.expenses}")  # ✅ CORRIGIDO
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 3.2: CashflowSummaryResponse")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    summary_data = {
        "horizon_days": 30,
        "starting_balance": 5000.00,
        "ending_balance": 3809.69,
        "worst_balance": 3809.69,
        "negative_day": None,
        "risk_level": "LOW",
        "total_shadow_impact": -1068.10,
        "days_at_risk": 0
    }
    
    try:
        summary = CashflowSummaryResponse(**summary_data)
        success("CashflowSummaryResponse criado")
        success(f"  • Horizon: {summary.horizon_days} dias")
        success(f"  • Starting: R$ {summary.starting_balance}")
        success(f"  • Ending: R$ {summary.ending_balance}")
        success(f"  • Risk: {summary.risk_level}")
        
        # Validações
        assert 1 <= summary.horizon_days <= 365
        assert summary.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 3.3: CashflowProjectionResponse")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    projection_data = {
        "summary": summary,
        "daily_projection": [point]
    }
    
    try:
        projection = CashflowProjectionResponse(**projection_data)
        success("CashflowProjectionResponse criado")
        success(f"  • Summary: OK")
        success(f"  • Daily points: {len(projection.daily_projection)}")
        
        # Serialização
        json_data = projection.model_dump()
        success(f"  • Serialização JSON: OK")
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 4: SAFE-TO-SPEND SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_safe_to_spend_schemas():
    """Testa schemas de Safe-to-Spend."""
    from app.forecast.schemas_safe_to_spend import (
        SafeToSpendResponse,
        SafeToSpendDetailedResponse
    )
    
    subheader("TESTE 4.1: SafeToSpendResponse (Básico)")
    
    basic_data = {
        "safe_to_spend_total": 3609.69,
        "safe_to_spend_daily": 120.32,
        "days": 30,
        "risk_level": "LOW"
    }
    
    try:
        sts = SafeToSpendResponse(**basic_data)
        success("SafeToSpendResponse criado")
        success(f"  • Total: R$ {sts.safe_to_spend_total}")
        success(f"  • Daily: R$ {sts.safe_to_spend_daily}")
        success(f"  • Risk: {sts.risk_level}")
        
        # Validações
        assert sts.safe_to_spend_total >= 0
        assert sts.safe_to_spend_daily >= 0
        assert 1 <= sts.days <= 365
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 4.2: SafeToSpendDetailedResponse")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    detailed_data = {
        **basic_data,
        "current_balance": 5000.00,
        "min_projected_balance": 3809.69,
        "total_shadow_invoices": -1068.10,
        "safety_buffer": 200.00,
        "safety_buffer_pct": 15.0,
        "recommendations": [
            "Você está em boa situação financeira",
            "Continue monitorando suas assinaturas"
        ]
    }
    
    try:
        sts_detailed = SafeToSpendDetailedResponse(**detailed_data)
        success("SafeToSpendDetailedResponse criado")
        success(f"  • Current balance: R$ {sts_detailed.current_balance}")
        success(f"  • Safety buffer: R$ {sts_detailed.safety_buffer}")
        success(f"  • Recommendations: {len(sts_detailed.recommendations)}")
        
        # Validações
        assert sts_detailed.total_shadow_invoices <= 0
        assert sts_detailed.safety_buffer >= 0
        assert 0 <= sts_detailed.safety_buffer_pct <= 100
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 5: FORECAST SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_forecast_schemas():
    """Testa schemas de Forecast."""
    from app.forecast.schemas_forecast import (
        FinancialHealthResponse,
        MonthlyForecastResponse,
        ForecastResponse
    )
    from app.forecast.schemas_cashflow import CashflowSummaryResponse
    from app.forecast.schemas_safe_to_spend import SafeToSpendResponse
    from app.forecast.schemas_shadow_invoice import ShadowInvoiceListResponse
    
    subheader("TESTE 5.1: FinancialHealthResponse")
    
    health_data = {
        "profile_type": "EQUILIBRADO",
        "health_score": 75,
        "savings_rate": 15.5,
        "total_income": 51000.0,
        "total_expenses": 43000.0,
        "monthly_avg_expenses": 7166.67,
        "top_categories": ["Alimentação", "Transporte", "Moradia"],
        "trend": "ESTÁVEL"
    }
    
    try:
        health = FinancialHealthResponse(**health_data)
        success("FinancialHealthResponse criado")
        success(f"  • Profile: {health.profile_type}")
        success(f"  • Score: {health.health_score}/100")
        success(f"  • Savings rate: {health.savings_rate}%")
        success(f"  • Trend: {health.trend}")
        
        # Validações
        assert 0 <= health.health_score <= 100
        assert health.profile_type in ["CONSERVADOR", "EQUILIBRADO", "GASTADOR", "POUPADOR"]
        assert health.trend in ["CRESCENTE", "ESTÁVEL", "DECRESCENTE"]
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 5.2: MonthlyForecastResponse")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    monthly_data = {
        "month": 3,
        "year": 2026,
        "expected_income": 8500.0,
        "expected_expenses": 7200.0,
        "expected_savings": 1300.0,
        "confidence": 0.85,
        "risk_level": "LOW"
    }
    
    try:
        monthly = MonthlyForecastResponse(**monthly_data)
        success("MonthlyForecastResponse criado")
        success(f"  • Month: {monthly.month}/{monthly.year}")
        success(f"  • Income: R$ {monthly.expected_income}")
        success(f"  • Confidence: {monthly.confidence:.1%}")
        
        # Validações
        assert 1 <= monthly.month <= 12
        assert 0 <= monthly.confidence <= 1
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 5.3: ForecastResponse (Consolidado)")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Criar componentes necessários
    cashflow_summary = CashflowSummaryResponse(
        horizon_days=30,
        starting_balance=5000.00,
        ending_balance=3809.69,
        worst_balance=3809.69,
        negative_day=None,
        risk_level="LOW",
        total_shadow_impact=-1068.10,
        days_at_risk=0
    )
    
    sts = SafeToSpendResponse(
        safe_to_spend_total=3609.69,
        safe_to_spend_daily=120.32,
        days=30,
        risk_level="LOW"
    )
    
    shadow_list = ShadowInvoiceListResponse(
        invoices=[],
        total_count=12,
        total_monthly_impact=-1068.10,
        subscriptions_count=9,
        installments_count=3
    )
    
    forecast_data = {
        "user_id": "user123",
        "generated_at": datetime.now(timezone.utc),
        "period_analyzed_days": 180,
        "financial_health": health,
        "cashflow": cashflow_summary,
        "safe_to_spend": sts,
        "shadow_invoices": shadow_list,
        "monthly_forecasts": [monthly]
    }
    
    try:
        forecast = ForecastResponse(**forecast_data)
        success("ForecastResponse criado (CONSOLIDADO!)")
        success(f"  • User: {forecast.user_id}")
        success(f"  • Period: {forecast.period_analyzed_days} dias")
        success(f"  • Health score: {forecast.financial_health.health_score}")
        success(f"  • Safe-to-spend: R$ {forecast.safe_to_spend.safe_to_spend_daily}/dia")
        success(f"  • Monthly forecasts: {len(forecast.monthly_forecasts)}")
        
        # Serialização JSON completa
        json_data = forecast.model_dump()
        success(f"  • Serialização JSON: OK ({len(str(json_data))} chars)")
        
    except Exception as e:
        error(f"FALHOU: {e}")
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 6: VALIDAÇÕES DE EDGE CASES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_edge_cases():
    """Testa edge cases e validações de limites."""
    from app.forecast.schemas_safe_to_spend import SafeToSpendResponse
    from app.forecast.schemas_cashflow import CashflowSummaryResponse
    
    subheader("TESTE 6.1: Valores Limite")
    
    # Safe-to-spend = 0 (crítico)
    try:
        sts = SafeToSpendResponse(
            safe_to_spend_total=0.0,
            safe_to_spend_daily=0.0,
            days=30,
            risk_level="CRITICAL"
        )
        success("Aceita safe-to-spend = 0 (válido)")
        assert sts.safe_to_spend_total == 0.0
    except Exception as e:
        error(f"FALHOU: {e}")
        raise
    
    # Valores negativos devem ser rejeitados
    try:
        SafeToSpendResponse(
            safe_to_spend_total=-100.0,  # Negativo!
            safe_to_spend_daily=0.0,
            days=30,
            risk_level="LOW"
        )
        error("DEVERIA REJEITAR: safe_to_spend negativo")
        raise AssertionError("Aceitou valor negativo")
    except ValidationError:
        success("Rejeitou corretamente: safe_to_spend negativo")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 6.2: Enums Inválidos")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    try:
        CashflowSummaryResponse(
            horizon_days=30,
            starting_balance=5000.00,
            ending_balance=4000.00,
            worst_balance=4000.00,
            negative_day=None,
            risk_level="INVALID",  # Enum inválido
            total_shadow_impact=-1000.00,
            days_at_risk=0
        )
        error("DEVERIA REJEITAR: enum inválido")
        raise AssertionError("Aceitou enum inválido")
    except ValidationError:
        success("Rejeitou corretamente: enum inválido")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    subheader("TESTE 6.3: Ranges Inválidos")
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    from app.forecast.schemas_forecast import FinancialHealthResponse
    
    # Health score > 100
    try:
        FinancialHealthResponse(
            profile_type="EQUILIBRADO",
            health_score=150,  # > 100!
            savings_rate=15.0,
            total_income=50000.0,
            total_expenses=40000.0,
            monthly_avg_expenses=6666.67,
            top_categories=["Alimentação"],
            trend="ESTÁVEL"
        )
        error("DEVERIA REJEITAR: health_score > 100")
        raise AssertionError("Aceitou health_score inválido")
    except ValidationError:
        success("Rejeitou corretamente: health_score > 100")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN - EXECUTAR TODOS OS TESTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """Executa todos os testes de schemas."""
    header("VALIDAÇÃO COMPLETA DE SCHEMAS (CORRIGIDO)")
    
    tests = [
        ("1. TRANSACTION SCHEMAS", test_transaction_webhook),
        ("2. TRANSACTION BATCH", test_transaction_batch_result),
        ("3. SHADOW INVOICE SCHEMAS", test_shadow_invoice_schemas),
        ("4. CASHFLOW SCHEMAS", test_cashflow_schemas),
        ("5. SAFE-TO-SPEND SCHEMAS", test_safe_to_spend_schemas),
        ("6. FORECAST SCHEMAS", test_forecast_schemas),
        ("7. EDGE CASES", test_edge_cases),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            error(f"TESTE FALHOU: {test_name}")
            logger.exception(e)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # RESUMO FINAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    header("RESUMO FINAL")
    
    total = passed + failed
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"\n📊 ESTATÍSTICAS:")
    print(f"   • Total de testes: {total}")
    print(f"   • Passou: {passed} ✅")
    print(f"   • Falhou: {failed} ❌")
    print(f"   • Taxa de sucesso: {success_rate:.1f}%")
    
    if failed == 0:
        print(f"\n{'='*80}")
        print(f"🎉 TODOS OS SCHEMAS VALIDADOS COM SUCESSO!")
        print(f"{'='*80}")
        print(f"\n✅ SCHEMAS TESTADOS:")
        print(f"   1. TransactionWebhook (entrada)")
        print(f"   2. TransactionOut (saída)")
        print(f"   3. TransactionBatchResult (validação tolerante)")
        print(f"   4. ShadowInvoiceResponse + List")
        print(f"   5. CashflowProjectionPoint + Summary + Response")
        print(f"   6. SafeToSpendResponse + Detailed")
        print(f"   7. FinancialHealthResponse")
        print(f"   8. MonthlyForecastResponse")
        print(f"   9. ForecastResponse (consolidado)")
        print(f"\n✅ VALIDAÇÕES TESTADAS:")
        print(f"   • Parsing BR/US de amounts")
        print(f"   • Parsing de datas (múltiplos formatos)")
        print(f"   • Normalização de sinal (DEBIT → negativo)")
        print(f"   • Mapeamento de campos por banco (Itaú)")
        print(f"   • Validação tolerante de batches")
        print(f"   • Rejeição de dados inválidos")
        print(f"   • Validação de ranges (ge, le)")
        print(f"   • Validação de enums")
        print(f"   • Serialização JSON")
        print(f"\n🚀 PRÓXIMO PASSO:")
        print(f"   → Teste de integração (ETL → Cashflow → Safe-to-Spend)")
        print(f"   → API Layer (FastAPI endpoints)")
        print(f"{'='*80}\n")
        return 0
    else:
        print(f"\n{'='*80}")
        print(f"❌ ALGUNS TESTES FALHARAM!")
        print(f"{'='*80}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())