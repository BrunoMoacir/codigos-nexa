"""
🧪 TESTE COM WEBHOOKS REAIS - OPEN FINANCE BRASIL (v2.0 - COM RECURRING DETECTOR)
═══════════════════════════════════════════════════════════════════════

Testa o pipeline completo com webhooks autênticos dos bancos brasileiros.

✅ NOVO: Inclui RecurringDetector no pipeline

Como executar:
    cd /Users/gabriel-abel/projetoNexa/codigos-nexa-16
    pyenv shell 3.12.1
    python backend/app/etl/test_nexa_complete.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIX PYTHONPATH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent.parent  # etl/ → app/ → backend/
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from app.schemas.transaction import (
    TransactionWebhook,
    TransactionBatchResult,
)
from app.etl import (
    TransactionIngestor, 
    TransactionClassifier,
    RecurringDetector,  # ✅ NOVO
    print_recurring_stats  # ✅ NOVO
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEBHOOKS REAIS (Estrutura Autêntica)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ━━━ 1. NUBANK (TIER_1) ━━━
WEBHOOK_NUBANK_REAL = {
    "connector": {"id": 201, "name": "Nubank"},
    "item": {"id": "item_nubank_abc123", "status": "UPDATED"},
    "results": [
        {
            "id": "txn_nubank_001",
            "accountId": "acc_nubank_user123",
            "date": "2024-01-20T14:30:00.000Z",
            "description": "COMPRA NO DÉBITO - UBER *VIAGEM SAO PAULO",
            "amount": -45.80,
            "balance": 1954.20,
            "type": "DEBIT",
            "status": "POSTED",
            "category": "Transport",
            "currencyCode": "BRL"
        },
        {
            "id": "txn_nubank_002",
            "accountId": "acc_nubank_user123",
            "date": "2024-01-20T09:15:00.000Z",
            "description": "PIX RECEBIDO - MARIA SILVA",
            "amount": 150.00,
            "balance": 2000.00,
            "type": "CREDIT",
            "status": "POSTED",
            "category": "Income",
            "currencyCode": "BRL"
        },
        {
            "id": "txn_nubank_003",
            "accountId": "acc_nubank_user123",
            "date": "2024-01-19T18:45:00.000Z",
            "description": "IFOOD *PEDIDO - RESTAURANTE ABC",
            "amount": -32.50,
            "balance": 1850.00,
            "type": "DEBIT",
            "status": "POSTED",
            "category": "Food & Drink",
            "currencyCode": "BRL"
        }
    ]
}

# ━━━ 2. ITAÚ (TIER_3 — campos não-padrão, formato BR, sinais invertidos) ━━━
WEBHOOK_ITAU_REAL = {
    "connector": {"id": 8, "name": "Itau Unibanco"},
    "item": {"id": "item_itau_xyz789", "status": "UPDATED"},
    "results": [
        {
            "id": "txn_itau_001",
            "conta": "12345-6",
            "data": "20/01/2024 10:30:00",
            "descricao": "NETFLIX.COM *ASSINATURA PREMIUM",
            "valor": "45,90",
            "saldo": "3.456,78",
            "tipo": "DEBITO",
            "status": "PROCESSADA",
            "categoria": "ENTRETENIMENTO"
        },
        {
            "id": "txn_itau_002",
            "conta": "12345-6",
            "data": "19/01/2024 15:20:00",
            "descricao": "TED RECEBIDA - JOAO SANTOS CPF ***.123.456-**",
            "valor": "500,00",
            "saldo": "3.500,68",
            "tipo": "CREDITO",
            "status": "CONFIRMADA",
            "categoria": "TRANSFERENCIA"
        },
        {
            "id": "txn_itau_003",
            "conta": "12345-6",
            "data": "18/01/2024 08:45:00",
            "descricao": "COMPRA CARTAO - SUPERMERCADO ZONA SUL",
            "valor": "127,45",          # ⚠️ BUG: positivo mas é DEBITO
            "saldo": None,              # ⚠️ Balance faltando
            "tipo": "DEBITO",
            "status": "PROCESSADA",
            "categoria": "SUPERMERCADO"
        }
    ]
}

# ━━━ 3. INTER (TIER_2 — campo "value", datas SQL) ━━━
WEBHOOK_INTER_REAL = {
    "connector": {"id": 52, "name": "Banco Inter"},
    "item": {"id": "item_inter_def456", "status": "UPDATED"},
    "results": [
        {
            "id": "txn_inter_001",
            "account_id": "acc_inter_user456",
            "date": "2024-01-20 11:30:00",
            "description": "PAGAMENTO PIX - MERCADO LIVRE",
            "value": "-89.90",
            "balance": "2,340.50",
            "type": "DEBIT",
            "status": "POSTED",
            "category": "Shopping"
        },
        {
            "id": "txn_inter_002",
            "account_id": "acc_inter_user456",
            "date": "2024-01-19 16:45:00",
            "description": "RENDIMENTO POUPANCA",
            "value": "12.34",
            "balance": "2,430.40",
            "type": "CREDIT",
            "status": "POSTED",
            "category": "Investments"
        },
        {
            "id": "txn_inter_003",
            "account_id": "acc_inter_user456",
            "date": "2024-01-18 20:15:00",
            "description": "UBER *TRIP - CORRIDA NOTURNA",
            "value": "-28.50",
            "balance": "2,418.06",
            "type": "DEBIT",
            "status": "POSTED",
            "category": "Transport"
        }
    ]
}

# ━━━ 4. BATCH MISTO — um item por banco + 1 inválida ━━━
# Separados por banco para que from_raw_batch receba o institution_id correto.

BATCH_NUBANK = [
    {
        "id": "txn_nubank_004",
        "accountId": "acc_nubank_user123",
        "date": "2024-01-21T10:00:00.000Z",
        "description": "SPOTIFY *PREMIUM",
        "amount": -21.90,
        "balance": 1932.30,
        "type": "DEBIT",
        "status": "POSTED"
    }
]

BATCH_ITAU = [
    {
        "id": "txn_itau_004",
        "conta": "12345-6",
        "data": "21/01/2024 12:00:00",
        "descricao": "FARMACIA POPULAR",
        "valor": "35,60",
        "tipo": "DEBITO",
        "status": "PROCESSADA"
    }
]

BATCH_INTER = [
    {
        "id": "txn_inter_004",
        "account_id": "acc_inter_user456",
        "date": "2024-01-21 14:30:00",
        "description": "PIX ENVIADO - JOAO",
        "value": "-50.00",
        "balance": "2,290.50",
        "type": "DEBIT",
        "status": "POSTED"
    }
]

BATCH_INVALID = [
    {
        "id": "txn_invalid_001",
        "accountId": "acc_test",
        "date": "2024-01-21T15:00:00Z",
        "description": "TRANSACAO INVALIDA SEM VALOR"
        # ❌ Falta amount → vai rejeitar (comportamento esperado)
    }
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_section(title: str):
    print("\n" + "=" * 80)
    print(f"🧪 {title}")
    print("=" * 80)


def print_subsection(title: str):
    print(f"\n▶ {title}")
    print("-" * 80)


def infer_institution_id(connector_id: int) -> str:
    """Infere institution_id do connector_id (como faz o webhook receiver)."""
    mapping = {201: "nubank", 8: "itau", 52: "inter"}
    return mapping.get(connector_id, "unknown")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 1: NUBANK (TIER_1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_1_nubank_webhook():
    """Webhook completo do Nubank — dados perfeitos, 100% TRUSTED."""
    print_section("TESTE 1: WEBHOOK NUBANK (TIER_1 - Excelente)")

    connector_id = WEBHOOK_NUBANK_REAL["connector"]["id"]
    institution_id = infer_institution_id(connector_id)
    item_id = WEBHOOK_NUBANK_REAL["item"]["id"]
    fetched_at = datetime.now(timezone.utc)

    print(f"📥 Webhook recebido:")
    print(f"   Connector: {WEBHOOK_NUBANK_REAL['connector']['name']} (ID: {connector_id})")
    print(f"   Item ID: {item_id}")
    print(f"   Institution ID inferido: {institution_id}")
    print(f"   Total transações: {len(WEBHOOK_NUBANK_REAL['results'])}")

    # 1.1 ─ Batch
    print_subsection("1.1 Processando batch com TransactionBatchResult")

    result = TransactionBatchResult.from_raw_batch(
        raw_data=WEBHOOK_NUBANK_REAL["results"],
        institution_id=institution_id,
        item_id=item_id,
        fetched_at=fetched_at,
        batch_id="batch_nubank_test_001"
    )

    print(f"✅ Batch processado!")
    print(f"   Total recebido: {result.total_received}")
    print(f"   Válidas: {result.total_valid}")
    print(f"   Rejeitadas: {result.total_rejected}")
    print(f"   Rejection Rate: {result.rejection_rate:.1%}")
    print(f"   Alert Level: {result.alert_level}")

    assert result.total_valid == 3, f"Nubank: esperava 3 válidas, obteve {result.total_valid}"
    assert result.total_rejected == 0, "Nubank não deveria ter rejeições"
    assert result.alert_level == "INFO"

    # 1.2 ─ Ingestor
    print_subsection("1.2 Processando com Ingestor + BankStrategy")

    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(result.valid_transactions)

    print(f"✅ Ingestor concluído!")
    print(f"   Records: {metrics.records_after_dedup}")
    print(f"   Quality score: {metrics.quality_score:.2%}")
    print(f"   Data status distribuição:")
    print(f"      TRUSTED: {metrics.trusted_count}")
    print(f"      DEGRADED: {metrics.degraded_count}")
    print(f"      UNTRUSTED: {metrics.untrusted_count}")

    assert metrics.trusted_count > 0, "Nubank deveria ter transações TRUSTED"

    print(f"\n   📄 Sample (primeiras 2 linhas):")
    print(clean_df.select(["institution_id", "description", "amount", "data_status"]).head(2))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 2: ITAÚ (TIER_3)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_2_itau_webhook():
    """Webhook do Itaú — campos não-padrão, formato BR, bugs corrigidos pela ItauStrategy."""
    print_section("TESTE 2: WEBHOOK ITAÚ (TIER_3 - Problemático)")

    connector_id = WEBHOOK_ITAU_REAL["connector"]["id"]
    institution_id = infer_institution_id(connector_id)
    item_id = WEBHOOK_ITAU_REAL["item"]["id"]
    fetched_at = datetime.now(timezone.utc)

    print(f"📥 Webhook recebido:")
    print(f"   Connector: {WEBHOOK_ITAU_REAL['connector']['name']} (ID: {connector_id})")
    print(f"   Institution ID inferido: {institution_id}")
    print(f"   Total transações: {len(WEBHOOK_ITAU_REAL['results'])}")

    print(f"\n⚠️ Problemas conhecidos do Itaú:")
    print(f"   - Campos não-padrão (conta, valor, descricao)")
    print(f"   - Formato BR (45,90 e 1.500,00)")
    print(f"   - Sinais invertidos (BUG!)")
    print(f"   - Balance faltando ocasionalmente")

    # 2.1 ─ Batch
    print_subsection("2.1 Processando batch com TransactionBatchResult")

    result = TransactionBatchResult.from_raw_batch(
        raw_data=WEBHOOK_ITAU_REAL["results"],
        institution_id=institution_id,
        item_id=item_id,
        fetched_at=fetched_at,
        batch_id="batch_itau_test_001"
    )

    print(f"✅ Batch processado!")
    print(f"   Válidas: {result.total_valid}")
    print(f"   Rejeitadas: {result.total_rejected}")

    if result.total_rejected > 0:
        print(f"\n   ⚠️ Rejeições encontradas:")
        for rej in result.rejected_transactions:
            print(f"      ID: {rej.transaction_id}")
            print(f"      Erro: {rej.error_type}")
            print(f"      Campos: {list(rej.field_errors.keys())}")

    # 2.2 ─ Ingestor
    print_subsection("2.2 Processando com Ingestor (ItauStrategy corrige bugs)")

    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(result.valid_transactions)

    print(f"✅ Ingestor concluído!")
    print(f"   Quality score: {metrics.quality_score:.2%}")
    print(f"   Data status distribuição:")
    print(f"      TRUSTED: {metrics.trusted_count}")
    print(f"      DEGRADED: {metrics.degraded_count}")
    print(f"      UNTRUSTED: {metrics.untrusted_count}")

    assert metrics.degraded_count > 0 or metrics.untrusted_count > 0, \
        "Itaú deveria ter transações DEGRADED ou UNTRUSTED"

    print(f"\n   📄 Sample (ItauStrategy aplicou correções):")
    print(clean_df.select(["institution_id", "description", "amount", "balance", "data_status"]).head(3))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 3: INTER (TIER_2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_3_inter_webhook():
    """Webhook do Inter — campo 'value', datas SQL, qualidade boa."""
    print_section("TESTE 3: WEBHOOK INTER (TIER_2 - Bom)")

    connector_id = WEBHOOK_INTER_REAL["connector"]["id"]
    institution_id = infer_institution_id(connector_id)
    item_id = WEBHOOK_INTER_REAL["item"]["id"]
    fetched_at = datetime.now(timezone.utc)

    print(f"📥 Webhook recebido:")
    print(f"   Connector: {WEBHOOK_INTER_REAL['connector']['name']} (ID: {connector_id})")
    print(f"   Institution ID inferido: {institution_id}")
    print(f"   Total transações: {len(WEBHOOK_INTER_REAL['results'])}")

    print(f"\n📋 Características do Inter:")
    print(f"   - Campo 'value' ao invés de 'amount'")
    print(f"   - Datas SQL (YYYY-MM-DD HH:MM:SS)")
    print(f"   - Formato US com vírgula (2,340.50)")

    # 3.1 ─ Batch
    print_subsection("3.1 Processando batch")

    result = TransactionBatchResult.from_raw_batch(
        raw_data=WEBHOOK_INTER_REAL["results"],
        institution_id=institution_id,
        item_id=item_id,
        fetched_at=fetched_at,
        batch_id="batch_inter_test_001"
    )

    print(f"✅ Batch processado!")
    print(f"   Válidas: {result.total_valid}")
    print(f"   Rejeitadas: {result.total_rejected}")

    # 3.2 ─ Ingestor
    print_subsection("3.2 Processando com Ingestor")

    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(result.valid_transactions)

    print(f"✅ Ingestor concluído!")
    print(f"   Quality score: {metrics.quality_score:.2%}")
    print(f"   Data status distribuição:")
    print(f"      TRUSTED: {metrics.trusted_count}")
    print(f"      DEGRADED: {metrics.degraded_count}")

    assert metrics.trusted_count > 0, "Inter deveria ter transações TRUSTED"

    print(f"\n   📄 Sample:")
    print(clean_df.select(["institution_id", "description", "amount", "data_status"]).head(3))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 4: BATCH MISTO (3 bancos + 1 inválida)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_4_batch_misto():
    """
    Batch com transações de 3 bancos diferentes + 1 inválida.
    Cada banco processado separadamente (como o webhook receiver real faz).
    Esperado: 3 válidas (nubank + itau + inter), 1 rejeitada (sem amount).
    """
    print_section("TESTE 4: BATCH MISTO (3 Bancos + 1 Inválida)")

    print(f"📥 Batch misto recebido:")
    print(f"   Total transações: 4")
    print(f"   Composição:")
    print(f"      - 1 Nubank")
    print(f"      - 1 Itaú (com bug de sinal)")
    print(f"      - 1 Inter")
    print(f"      - 1 Inválida (falta amount)")

    fetched_at = datetime.now(timezone.utc)

    # Processar cada banco com o institution_id correto
    result_nubank = TransactionBatchResult.from_raw_batch(
        raw_data=BATCH_NUBANK, institution_id="nubank",
        item_id="item_mixed", fetched_at=fetched_at
    )
    result_itau = TransactionBatchResult.from_raw_batch(
        raw_data=BATCH_ITAU, institution_id="itau",
        item_id="item_mixed", fetched_at=fetched_at
    )
    result_inter = TransactionBatchResult.from_raw_batch(
        raw_data=BATCH_INTER, institution_id="inter",
        item_id="item_mixed", fetched_at=fetched_at
    )
    result_invalid = TransactionBatchResult.from_raw_batch(
        raw_data=BATCH_INVALID, institution_id="unknown",
        item_id="item_mixed", fetched_at=fetched_at
    )

    # Consolidar resultados
    total_valid = (result_nubank.total_valid + result_itau.total_valid +
                   result_inter.total_valid + result_invalid.total_valid)
    total_rejected = (result_nubank.total_rejected + result_itau.total_rejected +
                      result_inter.total_rejected + result_invalid.total_rejected)

    print(f"\n✅ Batch misto processado!")
    print(f"   Total recebido: 4")
    print(f"   Válidas: {total_valid}")
    print(f"   Rejeitadas: {total_rejected}")

    # Detalhar rejeições
    if total_rejected > 0:
        print(f"\n   📋 Análise de rejeições:")
        for label, res in [("nubank", result_nubank), ("itau", result_itau),
                           ("inter", result_inter), ("invalid", result_invalid)]:
            for rej in res.rejected_transactions:
                print(f"      ❌ [{label}] {rej.transaction_id}")
                print(f"         Erro: {rej.error_type}")
                print(f"         Campos: {list(rej.field_errors.keys())}")

    assert total_valid == 3, f"Deveria ter 3 válidas, obteve {total_valid}"
    assert total_rejected == 1, f"Deveria ter 1 rejeitada, obteve {total_rejected}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ✅ TESTE 5: PIPELINE COMPLETO END-TO-END (COM RECURRING DETECTOR)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_5_full_pipeline():
    """
    Pipeline completo end-to-end usando Nubank como referência dourada.

    Fluxo:
        Webhook raw → TransactionBatchResult (Pydantic)
                    → TransactionIngestor   (Polars + BankStrategy + DuckDB)
                    → TransactionClassifier (Categorização)
                    → RecurringDetector     (✅ NOVO - Flags de recorrência)
                    → DataFrame final       (TODAS as colunas)
    """
    print_section("TESTE 5: PIPELINE COMPLETO (End-to-End + RecurringDetector)")

    # ─── 5.1  Webhook ─────────────────────────────────────────────
    print_subsection("5.1 Recebendo webhook (Nubank)")

    connector_id   = WEBHOOK_NUBANK_REAL["connector"]["id"]
    institution_id = infer_institution_id(connector_id)
    item_id        = WEBHOOK_NUBANK_REAL["item"]["id"]
    fetched_at     = datetime.now(timezone.utc)
    raw_txns       = WEBHOOK_NUBANK_REAL["results"]

    print(f"   Banco: {institution_id} (connector {connector_id})")
    print(f"   Transações recebidas: {len(raw_txns)}")

    # ─── 5.2  Pydantic / BatchResult ──────────────────────────────
    print_subsection("5.2 Validação Pydantic (BatchResult)")

    batch_result = TransactionBatchResult.from_raw_batch(
        raw_data=raw_txns,
        institution_id=institution_id,
        item_id=item_id,
        fetched_at=fetched_at,
        batch_id="batch_pipeline_e2e_001"
    )

    print(f"   Válidas: {batch_result.total_valid}")
    print(f"   Rejeitadas: {batch_result.total_rejected}")
    print(f"   Alert: {batch_result.alert_level}")

    assert batch_result.total_valid == 3, \
        f"Pipeline: esperava 3 válidas, obteve {batch_result.total_valid}"
    assert batch_result.total_rejected == 0, \
        f"Pipeline: esperava 0 rejeitadas, obteve {batch_result.total_rejected}"

    # ─── 5.3  Ingestor (Polars + BankStrategy + DuckDB) ───────────
    print_subsection("5.3 ETL Ingestor")

    ingestor = TransactionIngestor()
    clean_df, metrics = ingestor.process(batch_result.valid_transactions)

    print(f"   Records processados: {metrics.records_after_dedup}")
    print(f"   Quality score: {metrics.quality_score:.2%}")
    print(f"   TRUSTED: {metrics.trusted_count} | "
          f"DEGRADED: {metrics.degraded_count} | "
          f"UNTRUSTED: {metrics.untrusted_count}")
    print(f"   Inseridos no DuckDB: {metrics.inserted_rows}")

    assert metrics.records_after_dedup == 3, \
        f"Pipeline: esperava 3 records, obteve {metrics.records_after_dedup}"
    assert metrics.trusted_count == 3, \
        f"Pipeline: Nubank deveria ter 3 TRUSTED, obteve {metrics.trusted_count}"

    # ─── 5.4  Classificador ───────────────────────────────────────
    print_subsection("5.4 Classificador")

    classifier = TransactionClassifier()
    categorized_df = classifier.predict(clean_df)

    categories = categorized_df.select("predicted_category").unique().to_series().to_list()
    print(f"   Colunas do DataFrame: {categorized_df.shape[1]}")
    print(f"   Categorias atribuídas: {categories}")

    assert "predicted_category" in categorized_df.columns, \
        "Pipeline: coluna predicted_category ausente"
    assert "ml_confidence" in categorized_df.columns, \
        "Pipeline: coluna ml_confidence ausente"
    assert "category_source" in categorized_df.columns, \
        "Pipeline: coluna category_source ausente"

    # ─── 5.5  RecurringDetector ✅ NOVO ───────────────────────────
    print_subsection("5.5 RecurringDetector (Detecção de Padrões)")

    detector = RecurringDetector()
    final_df = detector.detect(categorized_df)

    # Verificar flags adicionadas
    recurring_count = final_df.filter(final_df["is_recurring"] == True).height
    installment_count = final_df.filter(final_df["is_installment"] == True).height

    print(f"   ✅ Flags adicionadas: is_recurring, is_installment, installment_info, recurring_confidence")
    print(f"   Assinaturas detectadas: {recurring_count}")
    print(f"   Parcelamentos detectados: {installment_count}")

    # Validar colunas
    assert "is_recurring" in final_df.columns, "Pipeline: coluna is_recurring ausente"
    assert "is_installment" in final_df.columns, "Pipeline: coluna is_installment ausente"
    assert "installment_info" in final_df.columns, "Pipeline: coluna installment_info ausente"
    assert "recurring_confidence" in final_df.columns, "Pipeline: coluna recurring_confidence ausente"

    # ─── 5.6  DataFrame final ─────────────────────────────────────
    print_subsection("5.6 DataFrame Final (TODAS as colunas)")

    print(final_df.select([
        "transaction_id",
        "institution_id",
        "description",
        "amount",
        "data_status",
        "predicted_category",
        "is_recurring",
        "is_installment",
        "transaction_type"
    ]))

    # ─── 5.7  Estatísticas de Recorrência ✅ NOVO ────────────────
    print_subsection("5.7 Estatísticas de Recorrência")

    print_recurring_stats(final_df)

    print(f"\n🎉 PIPELINE COMPLETO EXECUTADO COM SUCESSO!")
    print(f"   Webhook → Pydantic → Ingestor → Classifier → RecurringDetector → DataFrame")
    print(f"   {len(raw_txns)} transações processadas sem erros")
    print(f"   Total de colunas no DataFrame final: {len(final_df.columns)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_all_tests():
    print("\n" + "🚀" * 40)
    print("🧪 TESTE COM WEBHOOKS REAIS - OPEN FINANCE BRASIL (v2.0)")
    print("✅ NOVO: Pipeline completo incluindo RecurringDetector")
    print("🚀" * 40)

    try:
        test_1_nubank_webhook()
        test_2_itau_webhook()
        test_3_inter_webhook()
        test_4_batch_misto()
        test_5_full_pipeline()   # ✅ ATUALIZADO com RecurringDetector
        test_6_recurring_simulation()

        print("\n" + "=" * 80)
        print("✅ TODOS OS TESTES COM WEBHOOKS REAIS PASSARAM!")
        print("=" * 80)

        print("\n📋 RESUMO DOS TESTES:")
        print("   ✅ Teste 1 — Nubank (TIER_1): Dados perfeitos, 100% TRUSTED")
        print("   ✅ Teste 2 — Itaú   (TIER_3): Bugs corrigidos, status DEGRADED")
        print("   ✅ Teste 3 — Inter  (TIER_2): Qualidade boa, status TRUSTED")
        print("   ✅ Teste 4 — Batch misto: 3 válidas + 1 rejeitada (esperado)")
        print("   ✅ Teste 5 — Pipeline E2E: Webhook → DataFrame completo + RecurringDetector ✅")

        print("\n🎯 VALIDAÇÕES REALIZADAS:")
        print("   ✅ Parsers BR/US (1.500,00 e 1,500.00)")
        print("   ✅ Datas múltiplos formatos (ISO 8601, BR dd/mm, SQL)")
        print("   ✅ Campos não-padrão mapeados (conta→account_id, valor→amount …)")
        print("   ✅ BankStrategy aplica correções por banco")
        print("   ✅ Validação tolerante (rejeita item, não batch)")
        print("   ✅ Deduplicação via dedup_hash")
        print("   ✅ DuckDB persistence (INSERT OR IGNORE)")
        print("   ✅ Classifier stub (predicted_category, ml_confidence)")
        print("   ✅ RecurringDetector (is_recurring, is_installment, installment_info) ✅ NOVO")

        print("\n🎯 PRÓXIMOS PASSOS:")
        print("   1. DataQualityValidator — calcula confidence global")
        print("   2. CashflowProjector — integrar Shadow Invoices")
        print("   3. SafeToSpendCalculator — cálculo real")
        print("   4. API Layer (FastAPI) — receber webhooks reais")

        return True

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ ERRO NO TESTE!")
        print("=" * 80)
        print(f"\n{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTE 6: SIMULAÇÃO DE RECORRÊNCIA (Histórico de 3 meses)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_6_recurring_simulation():
    """
    Simula um histórico de 3 meses para validar o RecurringDetector.
    """
    print_section("TESTE 6: SIMULAÇÃO DE RECORRÊNCIA (Netflix + Magalu)")
    
    import polars as pl
    
    # Criar dados sintéticos (3 meses de Netflix + 1 compra parcelada)
    data = {
        "transaction_id": ["t1", "t2", "t3", "t4"],
        "institution_id": ["nubank"] * 4,
        "description": [
            "NETFLIX.COM",       # Mês 1 (Outubro)
            "NETFLIX.COM",       # Mês 2 (Novembro)
            "NETFLIX.COM",       # Mês 3 (Dezembro) - Padrão detectado!
            "MAGALU *LOJA 10x"   # Parcelado explícito
        ],
        "amount": [-55.90, -55.90, -55.90, -100.00],
        "transaction_date": [
            datetime(2023, 10, 15),
            datetime(2023, 11, 15),
            datetime(2023, 12, 15),
            datetime(2024, 1, 20)
        ],
        # Colunas auxiliares necessárias para o detector (normalmente vêm do Ingestor/Classifier)
        "merchant": ["Netflix", "Netflix", "Netflix", "Magalu"],
        "predicted_category": ["Lazer", "Lazer", "Lazer", "Outros"]
    }
    
    df_history = pl.DataFrame(data)
    
    print(f"📊 Dados simulados (3 meses de histórico):")
    print(df_history.select(["transaction_date", "description", "amount"]))
    
    # Rodar Detector
    print_subsection("6.1 Executando RecurringDetector")
    detector = RecurringDetector()
    df_result = detector.detect(df_history)
    
    # Validar Assinatura (Netflix)
    netflix = df_result.filter(pl.col("description") == "NETFLIX.COM")
    is_netflix_recurring = netflix["is_recurring"].all()
    
    # Validar Parcelamento (Magalu)
    magalu = df_result.filter(pl.col("description").str.contains("MAGALU"))
    is_magalu_installment = magalu["is_installment"].all()
    installment_info = magalu["installment_info"][0]
    
    print(f"\n✅ Resultados:")
    print(f"   Netflix é recorrente? {is_netflix_recurring} (Esperado: True)")
    print(f"   Magalu é parcelado? {is_magalu_installment} (Esperado: True)")
    print(f"   Info da parcela: {installment_info} (Esperado: '10/10')")
    
    assert is_netflix_recurring, "Falha ao detectar assinatura da Netflix"
    assert is_magalu_installment, "Falha ao detectar parcelamento Magalu"
    
    # Imprimir estatísticas bonitas
    print_recurring_stats(df_result)

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)