from app.core.explain import explain_safe_to_spend


def test_explain_safe_to_spend_positive():
    result = {
        "days": 30,
        "buffer": 1000,
        "min_projected_balance": 2000,
        "safe_to_spend_total": 1500,
        "safe_to_spend_daily": 50
    }

    text = explain_safe_to_spend(result)

    assert "R$ 50" in text
    assert "buffer" in text.lower()
    assert "30 dias" in text


def test_explain_safe_to_spend_zero():
    result = {
        "safe_to_spend_daily": 0
    }

    text = explain_safe_to_spend(result)

    assert "não há margem segura" in text.lower()
