"backend/app/agent/nodes/recurrency.py"
from app.core.recurrence import detect_recurring

def recurrence_node(state):
    recurring = detect_recurring(state["transactions"])
    state["recurring"] = recurring
    return state
