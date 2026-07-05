# tests/opportunities/test_real_balance_idle.py
"""
Opção B do plano OPP.1 — dinheiro parado com saldo REAL de conta corrente:
  1. IdleMoneyDetector usa o saldo real quando fresco; proxy como fallback
  2. OpportunityEngine expõe idle_source/balance_captured_at e ajusta o texto
  3. Enriquecimento de institution_id por metadado (Bank Match / tarifas F5)
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import polars as pl
import pytest

from app.core.db.balances import BalanceSnapshot
from app.opportunities.services.idle_money_detector import IdleMoneyDetector


def _transactions_df(monthly_net=2_000.0, months=4):
    """Histórico sintético: 4 meses de renda 5k e gasto 3k (proxy = 8k)."""
    rows = []
    today = date.today().replace(day=1)
    for m in range(1, months + 1):
        d = (today - timedelta(days=30 * m)).replace(day=5)
        rows.append({"date": d, "amount": 5_000.0})
        rows.append({"date": d, "amount": -(5_000.0 - monthly_net)})
    return pl.DataFrame(rows)


def _checking(balance=12_345.67):
    return BalanceSnapshot(
        balance=balance,
        bank_name="Nubank",
        account_type="CHECKING",
        captured_at=datetime.now(timezone.utc),
    )


class TestDetectorComSaldoReal:
    def test_saldo_real_substitui_proxy(self):
        detector = IdleMoneyDetector()
        with patch.object(
            IdleMoneyDetector, "_fetch_real_checking_balance", return_value=_checking(12_345.67)
        ):
            result = detector.detect("u1", transactions_df=_transactions_df())
        assert result.idle_source == "REAL_BALANCE"
        assert result.gross_idle_amount == 12_345.67
        assert result.balance_captured_at is not None

    def test_sem_saldo_fresco_cai_no_proxy(self):
        detector = IdleMoneyDetector()
        with patch.object(
            IdleMoneyDetector, "_fetch_real_checking_balance", return_value=None
        ):
            result = detector.detect("u1", transactions_df=_transactions_df())
        assert result.idle_source == "CASHFLOW_PROXY"
        assert result.gross_idle_amount == pytest.approx(8_000.0)
        assert result.balance_captured_at is None

    def test_reserva_de_emergencia_aplica_sobre_o_saldo_real(self):
        from types import SimpleNamespace

        detector = IdleMoneyDetector()
        profile = SimpleNamespace(fss_level="SAUDAVEL")
        with patch.object(
            IdleMoneyDetector, "_fetch_real_checking_balance", return_value=_checking(30_000.0)
        ):
            result = detector.detect(
                "u1", transactions_df=_transactions_df(), user_profile=profile
            )
        # reserva = 6 × avg_expenses (3k) = 18k; ocioso = 30k − 18k = 12k
        assert result.emergency_reserve == pytest.approx(18_000.0)
        assert result.idle_amount == pytest.approx(12_000.0)

    def test_falha_na_leitura_de_saldo_nao_derruba_a_deteccao(self):
        detector = IdleMoneyDetector()
        with patch(
            "app.core.db.balances.get_latest_balance", side_effect=Exception("db fora")
        ):
            result = detector.detect("u1", transactions_df=_transactions_df())
        assert result.idle_source == "CASHFLOW_PROXY"
        assert result.has_sufficient_data


class TestEngineExpoeOrigem:
    def test_response_carrega_idle_source_e_nota_de_saldo_real(self):
        from app.opportunities.services.opportunity_engine import OpportunityEngine

        engine = OpportunityEngine()
        with (
            patch.object(OpportunityEngine, "_fetch_transactions", return_value=_transactions_df()),
            patch.object(OpportunityEngine, "_build_user_profile", return_value=None),
            patch.object(
                IdleMoneyDetector, "_fetch_real_checking_balance", return_value=_checking(9_000.0)
            ),
        ):
            result = engine.analyze("u1", persist_snapshot=False)
        assert result.idle_source == "REAL_BALANCE"
        assert result.idle_amount == pytest.approx(9_000.0)
        assert "saldo real" in result.recommendation

    def test_proxy_tem_ressalva_de_estimativa(self):
        from app.opportunities.services.opportunity_engine import OpportunityEngine

        engine = OpportunityEngine()
        with (
            patch.object(OpportunityEngine, "_fetch_transactions", return_value=_transactions_df()),
            patch.object(OpportunityEngine, "_build_user_profile", return_value=None),
            patch.object(IdleMoneyDetector, "_fetch_real_checking_balance", return_value=None),
        ):
            result = engine.analyze("u1", persist_snapshot=False)
        assert result.idle_source == "CASHFLOW_PROXY"
        assert "estimado a partir do seu histórico" in result.recommendation


class TestEnriquecimentoInstitutionId:
    def _df(self, **cols):
        base = {
            "account_id": ["acc_001", "acc_999"],
            "transaction_date": [date(2026, 6, 5), date(2026, 6, 6)],
            "amount": [-29.9, -19.9],
            "description": ["TARIFA PACOTE DE SERVICOS", "TARIFA PACOTE DE SERVICOS"],
        }
        base.update(cols)
        return pl.DataFrame(base)

    def test_preenche_institution_id_pelo_metadado_da_conta(self):
        from app.opportunities.services.bank_match import BankMatchService

        with patch(
            "app.core.db.balances.get_account_bank_map",
            return_value={"acc_001": "Nubank"},
        ):
            enriched = BankMatchService._enrich_institution_id("u1", self._df())
        vals = enriched["institution_id"].to_list()
        assert vals[0] == "nubank"   # metadado → chave do INSTITUTION_ID_MAP
        assert vals[1] == ""         # conta sem mapa → heurística do F5 decide

    def test_nao_sobrescreve_institution_id_existente(self):
        from app.opportunities.services.bank_match import BankMatchService

        df = self._df(institution_id=["itau", ""])
        with patch(
            "app.core.db.balances.get_account_bank_map",
            return_value={"acc_001": "Nubank", "acc_999": "Banco Inter"},
        ):
            enriched = BankMatchService._enrich_institution_id("u1", df)
        assert enriched["institution_id"].to_list() == ["itau", "inter"]

    def test_atribuicao_flui_ate_o_pilar_de_tarifas(self):
        """Cadeia completa: metadado conta→banco → FeeDetector → tarifa real."""
        from app.opportunities.services.bank_match import BankMatchService

        df = self._df()
        with patch(
            "app.core.db.balances.get_account_bank_map",
            return_value={"acc_001": "Nubank"},
        ):
            fees = BankMatchService._detect_real_fees("u1", df)
        assert "Nubank" in fees

    def test_sem_mapa_devolve_df_original(self):
        from app.opportunities.services.bank_match import BankMatchService

        df = self._df()
        with patch("app.core.db.balances.get_account_bank_map", return_value={}):
            enriched = BankMatchService._enrich_institution_id("u1", df)
        assert "institution_id" not in enriched.columns
