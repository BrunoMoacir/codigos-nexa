# tests/cashflow/test_m1_3_budget.py
# Testes para M1.3 — Orçamento Inteligente por Categoria

import pytest
from datetime import date
import polars as pl

from app.cashflow.budget_advisor import (
    BudgetAdvisor,
    BudgetSuggestion,
    CategoryAllocation,
    BudgetCut,
    GroupSummary,
    suggest_budget,
    _classify_category,
    ESSENTIALS,
    WANTS,
    SAVINGS,
    _STATUS_OVER,
    _STATUS_UNDER,
    _STATUS_OK,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_df(rows: list[dict]) -> pl.DataFrame:
    """Cria DataFrame de transações compatível com BudgetAdvisor."""
    return pl.DataFrame({
        "transaction_date": [r["date"] for r in rows],
        "amount":           [r["amount"] for r in rows],
        "category":         [r["category"] for r in rows],
    })


def _prev_month(n: int = 1) -> date:
    """Retorna uma data N meses atrás."""
    today = date.today()
    m = today.month - n
    y = today.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 15)


# ── Fixtures ─────────────────────────────────────────────────────────────────

INCOME = 8_000.0

def _build_typical_df() -> pl.DataFrame:
    """
    Simula 3 meses de gastos com padrão típico:
      - moradia R$2.800 → essenciais ~35%
      - alimentacao R$1.200 → essenciais ~15%
      - lazer R$2.400 → desejos ~30%
      - total essenciais ≈ 50%, desejos ≈ 30%, poupança ≈ 0%
    """
    rows = []
    for n in [1, 2, 3]:
        d = _prev_month(n)
        rows += [
            {"date": d, "amount": -2800.0, "category": "moradia"},
            {"date": d, "amount": -1200.0, "category": "alimentacao"},
            {"date": d, "amount": -800.0,  "category": "lazer"},
            {"date": d, "amount": -400.0,  "category": "vestuario"},
            {"date": d, "amount": -800.0,  "category": "restaurante"},
            {"date": d, "amount": 8000.0,  "category": "receita"},   # renda (ignorada)
        ]
    return _make_df(rows)


# ── 1. classify_category ─────────────────────────────────────────────────────

def test_classify_essentials():
    for cat in ["moradia", "alimentacao", "transporte", "saude", "educacao"]:
        assert _classify_category(cat) == "essenciais"


def test_classify_savings():
    for cat in ["investimentos", "poupanca", "previdencia"]:
        assert _classify_category(cat) == "poupanca"


def test_classify_wants_default():
    for cat in ["lazer", "vestuario", "restaurante", "xyz_desconhecido"]:
        assert _classify_category(cat) == "desejos"


# ── 2. BudgetSuggestion model ─────────────────────────────────────────────────

def test_budget_suggestion_to_dict_has_all_keys():
    advisor = BudgetAdvisor()
    df = _build_typical_df()
    sug = advisor.suggest(df, monthly_income=INCOME)

    d = sug.to_dict()
    expected_keys = {
        "income", "history_months", "total_expenses_avg",
        "expenses_pct_income", "savings_gap", "group_summary",
        "allocations", "actionable_cuts", "rule_applied",
        "summary_text", "confidence",
    }
    assert expected_keys.issubset(set(d.keys()))


def test_group_summary_has_three_groups():
    advisor = BudgetAdvisor()
    df = _build_typical_df()
    sug = advisor.suggest(df, monthly_income=INCOME)

    groups = {g.group for g in sug.group_summary}
    assert groups == {"essenciais", "desejos", "poupanca"}


# ── 3. Lógica 50/30/20 ──────────────────────────────────────────────────────

def test_only_expenses_counted():
    """Renda positiva não deve entrar no cálculo de despesas."""
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    # Se renda fosse contada, total seria positivo — deve ser só despesas
    assert sug.total_expenses_avg > 0
    # receita de R$8.000 não deve inflar o total
    assert sug.total_expenses_avg < INCOME * 1.5


def test_spending_pct_income_reasonable():
    """expenses_pct_income deve estar entre 0 e 2 (0% a 200%)."""
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    assert 0.0 <= sug.expenses_pct_income <= 2.0


def test_savings_gap_when_no_savings():
    """Sem categoria de poupança → savings_gap ≈ 20% da renda."""
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    poupanca_group = next(g for g in sug.group_summary if g.group == "poupanca")
    if poupanca_group.current_amount == 0:
        assert sug.savings_gap > 0  # gap existe pois não há poupança real


def test_essentials_over_when_moradia_heavy():
    """moradia R$4.000 → essenciais > 50% → status OVER."""
    rows = [
        {"date": _prev_month(n), "amount": amt, "category": cat}
        for n in [1, 2, 3]
        for cat, amt in [("moradia", -4500.0), ("lazer", -500.0)]
    ]
    df = _make_df(rows)
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    ess_group = next(g for g in sug.group_summary if g.group == "essenciais")
    assert ess_group.status == _STATUS_OVER


def test_wants_within_reasonable_spending():
    """Lazer < 30% da renda → desejos deve estar WITHIN ou UNDER."""
    # Apenas moradia (essencial) alta + lazer baixo
    rows = [
        {"date": _prev_month(n), "amount": amt, "category": cat}
        for n in [1, 2, 3]
        for cat, amt in [("moradia", -3000.0), ("lazer", -500.0)]
    ]
    df = _make_df(rows)
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    desejos = next(g for g in sug.group_summary if g.group == "desejos")
    # R$500/mês lazer = 6.25% de R$8k → UNDER
    assert desejos.status in {_STATUS_OK, _STATUS_UNDER}


def test_savings_investment_classified_correctly():
    """Transações em 'investimentos' devem ir para grupo poupança."""
    rows = [
        {"date": _prev_month(n), "amount": -2000.0, "category": "investimentos"}
        for n in [1, 2, 3]
    ]
    df = _make_df(rows)
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    poupanca = next(g for g in sug.group_summary if g.group == "poupanca")
    # R$2.000 investido / R$8.000 renda = 25% → OVER ou OK
    assert poupanca.current_amount > 0


# ── 4. Allocations ────────────────────────────────────────────────────────────

def test_allocations_not_empty():
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    assert len(sug.allocations) > 0


def test_allocations_sum_matches_total_expenses():
    """Soma das alocações deve bater com total_expenses_avg (tolerância R$0.10)."""
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    total_from_allocs = sum(a.current_amount for a in sug.allocations)
    assert abs(total_from_allocs - sug.total_expenses_avg) < 0.10


def test_allocation_has_valid_status():
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    valid = {_STATUS_OK, _STATUS_OVER, _STATUS_UNDER}
    for a in sug.allocations:
        assert a.status in valid


# ── 5. Actionable cuts ────────────────────────────────────────────────────────

def test_actionable_cuts_sorted_by_saving():
    """Cortes devem estar ordenados do maior para o menor saving."""
    rows = [
        {"date": _prev_month(n), "amount": amt, "category": cat}
        for n in [1, 2, 3]
        for cat, amt in [
            ("moradia", -4500.0),
            ("alimentacao", -2000.0),
            ("lazer", -800.0),
        ]
    ]
    df = _make_df(rows)
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    if len(sug.actionable_cuts) > 1:
        savings = [c.saving for c in sug.actionable_cuts]
        assert savings == sorted(savings, reverse=True)


def test_no_cut_when_spending_ok():
    """Gasto balanceado → zero cortes sugeridos."""
    rows = [
        {"date": _prev_month(n), "amount": amt, "category": cat}
        for n in [1, 2, 3]
        for cat, amt in [
            ("moradia", -2000.0),      # 25%
            ("alimentacao", -1200.0),  # 15% → essenciais total 40%
            ("lazer", -1000.0),        # 12.5% → desejos OK
            ("investimentos", -1600.0) # 20% → poupança OK
        ]
    ]
    df = _make_df(rows)
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    # Com gasto bem distribuído, não deve ter cortes em essenciais
    ess_cuts = [c for c in sug.actionable_cuts if c.group == "essenciais"]
    # Essenciais = 40% < 50% → sem corte em essenciais
    assert len(ess_cuts) == 0


# ── 6. Summary text ───────────────────────────────────────────────────────────

def test_summary_text_not_empty():
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    assert len(sug.summary_text) > 20


def test_summary_text_mentions_groups():
    df = _build_typical_df()
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    text = sug.summary_text.lower()
    assert "essenciais" in text or "desejos" in text or "poupança" in text


# ── 7. Edge cases ─────────────────────────────────────────────────────────────

def test_empty_df_returns_empty_suggestion():
    df = pl.DataFrame({"transaction_date": [], "amount": [], "category": []})
    sug = BudgetAdvisor().suggest(df, monthly_income=INCOME)
    assert sug.confidence == 0.0
    assert sug.total_expenses_avg == 0.0
    assert len(sug.allocations) == 0


def test_invalid_income_raises():
    df = _build_typical_df()
    with pytest.raises(ValueError):
        BudgetAdvisor().suggest(df, monthly_income=0.0)

    with pytest.raises(ValueError):
        BudgetAdvisor().suggest(df, monthly_income=-100.0)


def test_only_one_history_month():
    """Fallback: apenas 1 mês disponível → ainda retorna sugestão."""
    rows = [
        {"date": _prev_month(1), "amount": -2000.0, "category": "moradia"},
        {"date": _prev_month(1), "amount": -1000.0, "category": "lazer"},
    ]
    df = _make_df(rows)
    sug = BudgetAdvisor(history_months=3).suggest(df, monthly_income=INCOME)
    assert sug.history_months >= 1
    assert sug.total_expenses_avg > 0


def test_confidence_lower_with_less_history():
    """Confiança deve ser menor quando há menos histórico disponível."""
    rows_full = [
        {"date": _prev_month(n), "amount": -2000.0, "category": "moradia"}
        for n in [1, 2, 3]
    ]
    rows_partial = [
        {"date": _prev_month(1), "amount": -2000.0, "category": "moradia"},
    ]
    sug_full    = BudgetAdvisor(history_months=3).suggest(_make_df(rows_full), INCOME)
    sug_partial = BudgetAdvisor(history_months=3).suggest(_make_df(rows_partial), INCOME)
    assert sug_full.confidence >= sug_partial.confidence


# ── 8. suggest_budget convenience function ────────────────────────────────────

def test_suggest_budget_convenience():
    df = _build_typical_df()
    sug = suggest_budget(df, monthly_income=INCOME)
    assert isinstance(sug, BudgetSuggestion)
    assert sug.income == INCOME


# ── 9. API endpoint ───────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1.routes.budget import router as budget_router

_app = FastAPI()
_app.include_router(budget_router)
_client = TestClient(_app)


def test_api_missing_income():
    """Sem monthly_income → 422."""
    resp = _client.get("/budget/user_test")
    assert resp.status_code == 422


def test_api_zero_income():
    """monthly_income=0 → 422 (gt=0 via Query)."""
    resp = _client.get("/budget/user_test?monthly_income=0")
    assert resp.status_code == 422


def test_api_negative_income():
    """monthly_income negativo → 422 (gt=0 via Query)."""
    resp = _client.get("/budget/user_test?monthly_income=-100")
    assert resp.status_code == 422
