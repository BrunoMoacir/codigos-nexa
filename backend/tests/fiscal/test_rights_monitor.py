# tests/fiscal/test_rights_monitor.py
# T3 — Monitor de Direitos Esquecidos (visão fiscal), sem valores fabricados.
#
# Regra de honestidade: nenhum conector pode inventar montantes. SVR e IRPF
# apontam para os fluxos de consulta REAL (assistida/autorizada) do módulo
# rights; FGTS é orientativo. estimated_amount é sempre 0.0 aqui.

import asyncio

import pytest

from app.core.config import settings
from app.fiscal.rights_monitor.services.fgts_connector import FGTSConnector
from app.fiscal.rights_monitor.services.monitor import RightsMonitorAggregator
from app.fiscal.rights_monitor.services.receita_connector import ReceitaConnector
from app.fiscal.rights_monitor.services.svr_connector import SVRConnector


def test_svr_connector_aponta_consulta_assistida_sem_fabricar_valor():
    candidate = asyncio.run(SVRConnector().check_rights(user_id="u1"))

    assert candidate.source == "SVR_BACEN"
    assert candidate.status == "PENDING_VERIFICATION"
    assert candidate.estimated_amount == 0.0
    assert "/rights/{user_id}/svr/check" in candidate.description
    assert candidate.action_url == "https://valoresareceber.bcb.gov.br/"


def test_fgts_connector_orientativo_sem_fabricar_valor():
    candidate = asyncio.run(FGTSConnector().check_rights(user_id="u1"))

    assert candidate.source == "FGTS"
    assert candidate.status == "PENDING_VERIFICATION"
    assert candidate.estimated_amount == 0.0


def test_receita_connector_com_serpro_configurado(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", True, raising=False)
    candidate = asyncio.run(ReceitaConnector().check_rights(user_id="u1"))

    assert candidate.source == "IR_RESTITUTION"
    assert candidate.status == "PENDING_VERIFICATION"
    assert candidate.estimated_amount == 0.0
    assert "/rights/{user_id}/ir/check" in candidate.description


def test_receita_connector_sem_serpro(monkeypatch):
    monkeypatch.setattr(settings, "SERPRO_RESTITUICAO_TRIAL", False, raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_KEY", "", raising=False)
    monkeypatch.setattr(settings, "SERPRO_CONSUMER_SECRET", "", raising=False)
    candidate = asyncio.run(ReceitaConnector().check_rights(user_id="u1"))

    assert candidate.status == "PENDING_VERIFICATION"
    assert "ainda não está" in candidate.description


def test_aggregator_reune_as_tres_fontes():
    report = asyncio.run(RightsMonitorAggregator().run_scan(user_id="user_2"))

    assert report.user_id == "user_2"
    assert len(report.candidates) == 3
    assert {c.source for c in report.candidates} == {"SVR_BACEN", "FGTS", "IR_RESTITUTION"}
    # Sem consulta real executada, nunca há valor "estimado":
    assert report.total_estimated_amount == 0.0


def test_aggregator_tolera_excecao_em_conector(monkeypatch):
    aggregator = RightsMonitorAggregator()

    async def boom(*args, **kwargs):
        raise ValueError("Simulated connection error")

    monkeypatch.setattr(aggregator.svr, "check_rights", boom)

    report = asyncio.run(aggregator.run_scan(user_id="user_err"))

    assert len(report.candidates) == 2
    assert "SVR_BACEN" not in {c.source for c in report.candidates}
