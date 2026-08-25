#!/usr/bin/env python3
"""
scripts/run_agent_evals.py — Evals de qualidade de prosa do agente Nexa.

Como funciona:
  1. Carrega evals/golden_conversations.json — cada caso FIXA as saídas das
     ferramentas (tool_fixtures): a única variável é a PROSA do LLM real.
  2. Constrói um agente com as MESMAS ferramentas (nome + descrição reais,
     para o roteamento ser idêntico), mas cujo corpo devolve o fixture.
  3. Invoca o LLM real (ANTHROPIC_API_KEY/OPENAI_API_KEY necessária).
  4. Avalia em duas camadas:
     - DETERMINÍSTICA: ferramentas esperadas chamadas, must_include_any,
       must_not_include, formato monetário BR;
     - JUIZ LLM (--judge): nota 1–5 por rubrica (clareza, fidelidade aos
       números, tom do cluster, honestidade/disclaimers) com justificativa.
  5. Relatório no terminal + evals/last_report.json. Exit 1 se qualquer
     check determinístico falhar ou (com --judge) média < 4.0.

Três camadas, de barata a cara:

  OFFLINE (--offline): sem chave, sem token, roda na suíte normal
      (tests/agent/test_evals_offline.py). Mede a metade da qualidade que é
      NOSSA: o modelo só acerta o tom se o tom estiver no prompt, só cita um
      número se o número estiver num fixture, e não tem como suprimir a linha
      `[NEXA]` se ela nunca chegar até ele. Um caso que reprova aqui não mede
      o agente — mede a nossa falha em dar a ele o que a resposta exige.

  DETERMINÍSTICA: invoca o LLM real e confere tools chamadas, termos
      obrigatórios, termos proibidos e formato monetário BR.

  JUIZ (--judge): nota 1–5 por rubrica, com justificativa.

Uso:
    python3 scripts/run_agent_evals.py --offline      # sem chave
    python3 scripts/run_agent_evals.py                # + LLM, determinístico
    python3 scripts/run_agent_evals.py --judge        # + juiz LLM
    python3 scripts/run_agent_evals.py --case saude-financeira-basica
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

GOLDEN_PATH = BACKEND / "evals" / "golden_conversations.json"
REPORT_PATH = BACKEND / "evals" / "last_report.json"

JUDGE_RUBRIC = """Você é um avaliador rigoroso de assistentes financeiros brasileiros.
Avalie a RESPOSTA abaixo (dada ao USUÁRIO, com base EXCLUSIVA nos DADOS DAS FERRAMENTAS)
em 4 critérios, nota 1-5 cada:

1. CLAREZA: resposta principal na primeira frase? Legível, sem jargão desnecessário?
2. FIDELIDADE: todos os números vêm dos dados das ferramentas, corretos e em formato
   R$ brasileiro? (Qualquer número inventado = nota 1 neste critério.)
3. TOM: adequado ao cluster indicado nos dados? (ESTRESSE_FINANCEIRO exige empatia e
   proibição de sugerir gastos; DIGITAL_NATIVO exige concisão; etc.)
4. HONESTIDADE: disclaimers cabíveis presentes (investimento = educacional; defesa =
   indícios), limitações admitidas, sem promessas?

FOCO ESPECÍFICO deste caso: {judge_focus}

Responda APENAS JSON válido:
{{"clareza": n, "fidelidade": n, "tom": n, "honestidade": n, "justificativa": "1-2 frases"}}"""


def build_prompt_modifier(perfil: str | None = None):
    """
    O montador de system prompt do eval — o MESMO de produção.

    Exposto (sem underscore) para que o teste possa afirmar a igualdade. Se o
    harness montar o prompt de outro jeito, o eval deixa de medir o agente que
    está no ar, e isso é invisível numa inspeção rápida.
    """
    from langchain_core.messages import SystemMessage

    from app.agent.graph import _trim_history, prompt_com_perfil

    def _modifier(state):
        messages = state["messages"] if isinstance(state, dict) else state
        return [SystemMessage(content=prompt_com_perfil(perfil))] + _trim_history(messages)

    return _modifier


def _build_eval_agent(fixtures: dict[str, str], perfil: str | None = None):
    """
    Agente com as tools reais substituídas por fixtures (mesmo nome/descrição).

    `perfil` reproduz o brief que o sistema injeta no system prompt em
    produção (ver `graph.prompt_com_perfil`). Sem ele, o eval mediria um agente
    sem cluster nenhum — que não é o que o usuário encontra.
    """
    from langchain_core.tools import StructuredTool

    from app.agent.graph import AGENT_TOOLS
    from langgraph.prebuilt import create_react_agent
    import inspect

    def _fixture_fn(tool_name):
        def fn(**kwargs):
            return fixtures.get(
                tool_name,
                f"[{tool_name}] Sem dados disponíveis para este usuário no momento.",
            )
        return fn

    eval_tools = [
        StructuredTool.from_function(
            func=_fixture_fn(original.name),
            name=original.name,
            description=original.description,
            args_schema=original.args_schema,
        )
        for original in AGENT_TOOLS
    ]

    from app.agent.graph import _build_llm

    llm = _build_llm()
    signature = inspect.signature(create_react_agent)
    kwarg = ("prompt" if "prompt" in signature.parameters else "state_modifier")
    return create_react_agent(llm, tools=eval_tools, **{kwarg: build_prompt_modifier(perfil)})


def _deterministic_checks(case: dict, answer: str, tools_called: list[str]) -> list[str]:
    failures = []
    for expected in case.get("expected_tools", []):
        if expected not in tools_called:
            failures.append(f"tool esperada não chamada: {expected}")
    for group in case.get("must_include_any", []):
        if not any(term.lower() in answer.lower() for term in group):
            failures.append(f"nenhum de {group} presente na resposta")
    for banned in case.get("must_not_include", []):
        if banned.lower() in answer.lower():
            failures.append(f"conteúdo proibido presente: {banned!r}")
    # formato monetário: se há "R$ 1234.56" (ponto decimal americano), reprova
    if re.search(r"R\$ ?\d+\.\d{2}(?!\d)", answer):
        failures.append("valor monetário em formato americano (use 1.234,56)")
    return failures


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CAMADA OFFLINE — o que ENTREGAMOS ao modelo, sem gastar token
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# A qualidade da resposta tem duas metades. A prosa é do modelo e só se mede
# invocando-o (`--judge`). A outra metade é nossa: o modelo só pode acertar o
# tom se o tom estiver no prompt, só pode citar um número se o número estiver
# num fixture, e não tem como não sugerir gasto se o próprio fixture sugerir.
#
# Esta camada mede essa metade, sem chave e sem token, e roda na suíte normal.
# Ela reprova um caso cujo CONTEXTO seja insuficiente para a resposta que o
# caso exige — que é um defeito de eval tão real quanto uma prosa ruim.

_NUMERO = re.compile(r"\d")


def _sem_acento(texto: str) -> str:
    """Comparação insensível a acento e caixa — `1 mes` e `1 mês` são o mesmo."""
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )


def _contexto_entregue(case: dict) -> tuple[str, dict[str, str]]:
    """O par (system prompt montado, fixtures) que o modelo receberia."""
    from app.agent.graph import prompt_com_perfil

    return prompt_com_perfil(case.get("profile_brief")), case.get("tool_fixtures", {})


def offline_checks(case: dict) -> list[str]:
    """
    Falhas no contexto entregue ao modelo. Lista vazia = o modelo tem o que
    precisa; se errar a partir daqui, o erro é dele.
    """
    from app.agent.graph import AGENT_TOOLS

    prompt, fixtures = _contexto_entregue(case)
    corpo = "\n".join(fixtures.values())
    falhas: list[str] = []

    # 1. O tom do cluster chegou junto?
    brief = case.get("profile_brief") or ""
    if "Cluster:" in brief:
        cluster = brief.split("Cluster:", 1)[1].split("\n", 1)[0].strip()
        if cluster and cluster not in prompt:
            falhas.append(f"cluster {cluster} não chegou ao system prompt")
        if "Tom recomendado:" not in prompt:
            falhas.append("brief sem 'Tom recomendado' — o modelo não sabe como falar")
        if cluster and cluster not in SYSTEM_PROMPT_CLUSTERS:
            falhas.append(f"cluster {cluster} não tem adaptação escrita no prompt")

    # 2. As ferramentas do caso existem e são roteáveis?
    registradas = {t.name for t in AGENT_TOOLS}
    for nome in list(fixtures) + case.get("expected_tools", []):
        if nome not in registradas:
            falhas.append(f"tool inexistente no registro: {nome}")
        elif f"`{nome}(" not in prompt and f"`{nome}`" not in prompt:
            falhas.append(f"tool {nome} sem seção no prompt — roteamento às cegas")

    # 3. O que o caso EXIGE na resposta está ancorado no que entregamos?
    #    Um `must_include_any` cujo grupo inteiro tenha número e nenhum termo
    #    apareça nos fixtures está pedindo invenção.
    #    Só é problema quando TODAS as alternativas do grupo trazem número e
    #    nenhuma está ancorada: aí o modelo é obrigado a inventar. Se o grupo
    #    tem saída não-numérica, ele pode responder sem inventar nada.
    derivados = case.get("derived_terms", {})
    corpo_norm = _sem_acento(corpo)
    for grupo in case.get("must_include_any", []):
        com_numero = [t for t in grupo if _NUMERO.search(t)]
        if not com_numero or len(com_numero) < len(grupo):
            continue
        ancorado = any(_sem_acento(t) in corpo_norm for t in com_numero)
        declarado = any(t in derivados for t in com_numero)
        if not ancorado and not declarado:
            falhas.append(
                f"grupo {com_numero} exige número que nenhum fixture fornece "
                f"nem `derived_terms` justifica"
            )

    # 4. Dois testes opostos sobre o mesmo `must_not_include`:
    #
    #    - CONTAMINAÇÃO: o termo não pode estar no contexto. Se o fixture já
    #      sugere gasto a quem está em estresse, nenhuma regra de prompt salva
    #      a resposta — o caso mediria o impossível.
    #    - SUPRESSÃO: o termo TEM de estar no contexto e não pode sair na
    #      resposta. É o caso da linha `[NEXA]`, que é informação de sistema.
    #      Aqui a ausência no contexto é que invalida o caso: sem o termo
    #      presente, o teste não exerce supressão nenhuma.
    #    A presença é medida no que é ESPECÍFICO do caso (fixtures + brief), não
    #    no system prompt genérico: `[NEXA]` aparece nas regras do prompt para
    #    todo caso, então olhar ali faria a checagem de supressão nunca disparar.
    especifico = f"{corpo}\n{case.get('profile_brief') or ''}".lower()
    suprimir = {t.lower() for t in case.get("suppress_from_context", [])}
    for proibido in case.get("must_not_include", []):
        presente = proibido.lower() in especifico
        if proibido.lower() in suprimir:
            if not presente:
                falhas.append(
                    f"{proibido!r} é declarado como supressão mas não está no "
                    f"contexto — o caso não testa nada"
                )
        elif proibido.lower() in corpo.lower():
            falhas.append(f"fixture contém o proibido {proibido!r} — nenhuma regra salva")

    # 5. Fixture com número deveria trazer procedência: é o que exercita as
    #    regras de `[NEXA]` do prompt.
    for nome, texto in fixtures.items():
        if _NUMERO.search(texto) and "[NEXA]" not in texto:
            falhas.append(f"fixture de {nome} tem número sem linha [NEXA]")

    return falhas


# Clusters com adaptação de tom escrita no system prompt.
SYSTEM_PROMPT_CLUSTERS = (
    "EXPLORADOR_GLOBAL", "URBANO_FOODIE", "INVESTIDOR_CAUTELOSO",
    "FAMILIA_ESTRUTURADA", "DIGITAL_NATIVO", "ESTRESSE_FINANCEIRO",
    "MICROEMPREENDEDOR", "NAO_CLASSIFICADO",
)


def _judge(case: dict, answer: str) -> dict | None:
    from app.agent.graph import _build_llm

    llm = _build_llm()
    prompt = JUDGE_RUBRIC.format(judge_focus=case.get("judge_focus", "qualidade geral"))
    content = (
        f"{prompt}\n\n=== DADOS DAS FERRAMENTAS ===\n{json.dumps(case['tool_fixtures'], ensure_ascii=False, indent=1)}"
        f"\n\n=== PERGUNTA DO USUÁRIO ===\n{case['user_message']}\n\n=== RESPOSTA ===\n{answer}"
    )
    raw = llm.invoke(content).content
    match = re.search(r"\{.*\}", raw if isinstance(raw, str) else str(raw), re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _rodar_offline(cases: list[dict]) -> int:
    """Relatório da camada offline. Devolve o exit code."""
    total_falhas = 0
    for case in cases:
        falhas = offline_checks(case)
        total_falhas += len(falhas)
        print(f"{'✅' if not falhas else '❌'} {case['id']}")
        for f in falhas:
            print(f"     ↳ {f}")

    completos = sum(1 for c in cases if not offline_checks(c))
    print(f"\nContexto completo em {completos}/{len(cases)} casos "
          f"({completos / len(cases):.0%})")
    if total_falhas:
        print(f"❌ {total_falhas} falha(s) de contexto — o modelo não teria como acertar")
        return 1
    print("✅ Todo caso entrega ao modelo o que a resposta exige")
    print("   (a prosa em si só se mede com --judge, que precisa de chave)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", action="store_true", help="ativa o juiz LLM (nota 1-5)")
    parser.add_argument("--case", help="roda apenas o caso com este id")
    parser.add_argument(
        "--offline", action="store_true",
        help="mede só o CONTEXTO entregue ao modelo — sem chave, sem token",
    )
    args = parser.parse_args()

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    cases = [c for c in golden["cases"] if not args.case or c["id"] == args.case]
    if not cases:
        print(f"Nenhum caso com id={args.case}")
        sys.exit(2)

    if args.offline:
        sys.exit(_rodar_offline(cases))

    from app.core.config import settings

    if not (settings.ANTHROPIC_API_KEY or settings.OPENAI_API_KEY):
        print("⚠️ Configure ANTHROPIC_API_KEY (ou OPENAI_API_KEY) para rodar os evals.")
        print("   Sem chave, `--offline` mede o contexto entregue ao modelo.")
        sys.exit(2)

    from langchain_core.messages import HumanMessage

    report, det_failures_total, judge_scores = [], 0, []

    for case in cases:
        agent = _build_eval_agent(case["tool_fixtures"], case.get("profile_brief"))
        result = agent.invoke({
            "messages": [HumanMessage(content=f"[user_id=eval_user] {case['user_message']}")]
        })
        messages = result["messages"]
        answer = messages[-1].content if messages else ""
        tools_called = [
            tc["name"]
            for m in messages
            for tc in (getattr(m, "tool_calls", None) or [])
        ]

        failures = _deterministic_checks(case, answer, tools_called)
        det_failures_total += len(failures)
        entry = {
            "id": case["id"],
            "tools_called": tools_called,
            "deterministic_failures": failures,
            "answer": answer,
        }

        if args.judge:
            verdict = _judge(case, answer)
            entry["judge"] = verdict
            if verdict:
                avg = sum(verdict[k] for k in ("clareza", "fidelidade", "tom", "honestidade")) / 4
                judge_scores.append(avg)
                entry["judge_avg"] = round(avg, 2)

        status = "✅" if not failures else "❌"
        extra = f" | juiz: {entry.get('judge_avg', '—')}" if args.judge else ""
        print(f"{status} {case['id']:<42} tools={tools_called}{extra}")
        for f in failures:
            print(f"     ↳ {f}")
        report.append(entry)

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRelatório: {REPORT_PATH}")

    overall_judge = (sum(judge_scores) / len(judge_scores)) if judge_scores else None
    if overall_judge is not None:
        print(f"Nota média do juiz: {overall_judge:.2f}/5")

    if det_failures_total:
        print(f"\n❌ {det_failures_total} falhas determinísticas")
        sys.exit(1)
    if overall_judge is not None and overall_judge < 4.0:
        print("\n❌ Média do juiz abaixo de 4.0")
        sys.exit(1)
    print("\n✅ Evals OK")


if __name__ == "__main__":
    main()
