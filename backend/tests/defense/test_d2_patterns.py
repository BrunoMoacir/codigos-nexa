"""
tests/defense/test_d2_patterns.py — D2: Cobranças Indevidas (padrões de regex)

Testa a lógica de matching de descrições contra serviços essenciais
sem precisar de banco de dados.

COMO RODAR:
    cd backend
    pytest tests/defense/test_d2_patterns.py -v
"""

import re
import pytest


# ── Importa o dicionário de serviços essenciais ───────────────────────────────

from app.defense.services.wrongful_charge_detector import _ESSENTIAL_SERVICES


class TestEssentialServicesConfig:
    """Valida a estrutura do catálogo de serviços essenciais."""

    def test_saque_esta_presente(self):
        assert "saque" in _ESSENTIAL_SERVICES

    def test_extrato_esta_presente(self):
        assert "extrato" in _ESSENTIAL_SERVICES

    def test_pix_recebimento_pf_esta_presente(self):
        """PIX recebimento PF foi adicionado conforme PDF seção 8."""
        assert "pix_recebimento_pf" in _ESSENTIAL_SERVICES

    def test_cada_servico_tem_campos_obrigatorios(self):
        for key, svc in _ESSENTIAL_SERVICES.items():
            assert "name" in svc, f"{key}: campo 'name' ausente"
            assert "patterns" in svc, f"{key}: campo 'patterns' ausente"
            assert "monthly_limit" in svc, f"{key}: campo 'monthly_limit' ausente"
            assert isinstance(svc["patterns"], list), f"{key}: 'patterns' deve ser lista"
            assert len(svc["patterns"]) > 0, f"{key}: lista de patterns vazia"

    def test_pix_recebimento_monthly_limit_none(self):
        """PF não deve pagar para receber Pix — sem franquia, proibição total."""
        svc = _ESSENTIAL_SERVICES["pix_recebimento_pf"]
        assert svc["monthly_limit"] is None

    def test_saque_franquia_4_por_mes(self):
        """Franquia de 4 saques gratuitos/mês (Res. CMN 3.919/2010)."""
        assert _ESSENTIAL_SERVICES["saque"]["monthly_limit"] == 4


class TestPatternMatching:
    """Testa se os padrões de regex capturam descrições típicas de extrato bancário."""

    @staticmethod
    def _matches(service_key: str, description: str) -> bool:
        import unicodedata
        def norm(s):
            return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

        svc = _ESSENTIAL_SERVICES[service_key]
        desc_norm = norm(description)
        return any(re.search(p, desc_norm, re.IGNORECASE) for p in svc["patterns"])

    def test_saque_captura_descricao_tipica(self):
        assert self._matches("saque", "SAQUE CAIXA ELETRONICO")

    def test_extrato_captura_descricao_tipica(self):
        assert self._matches("extrato", "TAR EXT CONTA")

    def test_pix_recebimento_captura_tarifa(self):
        assert self._matches("pix_recebimento_pf", "TAR PIX REC CONTA")

    def test_pix_recebimento_captura_alternativa(self):
        assert self._matches("pix_recebimento_pf", "TARIFA RECEBIMENTO PIX")

    def test_saque_nao_captura_pix_transferencia(self):
        """Transferência Pix não deve ser confundida com saque."""
        assert not self._matches("saque", "PIX TRANSFERENCIA ENVIADA")

    def test_extrato_nao_captura_saque(self):
        assert not self._matches("extrato", "SAQUE CAIXA ELETRONICO")
