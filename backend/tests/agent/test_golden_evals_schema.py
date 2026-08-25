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


def test_casos_de_cluster_trazem_o_brief_do_perfil(golden):
    """
    O cluster e o FSS chegam ao modelo pelo system prompt (o sistema injeta a
    partir do usuário autenticado), não por chamada de ferramenta. Um caso que
    afirma invariante de tom sem `profile_brief` mediria um agente sem cluster
    nenhum — que não é o que o usuário encontra.
    """
    for case in golden["cases"]:
        if "estresse" in case["id"] or "cluster" in case["id"]:
            assert case.get("profile_brief"), f"{case['id']}: sem profile_brief"
            assert "Cluster:" in case["profile_brief"], case["id"]


def test_o_harness_monta_o_prompt_como_producao():
    """
    Se o eval montar o system prompt de outro jeito, ele deixa de medir o
    agente que está no ar.
    """
    import sys

    from langchain_core.messages import HumanMessage

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from run_agent_evals import _build_eval_agent, build_prompt_modifier

    from app.agent.graph import SYSTEM_PROMPT, prompt_com_perfil

    brief = "Cluster: ESTRESSE_FINANCEIRO\nTom recomendado: empático"

    # O que o harness realmente entrega ao modelo, não só o que ele poderia.
    saida = build_prompt_modifier(brief)({"messages": [HumanMessage(content="oi")]})
    assert saida[0].content == prompt_com_perfil(brief)
    assert brief in saida[0].content and SYSTEM_PROMPT in saida[0].content
    assert isinstance(saida[1], HumanMessage)

    sem_perfil = build_prompt_modifier(None)({"messages": [HumanMessage(content="oi")]})
    assert sem_perfil[0].content == SYSTEM_PROMPT

    assert _build_eval_agent({}, brief) is not None
