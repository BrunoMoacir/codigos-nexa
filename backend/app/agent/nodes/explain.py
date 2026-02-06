"backend/app/agent/nodes/explain.py"
from app.core.explain import explain_safe_to_spend

def explain_node(state: dict) -> dict:
    explanation = explain_safe_to_spend(
        state["safe_to_spend"]
    )

    state["explanation"] = explanation
    return state
