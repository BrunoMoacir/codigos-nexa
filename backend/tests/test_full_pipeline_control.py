import polars as pl
from app.etl.ingestor import TransactionIngestor
from app.agent.builder import build_financial_agent


def test_full_pipeline_control_case():
    """
    Caso matematicamente controlado para detectar falso positivo.
    """

    raw = [
        {"date": "2026-01-01", "amount": 5000, "description": "SALARIO"},
        {"date": "2026-01-05", "amount": -1200, "description": "ALUGUEL"},
        {"date": "2026-01-10", "amount": -800, "description": "CARTAO"},
    ]

    df_raw = pl.DataFrame(raw)

    # Simula entrada no ETL
    ingestor = TransactionIngestor()
    df_clean = ingestor.process(df_raw)

    agent = build_financial_agent()

    result = agent.invoke({
        "transactions": df_clean
    })

    safe = result["safe_to_spend"]

    # 5000 - 1200 - 800 = 3000
    # buffer padrão = 1000 → safe = 2000 → diário ≈ 66

    assert safe["safe_to_spend_total"] >= 1900
    assert safe["safe_to_spend_daily"] >= 60
