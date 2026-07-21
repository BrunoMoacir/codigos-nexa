"""
tests/defense/test_d3_classify.py — D3: Juros Abusivos (funções puras)

Testa _classify() sem tocar banco de dados ou APIs externas.

COMO RODAR:
    cd backend
    pytest tests/defense/test_d3_classify.py -v
"""

import pytest
from app.defense.services.abusive_interest_detector import _classify, _THRESHOLDS


class TestClassify:
    """Testa a classificação de múltiplos de taxa."""

    def test_abaixo_da_media_retorna_none(self):
        """Taxa abaixo ou igual à média de mercado não é achado."""
        assert _classify(0.9, 1.0) is None

    def test_exatamente_media_retorna_low(self):
        """1,0x exato ativa o threshold 'low' (atenção), não retorna None."""
        t = _classify(1.0, 1.0)
        assert t is not None
        assert t.severity == "low"

    def test_abaixo_99_retorna_none(self):
        """Taxa 0,99x a média → sem achado."""
        assert _classify(0.99, 1.0) is None

    def test_1_01x_retorna_low(self):
        """Qualquer valor acima de 1,0x mas abaixo de 1,5x é low."""
        t = _classify(1.01, 1.0)
        assert t is not None
        assert t.severity == "low"

    def test_exatamente_1_5x_retorna_medium(self):
        """Boundary: exatamente 1,5x deve ser medium (>= inclusivo)."""
        t = _classify(1.5, 1.0)
        assert t is not None
        assert t.severity == "medium"

    def test_2x_retorna_medium(self):
        """2x a média é medium."""
        t = _classify(2.0, 1.0)
        assert t is not None
        assert t.severity == "medium"

    def test_exatamente_3x_retorna_high(self):
        """Boundary: exatamente 3,0x deve ser high (>= inclusivo)."""
        t = _classify(3.0, 1.0)
        assert t is not None
        assert t.severity == "high"

    def test_muito_alto_retorna_high(self):
        """Taxas astronômicas (ex: agiotas) são high."""
        t = _classify(10.0, 1.0)
        assert t is not None
        assert t.severity == "high"

    def test_mercado_zero_retorna_none(self):
        """Taxa de mercado zero → divisão inválida → retorna None."""
        assert _classify(100.0, 0.0) is None

    def test_mercado_negativo_retorna_none(self):
        """Taxa de mercado negativa → dado inválido → retorna None."""
        assert _classify(5.0, -1.0) is None

    def test_thresholds_ordenados_decrescente(self):
        """_THRESHOLDS deve estar ordenado de maior para menor múltiplo."""
        multiples = [t.multiple for t in _THRESHOLDS]
        assert multiples == sorted(multiples, reverse=True), (
            "Thresholds devem ser decrescentes para o loop funcionar corretamente"
        )

    def test_com_taxas_reais_medium(self):
        """Cenário realista: rotativo 16% a.m. vs mercado 10% a.m. = 1,6x → medium."""
        t = _classify(0.16, 0.10)
        assert t is not None
        assert t.severity == "medium"

    def test_com_taxas_reais_low(self):
        """Rotativo 12% vs mercado 10% = 1,2x → low."""
        t = _classify(0.12, 0.10)
        assert t is not None
        assert t.severity == "low"

    def test_consignado_abaixo_rotativo_low(self):
        """Consignado a 2% contra mercado 1,75% = 1,14x → low."""
        t = _classify(0.02, 0.0175)
        assert t is not None
        assert t.severity == "low"
