# tests/opportunities/test_opportunity_engine.py
"""
Ticket OPP1-C (docs/OPP1_DINHEIRO_PARADO_PLANO.md) — threshold de persistência
(R$500 / 30 dias) sobre o histórico de opportunity_snapshots.

Duas camadas de teste:
  1. Unidade direta de OpportunityEngine._evaluate_persistence — controla
     idle.has_sufficient_data/idle_amount e a lista de valores diários
     (monkeypatch em _fetch_daily_snapshot_values, sem tocar banco real).
  2. Integração via analyze() — confirma que os 4 campos novos chegam até
     OpportunitiesResponse e que a recomendação reflete o status.
"""
from datetime import date, datetime, timedelta, timezone

import polars as pl
import pytest

import app.core.db.queries as queries_module
from app.opportunities.services.idle_money_detector import IdleMoneyResult
from app.opportunities.services.opportunity_engine import OpportunityEngine

USER_ID = "test_user_opp1c"
_NOW = datetime.now(timezone.utc)


def _idle(idle_amount: float, has_sufficient_data: bool = True) -> IdleMoneyResult:
    return IdleMoneyResult(
        idle_amount=idle_amount,
        gross_idle_amount=idle_amount,
        emergency_reserve=0.0,
        reserve_months_applied=0,
        avg_income_3m=5000.0,
        avg_expenses_3m=3000.0,
        months_analyzed=3,
        has_sufficient_data=has_sufficient_data,
    )


class TestEvaluatePersistenceUnidade:
    def test_no_data_quando_historico_insuficiente(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            OpportunityEngine,
            "_fetch_daily_snapshot_values",
            staticmethod(lambda user_id, now: calls.append(1) or [999.0] * 30),
        )

        result = OpportunityEngine._evaluate_persistence(
            USER_ID, _idle(0.0, has_sufficient_data=False), _NOW
        )

        assert result["status"] == "NO_DATA"
        assert result["is_confirmed_idle"] is False
        assert result["days_tracked"] == 0
        assert calls == [], "NO_DATA deve retornar sem consultar snapshots"

    def test_no_idle_money_quando_idle_amount_zerado(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            OpportunityEngine,
            "_fetch_daily_snapshot_values",
            staticmethod(lambda user_id, now: calls.append(1) or [999.0] * 30),
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(0.0), _NOW)

        assert result["status"] == "NO_IDLE_MONEY"
        assert result["is_confirmed_idle"] is False
        assert calls == [], "NO_IDLE_MONEY deve retornar sem consultar snapshots"

    def test_preliminary_cold_start_menos_de_30_dias(self, monkeypatch):
        monkeypatch.setattr(
            OpportunityEngine,
            "_fetch_daily_snapshot_values",
            staticmethod(lambda user_id, now: [600.0] * 12),
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(1000.0), _NOW)

        assert result["status"] == "PRELIMINARY"
        assert result["is_confirmed_idle"] is False
        assert result["days_tracked"] == 12

    def test_confirmed_quando_30_dias_estaveis_acima_do_threshold(self, monkeypatch):
        monkeypatch.setattr(
            OpportunityEngine,
            "_fetch_daily_snapshot_values",
            staticmethod(lambda user_id, now: [600.0] * 30),
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(1000.0), _NOW)

        assert result["status"] == "CONFIRMED"
        assert result["is_confirmed_idle"] is True
        assert result["days_tracked"] == 30

    def test_preliminary_quando_30_dias_mas_oscila_abaixo_do_threshold(self, monkeypatch):
        # 20/30 acima de 500 → 66.7%, abaixo dos 90% exigidos
        values = [600.0] * 20 + [100.0] * 10
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: values)
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(1000.0), _NOW)

        assert result["status"] == "PRELIMINARY"
        assert result["is_confirmed_idle"] is False

    def test_boundary_exatamente_90_por_cento_confirma(self, monkeypatch):
        # 27/30 = 90.0% exatos → deve confirmar (>=)
        values = [600.0] * 27 + [100.0] * 3
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: values)
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(1000.0), _NOW)
        assert result["status"] == "CONFIRMED"

    def test_boundary_abaixo_de_90_por_cento_nao_confirma(self, monkeypatch):
        # 26/30 = 86.7% → não confirma
        values = [600.0] * 26 + [100.0] * 4
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: values)
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(1000.0), _NOW)
        assert result["status"] == "PRELIMINARY"

    def test_valor_exatamente_no_threshold_conta_como_acima(self, monkeypatch):
        # idle_amount >= 500 (não >) — 500.00 exato deve contar como "acima do threshold"
        values = [500.0] * 30
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: values)
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(1000.0), _NOW)
        assert result["status"] == "CONFIRMED"

    def test_zero_dias_de_historico_e_preliminary_nao_confirmed(self, monkeypatch):
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: [])
        )

        result = OpportunityEngine._evaluate_persistence(USER_ID, _idle(1000.0), _NOW)
        assert result["status"] == "PRELIMINARY"
        assert result["days_tracked"] == 0


class TestAnalyzeIntegracao:
    """Confirma que os campos do OPP1-C chegam até OpportunitiesResponse via analyze()."""

    @pytest.fixture(autouse=True)
    def _patch_transactions(self, monkeypatch):
        today = date.today()
        rows = []
        for months_back in range(4):
            base = today - timedelta(days=30 * months_back)
            rows.append({"date": base, "amount": 20000.0})
            rows.append({"date": base + timedelta(days=5), "amount": -1000.0})
        df = pl.DataFrame(rows)
        monkeypatch.setattr(queries_module, "get_transactions_for_user", lambda user_id: df)
        monkeypatch.setattr(
            OpportunityEngine, "_persist_snapshot", staticmethod(lambda *a, **k: None)
        )

    def test_response_expoe_campos_do_opp1c(self, monkeypatch):
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: [600.0] * 30)
        )

        result = OpportunityEngine().analyze(user_id=USER_ID, persist_snapshot=False)

        assert result.idle_detection_status == "CONFIRMED"
        assert result.is_confirmed_idle is True
        assert result.days_tracked == 30
        assert result.idle_detection_reason

    def test_recomendacao_menciona_estimativa_preliminar_quando_nao_confirmado(self, monkeypatch):
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: [600.0] * 5)
        )

        result = OpportunityEngine().analyze(user_id=USER_ID, persist_snapshot=False)

        assert result.idle_detection_status == "PRELIMINARY"
        assert "preliminar" in result.recommendation.lower()

    def test_recomendacao_confirmada_nao_leva_ressalva_preliminar(self, monkeypatch):
        monkeypatch.setattr(
            OpportunityEngine, "_fetch_daily_snapshot_values", staticmethod(lambda u, n: [600.0] * 30)
        )

        result = OpportunityEngine().analyze(user_id=USER_ID, persist_snapshot=False)

        assert "estimativa preliminar" not in result.recommendation.lower()
