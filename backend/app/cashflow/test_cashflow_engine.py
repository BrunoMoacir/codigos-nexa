from app.cashflow.engine import CashflowEngine
from app.simulation.bank_generator import BrazilianOpenFinanceRealisticGenerator
from app.etl.runner import run_full_etl_pipeline

def test_cashflow_engine_full():
    gen = BrazilianOpenFinanceRealisticGenerator(days=180)
    raw = gen.generate_all()

    df = run_full_etl_pipeline(raw)

    engine = CashflowEngine()
    result = engine.analyze(df)

    print(result)

    assert result["base"].current_balance > 0
    assert result["safe_to_spend"].risk_level in ["LOW", "MEDIUM", "HIGH"]
    assert len(result["forecast"].projection) == 30
