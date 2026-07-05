# tests/opportunities/test_balance_personalization.py
"""
OPP4-E — personalização com saldo real (account_balances via Pluggy):
  1. balances.py — normalização de tipo de conta e persistência/leitura
  2. SavingsVsCdiService.analyze_for_user — personalizado vs. genérico
  3. Bank Match — pilar de tarifas com custo real do extrato
  4. bank_names.banks_match — matching tolerante compartilhado
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.db.balances import BalanceSnapshot, normalize_account_type
from app.opportunities.services.bank_names import banks_match, find_matching
from app.opportunities.services.savings_vs_cdi import SavingsVsCdiService


# ── 1. Normalização de tipo de conta (payloads Pluggy variados) ──────

class TestNormalizeAccountType:
    def test_subtipo_pluggy_padrao(self):
        assert normalize_account_type({"type": "BANK", "subtype": "SAVINGS_ACCOUNT"}) == "SAVINGS"
        assert normalize_account_type({"type": "BANK", "subtype": "CHECKING_ACCOUNT"}) == "CHECKING"
        assert normalize_account_type({"type": "CREDIT", "subtype": "CREDIT_CARD"}) == "CREDIT"

    def test_payload_legado_sem_subtype(self):
        assert normalize_account_type({"type": "CHECKING"}) == "CHECKING"
        assert normalize_account_type({"type": "SAVINGS"}) == "SAVINGS"

    def test_desconhecido_vira_other(self):
        assert normalize_account_type({"type": "???"}) == "OTHER"
        assert normalize_account_type({}) == "OTHER"


# ── 2. Poupança personalizada ─────────────────────────────────────────

def _service_with_rates(cdi=0.1465, selic=0.15, tr=0.0):
    service = SavingsVsCdiService()
    service._anbima = type("_A", (), {"get_cdi": staticmethod(lambda: cdi)})()
    service._bacen = type("_B", (), {
        "get_selic": staticmethod(lambda: selic),
        "get_tr_monthly": staticmethod(lambda: tr),
    })()
    return service


def _snapshot(balance=15_000.0, bank="Nubank"):
    return BalanceSnapshot(
        balance=balance,
        bank_name=bank,
        account_type="SAVINGS",
        captured_at=datetime.now(timezone.utc),
    )


class TestSavingsPersonalizado:
    def test_com_saldo_real_usa_o_saldo_e_marca_personalizado(self):
        service = _service_with_rates()
        with patch(
            "app.core.db.balances.get_latest_balance", return_value=_snapshot(15_000.0)
        ):
            result = service.analyze_for_user("u1")
        assert result.is_personalized is True
        assert result.savings_balance_brl == 15_000.0
        assert result.amount_reference_brl == 15_000.0
        assert "Você tem R$" in result.reason
        assert "15,000.00" in result.reason

    def test_perda_escala_com_o_saldo_real(self):
        service = _service_with_rates()
        with patch("app.core.db.balances.get_latest_balance", return_value=_snapshot(10_000.0)):
            r10 = service.analyze_for_user("u1")
        with patch("app.core.db.balances.get_latest_balance", return_value=_snapshot(20_000.0)):
            r20 = service.analyze_for_user("u1")
        assert r20.estimated_loss_annual_brl == pytest.approx(
            r10.estimated_loss_annual_brl * 2, rel=1e-6
        )

    def test_sem_saldo_cai_no_generico_sem_afirmar_saldo(self):
        service = _service_with_rates()
        with patch("app.core.db.balances.get_latest_balance", return_value=None):
            result = service.analyze_for_user("u1")
        assert result.is_personalized is False
        assert result.savings_balance_brl is None
        assert result.amount_reference_brl == 10_000.0
        assert "Você tem R$" not in result.reason

    def test_saldo_zero_cai_no_generico(self):
        service = _service_with_rates()
        with patch("app.core.db.balances.get_latest_balance", return_value=_snapshot(0.0)):
            result = service.analyze_for_user("u1")
        assert result.is_personalized is False

    def test_falha_na_leitura_de_saldo_cai_no_generico(self):
        service = _service_with_rates()
        with patch(
            "app.core.db.balances.get_latest_balance", side_effect=Exception("db fora")
        ):
            result = service.analyze_for_user("u1")
        assert result.is_personalized is False
        assert result.status in ("BELOW_CDI", "NEAR_CDI", "NO_ADVANTAGE")


class TestCardPersonalizadoNoFeed:
    def test_card_personalizado_afirma_perda_no_titulo(self):
        from app.notifications.notifier import (
            SavingsBelowCdiInput,
            generate_savings_below_cdi_notification,
        )

        note = generate_savings_below_cdi_notification(SavingsBelowCdiInput(
            savings_annual_pct=6.17, cdi_annual_pct=14.65,
            amount_reference_brl=15_000.0, estimated_loss_annual_brl=1_272.0,
            severity="HIGH", reason="Você tem R$ 15.000,00 na poupança...",
            is_personalized=True, savings_balance_brl=15_000.0,
        ))[0]
        assert "Sua poupança" in note.title
        assert note.metadata["is_personalized"] is True

    def test_card_generico_nao_afirma_saldo(self):
        from app.notifications.notifier import (
            SavingsBelowCdiInput,
            generate_savings_below_cdi_notification,
        )

        note = generate_savings_below_cdi_notification(SavingsBelowCdiInput(
            savings_annual_pct=6.17, cdi_annual_pct=14.65,
            amount_reference_brl=10_000.0, estimated_loss_annual_brl=848.0,
            severity="HIGH", reason="ref",
        ))[0]
        assert "Sua poupança" not in note.title
        assert note.metadata["is_personalized"] is False


# ── 3. Bank Match com tarifas reais ───────────────────────────────────

class TestBankMatchTarifasReais:
    def test_tarifa_real_substitui_media_de_mercado(self):
        import polars as pl

        from app.opportunities.services.bank_match import BankMatchService
        from app.opportunities.services.bank_scorecard import BankScorecardService

        fake_df = pl.DataFrame({"description": ["TARIFA"], "amount": [-30.0]})
        with (
            patch.object(BankScorecardService, "_get_user_banks", return_value=set()),
            patch.object(
                BankMatchService, "_detect_real_fees", return_value={"NUBANK": 30.0}
            ),
        ):
            result = BankMatchService().build(
                user_id="u1", amount=10_000, holding_months=12,
                cdi_annual=0.1465, transactions_df=fake_df,
            )
        nubank = next(e for e in result.ranking if e.bank_name == "Nubank")
        assert nubank.projected_monthly_fee_brl == 30.0
        assert any("Você paga" in r for r in nubank.reasons)

    def test_sem_transacoes_usa_media_de_mercado(self):
        from app.opportunities.services.bank_match import BankMatchService
        from app.opportunities.services.bank_scorecard import BankScorecardService

        with patch.object(BankScorecardService, "_get_user_banks", return_value=set()):
            result = BankMatchService().build(
                user_id="u1", amount=10_000, holding_months=12,
                cdi_annual=0.1465, transactions_df=None,
            )
        assert result.ranking
        assert not any("Você paga" in r for e in result.ranking for r in e.reasons)


# ── 4. Matching compartilhado de nomes de banco ───────────────────────

class TestBanksMatch:
    def test_pluggy_connector_vs_catalogo(self):
        assert banks_match("Nu Pagamentos S.A.", "Nubank")
        assert banks_match("Banco Inter S.A.", "Banco Inter")
        assert banks_match("NUBANK", "Nubank")

    def test_emissor_vs_catalogo(self):
        assert banks_match("Inter", "Banco Inter")
        assert banks_match("XP", "XP Investimentos")

    def test_token_generico_nao_cruza_bancos(self):
        assert not banks_match("Nubank", "C6 Bank")
        assert not banks_match("PagBank", "Banco Pan")
        assert not banks_match("Banco Inter", "Banco Pan")

    def test_find_matching_retorna_chave(self):
        fees = {"NUBANK": 0.0, "SANTANDER": 25.9}
        assert find_matching("Nubank", fees) == "NUBANK"
        assert find_matching("Santander", fees) == "SANTANDER"
        assert find_matching("C6 Bank", fees) is None
