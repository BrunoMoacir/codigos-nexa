# tests/optimizer/test_r4b_promotions_complete.py
# R4.b completo: staleness guard, matching por programa, engine → feed, tool

import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.optimizer.promotion_tracker import PromotionTracker


def _promo(tmp_path, **overrides):
    today = date.today()
    promo = {
        "id": "teste-livelo-smiles",
        "loyalty_program": "livelo",
        "partner": "GOL Smiles",
        "bonus_pct": 100,
        "normal_rate_per_1000": 16.0,
        "effective_rate_per_1000": 32.0,
        "start_date": (today - timedelta(days=2)).isoformat(),
        "end_date": (today + timedelta(days=5)).isoformat(),
        "min_points": 1000,
        "max_points": None,
        "eligible_cards": ["Bradesco Livelo"],
        "description": "teste",
        "source": "teste",
        "last_verified": today.isoformat(),
    }
    promo.update(overrides)
    path = tmp_path / "promos.json"
    path.write_text(json.dumps([promo]))
    return path


# ── staleness guard ──────────────────────────────────────────────────────────

def test_promocao_ativa_e_verificada_aparece(tmp_path):
    tracker = PromotionTracker(data_path=_promo(tmp_path))
    assert len(tracker.get_active_promotions()) == 1


def test_promocao_ativa_mas_curadoria_velha_nao_alerta(tmp_path):
    velha = (date.today() - timedelta(days=60)).isoformat()
    tracker = PromotionTracker(data_path=_promo(tmp_path, last_verified=velha))
    assert tracker.get_active_promotions() == []            # não alerta
    assert len(tracker.get_active_promotions(include_stale=True)) == 1  # API vê


def test_promocao_expirada_nunca_aparece(tmp_path):
    fim = (date.today() - timedelta(days=1)).isoformat()
    inicio = (date.today() - timedelta(days=10)).isoformat()
    tracker = PromotionTracker(data_path=_promo(tmp_path, start_date=inicio, end_date=fim))
    assert tracker.get_active_promotions(include_stale=True) == []


# ── matching por programa ────────────────────────────────────────────────────

def test_matching_por_programa_independe_do_nome_do_cartao(tmp_path):
    tracker = PromotionTracker(data_path=_promo(tmp_path))
    alerts = tracker.check_opportunities_by_program({"livelo": 20000})
    assert len(alerts) == 1
    a = alerts[0]
    # 20k pontos: normal R$320, promo R$640 → extra R$320
    assert a.extra_value == pytest.approx(320.0)


def test_abaixo_do_minimo_nao_alerta(tmp_path):
    tracker = PromotionTracker(data_path=_promo(tmp_path, min_points=50000))
    assert tracker.check_opportunities_by_program({"livelo": 20000}) == []


def test_programa_diferente_nao_alerta(tmp_path):
    tracker = PromotionTracker(data_path=_promo(tmp_path))
    assert tracker.check_opportunities_by_program({"esfera": 100000}) == []


def test_max_points_limita_transferencia(tmp_path):
    tracker = PromotionTracker(data_path=_promo(tmp_path, max_points=5000))
    alerts = tracker.check_opportunities_by_program({"livelo": 20000})
    assert alerts[0].estimated_points == 5000


# ── engine → feed (o fio R4.b) ───────────────────────────────────────────────

def test_engine_gera_transfer_promo_input(tmp_path, monkeypatch):
    from app.notifications.engine import NotificationEngine
    import app.optimizer.promotion_tracker as pt_module

    monkeypatch.setattr(pt_module, "_DATA_PATH", _promo(tmp_path))
    with patch.object(
        NotificationEngine, "_credit_spend_and_issuers",
        return_value=(4000.0, {"Bradesco"}),
    ):
        promos = NotificationEngine._detect_transfer_promos("user_r4b")

    assert len(promos) == 1
    p = promos[0]
    assert p.from_program == "livelo"          # Bradesco emite cartões Livelo
    assert p.to_program == "GOL Smiles"
    assert p.bonus_pct == pytest.approx(1.0)   # fração p/ o gerador de cards
    assert p.user_points == 4000 * 0.25 * 12   # estimativa conservadora


def test_engine_sem_emissor_do_programa_nao_alerta(tmp_path, monkeypatch):
    from app.notifications.engine import NotificationEngine
    import app.optimizer.promotion_tracker as pt_module

    monkeypatch.setattr(pt_module, "_DATA_PATH", _promo(tmp_path))
    with patch.object(
        NotificationEngine, "_credit_spend_and_issuers",
        return_value=(4000.0, {"Nubank"}),  # Nubank não acumula Livelo
    ):
        promos = NotificationEngine._detect_transfer_promos("user_r4b")
    assert promos == []


def test_engine_sem_gasto_nao_alerta(tmp_path, monkeypatch):
    from app.notifications.engine import NotificationEngine
    import app.optimizer.promotion_tracker as pt_module

    monkeypatch.setattr(pt_module, "_DATA_PATH", _promo(tmp_path))
    with patch.object(
        NotificationEngine, "_credit_spend_and_issuers",
        return_value=(0.0, {"Bradesco"}),
    ):
        assert NotificationEngine._detect_transfer_promos("user_r4b") == []


def test_input_vira_card_transfer_promo():
    from app.notifications.notifier import (
        TransferPromoInput,
        generate_transfer_promo_notifications,
    )

    notes = generate_transfer_promo_notifications([
        TransferPromoInput(
            from_program="livelo", to_program="GOL Smiles",
            bonus_pct=1.0, end_date="2026-07-27", user_points=12000,
        )
    ])
    assert len(notes) == 1
    assert notes[0].type == "TRANSFER_PROMO"
    assert "100%" in notes[0].title


# ── tool do agente (feed+chat completo) ──────────────────────────────────────

def test_tool_lista_promocoes_ativas(tmp_path, monkeypatch):
    import app.optimizer.promotion_tracker as pt_module

    monkeypatch.setattr(pt_module, "_DATA_PATH", _promo(tmp_path))
    from app.agent.tools.get_transfer_promotions import get_transfer_promotions

    out = get_transfer_promotions.invoke({"user_id": "u1"})
    assert "livelo" in out and "GOL Smiles" in out
    assert "Confirme as condições" in out  # honestidade obrigatória


def test_tool_registrada_no_grafo():
    import app.agent.graph as graph_src
    src = open(graph_src.__file__).read()
    assert "get_transfer_promotions," in src
