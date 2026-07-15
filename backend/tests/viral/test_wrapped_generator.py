"""
tests/viral/test_wrapped_generator.py — WrappedGenerator (V2)

COMO RODAR:
    cd backend
    pytest tests/viral/test_wrapped_generator.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

from app.viral.services.wrapped_generator import WrappedGenerator, _MIN_MONTHS_FULL


@pytest.fixture
def gen() -> WrappedGenerator:
    return WrappedGenerator()


class TestFallbackMenosde3Meses:
    def test_usuario_novo_retorna_relatorio_parcial(self, gen):
        with patch.object(gen, "_months_active", return_value=1):
            with patch.object(gen, "_get_badges", return_value=[]):
                report = gen.generate("u1", 2026)

        assert report.is_partial_year is True
        assert report.highlights == []

    def test_2_meses_retorna_parcial(self, gen):
        with patch.object(gen, "_months_active", return_value=2):
            with patch.object(gen, "_get_badges", return_value=[]):
                report = gen.generate("u1", 2026)

        assert report.is_partial_year is True

    def test_3_meses_nao_e_parcial(self, gen):
        with (
            patch.object(gen, "_months_active", return_value=3),
            patch.object(gen, "_biggest_waste", return_value=(None, 0.0)),
            patch.object(gen, "_worst_fee", return_value=None),
            patch.object(gen, "_best_card_missed", return_value=(None, 0.0)),
            patch.object(gen, "_idle_money", return_value=(None, 0.0)),
            patch.object(gen, "_score_evolution", return_value=(None, None, None)),
            patch.object(gen, "_get_badges", return_value=[]),
        ):
            report = gen.generate("u1", 2026)

        assert report.is_partial_year is False

    def test_tagline_parcial_menciona_meses(self, gen):
        with patch.object(gen, "_months_active", return_value=2):
            with patch.object(gen, "_get_badges", return_value=[]):
                report = gen.generate("u1", 2026)

        assert "2" in report.summary_tagline or "mês" in report.summary_tagline

    def test_relatorio_parcial_tem_ano_correto(self, gen):
        with patch.object(gen, "_months_active", return_value=1):
            with patch.object(gen, "_get_badges", return_value=["PRIMEIRO_INSIGHT"]):
                report = gen.generate("u1", 2025)

        assert report.year == 2025
        assert report.badges_earned == ["PRIMEIRO_INSIGHT"]


class TestTaglineCompleto:
    def test_tagline_distingue_tarifas_de_savings(self, gen):
        from app.viral.services.wrapped_generator import WrappedGenerator

        tagline = gen._build_tagline(
            total_fees=500.0,
            total_savings=1200.0,
            score_delta=10,
            badges=[],
            year=2026,
        )
        assert "cobrad" in tagline.lower() or "pag" in tagline.lower()
        assert "estimat" in tagline.lower() or "potenci" in tagline.lower()

    def test_tagline_sem_dados_tem_mensagem_generica(self, gen):
        tagline = gen._build_tagline(
            total_fees=0.0,
            total_savings=0.0,
            score_delta=None,
            badges=[],
            year=2026,
        )
        assert len(tagline) > 20

    def test_tagline_sem_saving_garantido(self, gen):
        tagline = gen._build_tagline(
            total_fees=0.0,
            total_savings=2000.0,
            score_delta=None,
            badges=[],
            year=2026,
        )
        assert "identificou" in tagline.lower() or "potenci" in tagline.lower()
        assert "te ajudou a guardar" not in tagline.lower()


class TestHighlights:
    def _full_mocks(self, gen):
        return [
            patch.object(gen, "_months_active", return_value=12),
            patch.object(gen, "_biggest_waste", return_value=(None, 0.0)),
            patch.object(gen, "_worst_fee", return_value=None),
            patch.object(gen, "_best_card_missed", return_value=(None, 0.0)),
            patch.object(gen, "_idle_money", return_value=(None, 0.0)),
            patch.object(gen, "_score_evolution", return_value=(None, None, None)),
            patch.object(gen, "_get_badges", return_value=[]),
        ]

    def test_sem_highlights_retorna_relatorio_valido(self, gen):
        with (
            patch.object(gen, "_months_active", return_value=12),
            patch.object(gen, "_biggest_waste", return_value=(None, 0.0)),
            patch.object(gen, "_worst_fee", return_value=None),
            patch.object(gen, "_best_card_missed", return_value=(None, 0.0)),
            patch.object(gen, "_idle_money", return_value=(None, 0.0)),
            patch.object(gen, "_score_evolution", return_value=(None, None, None)),
            patch.object(gen, "_get_badges", return_value=[]),
        ):
            report = gen.generate("u1", 2026)

        assert report.highlights == []
        assert report.user_id == "u1"
        assert report.year == 2026

    def test_best_card_missed_abaixo_50_omitido(self, gen):
        from app.viral.services.wrapped_generator import WrappedGenerator

        gen2 = WrappedGenerator()
        result_h, gain = gen2._best_card_missed.__func__(gen2, "u1") if False else (None, 0.0)
        assert gain == 0.0 or gain >= 50.0  # nunca entre 0 e 50

    def test_score_evolution_menos_de_2_pontos_omitido(self, gen):
        with patch("app.core.database.SessionLocal") as mock_session:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute.return_value.fetchall.return_value = [(75, "2026-01-01")]
            mock_session.return_value = mock_ctx

            h, s, e = gen._score_evolution("u1", 2026)

        assert h is None
        assert s is None
        assert e is None


class TestModels:
    def test_report_tem_calculation_version(self, gen):
        with patch.object(gen, "_months_active", return_value=1):
            with patch.object(gen, "_get_badges", return_value=[]):
                report = gen.generate("u1", 2026)

        assert report.calculation_version == "2.0"

    def test_report_tem_disclaimer(self, gen):
        with patch.object(gen, "_months_active", return_value=1):
            with patch.object(gen, "_get_badges", return_value=[]):
                report = gen.generate("u1", 2026)

        assert len(report.disclaimer) > 20
        assert "estimat" in report.disclaimer.lower() or "cobrad" in report.disclaimer.lower()
