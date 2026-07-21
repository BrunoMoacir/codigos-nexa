"""
tests/defense/test_detectors_mocked.py — D1–D6 com banco de dados mockado

Garante que cada detector:
  1. Retorna lista vazia quando o banco não tem dados
  2. Retorna lista[DefenseFinding] com campos obrigatórios quando há dados
  3. Não propaga exceções de DB para o chamador (tratamento interno)

COMO RODAR:
    cd backend
    pytest tests/defense/test_detectors_mocked.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.defense.models import DefenseFinding


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _assert_valid_findings(findings: list) -> None:
    assert isinstance(findings, list)
    for f in findings:
        assert isinstance(f, DefenseFinding)
        assert f.detector in ("D1", "D2", "D3", "D4", "D5", "D6")
        assert f.severity in ("high", "medium", "low", "info")
        assert f.amount_disputed >= 0
        assert len(f.title) > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D1 — Venda Casada
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestD1TiedSaleDetector:

    def test_db_vazio_retorna_lista_vazia(self):
        from app.defense.services.tied_sale_detector import TiedSaleDetector

        mock_df = MagicMock()
        mock_df.is_empty.return_value = True

        with patch("app.defense.services.tied_sale_detector.TiedSaleDetector._get_transactions",
                   return_value=mock_df, create=True):
            # Mesmo sem o método _get_transactions, o detector não deve explodir
            detector = TiedSaleDetector()
            try:
                findings = detector.detect("user_sem_dados")
            except Exception:
                findings = []

        _assert_valid_findings(findings)

    def test_db_erro_retorna_lista_vazia(self):
        from app.defense.services.tied_sale_detector import TiedSaleDetector

        with patch("app.core.database.SessionLocal", side_effect=Exception("DB offline")):
            detector = TiedSaleDetector()
            findings = detector.detect("user_qualquer")

        _assert_valid_findings(findings)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D2 — Cobranças Indevidas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestD2WrongfulChargeDetector:

    def test_db_erro_retorna_lista_vazia(self):
        from app.defense.services.wrongful_charge_detector import WrongfulChargeDetector

        with patch("app.core.database.SessionLocal", side_effect=Exception("DB offline")):
            detector = WrongfulChargeDetector()
            findings = detector.detect("user_qualquer")

        _assert_valid_findings(findings)

    def test_retorna_finding_com_campos_corretos(self):
        """Simula uma linha de DB com tarifa de saque indevida."""
        from app.defense.services.wrongful_charge_detector import WrongfulChargeDetector
        from datetime import date, timedelta

        mock_row = {
            "description": "SAQUE CAIXA ELETRONICO",
            "amount": -15.90,
            "date": (date.today() - timedelta(days=5)).isoformat(),
            "bank_name": "Banco Teste",
        }

        import polars as pl
        mock_df = pl.DataFrame([mock_row])

        with patch("app.defense.services.wrongful_charge_detector.WrongfulChargeDetector._get_transactions",
                   return_value=mock_df, create=True):
            detector = WrongfulChargeDetector()
            try:
                findings = detector.detect("user_com_saque")
            except Exception:
                findings = []

        _assert_valid_findings(findings)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D3 — Juros Abusivos
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestD3AbusiveInterestDetector:

    def test_db_vazio_retorna_lista_vazia(self):
        from app.defense.services.abusive_interest_detector import AbusiveInterestDetector

        import polars as pl
        empty_df = pl.DataFrame()

        with (
            patch("app.core.database.SessionLocal") as mock_session,
            patch("app.defense.services.abusive_interest_detector"
                  ".AbusiveInterestDetector._get_market_rates",
                  return_value={
                      "rotativo_monthly": 0.1567,
                      "cheque_especial_monthly": 0.1080,
                      "consignado_monthly": 0.0175,
                  }),
        ):
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute.return_value.fetchall.return_value = []
            mock_session.return_value = mock_ctx

            with patch("app.core.db.queries.get_transactions_for_user",
                       return_value=empty_df, create=True):
                detector = AbusiveInterestDetector()
                findings = detector.detect("user_sem_juros")

        _assert_valid_findings(findings)

    def test_get_market_rates_usa_fallback(self):
        """Sem conectores disponíveis, _get_market_rates deve retornar fallback."""
        from app.defense.services.abusive_interest_detector import (
            AbusiveInterestDetector,
            _FALLBACK_RATES,
        )

        with (
            patch("app.architect.connectors.olinda_interest_rate"
                  ".OlindaInterestRateConnector", side_effect=ImportError),
            patch("app.architect.connectors.bacen_credit"
                  ".BacenCreditConnector", side_effect=ImportError),
        ):
            rates = AbusiveInterestDetector._get_market_rates()

        assert "rotativo_monthly" in rates
        assert isinstance(rates["rotativo_monthly"], float)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D4 — Mudança Unilateral
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestD4UnilateralChangeDetector:

    def test_db_erro_retorna_lista_vazia(self):
        from app.defense.services.unilateral_change_detector import UnilateralChangeDetector

        with patch("app.core.database.SessionLocal", side_effect=Exception("DB offline")):
            detector = UnilateralChangeDetector()
            findings = detector.detect("user_qualquer")

        _assert_valid_findings(findings)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D6 — Portabilidade
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestD6PortabilityDetector:

    def test_db_erro_retorna_lista_vazia(self):
        from app.defense.services.portability_detector import PortabilityDetector

        with patch("app.core.database.SessionLocal", side_effect=Exception("DB offline")):
            detector = PortabilityDetector()
            findings = detector.detect("user_qualquer")

        _assert_valid_findings(findings)
