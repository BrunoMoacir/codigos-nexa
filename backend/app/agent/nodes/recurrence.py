from app.core.recurrence import detect_recurring_transactions

def recurrence_node(state):
    recurring = detect_recurring_transactions(state["transactions"])
    state["recurring"] = recurring
    return state
