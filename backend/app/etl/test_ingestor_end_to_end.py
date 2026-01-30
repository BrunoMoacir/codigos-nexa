"""
test_ingestor_end_to_end.py - Teste completo do TransactionIngestor

Execute:
    python -m pytest app/etl/test_ingestor_end_to_end.py -v
"""

from datetime import datetime, timezone
import polars as pl
from app.etl.ingestor import TransactionIngestor
from app.schemas.transaction import TransactionWebhook


def test_ingestor_full_pipeline():
    """
    Testa pipeline completo do Ingestor:
        1. Recebe TransactionWebhook
        2. Limpa e normaliza
        3. Deduplica
        4. Enriquece colunas
        5. Retorna DataFrame + Métricas
    """
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. CRIAR TRANSAÇÕES DE TESTE (validadas pelo Pydantic)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    transactions = [
        # Transação Nubank
        TransactionWebhook(
            transaction_id="txn_nubank_1",
            amount=-45.0,
            transaction_date="2024-01-20T10:30:00Z",
            description="  UBER TRIP  ",  # Com espaços (vai normalizar)
            balance=1500.0,
            account_id="acc_nubank",
            institution_id="nubank",
            item_id="item_123",
            fetched_at=datetime.now(timezone.utc)
        ),
        
        # Transação Itaú
        TransactionWebhook(
            transaction_id="txn_itau_1",
            amount=-50.0,
            transaction_date="2024-01-21T08:00:00Z",
            description="UBER VIAGEM",
            balance=1450.0,
            account_id="acc_itau",
            institution_id="itau",
            item_id="item_456",
            fetched_at=datetime.now(timezone.utc)
        ),
        
        # Duplicata (vai ser removida)
        TransactionWebhook(
            transaction_id="txn_nubank_1_duplicate",
            amount=-45.0,  # Mesmo amount
            transaction_date="2024-01-20T10:30:00Z",  # Mesma data
            description="  UBER TRIP SAO PAULO  ",  # Primeiros 20 chars iguais
            balance=1500.0,
            account_id="acc_nubank",  # Mesma conta
            institution_id="nubank",
            item_id="item_123",
            fetched_at=datetime.now(timezone.utc)
        ),
    ]
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. PROCESSAR COM INGESTOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    ingestor = TransactionIngestor()  # ✅ Sem argumentos
    clean_df, metrics = ingestor.process(transactions)  # ✅ Método correto
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. ASSERTS - ESTRUTURA DO DATAFRAME
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # DataFrame deve ser Polars, não Pandas
    assert isinstance(clean_df, pl.DataFrame), "Deve retornar pl.DataFrame"
    
    # Deve ter removido 1 duplicata (3 transações → 2 únicas)
    assert len(clean_df) == 2, f"Esperava 2 transações, mas tem {len(clean_df)}"
    
    # Colunas obrigatórias devem existir
    required_columns = [
        "transaction_id",
        "amount",
        "description",
        "institution_id",
        "month",  # Enriquecida
        "day_of_week",  # Enriquecida
        "transaction_type"  # Enriquecida
    ]
    
    for col in required_columns:
        assert col in clean_df.columns, f"Coluna '{col}' não existe no DataFrame"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. ASSERTS - MÉTRICAS DE QUALIDADE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    assert metrics.total_records == 3, "Total de transações recebidas"
    assert metrics.duplicates_removed == 1, "Deve ter removido 1 duplicata"
    assert metrics.records_after_dedup == 2, "Deve ter 2 transações únicas"
    
    # Quality score = 2/3 = 0.6666...
    assert 0.65 <= metrics.quality_score <= 0.67, \
        f"Quality score esperado ~0.66, mas foi {metrics.quality_score}"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. ASSERTS - NORMALIZAÇÃO DE TEXTO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # Pega primeira transação (Nubank)
    first_row = clean_df.row(0, named=True)
    
    # Description deve estar normalizada (lowercase, sem espaços extras)
    assert first_row["description"] == "uber trip", \
        f"Texto não normalizado: '{first_row['description']}'"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. ASSERTS - COLUNAS ENRIQUECIDAS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # month deve ser 1 (janeiro)
    assert first_row["month"] == 1, f"Mês esperado: 1, mas foi {first_row['month']}"
    
    # transaction_type deve ser DEBIT (amount negativo)
    assert first_row["transaction_type"] == "DEBIT", \
        f"Tipo esperado: DEBIT, mas foi {first_row['transaction_type']}"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. ASSERTS - TIPOS DE DADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # amount deve ser Float64 (não Decimal)
    assert clean_df["amount"].dtype == pl.Float64, \
        f"amount deve ser Float64, mas é {clean_df['amount'].dtype}"
    
    # balance deve ser Float64
    assert clean_df["balance"].dtype == pl.Float64, \
        f"balance deve ser Float64, mas é {clean_df['balance'].dtype}"
    
    print("✅ Todos os testes passaram!")