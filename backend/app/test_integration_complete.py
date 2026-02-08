"""
test_integration_intelligence_only.py - Teste de Integração (APENAS INTELIGÊNCIA)

OBJETIVO:
    Validar TODA a INTELIGÊNCIA do sistema (SEM persistência DuckDB):
    
    ✅ Schemas Pydantic (TransactionWebhook + validações)
    ✅ ETL Pipeline (Classifier + BankStrategy)
    ✅ Shadow Invoices (Subscription + Installment Detectors)
    ✅ Cashflow (CashflowProjector)
    ✅ Safe-to-Spend (SafeToSpendCalculator)
    ✅ Domain Engines (FinanceEngine + SafeToSpendEngine)

REMOVIDO:
    ❌ TransactionIngestor (depende de DuckDB)
    ❌ Persistência em banco de dados

FOCO:
    🧠 Validar que a MATEMÁTICA, DETECÇÃO e PROJEÇÃO funcionam 100%

EXECUÇÃO:
    cd backend/app
    python test_integration_intelligence_only.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SETUP PATH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

project_root = Path(__file__).parent.parent.parent
backend_path = project_root / "backend"

if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
    print(f"✅ Python path: {backend_path}\n")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS (TODOS OS MÓDULOS DE INTELIGÊNCIA)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import polars as pl
from pydantic import ValidationError

# Schemas
from app.schemas.transaction import TransactionWebhook, TransactionBatchResult
from app.schemas.enums import TransactionType, DataStatus

# ETL (SEM Ingestor - depende de DuckDB)
from app.etl.classifier import TransactionClassifier
from app.etl.bank_strategy import get_bank_strategy
from app.etl.shadow_invoices import run_shadow_invoice_detection

# Cashflow
from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendCalculator

# Domain Engines
from app.domain.finance_engine import FinanceEngine
from app.domain.safe_to_spend_engine import SafeToSpendEngine


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES PARA MÉTRICAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class TestMetrics:
    """Métricas de um teste individual."""
    test_name: str
    passed: bool
    duration_ms: float
    assertions_passed: int
    assertions_failed: int
    details: Dict[str, Any]
    
    def to_dict(self):
        return asdict(self)


@dataclass
class IntegrationReport:
    """Relatório completo da integração."""
    total_tests: int
    passed_tests: int
    failed_tests: int
    total_duration_ms: float
    test_metrics: List[TestMetrics]
    
    def success_rate(self):
        return self.passed_tests / self.total_tests if self.total_tests > 0 else 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BASELINES ESPERADOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BASELINE = {
    "total_transactions": 250,
    "min_subscriptions": 5,
    "min_installments": 1,      # ✅ Detector pega apenas 1 parcelamento
    "cashflow_days": 30,
    "min_safe_to_spend": 0,
    "max_rejection_rate": 0.02,  # ✅ 2% (4 inválidas em ~287 total)
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GERADOR DE DADOS DE TESTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_test_transactions(months: int = 12) -> List[Dict[str, Any]]:
    """Cria dataset de teste com 12 meses de transações."""
    base_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    transactions = []
    
    # Salário mensal
    for month in range(months):
        date = base_date + timedelta(days=30 * month + 5)
        transactions.append({
            "transaction_id": f"sal_{month}",
            "account_id": "acc_001",
            "institution_id": "nubank",
            "item_id": "item_nubank_001",
            "amount": "8500.00",
            "transaction_date": date,
            "description": "SALARIO EMPRESA XYZ LTDA",
            "balance": None,
            "type": "CREDIT",
            "source": "PLUGGY",
            "fetched_at": datetime.now(timezone.utc)
        })
    
    # Assinaturas recorrentes
    subscriptions = [
        ("netflix", "NETFLIX.COM *ASSINATURA PREMIUM", -49.90, 10),
        ("spotify", "SPOTIFY *PREMIUM FAMILIAR", -21.90, 12),
        ("prime", "AMAZON PRIME *ASSINATURA", -14.90, 15),
        ("youtube", "YOUTUBE PREMIUM", -20.90, 8),
        ("icloud", "APPLE.COM/BILL ICLOUD 50GB", -3.90, 20),
    ]
    
    for month in range(months):
        for sub_id, desc, amount, day in subscriptions:
            date = base_date + timedelta(days=30 * month + day)
            transactions.append({
                "transaction_id": f"{sub_id}_{month}",
                "account_id": "acc_001",
                "institution_id": "nubank",
                "item_id": "item_nubank_001",
                "amount": str(amount),
                "transaction_date": date,
                "description": desc,
                "balance": None,
                "type": "DEBIT",
                "source": "PLUGGY",
                "fetched_at": datetime.now(timezone.utc)
            })
    
    # Parcelamentos
    for i in range(min(12, months)):
        date = base_date + timedelta(days=30 * i + 10)
        transactions.append({
            "transaction_id": f"celular_{i+1}",
            "account_id": "acc_001",
            "institution_id": "nubank",
            "item_id": "item_nubank_001",
            "amount": "-120.00",
            "transaction_date": date,
            "description": f"COMPRA PARCELADA {i+1:02d}/12 SAMSUNG GALAXY",
            "balance": None,
            "type": "DEBIT",
            "installment_number": i+1,
            "installment_total": 12,
            "source": "PLUGGY",
            "fetched_at": datetime.now(timezone.utc)
        })
    
    # Contas fixas
    fixed_expenses = [
        ("aluguel", "ALUGUEL APTO CENTRO", -1500.00, 1),
        ("condominio", "CONDOMINIO EDIFICIO PARQUE", -350.00, 1),
        ("luz", "ENEL ENERGIA ELETRICA", -180.00, 5),
        ("internet", "VIVO FIBRA 300MB", -99.90, 8),
    ]
    
    for month in range(months):
        for exp_id, desc, amount, day in fixed_expenses:
            date = base_date + timedelta(days=30 * month + day)
            transactions.append({
                "transaction_id": f"{exp_id}_{month}",
                "account_id": "acc_001",
                "institution_id": "nubank",
                "item_id": "item_nubank_001",
                "amount": str(amount),
                "transaction_date": date,
                "description": desc,
                "balance": None,
                "type": "DEBIT",
                "source": "PLUGGY",
                "fetched_at": datetime.now(timezone.utc)
            })
    
    # Gastos variáveis
    import random
    random.seed(42)
    
    variable_expenses = [
        ("UBER *TRIP", -25.00),
        ("IFOOD *DELIVERY", -45.00),
        ("MERCADO EXTRA", -320.00),
        ("POSTO SHELL", -250.00),
        ("FARMACIA DROGASIL", -80.00),
    ]
    
    for month in range(months):
        for i in range(random.randint(10, 15)):
            desc, base_amount = random.choice(variable_expenses)
            amount = base_amount * random.uniform(0.8, 1.2)
            day = random.randint(1, 28)
            date = base_date + timedelta(days=30 * month + day)
            transactions.append({
                "transaction_id": f"var_{month}_{i}",
                "account_id": "acc_001",
                "institution_id": "nubank",
                "item_id": "item_nubank_001",
                "amount": f"{amount:.2f}",
                "transaction_date": date,
                "description": desc,
                "balance": None,
                "type": "DEBIT",
                "source": "PLUGGY",
                "fetched_at": datetime.now(timezone.utc)
            })
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. DADOS INVÁLIDOS (para testar rejeição Pydantic)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Transação sem amount (obrigatório)
    transactions.append({
        "transaction_id": "invalid_1",
        "account_id": "acc_001",
        "institution_id": "nubank",
        "item_id": "item_nubank_001",
        # amount: None,  # ❌ FALTANDO (obrigatório)
        "transaction_date": base_date + timedelta(days=1),
        "description": "TRANSACAO SEM AMOUNT",
        "balance": None,
        "type": "DEBIT",
        "source": "PLUGGY",
        "fetched_at": datetime.now(timezone.utc)
    })
    
    # Transação com amount inválido (string não numérica)
    transactions.append({
        "transaction_id": "invalid_2",
        "account_id": "acc_001",
        "institution_id": "nubank",
        "item_id": "item_nubank_001",
        "amount": "abc123",  # ❌ Não numérico
        "transaction_date": base_date + timedelta(days=2),
        "description": "AMOUNT INVALIDO",
        "balance": None,
        "type": "DEBIT",
        "source": "PLUGGY",
        "fetched_at": datetime.now(timezone.utc)
    })
    
    # Transação com data inválida
    transactions.append({
        "transaction_id": "invalid_3",
        "account_id": "acc_001",
        "institution_id": "nubank",
        "item_id": "item_nubank_001",
        "amount": "-50.00",
        "transaction_date": "data_invalida_xyz",  # ❌ Formato inválido
        "description": "DATA INVALIDA",
        "balance": None,
        "type": "DEBIT",
        "source": "PLUGGY",
        "fetched_at": datetime.now(timezone.utc)
    })
    
    # Transação sem transaction_id (obrigatório)
    transactions.append({
        # transaction_id: None,  # ❌ FALTANDO (obrigatório)
        "account_id": "acc_001",
        "institution_id": "nubank",
        "item_id": "item_nubank_001",
        "amount": "-30.00",
        "transaction_date": base_date + timedelta(days=3),
        "description": "SEM TRANSACTION_ID",
        "balance": None,
        "type": "DEBIT",
        "source": "PLUGGY",
        "fetched_at": datetime.now(timezone.utc)
    })
    
    return sorted(
        transactions, 
        key=lambda x: x.get("transaction_date", base_date) 
        if isinstance(x.get("transaction_date"), datetime) 
        else base_date
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_header(title: str):
    print("\n" + "="*80)
    print(f"🧪 {title}")
    print("="*80)

def print_subheader(title: str):
    print(f"\n▶ {title}")
    print("-" * 80)

def print_metric(label: str, value: Any, unit: str = ""):
    print(f"   ✅ {label}: {value}{unit}")

def print_ascii_bar(label: str, value: float, max_value: float, width: int = 40):
    pct = min(value / max_value, 1.0) if max_value > 0 else 0
    bar_length = int(pct * width)
    bar = "█" * bar_length + "░" * (width - bar_length)
    print(f"   {label:30s} {bar} {pct*100:5.1f}%")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 1: PYDANTIC VALIDATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_1_pydantic_validation() -> Tuple[List[TransactionWebhook], TestMetrics]:
    """Valida schemas Pydantic."""
    print_header("TESTE 1: VALIDAÇÃO PYDANTIC (TransactionWebhook)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        raw_data = create_test_transactions(months=12)
        validated = []
        rejected = []
        
        for raw in raw_data:
            try:
                txn = TransactionWebhook(**raw)
                validated.append(txn)
            except ValidationError as e:
                rejected.append(raw)
                # Debug: mostrar primeira rejeitada
                if len(rejected) == 1:
                    print(f"\n   ⚠️ Exemplo de rejeição:")
                    print(f"      ID: {raw.get('transaction_id', 'N/A')}")
                    print(f"      Erro: {str(e).split('\n')[0][:80]}...")
        
        print_metric("Validadas", f"{len(validated)}/{len(raw_data)}")
        print_metric("Rejeitadas", f"{len(rejected)}/{len(raw_data)}")
        
        # Assertions
        if len(rejected) / len(raw_data) <= BASELINE["max_rejection_rate"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        debits = [t for t in validated if t.type == "DEBIT"]
        credits = [t for t in validated if t.type == "CREDIT"]
        
        if all(t.amount < 0 for t in debits) and all(t.amount > 0 for t in credits):
            assertions_passed += 1
            print_metric("Normalização de sinal", "OK ✅")
        else:
            assertions_failed += 1
        
        if len(validated) >= BASELINE["total_transactions"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_1_pydantic_validation",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details={"validated": len(validated), "rejected": len(rejected)}
        )
        
        print_metric("Tempo execução", f"{duration_ms:.2f}", " ms")
        print(f"\n{'✅' if metrics.passed else '❌'} TESTE 1: {'PASSOU' if metrics.passed else 'FALHOU'}")
        
        return validated, metrics
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        metrics = TestMetrics(
            test_name="test_1_pydantic_validation",
            passed=False,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed + 1,
            details={"error": str(e)}
        )
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 2: ETL PIPELINE (SEM INGESTOR)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_2_etl_pipeline(validated_transactions: List[TransactionWebhook]) -> Tuple[pl.DataFrame, TestMetrics]:
    """Valida Pipeline ETL (BankStrategy + Classifier)."""
    print_header("TESTE 2: PIPELINE ETL (BankStrategy + Classifier)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        # Converter para Polars DataFrame manualmente (SEM Ingestor)
        print_subheader("STEP 1: Converter para DataFrame")
        
        data_list = []
        for txn in validated_transactions:
            data_list.append({
                "transaction_id": txn.transaction_id,
                "account_id": txn.account_id,
                "institution_id": txn.institution_id,
                "item_id": txn.item_id,
                "amount": float(txn.amount),
                "transaction_date": txn.transaction_date,
                "description": txn.description,
                "merchant_clean": txn.description.split()[0][:30],  # Simplificado
                "type": txn.type,
                "category": None,
                "predicted_category": None,
                "data_status": "TRUSTED",
                "dedup_hash": txn.dedup_hash,
            })
        
        df_clean = pl.DataFrame(data_list)
        
        print_metric("DataFrame criado", f"{df_clean.height} linhas")
        
        # BankStrategy
        print_subheader("STEP 2: BankStrategy (Nubank)")
        
        strategy = get_bank_strategy("nubank")
        details["bank_strategy"] = strategy.__class__.__name__
        details["bank_tier"] = strategy.tier.value
        
        print_metric("Strategy", strategy.__class__.__name__)
        print_metric("Tier", strategy.tier.value)
        
        if strategy.tier.value == "TIER_1":
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # Classifier
        print_subheader("STEP 3: TransactionClassifier")
        
        classifier = TransactionClassifier(mode="RULES")
        df_categorized = classifier.predict(df_clean)
        
        categories = (
            df_categorized
            .group_by("predicted_category")
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
        )
        
        print("\n   📊 Distribuição de Categorias:")
        for row in categories.iter_rows(named=True):
            print_ascii_bar(
                row["predicted_category"],
                row["count"],
                df_categorized.height
            )
        
        if len(categories) >= 3:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        assert df_categorized.height > 0
        assert "predicted_category" in df_categorized.columns
        assertions_passed += 2
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_2_etl_pipeline",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details={"categories": len(categories)}
        )
        
        print_metric("Tempo execução", f"{duration_ms:.2f}", " ms")
        print(f"\n{'✅' if metrics.passed else '❌'} TESTE 2: {'PASSOU' if metrics.passed else 'FALHOU'}")
        
        return df_categorized, metrics
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        metrics = TestMetrics(
            test_name="test_2_etl_pipeline",
            passed=False,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed + 1,
            details={"error": str(e)}
        )
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 3: SHADOW INVOICES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_3_shadow_invoices(df_categorized: pl.DataFrame) -> Tuple[pl.DataFrame, TestMetrics]:
    """Valida Shadow Invoices."""
    print_header("TESTE 3: SHADOW INVOICES (Subscription + Installment)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        shadow_df = run_shadow_invoice_detection(df_categorized)
        
        if shadow_df.is_empty():
            print("\n⚠️ Nenhuma shadow invoice detectada!")
            assertions_failed += 1
            return pl.DataFrame(), TestMetrics(
                test_name="test_3_shadow_invoices",
                passed=False,
                duration_ms=(time.time() - start_time) * 1000,
                assertions_passed=0,
                assertions_failed=1,
                details={"error": "Nenhuma shadow detectada"}
            )
        
        subscriptions = shadow_df.filter(pl.col("type") == "SUBSCRIPTION")
        installments = shadow_df.filter(pl.col("type") == "INSTALLMENT")
        
        print_metric("Total detectado", shadow_df.height)
        print_metric("Assinaturas", subscriptions.height)
        print_metric("Parcelamentos", installments.height)
        
        if subscriptions.height >= BASELINE["min_subscriptions"]:
            assertions_passed += 1
            print(f"   ✅ Assinaturas: {subscriptions.height} >= {BASELINE['min_subscriptions']}")
        else:
            assertions_failed += 1
        
        if installments.height >= BASELINE["min_installments"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        if subscriptions.height > 0:
            print(f"\n   🔁 Assinaturas:")
            for row in subscriptions.head(5).iter_rows(named=True):
                print(f"      • {row['metadata']['description']}: R$ {row['amount']:.2f}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_3_shadow_invoices",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details={"subscriptions": subscriptions.height, "installments": installments.height}
        )
        
        print_metric("Tempo execução", f"{duration_ms:.2f}", " ms")
        print(f"\n{'✅' if metrics.passed else '❌'} TESTE 3: {'PASSOU' if metrics.passed else 'FALHOU'}")
        
        return shadow_df, metrics
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        metrics = TestMetrics(
            test_name="test_3_shadow_invoices",
            passed=False,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed + 1,
            details={"error": str(e)}
        )
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 4: CASHFLOW PROJECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_4_cashflow_projection(df_categorized: pl.DataFrame, shadow_df: pl.DataFrame) -> Tuple[pl.DataFrame, Any, TestMetrics]:
    """Valida Cashflow Projector."""
    print_header("TESTE 4: PROJEÇÃO DE CASHFLOW (CashflowProjector)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    
    try:
        # Calcular saldo
        df_with_balance = df_categorized.sort("transaction_date")
        df_with_balance = df_with_balance.with_columns(
            pl.col("amount").cum_sum().alias("balance")
        )
        
        starting_balance = 5000.0
        df_with_balance = df_with_balance.with_columns(
            (pl.col("balance") + starting_balance).alias("balance")
        )
        
        # Projetar
        projector = CashflowProjector(horizon_days=30)
        projection_df = projector.project(
            transactions_df=df_with_balance,
            shadow_invoices_df=shadow_df
        )
        
        last_balance = float(df_with_balance["balance"][-1])
        summary = projector.get_summary(projection_df, last_balance)
        
        print(f"\n📊 Resumo:")
        print_metric("Período", f"{summary.horizon_days} dias")
        print_metric("Saldo inicial", f"R$ {summary.starting_balance:,.2f}")
        print_metric("Saldo final", f"R$ {summary.ending_balance:,.2f}")
        print_metric("Risk level", summary.risk_level)
        print_metric("Shadow impact", f"R$ {summary.total_shadow_impact:,.2f}")
        
        if projection_df.height == BASELINE["cashflow_days"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        if summary.total_shadow_impact < 0:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_4_cashflow_projection",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details={"horizon_days": summary.horizon_days}
        )
        
        print_metric("Tempo execução", f"{duration_ms:.2f}", " ms")
        print(f"\n{'✅' if metrics.passed else '❌'} TESTE 4: {'PASSOU' if metrics.passed else 'FALHOU'}")
        
        return projection_df, summary, metrics
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        metrics = TestMetrics(
            test_name="test_4_cashflow_projection",
            passed=False,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed + 1,
            details={"error": str(e)}
        )
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 5: SAFE-TO-SPEND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_5_safe_to_spend(projection_df: pl.DataFrame) -> Tuple[Any, TestMetrics]:
    """Valida Safe-to-Spend Calculator."""
    print_header("TESTE 5: SAFE-TO-SPEND (SafeToSpendCalculator)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    
    try:
        calculator = SafeToSpendCalculator(safety_buffer_pct=0.15)
        result = calculator.calculate(projection_df, horizon_days=30)
        
        print(f"\n💰 Resultado:")
        print_metric("Safe-to-spend total", f"R$ {result.safe_to_spend_total:,.2f}")
        print_metric("Safe-to-spend diário", f"R$ {result.safe_to_spend_daily:,.2f}")
        print_metric("Risk level", result.risk_level)
        print_metric("Buffer", f"R$ {result.safety_buffer:,.2f}")
        
        if result.safe_to_spend_total >= BASELINE["min_safe_to_spend"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        if result.safety_buffer > 0:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        if result.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_5_safe_to_spend",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details={"safe_to_spend_daily": result.safe_to_spend_daily}
        )
        
        print_metric("Tempo execução", f"{duration_ms:.2f}", " ms")
        print(f"\n{'✅' if metrics.passed else '❌'} TESTE 5: {'PASSOU' if metrics.passed else 'FALHOU'}")
        
        return result, metrics
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        metrics = TestMetrics(
            test_name="test_5_safe_to_spend",
            passed=False,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed + 1,
            details={"error": str(e)}
        )
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 6: DOMAIN ENGINES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_6_domain_engines(df_categorized: pl.DataFrame) -> TestMetrics:
    """Valida Domain Engines."""
    print_header("TESTE 6: DOMAIN ENGINES (Finance + SafeToSpend)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    
    try:
        print_subheader("STEP 1: FinanceEngine")
        
        income = float(df_categorized.filter(pl.col("amount") > 0)["amount"].sum())
        expenses = float(abs(df_categorized.filter(pl.col("amount") < 0)["amount"].sum()))
        
        finance_engine = FinanceEngine()
        summary = finance_engine.calculate_summary(income, expenses)
        
        print_metric("Receita", f"R$ {summary['income']:,.2f}")
        print_metric("Despesa", f"R$ {summary['expenses']:,.2f}")
        print_metric("Health score", f"{summary['health_score']}/100")
        
        if 0 <= summary["health_score"] <= 100:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        print_subheader("STEP 2: SafeToSpendEngine")
        
        sts_engine = SafeToSpendEngine()
        sts_result = sts_engine.calculate(
            current_balance=5000.0,
            upcoming_fixed_expenses=2000.0,
            upcoming_subscriptions=150.0,
            upcoming_installments=370.0,
            safety_buffer_pct=0.10
        )
        
        print_metric("Safe-to-spend", f"R$ {sts_result['safe_to_spend']:,.2f}")
        print_metric("Risk level", sts_result["risk_level"])
        
        if sts_result["safe_to_spend"] >= 0:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_6_domain_engines",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details={"health_score": summary["health_score"]}
        )
        
        print_metric("Tempo execução", f"{duration_ms:.2f}", " ms")
        print(f"\n{'✅' if metrics.passed else '❌'} TESTE 6: {'PASSOU' if metrics.passed else 'FALHOU'}")
        
        return metrics
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        metrics = TestMetrics(
            test_name="test_6_domain_engines",
            passed=False,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed + 1,
            details={"error": str(e)}
        )
        raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RELATÓRIO FINAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_final_report(report: IntegrationReport, sts_result: Any, summary: Any):
    """Imprime relatório final."""
    
    print("\n" + "="*80)
    print("📊 RELATÓRIO FINAL - TESTE DE INTELIGÊNCIA")
    print("="*80)
    
    print(f"\n🧪 TESTES EXECUTADOS:")
    print(f"   • Total: {report.total_tests}")
    print(f"   • Passou: {report.passed_tests} ✅")
    print(f"   • Falhou: {report.failed_tests} ❌")
    print(f"   • Taxa de sucesso: {report.success_rate()*100:.1f}%")
    print(f"   • Tempo total: {report.total_duration_ms:.2f} ms")
    
    print(f"\n📋 BREAKDOWN:")
    for m in report.test_metrics:
        status = "✅" if m.passed else "❌"
        print(f"   {status} {m.test_name}")
        print(f"      Assertions: {m.assertions_passed}/{m.assertions_passed + m.assertions_failed}")
        print(f"      Tempo: {m.duration_ms:.2f} ms")
    
    print(f"\n💰 RESULTADOS FINAIS:")
    print(f"   • Safe-to-Spend Diário: R$ {sts_result.safe_to_spend_daily:,.2f}")
    print(f"   • Safe-to-Spend Total: R$ {sts_result.safe_to_spend_total:,.2f}")
    print(f"   • Risk Level: {sts_result.risk_level}")
    print(f"   • Shadow Impact: R$ {summary.total_shadow_impact:,.2f}")
    
    if report.failed_tests == 0:
        print(f"\n{'='*80}")
        print(f"🎉 SUCESSO! TODA A INTELIGÊNCIA VALIDADA!")
        print(f"{'='*80}")
        print(f"\n✅ SISTEMA PRONTO PARA API LAYER!")
    else:
        print(f"\n{'='*80}")
        print(f"❌ ALGUNS TESTES FALHARAM!")
        print(f"{'='*80}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """Executa todos os testes."""
    
    print("\n" + "="*80)
    print("🎯 TESTE DE INTELIGÊNCIA COMPLETO - NEXA AI")
    print("="*80)
    print("\nVALIDANDO:")
    print("   1. Schemas Pydantic")
    print("   2. ETL Pipeline (BankStrategy + Classifier)")
    print("   3. Shadow Invoices")
    print("   4. Cashflow Projection")
    print("   5. Safe-to-Spend")
    print("   6. Domain Engines")
    
    start_time_total = time.time()
    all_metrics: List[TestMetrics] = []
    
    try:
        validated, m1 = test_1_pydantic_validation()
        all_metrics.append(m1)
        
        df_categorized, m2 = test_2_etl_pipeline(validated)
        all_metrics.append(m2)
        
        shadow_df, m3 = test_3_shadow_invoices(df_categorized)
        all_metrics.append(m3)
        
        projection_df, summary, m4 = test_4_cashflow_projection(df_categorized, shadow_df)
        all_metrics.append(m4)
        
        sts_result, m5 = test_5_safe_to_spend(projection_df)
        all_metrics.append(m5)
        
        m6 = test_6_domain_engines(df_categorized)
        all_metrics.append(m6)
        
        total_duration_ms = (time.time() - start_time_total) * 1000
        
        report = IntegrationReport(
            total_tests=len(all_metrics),
            passed_tests=sum(1 for m in all_metrics if m.passed),
            failed_tests=sum(1 for m in all_metrics if not m.passed),
            total_duration_ms=total_duration_ms,
            test_metrics=all_metrics
        )
        
        print_final_report(report, sts_result, summary)
        
        sys.exit(0 if report.failed_tests == 0 else 1)
        
    except Exception as e:
        print("\n" + "="*80)
        print("❌ ERRO CRÍTICO!")
        print("="*80)
        print(f"\nErro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()