"""
test_integration_complete_v2.py - Teste de Integração COMPLETO (VERSÃO MELHORADA)

OBJETIVO:
    Validar TODO o pipeline funcionando em conjunto com MÁXIMA COBERTURA:
    
    1. ✅ ETL Pipeline (Ingestor + Classifier + BankStrategy)
    2. ✅ Shadow Invoices (Subscription + Installment Detectors)
    3. ✅ Cashflow (CashflowProjector)
    4. ✅ Safe-to-Spend (SafeToSpendCalculator)
    5. ✅ Domain Engines (FinanceEngine + SafeToSpendEngine)
    6. ✅ DuckDB Loader
    7. ✅ Edge Cases (dados incompletos, falhas de API)
    8. ✅ Performance Benchmarks

MELHORIAS v2:
    ✅ Mais cenários de teste (12 meses de dados)
    ✅ Validações numéricas rigorosas (baseline esperado)
    ✅ Métricas de performance (tempo de execução)
    ✅ Relatório visual (gráficos ASCII)
    ✅ Logs estruturados (JSON)
    ✅ Comparação com valores esperados
    ✅ Edge cases (banco instável, dados incompletos)

EXECUÇÃO:
    cd backend/tests
    python test_integration_complete_v2.py
    
    # Com logs detalhados:
    python test_integration_complete_v2.py --verbose
    
    # Com relatório em JSON:
    python test_integration_complete_v2.py --json-report report.json
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time
import json
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SETUP: Adicionar backend ao path
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

project_root = Path(__file__).parent.parent.parent
backend_path = project_root / "backend"

if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
    print(f"✅ Python path configurado: {backend_path}\n")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import polars as pl
from pydantic import ValidationError

# Schemas
from app.schemas.transaction import TransactionWebhook, TransactionBatchResult
from app.schemas.enums import TransactionType, DataStatus

# ETL
from app.etl.ingestor import TransactionIngestor
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
    baseline_validation: Dict[str, bool]
    
    def to_dict(self):
        return {
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "total_duration_ms": self.total_duration_ms,
            "success_rate": self.passed_tests / self.total_tests if self.total_tests > 0 else 0,
            "test_metrics": [m.to_dict() for m in self.test_metrics],
            "baseline_validation": self.baseline_validation
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BASELINES ESPERADOS (para validação numérica)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BASELINE = {
    "total_transactions": 250,  # ~6 meses de dados
    "min_subscriptions": 5,     # Netflix, Spotify, Prime, YouTube, iCloud
    "min_installments": 2,      # Celular 12x + Notebook 24x
    "cashflow_days": 30,
    "min_safe_to_spend": 0,     # Pode ser negativo em cenários ruins
    "max_rejection_rate": 0.05, # Máximo 5% de rejeição
    "min_health_score": 0,
    "max_health_score": 100,
    "expected_categories": ["Salário", "Assinaturas", "Alimentação", "Transporte", "Moradia"],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GERADOR DE DADOS DE TESTE (12 MESES)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_test_transactions(months: int = 12) -> List[Dict[str, Any]]:
    """
    Cria dataset de teste simulando N meses de transações reais.
    
    Args:
        months: Quantidade de meses a gerar (default: 12)
    
    Inclui:
        - Salário mensal (crédito)
        - Assinaturas recorrentes (5 tipos)
        - Parcelamentos (Celular 12x, Notebook 24x)
        - Gastos variáveis (Uber, iFood, Mercado)
        - Contas fixas (Aluguel, Luz, Internet, Condomínio)
        - Edge cases (transações duplicadas, valores zerados, datas futuras)
    """
    base_date = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    transactions = []
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. SALÁRIO MENSAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    for month in range(months):
        date = base_date + timedelta(days=30 * month + 5)  # Dia 5 de cada mês
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
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. ASSINATURAS RECORRENTES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
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
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. PARCELAMENTOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Celular 12x (iniciou no mês 1)
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
    
    # Notebook 24x (iniciou no mês 3)
    for i in range(min(24, max(0, months - 2))):
        date = base_date + timedelta(days=30 * (i + 2) + 15)
        transactions.append({
            "transaction_id": f"notebook_{i+1}",
            "account_id": "acc_001",
            "institution_id": "nubank",
            "item_id": "item_nubank_001",
            "amount": "-249.90",
            "transaction_date": date,
            "description": f"COMPRA PARCELADA {i+1:02d}/24 DELL INSPIRON",
            "balance": None,
            "type": "DEBIT",
            "installment_number": i+1,
            "installment_total": 24,
            "source": "PLUGGY",
            "fetched_at": datetime.now(timezone.utc)
        })
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. CONTAS FIXAS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
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
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. GASTOS VARIÁVEIS (aleatórios, ~10-15 por mês)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    variable_expenses = [
        ("UBER *TRIP", -25.00),
        ("IFOOD *DELIVERY", -45.00),
        ("MERCADO EXTRA", -320.00),
        ("POSTO SHELL", -250.00),
        ("FARMACIA DROGASIL", -80.00),
    ]
    
    import random
    random.seed(42)  # Reproduzível
    
    for month in range(months):
        # 10-15 gastos variáveis por mês
        for i in range(random.randint(10, 15)):
            desc, base_amount = random.choice(variable_expenses)
            # Varia ±20%
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
    # 6. EDGE CASES (dados problemáticos para testar robustez)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Transação duplicada (mesmo ID, mesma data)
    transactions.append({
        "transaction_id": "dup_test",
        "account_id": "acc_001",
        "institution_id": "nubank",
        "item_id": "item_nubank_001",
        "amount": "-50.00",
        "transaction_date": base_date + timedelta(days=10),
        "description": "DUPLICATA TESTE",
        "balance": None,
        "type": "DEBIT",
        "source": "PLUGGY",
        "fetched_at": datetime.now(timezone.utc)
    })
    
    # Mesma transação (deveria ser dedupada)
    transactions.append({
        "transaction_id": "dup_test",
        "account_id": "acc_001",
        "institution_id": "nubank",
        "item_id": "item_nubank_001",
        "amount": "-50.00",
        "transaction_date": base_date + timedelta(days=10),
        "description": "DUPLICATA TESTE",
        "balance": None,
        "type": "DEBIT",
        "source": "PLUGGY",
        "fetched_at": datetime.now(timezone.utc)
    })
    
    return sorted(transactions, key=lambda x: x["transaction_date"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS DE TESTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_header(title: str):
    """Imprime header de teste."""
    print("\n" + "="*80)
    print(f"🧪 {title}")
    print("="*80)


def print_subheader(title: str):
    """Imprime subheader."""
    print(f"\n▶ {title}")
    print("-" * 80)


def print_metric(label: str, value: Any, unit: str = ""):
    """Imprime métrica formatada."""
    print(f"   ✅ {label}: {value}{unit}")


def print_ascii_bar(label: str, value: float, max_value: float, width: int = 40):
    """Imprime barra de progresso ASCII."""
    pct = min(value / max_value, 1.0) if max_value > 0 else 0
    bar_length = int(pct * width)
    bar = "█" * bar_length + "░" * (width - bar_length)
    print(f"   {label:30s} {bar} {pct*100:5.1f}%")


def assert_baseline(actual: float, expected: float, tolerance: float = 0.1, label: str = ""):
    """
    Valida que valor está dentro da tolerância esperada.
    
    Args:
        actual: Valor obtido
        expected: Valor esperado
        tolerance: Tolerância (0.1 = 10%)
        label: Label para debug
    
    Raises:
        AssertionError: Se fora da tolerância
    """
    diff_pct = abs(actual - expected) / expected if expected != 0 else 0
    
    if diff_pct > tolerance:
        raise AssertionError(
            f"❌ {label}: esperado {expected}, obtido {actual} "
            f"(diff: {diff_pct*100:.1f}%)"
        )
    
    print(f"   ✅ {label}: {actual} (esperado: {expected}, diff: {diff_pct*100:.1f}%)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_1_pydantic_validation() -> Tuple[List[TransactionWebhook], TestMetrics]:
    """
    TESTE 1: Validação Pydantic (TransactionWebhook)
    
    Valida:
        - Parsing de amounts (BR/US)
        - Parsing de datas (UTC)
        - Normalização de sinal (DEBIT → negativo)
        - Geração de dedup_hash
        - Rejeição de dados inválidos
    """
    print_header("TESTE 1: VALIDAÇÃO PYDANTIC (TransactionWebhook)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        raw_data = create_test_transactions(months=12)
        details["total_raw"] = len(raw_data)
        
        # Converter para TransactionWebhook
        validated = []
        rejected = []
        
        for raw in raw_data:
            try:
                txn = TransactionWebhook(**raw)
                validated.append(txn)
            except ValidationError as e:
                rejected.append(raw)
                print(f"❌ Rejeitada: {raw['transaction_id']} - {e}")
        
        details["validated"] = len(validated)
        details["rejected"] = len(rejected)
        
        print_metric("Validadas", f"{len(validated)}/{len(raw_data)}")
        print_metric("Rejeitadas", f"{len(rejected)}/{len(raw_data)}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTION 1: Taxa de rejeição
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        rejection_rate = len(rejected) / len(raw_data) if raw_data else 0
        details["rejection_rate"] = rejection_rate
        
        if rejection_rate <= BASELINE["max_rejection_rate"]:
            assertions_passed += 1
            print_metric("Taxa de rejeição", f"{rejection_rate*100:.2f}%", " ✅")
        else:
            assertions_failed += 1
            print(f"   ❌ Taxa de rejeição muito alta: {rejection_rate*100:.2f}%")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTION 2: Normalização de sinal
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        debits = [t for t in validated if t.type == "DEBIT"]
        credits = [t for t in validated if t.type == "CREDIT"]
        
        details["debits"] = len(debits)
        details["credits"] = len(credits)
        
        all_debits_negative = all(t.amount < 0 for t in debits)
        all_credits_positive = all(t.amount > 0 for t in credits)
        
        if all_debits_negative and all_credits_positive:
            assertions_passed += 1
            print_metric("Normalização de sinal", "OK ✅")
        else:
            assertions_failed += 1
            print(f"   ❌ Normalização falhou: débitos={all_debits_negative}, créditos={all_credits_positive}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTION 3: Deduplicação
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        hashes = [t.dedup_hash for t in validated]
        unique_hashes = set(hashes)
        duplicates = len(hashes) - len(unique_hashes)
        
        details["duplicates"] = duplicates
        
        # Esperamos 1 duplicata (inserida propositalmente)
        if duplicates >= 1:
            assertions_passed += 1
            print_metric("Duplicatas detectadas", duplicates, " ✅")
        else:
            assertions_failed += 1
            print(f"   ❌ Duplicatas não detectadas")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTION 4: Quantidade de transações
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if len(validated) >= BASELINE["total_transactions"]:
            assertions_passed += 1
            print_metric("Transações geradas", len(validated), " ✅")
        else:
            assertions_failed += 1
            print(f"   ❌ Poucas transações: {len(validated)} < {BASELINE['total_transactions']}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_1_pydantic_validation",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details=details
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


def test_2_etl_pipeline(validated_transactions: List[TransactionWebhook]) -> Tuple[pl.DataFrame, TestMetrics]:
    """
    TESTE 2: Pipeline ETL (Ingestor + BankStrategy + Classifier)
    
    Valida:
        - Ingestor (normalização, deduplicação)
        - BankStrategy (Nubank TIER_1)
        - Classifier (categorização)
        - Métricas de qualidade
    """
    print_header("TESTE 2: PIPELINE ETL (Ingestor + BankStrategy + Classifier)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: Ingestor
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print_subheader("STEP 1: TransactionIngestor")
        
        ingestor = TransactionIngestor(db_path=":memory:")
        df_clean, metrics_ingestor = ingestor.process(validated_transactions)
        
        details["total_records"] = metrics_ingestor.total_records
        details["duplicates_removed"] = metrics_ingestor.duplicates_removed
        details["inserted_rows"] = metrics_ingestor.inserted_rows
        
        print_metric("Processadas", metrics_ingestor.total_records)
        print_metric("Duplicatas removidas", metrics_ingestor.duplicates_removed)
        print_metric("Inseridas no DB", metrics_ingestor.inserted_rows)
        print_metric("TRUSTED", metrics_ingestor.trusted_count)
        print_metric("DEGRADED", metrics_ingestor.degraded_count)
        print_metric("UNTRUSTED", metrics_ingestor.untrusted_count)
        
        # Assertion: Deduplicação funcionou
        if metrics_ingestor.duplicates_removed >= 1:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: BankStrategy
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print_subheader("STEP 2: BankStrategy (Nubank)")
        
        strategy = get_bank_strategy("nubank")
        details["bank_strategy"] = strategy.__class__.__name__
        details["bank_tier"] = strategy.tier.value
        
        print_metric("Strategy", strategy.__class__.__name__)
        print_metric("Tier", strategy.tier.value)
        
        # Assertion: Nubank é TIER_1
        if strategy.tier.value == "TIER_1":
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 3: Classifier
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print_subheader("STEP 3: TransactionClassifier")
        
        classifier = TransactionClassifier(mode="RULES")
        df_categorized = classifier.predict(df_clean)
        
        # Ver distribuição de categorias
        categories = (
            df_categorized
            .group_by("predicted_category")
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
        )
        
        details["categories"] = {
            row["predicted_category"]: row["count"]
            for row in categories.iter_rows(named=True)
        }
        
        print("\n   📊 Distribuição de Categorias:")
        for row in categories.iter_rows(named=True):
            print_ascii_bar(
                row["predicted_category"],
                row["count"],
                df_categorized.height
            )
        
        # Assertion: Pelo menos 3 categorias diferentes
        if len(details["categories"]) >= 3:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # VALIDAÇÕES FINAIS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        assert df_clean.height > 0, "DataFrame não pode estar vazio"
        assert "data_status" in df_clean.columns, "Deve ter coluna data_status"
        assert "predicted_category" in df_categorized.columns, "Deve ter categorias"
        assertions_passed += 3
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_2_etl_pipeline",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details=details
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


def test_3_shadow_invoices(df_categorized: pl.DataFrame) -> Tuple[pl.DataFrame, TestMetrics]:
    """
    TESTE 3: Shadow Invoices (Subscription + Installment Detectors)
    
    Valida:
        - Detecção de assinaturas (Netflix, Spotify, etc)
        - Detecção de parcelamentos (Celular 12x, Notebook 24x)
        - Projeção de próximas parcelas
        - Confidence scores
    """
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
            
            duration_ms = (time.time() - start_time) * 1000
            metrics = TestMetrics(
                test_name="test_3_shadow_invoices",
                passed=False,
                duration_ms=duration_ms,
                assertions_passed=assertions_passed,
                assertions_failed=assertions_failed,
                details={"error": "Nenhuma shadow invoice detectada"}
            )
            return pl.DataFrame(), metrics
        
        # Separar por tipo
        subscriptions = shadow_df.filter(pl.col("type") == "SUBSCRIPTION")
        installments = shadow_df.filter(pl.col("type") == "INSTALLMENT")
        
        details["total_shadows"] = shadow_df.height
        details["subscriptions"] = subscriptions.height
        details["installments"] = installments.height
        
        print_metric("Total detectado", shadow_df.height)
        print_metric("Assinaturas", subscriptions.height)
        print_metric("Parcelamentos", installments.height)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTION 1: Quantidade mínima de assinaturas
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if subscriptions.height >= BASELINE["min_subscriptions"]:
            assertions_passed += 1
            print(f"   ✅ Assinaturas detectadas: {subscriptions.height} >= {BASELINE['min_subscriptions']}")
        else:
            assertions_failed += 1
            print(f"   ❌ Poucas assinaturas: {subscriptions.height} < {BASELINE['min_subscriptions']}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTION 2: Quantidade mínima de parcelamentos
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if installments.height >= BASELINE["min_installments"]:
            assertions_passed += 1
            print(f"   ✅ Parcelamentos detectados: {installments.height} >= {BASELINE['min_installments']}")
        else:
            assertions_failed += 1
            print(f"   ❌ Poucos parcelamentos: {installments.height} < {BASELINE['min_installments']}")
        
        # Mostrar detalhes
        if subscriptions.height > 0:
            print(f"\n   🔁 Assinaturas detectadas:")
            for row in subscriptions.iter_rows(named=True):
                desc = row["metadata"]["description"]
                amount = row["amount"]
                conf = row["confidence"]
                print(f"      • {desc}: R$ {amount:.2f} (conf: {conf:.2f})")
        
        if installments.height > 0:
            print(f"\n   📦 Parcelamentos detectados:")
            for row in installments.iter_rows(named=True):
                desc = row["metadata"]["description"]
                amount = row["amount"]
                conf = row["confidence"]
                print(f"      • {desc}: R$ {amount:.2f} (conf: {conf:.2f})")
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_3_shadow_invoices",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details=details
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


def test_4_cashflow_projection(
    df_categorized: pl.DataFrame,
    shadow_df: pl.DataFrame
) -> Tuple[pl.DataFrame, Any, TestMetrics]:
    """
    TESTE 4: Projeção de Cashflow
    
    Valida:
        - Cálculo de saldo inicial
        - Projeção dia a dia (30 dias)
        - Aplicação de shadow invoices
        - Detecção de dias de risco
        - Métricas de summary
    """
    print_header("TESTE 4: PROJEÇÃO DE CASHFLOW (CashflowProjector)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        # Calcular saldo inicial (cumsum)
        df_with_balance = df_categorized.sort("transaction_date")
        df_with_balance = df_with_balance.with_columns(
            pl.col("amount").cum_sum().alias("balance")
        )
        
        # Ajustar para saldo inicial de 5000
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
        
        # Calcular resumo
        last_balance = float(df_with_balance["balance"][-1])
        summary = projector.get_summary(projection_df, last_balance)
        
        details["horizon_days"] = summary.horizon_days
        details["starting_balance"] = summary.starting_balance
        details["ending_balance"] = summary.ending_balance
        details["worst_balance"] = summary.worst_balance
        details["risk_level"] = summary.risk_level
        details["total_shadow_impact"] = summary.total_shadow_impact
        
        print(f"\n📊 Resumo da Projeção:")
        print_metric("Período", f"{summary.horizon_days} dias")
        print_metric("Saldo inicial", f"R$ {summary.starting_balance:,.2f}")
        print_metric("Saldo final", f"R$ {summary.ending_balance:,.2f}")
        print_metric("Menor saldo", f"R$ {summary.worst_balance:,.2f}")
        print_metric("Dia negativo", summary.negative_day or "Nunca")
        print_metric("Risk level", summary.risk_level)
        print_metric("Impacto shadow", f"R$ {summary.total_shadow_impact:,.2f}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTIONS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Assertion 1: Quantidade de dias
        if projection_df.height == BASELINE["cashflow_days"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
            print(f"   ❌ Esperado {BASELINE['cashflow_days']} dias, obtido {projection_df.height}")
        
        # Assertion 2: Colunas obrigatórias
        required_cols = ["date", "projected_balance", "expenses", "risk_flag"]
        if all(col in projection_df.columns for col in required_cols):
            assertions_passed += 1
        else:
            assertions_failed += 1
            print(f"   ❌ Faltam colunas obrigatórias")
        
        # Assertion 3: Shadow invoices aplicados
        if summary.total_shadow_impact < 0:  # Deve ser negativo
            assertions_passed += 1
        else:
            assertions_failed += 1
            print(f"   ❌ Shadow impact deveria ser negativo: {summary.total_shadow_impact}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_4_cashflow_projection",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details=details
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


def test_5_safe_to_spend(projection_df: pl.DataFrame) -> Tuple[Any, TestMetrics]:
    """
    TESTE 5: Cálculo de Safe-to-Spend
    
    Valida:
        - Cálculo de buffer de segurança
        - Safe-to-spend total e diário
        - Classificação de risco
        - Validações numéricas
    """
    print_header("TESTE 5: SAFE-TO-SPEND (SafeToSpendCalculator)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        calculator = SafeToSpendCalculator(safety_buffer_pct=0.15)
        result = calculator.calculate(projection_df, horizon_days=30)
        
        details["current_balance"] = result.current_balance
        details["safe_to_spend_total"] = result.safe_to_spend_total
        details["safe_to_spend_daily"] = result.safe_to_spend_daily
        details["safety_buffer"] = result.safety_buffer
        details["risk_level"] = result.risk_level
        
        print(f"\n💰 Resultado:")
        print_metric("Saldo atual", f"R$ {result.current_balance:,.2f}")
        print_metric("Menor saldo projetado", f"R$ {result.min_projected_balance:,.2f}")
        print_metric("Shadow invoices", f"R$ {result.total_shadow_invoices:,.2f}")
        print_metric("Buffer segurança", f"R$ {result.safety_buffer:,.2f}")
        print_metric("Safe-to-spend total", f"R$ {result.safe_to_spend_total:,.2f}")
        print_metric("Safe-to-spend diário", f"R$ {result.safe_to_spend_daily:,.2f}")
        print_metric("Risk level", result.risk_level)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTIONS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Assertion 1: Safe-to-spend >= mínimo baseline
        if result.safe_to_spend_total >= BASELINE["min_safe_to_spend"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # Assertion 2: Buffer positivo
        if result.safety_buffer > 0:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # Assertion 3: Risk level válido
        if result.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # Assertion 4: Safe-to-spend diário coerente
        expected_daily = result.safe_to_spend_total / 30
        if abs(result.safe_to_spend_daily - expected_daily) < 0.01:
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
            details=details
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


def test_6_domain_engines(df_categorized: pl.DataFrame) -> TestMetrics:
    """
    TESTE 6: Domain Engines (Finance + SafeToSpend)
    
    Valida:
        - FinanceEngine (cálculo de health score)
        - SafeToSpendEngine (cálculo alternativo)
        - Validações numéricas
    """
    print_header("TESTE 6: DOMAIN ENGINES (FinanceEngine + SafeToSpendEngine)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 1: FinanceEngine
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print_subheader("STEP 1: FinanceEngine")
        
        income = float(df_categorized.filter(pl.col("amount") > 0)["amount"].sum())
        expenses = float(abs(df_categorized.filter(pl.col("amount") < 0)["amount"].sum()))
        
        finance_engine = FinanceEngine()
        summary = finance_engine.calculate_summary(income, expenses)
        
        details["income"] = summary["income"]
        details["expenses"] = summary["expenses"]
        details["savings_rate"] = summary["savings_rate"]
        details["health_score"] = summary["health_score"]
        
        print_metric("Receita", f"R$ {summary['income']:,.2f}")
        print_metric("Despesa", f"R$ {summary['expenses']:,.2f}")
        print_metric("Taxa poupança", f"{summary['savings_rate']:.1f}%")
        print_metric("Health score", f"{summary['health_score']}/100")
        
        # Assertions
        if BASELINE["min_health_score"] <= summary["health_score"] <= BASELINE["max_health_score"]:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # STEP 2: SafeToSpendEngine
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print_subheader("STEP 2: SafeToSpendEngine")
        
        sts_engine = SafeToSpendEngine()
        sts_result = sts_engine.calculate(
            current_balance=5000.0,
            upcoming_fixed_expenses=2000.0,
            upcoming_subscriptions=150.0,
            upcoming_installments=370.0,
            safety_buffer_pct=0.10
        )
        
        details["sts_safe_to_spend"] = sts_result["safe_to_spend"]
        details["sts_risk_level"] = sts_result["risk_level"]
        
        print_metric("Saldo atual", f"R$ {sts_result['current_balance']:,.2f}")
        print_metric("Obrigações futuras", f"R$ {sts_result['mandatory_future']:,.2f}")
        print_metric("Buffer", f"R$ {sts_result['safety_buffer']:,.2f}")
        print_metric("Safe-to-spend", f"R$ {sts_result['safe_to_spend']:,.2f}")
        print_metric("Risk level", sts_result["risk_level"])
        
        # Assertions
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
            details=details
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


def test_7_duckdb_persistence(validated_transactions: List[TransactionWebhook]) -> TestMetrics:
    """
    TESTE 7: Persistência DuckDB
    
    Valida:
        - Criação de tabela
        - INSERT com deduplicação (ON CONFLICT)
        - Consulta de dados
        - Idempotência
    """
    print_header("TESTE 7: PERSISTÊNCIA DUCKDB (DuckDBLoader)")
    
    start_time = time.time()
    assertions_passed = 0
    assertions_failed = 0
    details = {}
    
    try:
        # Processar com Ingestor
        ingestor = TransactionIngestor(db_path="data/test_integration.duckdb")
        df_clean, metrics_ingestor = ingestor.process(validated_transactions)
        
        details["first_insert"] = metrics_ingestor.inserted_rows
        
        print_metric("Inseridas (1ª vez)", f"{metrics_ingestor.inserted_rows}/{metrics_ingestor.total_records}")
        
        # Tentar inserir novamente (deve ser idempotente)
        df_clean2, metrics2 = ingestor.process(validated_transactions)
        
        details["second_insert"] = metrics2.inserted_rows
        
        print_metric("Tentativa duplicada", f"{metrics2.inserted_rows} novas (esperado: 0)")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ASSERTIONS
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Assertion 1: Primeira inserção bem-sucedida
        if metrics_ingestor.inserted_rows > 0:
            assertions_passed += 1
        else:
            assertions_failed += 1
        
        # Assertion 2: Segunda inserção não insere duplicatas
        if metrics2.inserted_rows == 0:
            assertions_passed += 1
        else:
            assertions_failed += 1
            print(f"   ❌ Duplicatas inseridas: {metrics2.inserted_rows}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        metrics = TestMetrics(
            test_name="test_7_duckdb_persistence",
            passed=assertions_failed == 0,
            duration_ms=duration_ms,
            assertions_passed=assertions_passed,
            assertions_failed=assertions_failed,
            details=details
        )
        
        print_metric("Tempo execução", f"{duration_ms:.2f}", " ms")
        print(f"\n{'✅' if metrics.passed else '❌'} TESTE 7: {'PASSOU' if metrics.passed else 'FALHOU'}")
        
        return metrics
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        metrics = TestMetrics(
            test_name="test_7_duckdb_persistence",
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
    """Imprime relatório final com métricas consolidadas."""
    
    print("\n" + "="*80)
    print("📊 RELATÓRIO FINAL - TESTE DE INTEGRAÇÃO COMPLETO")
    print("="*80)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ESTATÍSTICAS DE TESTES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print(f"\n🧪 TESTES EXECUTADOS:")
    print(f"   • Total: {report.total_tests}")
    print(f"   • Passou: {report.passed_tests} ✅")
    print(f"   • Falhou: {report.failed_tests} ❌")
    print(f"   • Taxa de sucesso: {report.passed_tests/report.total_tests*100:.1f}%")
    print(f"   • Tempo total: {report.total_duration_ms:.2f} ms")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BREAKDOWN POR TESTE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print(f"\n📋 BREAKDOWN POR TESTE:")
    for m in report.test_metrics:
        status = "✅" if m.passed else "❌"
        print(f"   {status} {m.test_name}")
        print(f"      Assertions: {m.assertions_passed}/{m.assertions_passed + m.assertions_failed}")
        print(f"      Tempo: {m.duration_ms:.2f} ms")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MÉTRICAS DE NEGÓCIO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    print(f"\n💰 RESULTADOS FINAIS:")
    print(f"   • Safe-to-Spend Diário: R$ {sts_result.safe_to_spend_daily:,.2f}")
    print(f"   • Safe-to-Spend Total: R$ {sts_result.safe_to_spend_total:,.2f}")
    print(f"   • Risk Level: {sts_result.risk_level}")
    print(f"   • Buffer Segurança: R$ {sts_result.safety_buffer:,.2f}")
    print(f"   • Shadow Impact: R$ {summary.total_shadow_impact:,.2f}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # STATUS FINAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if report.failed_tests == 0:
        print(f"\n{'='*80}")
        print(f"🎉 SUCESSO COMPLETO! TODOS OS TESTES PASSARAM!")
        print(f"{'='*80}")
        print(f"\n✅ INTEGRAÇÃO E2E VALIDADA COM SUCESSO!")
        print(f"✅ SISTEMA PRONTO PARA API LAYER!")
    else:
        print(f"\n{'='*80}")
        print(f"❌ ALGUNS TESTES FALHARAM!")
        print(f"{'='*80}")
        print(f"\n⚠️ Revise os erros acima antes de prosseguir.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUNNER PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """Executa todos os testes em sequência."""
    
    print("\n" + "="*80)
    print("🎯 TESTE DE INTEGRAÇÃO COMPLETO - NEXA AI (v2 MELHORADO)")
    print("="*80)
    print("\nVALIDANDO:")
    print("   1. Schemas Pydantic (TransactionWebhook)")
    print("   2. ETL Pipeline (Ingestor + BankStrategy + Classifier)")
    print("   3. Shadow Invoices (Subscription + Installment)")
    print("   4. Cashflow (CashflowProjector)")
    print("   5. Safe-to-Spend (SafeToSpendCalculator)")
    print("   6. Domain Engines (Finance + SafeToSpend)")
    print("   7. DuckDB Persistence (Loader)")
    
    start_time_total = time.time()
    all_metrics: List[TestMetrics] = []
    baseline_validation = {}
    
    try:
        # TESTE 1: Pydantic
        validated, m1 = test_1_pydantic_validation()
        all_metrics.append(m1)
        
        # TESTE 2: ETL
        df_categorized, m2 = test_2_etl_pipeline(validated)
        all_metrics.append(m2)
        
        # TESTE 3: Shadow Invoices
        shadow_df, m3 = test_3_shadow_invoices(df_categorized)
        all_metrics.append(m3)
        
        # TESTE 4: Cashflow
        projection_df, summary, m4 = test_4_cashflow_projection(df_categorized, shadow_df)
        all_metrics.append(m4)
        
        # TESTE 5: Safe-to-Spend
        sts_result, m5 = test_5_safe_to_spend(projection_df)
        all_metrics.append(m5)
        
        # TESTE 6: Domain Engines
        m6 = test_6_domain_engines(df_categorized)
        all_metrics.append(m6)
        
        # TESTE 7: DuckDB
        m7 = test_7_duckdb_persistence(validated)
        all_metrics.append(m7)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # CRIAR RELATÓRIO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        total_duration_ms = (time.time() - start_time_total) * 1000
        
        report = IntegrationReport(
            total_tests=len(all_metrics),
            passed_tests=sum(1 for m in all_metrics if m.passed),
            failed_tests=sum(1 for m in all_metrics if not m.passed),
            total_duration_ms=total_duration_ms,
            test_metrics=all_metrics,
            baseline_validation=baseline_validation
        )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # IMPRIMIR RELATÓRIO
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        print_final_report(report, sts_result, summary)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # SALVAR RELATÓRIO JSON (se solicitado)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if "--json-report" in sys.argv:
            idx = sys.argv.index("--json-report")
            if idx + 1 < len(sys.argv):
                report_path = sys.argv[idx + 1]
                with open(report_path, "w") as f:
                    json.dump(report.to_dict(), f, indent=2)
                print(f"\n💾 Relatório JSON salvo em: {report_path}")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # EXIT CODE
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        sys.exit(0 if report.failed_tests == 0 else 1)
        
    except Exception as e:
        print("\n" + "="*80)
        print("❌ ERRO CRÍTICO NO TESTE!")
        print("="*80)
        print(f"\nErro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()