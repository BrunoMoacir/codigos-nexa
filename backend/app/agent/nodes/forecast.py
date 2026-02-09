from app.cashflow.projector import CashflowProjector
from app.cashflow.safe_to_spend import SafeToSpendCalculator

def forecast_node(state):
    """Node do LangGraph que faz forecast."""
    
    # Usar CashflowProjector (implementação correta)
    projector = CashflowProjector(horizon_days=30)
    projection_df = projector.project(
        transactions_df=state["transactions_df"],
        shadow_invoices_df=state["shadow_invoices_df"]
    )
    
    # Calcular safe-to-spend
    calculator = SafeToSpendCalculator(safety_buffer_pct=0.15)
    sts_result = calculator.calculate(projection_df, horizon_days=30)
    
    # Atualizar state
    state["projection"] = projection_df
    state["safe_to_spend"] = sts_result
    
    return state