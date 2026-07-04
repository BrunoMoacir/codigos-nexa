# tests/opportunities/test_chat_api_parity.py
"""
Ticket OPP1-A (docs/OPP1_DINHEIRO_PARADO_PLANO.md).

Antes desta mudança, `app/agent/tools/get_opportunities.py` (chat) tinha uma
função `_calc_idle_amount` própria, quase idêntica a
`IdleMoneyDetector._calculate`, calculando dinheiro ocioso de forma
independente do endpoint REST / job diário. Este teste garante que:

  1. essa implementação duplicada não volta a existir na tool;
  2. chat e OpportunityEngine (usado pela API e pelo job) retornam
     exatamente o mesmo idle_amount para os mesmos dados de entrada.
"""
from datetime import date, timedelta

import polars as pl
import pytest

import app.core.db.queries as queries_module
import app.agent.tools.get_opportunities as chat_tool_module
from app.opportunities.services.opportunity_engine import OpportunityEngine

USER_ID = "test_user_opp1a"


def _synthetic_transactions() -> pl.DataFrame:
    """~3 meses de renda e despesa com sobra mensal previsível (idle > 0)."""
    today = date.today()
    rows = []
    for months_back in range(4):  # cobre a janela usada pelo detector (cutoff ~3 meses)
        base = today - timedelta(days=30 * months_back)
        rows.append({"date": base, "amount": 6000.0})               # renda
        rows.append({"date": base + timedelta(days=5), "amount": -3500.0})  # despesa
    return pl.DataFrame(rows)


@pytest.fixture(autouse=True)
def _patch_transactions(monkeypatch):
    df = _synthetic_transactions()
    monkeypatch.setattr(queries_module, "get_transactions_for_user", lambda user_id: df)


def test_chat_tool_nao_tem_calculo_proprio_de_idle_amount():
    """Regressão: a tool não pode reintroduzir uma fórmula de ocioso paralela."""
    assert not hasattr(chat_tool_module, "_calc_idle_amount")


def test_chat_e_engine_retornam_o_mesmo_idle_amount():
    expected = OpportunityEngine().analyze(
        user_id=USER_ID, holding_months=12, persist_snapshot=False
    )
    assert expected.idle_amount > 0, "fixture deveria gerar dinheiro ocioso positivo"

    text = chat_tool_module.get_opportunities.invoke({"user_id": USER_ID})

    assert f"R$ {expected.idle_amount:,.2f}" in text


def test_chat_tool_sem_transacoes_nao_quebra(monkeypatch):
    monkeypatch.setattr(
        queries_module, "get_transactions_for_user", lambda user_id: pl.DataFrame()
    )
    text = chat_tool_module.get_opportunities.invoke({"user_id": USER_ID})
    assert isinstance(text, str)
    assert len(text) > 0


def test_chat_tool_nao_persiste_snapshot(monkeypatch):
    """A tool roda sob demanda a cada pergunta do chat; não deve gravar
    opportunity_snapshots a cada chamada (isso é papel do job diário / GET
    explícito da API) — ver docstring do módulo."""
    calls = []
    from app.opportunities.services import opportunity_engine as engine_module

    original_persist = engine_module.OpportunityEngine._persist_snapshot
    monkeypatch.setattr(
        engine_module.OpportunityEngine,
        "_persist_snapshot",
        staticmethod(lambda *a, **k: calls.append((a, k))),
    )

    chat_tool_module.get_opportunities.invoke({"user_id": USER_ID})

    assert calls == [], "chat tool não deveria acionar persistência de snapshot"
