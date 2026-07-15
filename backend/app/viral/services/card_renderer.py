"""
app/viral/services/card_renderer.py — Renderiza cartão compartilhável (SVG)

Gera um SVG puro (sem dependências externas como Pillow) com o resumo de
economia ou wrapped anual, pronto para exportar como imagem ou compartilhar.
"""

from __future__ import annotations

import html

from app.viral.models import SavingsCard, WrappedReport

_WIDTH = 1080
_HEIGHT = 1080


class CardRenderer:
    """Renderiza SavingsCard e WrappedReport como SVG compartilhável."""

    def render_savings_card(self, card: SavingsCard) -> str:
        total = f"R$ {card.total_annual_savings_brl:,.2f}"
        rows = "".join(
            self._source_row(i, s.name, s.annual_savings_brl)
            for i, s in enumerate(card.sources[:4])
        )

        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" viewBox="0 0 {_WIDTH} {_HEIGHT}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0A0E27"/>
      <stop offset="100%" stop-color="#1B1F4D"/>
    </linearGradient>
  </defs>
  <rect width="{_WIDTH}" height="{_HEIGHT}" fill="url(#bg)"/>

  <text x="60" y="120" font-family="Arial, sans-serif" font-size="36" fill="#8B93FF" font-weight="bold">NEXA</text>
  <text x="60" y="220" font-family="Arial, sans-serif" font-size="40" fill="#FFFFFF">A Nexa te ajudou a guardar</text>

  <text x="60" y="340" font-family="Arial, sans-serif" font-size="96" fill="#4ADE80" font-weight="bold">{html.escape(total)}</text>

  <text x="60" y="400" font-family="Arial, sans-serif" font-size="28" fill="#A0A8FF">em {card.months_active} mês(es) de uso</text>

  <line x1="60" y1="460" x2="{_WIDTH - 60}" y2="460" stroke="#3B4080" stroke-width="2"/>

  {rows}

  <text x="60" y="{_HEIGHT - 80}" font-family="Arial, sans-serif" font-size="22" fill="#6B72A8">{html.escape(card.tagline)}</text>
  <text x="60" y="{_HEIGHT - 50}" font-family="Arial, sans-serif" font-size="18" fill="#4A4F80">nexa.app</text>
  <text x="60" y="{_HEIGHT - 18}" font-family="Arial, sans-serif" font-size="14" fill="#555980" font-style="italic">Potencial estimado. Resultado depende de condições de mercado e ação do usuário.</text>
</svg>"""

    def render_wrapped_card(self, report: WrappedReport) -> str:
        highlight_rows = "".join(
            self._highlight_row(i, h.title, h.value_formatted)
            for i, h in enumerate(report.highlights[:5])
        )

        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{_HEIGHT}" viewBox="0 0 {_WIDTH} {_HEIGHT}">
  <defs>
    <linearGradient id="bg2" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1B0E3D"/>
      <stop offset="100%" stop-color="#3D1B5E"/>
    </linearGradient>
  </defs>
  <rect width="{_WIDTH}" height="{_HEIGHT}" fill="url(#bg2)"/>

  <text x="60" y="110" font-family="Arial, sans-serif" font-size="32" fill="#C39BFF" font-weight="bold">NEXA WRAPPED {report.year}</text>
  <text x="60" y="180" font-family="Arial, sans-serif" font-size="44" fill="#FFFFFF" font-weight="bold">Banco vs. Você</text>

  <line x1="60" y1="220" x2="{_WIDTH - 60}" y2="220" stroke="#5B3F8A" stroke-width="2"/>

  {highlight_rows}

  <text x="60" y="{_HEIGHT - 100}" font-family="Arial, sans-serif" font-size="22" fill="#D9C2FF">{html.escape(_truncate(report.summary_tagline, 90))}</text>
  <text x="60" y="{_HEIGHT - 60}" font-family="Arial, sans-serif" font-size="18" fill="#8A6FB0">nexa.app</text>
  <text x="60" y="{_HEIGHT - 30}" font-family="Arial, sans-serif" font-size="14" fill="#6B508A" font-style="italic">Tarifas: valores cobrados. Savings: estimativas — sujeitas a condições e ação do usuário.</text>
</svg>"""

    @staticmethod
    def _source_row(index: int, name: str, value: float) -> str:
        y = 520 + index * 80
        return (
            f'<text x="60" y="{y}" font-family="Arial, sans-serif" font-size="26" fill="#C8CCFF">'
            f'{html.escape(name)}</text>'
            f'<text x="{_WIDTH - 60}" y="{y}" font-family="Arial, sans-serif" font-size="26" '
            f'fill="#4ADE80" text-anchor="end" font-weight="bold">R$ {value:,.2f}</text>'
        )

    @staticmethod
    def _highlight_row(index: int, title: str, value: str) -> str:
        y = 290 + index * 130
        return (
            f'<text x="60" y="{y}" font-family="Arial, sans-serif" font-size="24" fill="#D9C2FF">'
            f'{html.escape(_truncate(title, 40))}</text>'
            f'<text x="60" y="{y + 45}" font-family="Arial, sans-serif" font-size="42" fill="#FFFFFF" '
            f'font-weight="bold">{html.escape(_truncate(value, 30))}</text>'
        )


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"
