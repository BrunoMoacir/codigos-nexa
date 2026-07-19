# tests/agent/test_golden_evals_schema.py
# Valida o golden set de evals SEM chamar LLM — roda na suíte normal.
# Garante que o arquivo não apodrece: schema, tools referenciadas existem,
# e o harness constrói o agente de eval (fixtures no lugar das tools reais).

import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden_conversations.json"


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_set_existe_com_casos_suficientes(golden):
    assert len(golden["cases"]) >= 8


def test_schema_de_cada_caso(golden):
    ids = set()
    for case in golden["cases"]:
        assert case["id"] and case["id"] not in ids, f"id duplicado: {case.get('id')}"
        ids.add(case["id"])
        assert case["user_message"].strip()
        assert isinstance(case["tool_fixtures"], dict)
        assert isinstance(case.get("expected_tools", []), list)
        assert case.get("judge_focus", "").strip(), f"{case['id']}: judge_focus vazio"
        for group in case.get("must_include_any", []):
            assert isinstance(group, list) and group, f"{case['id']}: grupo vazio"


def test_tools_referenciadas_existem_no_registro(golden):
    from app.agent.graph import AGENT_TOOLS

    registradas = {t.name for t in AGENT_TOOLS}
    for case in golden["cases"]:
        for name in list(case["tool_fixtures"]) + case.get("expected_tools", []):
            assert name in registradas, f"{case['id']}: tool desconhecida {name}"


def test_invariantes_de_produto_estao_cobertos(golden):
    """O golden set precisa cobrir os invariantes que mais importam."""
    ids = {c["id"] for c in golden["cases"]}
    assert any("estresse" in i for i in ids), "falta caso de ESTRESSE_FINANCEIRO"
    assert any("spoofing" in i or "user-id" in i for i in ids), "falta caso de spoofing"
    assert any("defesa" in i or "indicio" in i for i in ids), "falta caso de linguagem de indício"


def test_harness_constroi_agente_de_eval_sem_llm_call():
    """O builder de agente com fixtures precisa montar sem erro (não invoca)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from run_agent_evals import _build_eval_agent

    agent = _build_eval_agent({"get_financial_forecast": "Safe-to-spend: R$ 10,00/dia"})
    assert agent is not None


def test_checks_deterministicos_pegam_violacoes():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from run_agent_evals import _deterministic_checks

    case = {
        "expected_tools": ["get_financial_forecast"],
        "must_include_any": [["87"]],
        "must_not_include": ["JSON"],
    }
    # resposta ruim: sem tool, sem número, com proibido e formato americano
    falhas = _deterministic_checks(case, "Aqui está o JSON: R$ 100.50", [])
    assert len(falhas) == 4
    # resposta boa
    ok = _deterministic_checks(
        case, "Sua margem é R$ 87,40 por dia.", ["get_financial_forecast"]
    )
    assert ok == []
