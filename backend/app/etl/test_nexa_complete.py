"""
🧪 TESTE DEFINITIVO DO ETL - PIPELINE COMPLETO COM 90 DIAS
═══════════════════════════════════════════════════════════════════════

O teste mais completo possível do ETL Nexa AI.

FEATURES:
    ✅ 90 dias de transações realistas (gerador automático)
    ✅ Banco Nubank (TIER_1 - dados perfeitos)
    ✅ Assinaturas recorrentes (Netflix, Spotify, Amazon Prime)
    ✅ Parcelamentos (compra 12x)
    ✅ Despesas fixas (aluguel, condomínio, contas)
    ✅ Gastos variáveis (alimentação, transporte, saúde)
    ✅ Receitas mensais (salário)
    ✅ Validações completas (10 checkpoints)

PIPELINE COMPLETO:
    1. TransactionBatchResult - Validação Pydantic
    2. TransactionIngestor - Normalização + BankStrategy + DuckDB
    3. TransactionClassifier - Categorização (10 categorias)
    4. RecurringDetector - Assinaturas + Parcelamentos
    5. DataQualityValidator - Análise de qualidade global
    6. UserProfileAnalyzer - Perfil financeiro
    7. Shadow Invoice Detection - Obrigações futuras

Como executar:
    cd /Users/gabriel-abel/projetoNexa/codigos-nexa-19
    pyenv shell 3.12.1
    python backend/app/etl/test_etl_ultimate.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import random

# Fix PYTHONPATH
current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Imports
import polars as pl
from app.schemas.transaction import TransactionBatchResult
from app.etl import (
    TransactionIngestor,
    TransactionClassifier,
    RecurringDetector,
    DataQualityValidator,
    UserProfileAnalyzer,
    run_shadow_invoice_detection,
    print_recurring_stats
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GERADOR DE DADOS REALISTAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RealisticTransactionGenerator:
    """Gera 90 dias de transações realistas de um brasileiro típico."""
    
    def __init__(self):
        self.now = datetime.now(timezone.utc)
        self.balance = 5000.0
        self.counter = 0
    
    def generate(self) -> list[dict]:
        """Gera todas as transações (90 dias)."""
        txns = []
        
        # Receitas (salário)
        txns.extend(self._salario())
        
        # Despesas fixas
        txns.extend(self._aluguel())
        txns.extend(self._condominio())
        txns.extend(self._contas())
        
        # Assinaturas (Netflix, Spotify, Prime)
        txns.extend(self._assinaturas())
        
        # Parcelamento (12x)
        txns.extend(self._parcelamento())
        
        # Gastos variáveis
        txns.extend(self._alimentacao())
        txns.extend(self._transporte())
        txns.extend(self._saude())
        
        # Ordenar por data + recalcular saldo
        txns.sort(key=lambda t: t["date"])
        self._recalcular_saldo(txns)
        
        return txns
    
    def _salario(self):
        """Salário mensal (dia 1)."""
        txns = []
        for m in [2, 1, 0]:
            txns.append({
                "id": f"sal_{self.counter}",
                "accountId": "acc_123",
                "date": (self.now - timedelta(days=m*30+25)).isoformat(),
                "description": "PIX RECEBIDO - EMPRESA XPTO LTDA SALARIO",
                "amount": 5000.0,
                "type": "CREDIT",
                "status": "POSTED"
            })
            self.counter += 1
        return txns
    
    def _aluguel(self):
        """Aluguel mensal (dia 5)."""
        txns = []
        for m in [2, 1, 0]:
            txns.append({
                "id": f"aluguel_{self.counter}",
                "accountId": "acc_123",
                "date": (self.now - timedelta(days=m*30+25)).isoformat(),
                "description": "TED ENVIADA - ALUGUEL APARTAMENTO",
                "amount": -1500.0,
                "type": "DEBIT",
                "status": "POSTED"
            })
            self.counter += 1
        return txns
    
    def _condominio(self):
        """Condomínio mensal (dia 10)."""
        txns = []
        for m in [2, 1, 0]:
            txns.append({
                "id": f"cond_{self.counter}",
                "accountId": "acc_123",
                "date": (self.now - timedelta(days=m*30+20)).isoformat(),
                "description": "BOLETO CONDOMINIO EDIFICIO",
                "amount": -450.0,
                "type": "DEBIT",
                "status": "POSTED"
            })
            self.counter += 1
        return txns
    
    def _contas(self):
        """Contas essenciais (luz, água, internet, telefone)."""
        txns = []
        contas = [
            ("ENEL CONTA LUZ", -234.56, 12),
            ("SABESP AGUA", -89.00, 15),
            ("CLARO NET INTERNET", -129.90, 10),
        ]
        for desc, amt, day in contas:
            for m in [2, 1, 0]:
                txns.append({
                    "id": f"conta_{self.counter}",
                    "accountId": "acc_123",
                    "date": (self.now - timedelta(days=m*30+(30-day))).isoformat(),
                    "description": desc,
                    "amount": amt,
                    "type": "DEBIT",
                    "status": "POSTED"
                })
                self.counter += 1
        return txns
    
    def _assinaturas(self):
        """Assinaturas (Netflix, Spotify, Prime)."""
        txns = []
        subs = [
            ("NETFLIX.COM *ASSINATURA PREMIUM", -49.90, 10),
            ("SPOTIFY *PREMIUM", -21.90, 15),
            ("AMAZON PRIME VIDEO", -14.90, 20)
        ]
        for desc, amt, day in subs:
            for m in [2, 1, 0]:  # 3 meses para detectar padrão
                txns.append({
                    "id": f"sub_{self.counter}",
                    "accountId": "acc_123",
                    "date": (self.now - timedelta(days=m*30+(30-day))).isoformat(),
                    "description": desc,
                    "amount": amt,
                    "type": "DEBIT",
                    "status": "POSTED"
                })
                self.counter += 1
        return txns
    
    def _parcelamento(self):
        """Parcelamento 12x."""
        txns = []
        for n in range(1, 6):  # 5 parcelas pagas
            txns.append({
                "id": f"parc_{self.counter}",
                "accountId": "acc_123",
                "date": (self.now - timedelta(days=(5-n)*30+20)).isoformat(),
                "description": f"COMPRA PARCELADA {n}/12 - MAGAZINE LUIZA",
                "amount": -120.0,
                "type": "DEBIT",
                "status": "POSTED"
            })
            self.counter += 1
        return txns
    
    def _alimentacao(self):
        """Gastos com alimentação (a cada 3 dias)."""
        txns = []
        for day in range(0, 90, 3):
            txns.append({
                "id": f"food_{self.counter}",
                "accountId": "acc_123",
                "date": (self.now - timedelta(days=day)).isoformat(),
                "description": "IFOOD PEDIDO DELIVERY",
                "amount": round(-random.uniform(25, 60), 2),
                "type": "DEBIT",
                "status": "POSTED"
            })
            self.counter += 1
        return txns
    
    def _transporte(self):
        """Gastos com transporte (a cada 4 dias)."""
        txns = []
        for day in range(1, 90, 4):
            txns.append({
                "id": f"uber_{self.counter}",
                "accountId": "acc_123",
                "date": (self.now - timedelta(days=day)).isoformat(),
                "description": "UBER VIAGEM",
                "amount": round(-random.uniform(15, 40), 2),
                "type": "DEBIT",
                "status": "POSTED"
            })
            self.counter += 1
        return txns
    
    def _saude(self):
        """Gastos com saúde (a cada 10 dias)."""
        txns = []
        for day in range(5, 90, 10):
            txns.append({
                "id": f"farm_{self.counter}",
                "accountId": "acc_123",
                "date": (self.now - timedelta(days=day)).isoformat(),
                "description": "FARMACIA DROGARIA SAO PAULO",
                "amount": round(-random.uniform(30, 80), 2),
                "type": "DEBIT",
                "status": "POSTED"
            })
            self.counter += 1
        return txns
    
    def _recalcular_saldo(self, txns):
        """Recalcula balance acumulado."""
        current = self.balance
        for txn in txns:
            current += txn["amount"]
            txn["balance"] = round(current, 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def header(title): print(f"\n{'='*80}\n🧪 {title}\n{'='*80}")
def section(title): print(f"\n▶ {title}\n{'-'*80}")
def metric(label, value): print(f"   ✅ {label:<40} {value}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE DEFINITIVO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_ultimate():
    header("TESTE DEFINITIVO: PIPELINE ETL COMPLETO (90 DIAS)")
    
    # STEP 1: Gerar dados
    section("STEP 1: Geração de Dados Realistas (90 dias)")
    gen = RealisticTransactionGenerator()
    raw = gen.generate()
    metric("Transações geradas", len(raw))
    metric("Saldo final", f"R$ {raw[-1]['balance']:,.2f}")
    
    # STEP 2: Validação Pydantic
    section("STEP 2: Validação Pydantic")
    batch = TransactionBatchResult.from_raw_batch(
        raw_data=raw,
        institution_id="nubank",
        item_id="test_ultimate",
        fetched_at=datetime.now(timezone.utc),
        batch_id="batch_90d"
    )
    metric("Válidas", batch.total_valid)
    metric("Rejeitadas", batch.total_rejected)
    assert batch.total_valid > 80
    
    # STEP 3: Ingestor
    section("STEP 3: Ingestor (Polars + BankStrategy)")
    ing = TransactionIngestor()
    df, met = ing.process(batch.valid_transactions)
    metric("Records processados", met.records_after_dedup)
    metric("Quality score", f"{met.quality_score:.1%}")
    metric("TRUSTED", met.trusted_count)
    assert df.height > 80
    
    # STEP 4: Classifier
    section("STEP 4: Classifier (Categorização)")
    clf = TransactionClassifier()
    df = clf.predict(df)
    cats = df["predicted_category"].n_unique()
    metric("Categorias únicas", cats)
    metric("Confiança média", f"{df['ml_confidence'].mean():.1%}")
    assert cats >= 5
    
    # STEP 5: RecurringDetector
    section("STEP 5: RecurringDetector")
    det = RecurringDetector()
    df = det.detect(df)
    subs = df.filter(pl.col("is_recurring") == True).height
    inst = df.filter(pl.col("is_installment") == True).height
    metric("Assinaturas", subs)
    metric("Parcelamentos", inst)
    assert subs >= 2
    print_recurring_stats(df)
    
    # STEP 6: DataQualityValidator
    section("STEP 6: DataQualityValidator")
    val = DataQualityValidator()
    qr = val.validate(df, 90)
    metric("Confiança global", f"{qr.overall_confidence:.1%}")
    metric("Qualidade", qr.quality_level)
    metric("Cobertura", f"{qr.temporal_coverage:.1%}")
    assert qr.overall_confidence >= 0.60
    
    # STEP 7: UserProfileAnalyzer
    section("STEP 7: UserProfileAnalyzer")
    prof = UserProfileAnalyzer()
    p = prof.analyze(df)
    metric("Perfil", p.profile_type)
    metric("Health score", f"{p.financial_health_score}/100")
    metric("Taxa poupança", f"{p.savings_rate:.1f}%")
    assert p.profile_type in ["CONSERVADOR", "EQUILIBRADO", "GASTADOR"]
    
    # STEP 8: Shadow Invoices
    section("STEP 8: Shadow Invoice Detection")
    sh = run_shadow_invoice_detection(df)
    metric("Shadow invoices", sh.height)
    if not sh.is_empty():
        total = abs(sh["amount"].sum())
        metric("Impacto mensal", f"R$ {total:,.2f}")
    assert sh.height >= 2
    
    # RESUMO FINAL
    header("RESUMO FINAL")
    print(f"\n📊 ESTATÍSTICAS COMPLETAS:")
    print(f"   • Transações: {df.height}")
    print(f"   • Categorias: {cats}")
    print(f"   • Assinaturas: {subs}")
    print(f"   • Parcelamentos: {inst}")
    print(f"   • Confiança: {qr.overall_confidence:.1%} ({qr.quality_level})")
    print(f"   • Perfil: {p.profile_type} (health: {p.financial_health_score}/100)")
    print(f"   • Shadow invoices: {sh.height}")
    
    print(f"\n{'='*80}")
    print("✅ TODOS OS TESTES PASSARAM!")
    print(f"{'='*80}\n")
    
    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    try:
        success = test_ultimate()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)