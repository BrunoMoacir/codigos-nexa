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

Uso:
    python3 scripts/run_agent_evals.py                # só determinístico
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


def _build_eval_agent(fixtures: dict[str, str]):
    """Agente com as tools reais substituídas por fixtures (mesmo nome/descrição)."""
    from langchain_core.tools import StructuredTool

    from app.agent.graph import AGENT_TOOLS, _prepare_model_messages
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
    return create_react_agent(llm, tools=eval_tools, **{kwarg: _prepare_model_messages})


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", action="store_true", help="ativa o juiz LLM (nota 1-5)")
    parser.add_argument("--case", help="roda apenas o caso com este id")
    args = parser.parse_args()

    from app.core.config import settings

    if not (settings.ANTHROPIC_API_KEY or settings.OPENAI_API_KEY):
        print("⚠️ Configure ANTHROPIC_API_KEY (ou OPENAI_API_KEY) para rodar os evals.")
        sys.exit(2)

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    cases = [c for c in golden["cases"] if not args.case or c["id"] == args.case]
    if not cases:
        print(f"Nenhum caso com id={args.case}")
        sys.exit(2)

    from langchain_core.messages import HumanMessage

    report, det_failures_total, judge_scores = [], 0, []

    for case in cases:
        agent = _build_eval_agent(case["tool_fixtures"])
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
