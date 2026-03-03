# tests/test_subscription_detector.py
# Testes para M1.5 — Detecção de Assinaturas Esquecidas

import datetime
import pytest
import polars as pl

from app.etl.subscription_detector import (
    SubscriptionDetector,
    AlertReason,
    detect_subscriptions,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _df(rows: list[dict]) -> pl.DataFrame:
    """Cria DataFrame de transações no formato da F1."""
    return pl.DataFrame({
        "date":        [r["date"] for r in rows],
        "amount":      [r["amount"] for r in rows],
        "description": [r["description"] for r in rows],
        "category":    [r.get("category", "Outros") for r in rows],
    })


def _monthly(description: str, amount: float, months: int, start_day: int = 15) -> list[dict]:
    """Gera `months` cobranças mensais negativas (despesas) do mesmo merchant."""
    today = datetime.date.today()
    rows = []
    for i in range(months):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        d = min(start_day, 28)
        rows.append({
            "date": datetime.date(y, m, d),
            "amount": -amount,
            "description": description,
        })
    return rows


# ── Testes: detecção de recorrência ──────────────────────────────────────────

def test_detects_stable_recurring():
    """Assinatura com mesmo valor por 4 meses deve ser detectada."""
    rows = _monthly("Netflix", 55.90, 4)
    report = detect_subscriptions(_df(rows), user_id="u1")
    assert report.total_subscriptions >= 1
    names = [s.merchant for s in report.subscriptions]
    assert any("netflix" in n for n in names)


def test_no_subscription_with_single_occurrence():
    """Cobrança única não pode ser classificada como assinatura."""
    rows = [{"date": datetime.date.today(), "amount": -55.90, "description": "Netflix"}]
    report = detect_subscriptions(_df(rows), user_id="u1")
    assert report.total_subscriptions == 0


def test_no_subscription_when_all_same_month():
    """Múltiplas cobranças no mesmo mês (ex: semanal) não são assinatura mensal."""
    today = datetime.date.today()
    rows = [
        {"date": datetime.date(today.year, today.month, d), "amount": -55.90, "description": "Netflix"}
        for d in [1, 8, 15, 22]
    ]
    report = detect_subscriptions(_df(rows), user_id="u1")
    # Todas no mesmo mês → nenhuma assinatura mensal
    assert report.total_subscriptions == 0


def test_ignores_positive_transactions():
    """Entradas (valor positivo) não devem ser analisadas."""
    rows = _monthly("Netflix", 55.90, 4)   # _monthly já gera amount negativo
    # Adicionar receita com mesmo nome (positivo)
    rows_income = [
        {"date": datetime.date.today().replace(day=1), "amount": 200.0, "description": "Netflix"}
    ]
    df = _df(rows + rows_income)
    report = detect_subscriptions(df, user_id="u1")
    # O valor mensal deve ser 55.90, não confundir com a entrada positiva
    subs = [s for s in report.subscriptions if "netflix" in s.merchant]
    assert len(subs) >= 1
    assert subs[0].monthly_amount == pytest.approx(55.90, abs=1.0)


# ── Testes: heurísticas de alerta ─────────────────────────────────────────────

def test_alert_duplicate_category_three_streamings():
    """3 serviços de streaming → DUPLICATE_CATEGORY em todos os 3."""
    rows = (
        _monthly("Netflix", 55.90, 3)
        + _monthly("Disney+", 33.90, 3)
        + _monthly("Max HBO", 34.90, 3)
    )
    report = detect_subscriptions(_df(rows), user_id="u2")
    # Todos devem ter DUPLICATE_CATEGORY (ou ao menos 1 alertado)
    alerted_reasons = [r for a in report.alerted for r in a.alerts]
    assert AlertReason.DUPLICATE_CATEGORY in alerted_reasons


def test_no_alert_two_streamings():
    """2 serviços de streaming NÃO devem disparar DUPLICATE_CATEGORY (limiar é 3+)."""
    rows = _monthly("Netflix", 55.90, 3) + _monthly("Disney+", 33.90, 3)
    report = detect_subscriptions(_df(rows), user_id="u3")
    dup_alerts = [a for a in report.alerted if AlertReason.DUPLICATE_CATEGORY in a.alerts]
    assert len(dup_alerts) == 0


def test_alert_low_value():
    """Assinatura < R$15 → LOW_VALUE."""
    rows = _monthly("SomeApp Micro", 9.90, 4)
    report = detect_subscriptions(_df(rows), user_id="u4")
    alerted_reasons = [r for a in report.alerted for r in a.alerts]
    assert AlertReason.LOW_VALUE in alerted_reasons


def test_no_alert_low_value_above_threshold():
    """Assinatura R$20 não deve disparar LOW_VALUE."""
    rows = _monthly("SomeApp", 20.00, 4)
    report = detect_subscriptions(_df(rows), user_id="u4")
    lv_alerts = [a for a in report.alerted if AlertReason.LOW_VALUE in a.alerts]
    assert len(lv_alerts) == 0


def test_alert_price_increase():
    """Reajuste de >10% entre primeira e última cobrança → PRICE_INCREASE."""
    today = datetime.date.today()
    rows = []
    # 5 cobranças estáveis em R$30, depois sobe para R$40 (reajuste de 33%)
    for i in [6, 5, 4, 3, 2]:
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12; y -= 1
        rows.append({"date": datetime.date(y, m, 15), "amount": -30.0, "description": "SomeService"})
    # Cobrança recente: R$40
    rows.append({"date": today.replace(day=15), "amount": -40.0, "description": "SomeService"})

    report = detect_subscriptions(_df(rows), user_id="u5")
    alerted_reasons = [r for a in report.alerted for r in a.alerts]
    assert AlertReason.PRICE_INCREASE in alerted_reasons


def test_no_alert_small_price_variation():
    """Variação de 5% não deve disparar PRICE_INCREASE (limiar é 10%)."""
    today = datetime.date.today()
    rows = []
    for i in [3, 2, 1]:
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12; y -= 1
        amount = 55.90 if i == 3 else 58.00  # +3.7%
        rows.append({"date": datetime.date(y, m, 15), "amount": -amount, "description": "Netflix"})
    rows.append({"date": today.replace(day=15), "amount": -58.00, "description": "Netflix"})

    report = detect_subscriptions(_df(rows), user_id="u5")
    pi_alerts = [a for a in report.alerted if AlertReason.PRICE_INCREASE in a.alerts]
    assert len(pi_alerts) == 0


# ── Testes: edge cases ────────────────────────────────────────────────────────

def test_empty_dataframe():
    """DataFrame vazio → relatório vazio sem erro."""
    report = detect_subscriptions(pl.DataFrame(), user_id="empty")
    assert report.total_subscriptions == 0
    assert report.total_monthly_cost == 0.0


def test_summary_text_populated():
    """Com assinaturas detectadas, summary_text deve ser preenchido."""
    rows = _monthly("Netflix", 55.90, 4) + _monthly("Spotify", 21.90, 4)
    report = detect_subscriptions(_df(rows), user_id="u6")
    assert len(report.summary_text) > 20
    assert "assinatura" in report.summary_text.lower()


def test_total_monthly_cost_correct():
    """total_monthly_cost deve somar o valor mais recente de cada assinatura."""
    rows = _monthly("Netflix", 55.90, 3) + _monthly("Spotify", 21.90, 3)
    report = detect_subscriptions(_df(rows), user_id="u7")
    assert report.total_monthly_cost == pytest.approx(55.90 + 21.90, abs=1.0)


# ── Teste da API endpoint ─────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.v1.routes.subscriptions import router as sub_router

_app = FastAPI()
_app.include_router(sub_router)
_client = TestClient(_app)


def test_api_subscriptions_missing_user_id():
    """Chamada sem user_id na URL deve retornar 404 ou 405 (path não encontrado)."""
    response = _client.get("/subscriptions/")
    # FastAPI retorna 404 quando o path param está ausente
    assert response.status_code in (404, 405)
