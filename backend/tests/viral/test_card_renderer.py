"""
tests/viral/test_card_renderer.py — CardRenderer (V1/V2)

COMO RODAR:
    cd backend
    pytest tests/viral/test_card_renderer.py -v
"""

from datetime import datetime, timezone

import pytest

from app.viral.models import (
    DISCLAIMER_SAVINGS,
    DISCLAIMER_WRAPPED,
    SavingsCard,
    SavingsSource,
    WrappedHighlight,
    WrappedReport,
)
from app.viral.services.card_renderer import CardRenderer


@pytest.fixture
def renderer() -> CardRenderer:
    return CardRenderer()


def _make_card(total: float = 1500.0, sources: int = 2) -> SavingsCard:
    srcs = [
        SavingsSource(
            name=f"Módulo {i}",
            module=f"mod{i}",
            annual_savings_brl=total / sources,
            description="desc",
            amount_type="estimated_potential",
        )
        for i in range(sources)
    ]
    return SavingsCard(
        user_id="u1",
        generated_at=datetime.now(timezone.utc),
        total_annual_savings_brl=total,
        sources=srcs,
        months_active=6,
        tagline="Teste",
    )


def _make_wrapped(highlights: int = 3) -> WrappedReport:
    hs = [
        WrappedHighlight(
            category="biggest_waste",
            title=f"Highlight {i}",
            value_formatted=f"R$ {100 * i:,.2f}",
            description="desc",
        )
        for i in range(1, highlights + 1)
    ]
    return WrappedReport(
        user_id="u1",
        year=2026,
        generated_at=datetime.now(timezone.utc),
        highlights=hs,
        total_fees_paid_year=800.0,
        total_savings_identified=2000.0,
        summary_tagline="Resumo teste",
    )


class TestSavingsCardSVG:
    def test_retorna_string_svg(self, renderer):
        svg = renderer.render_savings_card(_make_card())
        assert isinstance(svg, str)
        assert svg.strip().startswith("<svg")

    def test_svg_bem_formado(self, renderer):
        svg = renderer.render_savings_card(_make_card())
        assert "</svg>" in svg

    def test_total_aparece_no_svg(self, renderer):
        svg = renderer.render_savings_card(_make_card(1500.0))
        assert "1.500,00" in svg

    def test_disclaimer_presente(self, renderer):
        svg = renderer.render_savings_card(_make_card())
        assert "estimado" in svg.lower()

    def test_svg_com_zero_sources(self, renderer):
        card = SavingsCard(
            user_id="u1",
            generated_at=datetime.now(timezone.utc),
            total_annual_savings_brl=0.0,
            sources=[],
            months_active=1,
            tagline="Nenhuma oportunidade ainda.",
        )
        svg = renderer.render_savings_card(card)
        assert "<svg" in svg

    def test_caracteres_especiais_escapados(self, renderer):
        card = _make_card()
        card.tagline = 'Teste <XSS> & "aspas"'
        svg = renderer.render_savings_card(card)
        assert "<XSS>" not in svg
        assert "&lt;XSS&gt;" in svg

    def test_nexa_url_presente(self, renderer):
        svg = renderer.render_savings_card(_make_card())
        assert "nexa.app" in svg

    def test_sem_cache_control_no_svg_content(self, renderer):
        svg = renderer.render_savings_card(_make_card())
        assert "Cache-Control" not in svg


class TestWrappedCardSVG:
    def test_retorna_string_svg(self, renderer):
        svg = renderer.render_wrapped_card(_make_wrapped())
        assert isinstance(svg, str)
        assert "<svg" in svg

    def test_disclaimer_presente(self, renderer):
        svg = renderer.render_wrapped_card(_make_wrapped())
        assert "estimat" in svg.lower()

    def test_ano_aparece_no_svg(self, renderer):
        svg = renderer.render_wrapped_card(_make_wrapped())
        assert "2026" in svg

    def test_svg_com_zero_highlights(self, renderer):
        wrapped = _make_wrapped(highlights=0)
        svg = renderer.render_wrapped_card(wrapped)
        assert "<svg" in svg

    def test_titulo_longo_truncado(self, renderer):
        hs = [
            WrappedHighlight(
                category="biggest_waste",
                title="T" * 100,
                value_formatted="R$ 0,00",
                description="d",
            )
        ]
        wrapped = WrappedReport(
            user_id="u1",
            year=2026,
            generated_at=datetime.now(timezone.utc),
            highlights=hs,
            total_fees_paid_year=0.0,
            total_savings_identified=0.0,
            summary_tagline="s",
        )
        svg = renderer.render_wrapped_card(wrapped)
        assert "T" * 100 not in svg

    def test_caracteres_especiais_escapados(self, renderer):
        wrapped = _make_wrapped()
        wrapped.summary_tagline = "<script>alert(1)</script>"
        svg = renderer.render_wrapped_card(wrapped)
        assert "<script>" not in svg
