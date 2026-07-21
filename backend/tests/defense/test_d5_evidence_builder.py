"""
tests/defense/test_d5_evidence_builder.py — D5: Dossiê de Evidências

Testa EvidenceBuilder com achados sintéticos (sem banco de dados).
Cobre build_dossier, calc_monetary_correction e build_zip_package.

COMO RODAR:
    cd backend
    pytest tests/defense/test_d5_evidence_builder.py -v
"""

import zipfile
import io
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.defense.models import DefenseFinding
from app.defense.services.evidence_builder import EvidenceBuilder


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_finding(
    detector="D2",
    severity="medium",
    bank_name="Banco Teste",
    amount=250.0,
) -> DefenseFinding:
    return DefenseFinding(
        detector=detector,
        severity=severity,
        bank_name=bank_name,
        title="Tarifa indevida de saque",
        description="Cobrança de saque dentro da franquia gratuita mensal.",
        amount_disputed=amount,
        legal_basis="Res. CMN 3.919/2010, art. 7º",
        recommended_action="Solicite estorno no SAC.",
        evidence_points=["Cobrança em 2026-03-15", "Franquia: 4 saques gratuitos/mês"],
    )


@pytest.fixture
def builder() -> EvidenceBuilder:
    return EvidenceBuilder()


@pytest.fixture
def single_finding() -> list[DefenseFinding]:
    return [_make_finding()]


@pytest.fixture
def multi_findings() -> list[DefenseFinding]:
    return [
        _make_finding("D1", "high",   "Banco A", 500.0),
        _make_finding("D2", "medium", "Banco B", 150.0),
        _make_finding("D3", "low",    "Banco A", 80.0),
    ]


# ── build_dossier ─────────────────────────────────────────────────────────────

class TestBuildDossier:

    def test_sem_achados_retorna_dossie_vazio(self, builder):
        d = builder.build_dossier(user_id="u1", findings=[])
        assert d.total_findings == 0
        assert d.total_disputed_amount == 0.0
        assert d.monetary_correction is None

    def test_total_calculado_corretamente(self, builder, multi_findings):
        d = builder.build_dossier(user_id="u1", findings=multi_findings)
        assert d.total_findings == 3
        assert abs(d.total_disputed_amount - 730.0) < 0.01

    def test_gera_carta_contestacao(self, builder, single_finding):
        d = builder.build_dossier(user_id="u1", findings=single_finding)
        assert len(d.contestation_letter) > 100
        assert "Banco Teste" in d.contestation_letter or "contestação" in d.contestation_letter.lower()

    def test_gera_relato_procon(self, builder, single_finding):
        d = builder.build_dossier(user_id="u1", findings=single_finding)
        assert len(d.procon_narrative) > 50

    def test_gera_peticao_jec(self, builder, single_finding):
        d = builder.build_dossier(user_id="u1", findings=single_finding)
        assert len(d.jec_petition) > 50

    def test_sem_charge_date_sem_correcao_monetaria(self, builder, single_finding):
        d = builder.build_dossier(user_id="u1", findings=single_finding)
        assert d.monetary_correction is None

    def test_com_charge_date_tem_correcao(self, builder, single_finding):
        charge = date.today() - timedelta(days=180)
        d = builder.build_dossier(
            user_id="u1", findings=single_finding, charge_date=charge
        )
        assert d.monetary_correction is not None
        assert d.monetary_correction.corrected_value >= d.monetary_correction.original_value

    def test_disclaimer_esta_presente(self, builder, single_finding):
        d = builder.build_dossier(user_id="u1", findings=single_finding)
        assert "AVISO LEGAL" in d.disclaimer or "indício" in d.disclaimer.lower()


# ── calc_monetary_correction ─────────────────────────────────────────────────

class TestCalcMonetaryCorrection:

    def test_selic_fator_maior_que_um(self, builder):
        start = date(2025, 1, 1)
        end   = date(2025, 12, 31)
        mc = builder.calc_monetary_correction(1000.0, start, end, "SELIC")
        assert mc.correction_factor > 1.0
        assert mc.corrected_value > 1000.0

    def test_ipca_fator_maior_que_um(self, builder):
        start = date(2025, 1, 1)
        end   = date(2025, 12, 31)
        mc = builder.calc_monetary_correction(1000.0, start, end, "IPCA")
        assert mc.correction_factor >= 1.0

    def test_inpc_fator_maior_que_um(self, builder):
        start = date(2025, 1, 1)
        end   = date(2025, 12, 31)
        mc = builder.calc_monetary_correction(500.0, start, end, "INPC")
        assert mc.correction_factor >= 1.0

    def test_mesmo_dia_fator_um(self, builder):
        today = date.today()
        mc = builder.calc_monetary_correction(100.0, today, today, "SELIC")
        assert mc.correction_factor == pytest.approx(1.0, abs=0.001)
        assert mc.correction_brl == pytest.approx(0.0, abs=0.01)

    def test_campos_do_modelo_corretos(self, builder):
        start = date(2025, 6, 1)
        end   = date(2026, 6, 1)
        mc = builder.calc_monetary_correction(200.0, start, end, "IPCA")
        assert mc.original_value == pytest.approx(200.0)
        assert mc.charge_date == start
        assert mc.reference_date == end
        assert mc.index == "IPCA"
        assert mc.corrected_value == pytest.approx(mc.original_value * mc.correction_factor, abs=0.02)
        assert mc.correction_brl == pytest.approx(mc.corrected_value - mc.original_value, abs=0.02)


# ── build_zip_package ─────────────────────────────────────────────────────────

class TestBuildZipPackage:

    def test_retorna_bytes(self, builder, single_finding):
        result = builder.build_zip_package(user_id="u1", findings=single_finding)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_zip_valido_com_5_arquivos(self, builder, single_finding):
        result = builder.build_zip_package(user_id="u1", findings=single_finding)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert "00_LEIA_ME.txt" in names
        assert "01_carta_contestacao.txt" in names
        assert "02_relato_procon.txt" in names
        assert "03_peticao_jec.txt" in names
        assert "04_resumo_achados.txt" in names
        assert len(names) == 5

    def test_zip_vazio_ainda_valido(self, builder):
        result = builder.build_zip_package(user_id="u1", findings=[])
        assert isinstance(result, bytes)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert len(zf.namelist()) == 5

    def test_carta_nao_vazia_no_zip(self, builder, multi_findings):
        result = builder.build_zip_package(user_id="u1", findings=multi_findings)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            carta = zf.read("01_carta_contestacao.txt").decode("utf-8")
        assert len(carta) > 100
