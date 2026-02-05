from langgraph.graph import StateGraph, END
from app.agent.state import FinancialState
from app.agent.nodes.recurrence import recurrence_node
from app.agent.nodes.forecast import forecast_node
from app.agent.nodes.explain import explain_node

def build_financial_agent():
    graph = StateGraph(FinancialState)

    graph.add_node("recurrence", recurrence_node)
    graph.add_node("forecast", forecast_node)
    graph.add_node("explain", explain_node)

    graph.set_entry_point("recurrence")
    graph.add_edge("recurrence", "forecast")
    graph.add_edge("forecast", "explain")
    graph.add_edge("explain", END)

    return graph.compile()
