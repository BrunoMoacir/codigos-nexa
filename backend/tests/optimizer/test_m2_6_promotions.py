# tests/optimizer/test_m2_6_promotions.py
# Testes para M2.6 — Alertas de Promoções de Transferência Bonificada

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.optimizer.promotion_tracker import (
    PromotionTracker,
    TransferPromotion,
    PromotionAlert,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_promo(
    id: str = "test-promo",
    loyalty: str = "livelo",
    partner: str = "LATAM Pass",
    bonus_pct: float = 100.0,
    normal: float = 16.0,
    effective: float = 32.0,
    start_offset: int = -5,    # dias em relação a hoje
    end_offset: int = 10,
    min_points: int = 1000,
    max_points: int = None,
    eligible_cards: list = None,
) -> dict:
    today = date.today()
    return {
        "id": id,
        "loyalty_program": loyalty,
        "partner": partner,
        "bonus_pct": bonus_pct,
        "normal_rate_per_1000": normal,
        "effective_rate_per_1000": effective,
        "start_date": (today + timedelta(days=start_offset)).isoformat(),
        "end_date":   (today + timedelta(days=end_offset)).isoformat(),
        "min_points": min_points,
        "max_points": max_points,
        "eligible_cards": eligible_cards or ["Cartão Teste"],
        "description": "Promoção de teste",
        "source": "manual",
        "last_verified": today.isoformat(),
    }


def _make_tracker(promos: list[dict]) -> PromotionTracker:
    """Cria um PromotionTracker com arquivo JSON temporário."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(promos, f)
        path = Path(f.name)
    return PromotionTracker(data_path=path)


# ── Testes: TransferPromotion ─────────────────────────────────────────────────

def test_promo_is_active_today():
    p = _make_promo(start_offset=-1, end_offset=1)
    tracker = _make_tracker([p])
    assert len(tracker.get_active_promotions()) == 1


def test_promo_expired():
    p = _make_promo(start_offset=-10, end_offset=-1)
    tracker = _make_tracker([p])
    assert len(tracker.get_active_promotions()) == 0


def test_promo_not_started_yet():
    p = _make_promo(start_offset=5, end_offset=15)
    tracker = _make_tracker([p])
    assert len(tracker.get_active_promotions()) == 0


def test_include_expired_flag():
    active = _make_promo(id="active", start_offset=-1, end_offset=5)
    expired = _make_promo(id="expired", start_offset=-20, end_offset=-5)
    tracker = _make_tracker([active, expired])

    assert len(tracker.get_all_promotions(include_expired=False)) == 1
    assert len(tracker.get_all_promotions(include_expired=True)) == 2


def test_days_remaining_correct():
    today = date.today()
    p_raw = _make_promo(start_offset=-2, end_offset=7)
    tracker = _make_tracker([p_raw])
    promo = tracker.get_active_promotions()[0]
    assert promo.days_remaining == 7


def test_days_remaining_zero_for_expired():
    p = _make_promo(start_offset=-10, end_offset=-1)
    tracker = _make_tracker([p])
    all_promos = tracker.get_all_promotions(include_expired=True)
    assert all_promos[0].days_remaining == 0


# ── Testes: check_user_opportunities ─────────────────────────────────────────

def test_opportunity_match_card():
    """Usuário com cartão elegível e saldo suficiente → alerta."""
    promo = _make_promo(
        loyalty="livelo",
        partner="LATAM Pass",
        bonus_pct=100,
        normal=16.0,
        effective=32.0,
        min_points=1000,
        eligible_cards=["Inter Black"],
    )
    tracker = _make_tracker([promo])
    alerts = tracker.check_user_opportunities(
        user_cards=["Inter Black"],
        user_points_balance={"livelo": 10_000},
    )
    assert len(alerts) == 1
    assert alerts[0].user_card == "Inter Black"
    assert alerts[0].potential_value_promo == pytest.approx(320.0, abs=0.1)
    assert alerts[0].potential_value_normal == pytest.approx(160.0, abs=0.1)
    assert alerts[0].extra_value == pytest.approx(160.0, abs=0.1)


def test_opportunity_no_matching_card():
    """Usuário sem cartão elegível → nenhum alerta."""
    promo = _make_promo(eligible_cards=["Cartão Premium X"])
    tracker = _make_tracker([promo])
    alerts = tracker.check_user_opportunities(
        user_cards=["Cartão Comum"],
        user_points_balance={"livelo": 50_000},
    )
    assert len(alerts) == 0


def test_opportunity_below_min_points():
    """Saldo abaixo do mínimo → nenhum alerta."""
    promo = _make_promo(min_points=5000, eligible_cards=["Inter Black"])
    tracker = _make_tracker([promo])
    alerts = tracker.check_user_opportunities(
        user_cards=["Inter Black"],
        user_points_balance={"livelo": 2000},  # < 5000
    )
    assert len(alerts) == 0


def test_opportunity_respects_max_points():
    """Saldo maior que o limite máximo → calcula apenas com o max."""
    promo = _make_promo(
        normal=10.0,
        effective=20.0,
        min_points=1000,
        max_points=5000,
        eligible_cards=["Inter Black"],
    )
    tracker = _make_tracker([promo])
    alerts = tracker.check_user_opportunities(
        user_cards=["Inter Black"],
        user_points_balance={"livelo": 50_000},
    )
    assert len(alerts) == 1
    # Deve calcular com 5.000 pontos (max), não 50.000
    assert alerts[0].estimated_points == 5000
    assert alerts[0].potential_value_promo == pytest.approx(100.0, abs=0.1)


def test_opportunities_sorted_by_extra_value():
    """Alertas ordenados pelo valor extra decrescente."""
    promo_big = _make_promo(
        id="big",
        loyalty="livelo",
        normal=10.0,
        effective=30.0,       # extra grande
        eligible_cards=["Cartão A"],
    )
    promo_small = _make_promo(
        id="small",
        loyalty="smiles",
        normal=10.0,
        effective=12.0,       # extra pequeno
        eligible_cards=["Cartão B"],
    )
    tracker = _make_tracker([promo_small, promo_big])  # invertido
    alerts = tracker.check_user_opportunities(
        user_cards=["Cartão A", "Cartão B"],
        user_points_balance={"livelo": 10_000, "smiles": 10_000},
    )
    assert len(alerts) == 2
    assert alerts[0].extra_value > alerts[1].extra_value


def test_real_json_file_loads():
    """Verifica que o JSON de seed carrega sem erros e tem promoções."""
    real_tracker = PromotionTracker()  # usa _DATA_PATH padrão
    all_promos = real_tracker.get_all_promotions(include_expired=True)
    assert len(all_promos) >= 3  # temos 4 no seed


def test_alert_text_mentions_partner():
    """Texto do alerta deve citar o parceiro de destino."""
    promo = _make_promo(partner="LATAM Pass", eligible_cards=["Inter Black"])
    tracker = _make_tracker([promo])
    alerts = tracker.check_user_opportunities(
        user_cards=["Inter Black"],
        user_points_balance={"livelo": 10_000},
    )
    assert "LATAM Pass" in alerts[0].alert_text


def test_empty_tracker_no_error():
    """Tracker vazio não deve lançar erro."""
    tracker = _make_tracker([])
    assert tracker.get_active_promotions() == []
    assert tracker.check_user_opportunities(["Card X"], {"prog": 100}) == []


# ── Teste da API ──────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.optimizer.router import router as opt_router

_app = FastAPI()
_app.include_router(opt_router)
_client = TestClient(_app)


def test_api_list_promotions_returns_200():
    """GET /optimizer/promotions deve retornar 200."""
    resp = _client.get("/optimizer/promotions")
    assert resp.status_code == 200
    data = resp.json()
    assert "promotions" in data
    assert "total" in data


def test_api_list_promotions_include_expired():
    """?include_expired=true deve retornar mais itens."""
    r_active  = _client.get("/optimizer/promotions?include_expired=false")
    r_expired = _client.get("/optimizer/promotions?include_expired=true")
    assert r_expired.json()["total"] >= r_active.json()["total"]


def test_api_opportunities_missing_cards():
    """Sem cards → 422."""
    resp = _client.get("/optimizer/promotions/opportunities?user_id=u1&cards=")
    assert resp.status_code == 422


def test_api_opportunities_with_cards():
    """Com cards válidos → 200 e estrutura correta."""
    resp = _client.get(
        "/optimizer/promotions/opportunities"
        "?user_id=u1"
        "&cards=Inter Black"
        "&points_balance=smiles:20000,livelo:8000"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "opportunities" in data
    assert "alerted_count" in data
