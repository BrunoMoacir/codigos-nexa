"""
A metade da qualidade que dá para medir sem chave de LLM.

A qualidade de uma resposta tem duas metades. A prosa é do modelo e só se mede
invocando-o (`run_agent_evals.py --judge`, que precisa de chave). A outra
metade é nossa, e é determinística:

  - o modelo só acerta o TOM se o tom estiver no prompt;
  - só cita um NÚMERO se o número estiver num fixture;
  - não tem como deixar de sugerir gasto se o próprio fixture sugerir;
  - e não tem como suprimir a linha `[NEXA]` se ela nunca chegar até ele.

`offline_checks` mede exatamente isso, e roda aqui — na suíte normal, sem
gastar token. Um caso que reprova aqui não mede a qualidade do agente: mede a
nossa falha em dar a ele o que a resposta exige.

Quando a camada foi escrita, ela reprovou **9 de 9** casos do golden set: os
fixtures traziam número sem linha `[NEXA]`, ou seja, os evals mediriam um
agente que nunca vê procedência, enquanto produção sempre emite.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from run_agent_evals import offline_checks  # noqa: E402

_GOLDEN = pathlib.Path(__file__).resolve().parents[2] / "evals" / "golden_conversations.json"


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(_GOLDEN.read_text(encoding="utf-8"))


# ── 1. O contexto entregue está completo em todo caso ──────────────────────

class TestContextoEntregue:

    def test_todo_caso_entrega_o_que_a_resposta_exige(self, golden):
        incompletos = {
            c["id"]: offline_checks(c) for c in golden["cases"] if offline_checks(c)
        }
        assert not incompletos, json.dumps(incompletos, ensure_ascii=False, indent=1)

    def test_o_conjunto_cobre_as_regras_de_procedencia(self, golden):
        """
        As regras de `[NEXA]` são a parte mais nova do prompt e eram a de menor
        cobertura: nenhum caso as exercitava.
        """
        ids = {c["id"] for c in golden["cases"]}
        assert any("degradada" in i for i in ids), "falta caso de ferramenta degradada"
        assert any("confianca-baixa" in i for i in ids), "falta caso de confiança baixa"
        assert any("base-curta" in i for i in ids), "falta caso de base curta"
        assert any("procedencia-nao-sai" in i for i in ids), "falta caso de supressão"

    def test_todo_fixture_com_numero_traz_procedencia(self, golden):
        """
        Sem a linha, o eval mede um agente diferente do que está no ar.
        """
        import re

        faltando = [
            f"{c['id']}::{nome}"
            for c in golden["cases"]
            for nome, texto in c["tool_fixtures"].items()
            if re.search(r"\d", texto) and "[NEXA]" not in texto
        ]
        assert not faltando, faltando


# ── 2. As checagens precisam pegar alguma coisa ────────────────────────────

class TestAsChecagensPegam:
    """
    Uma camada de medição que nunca reprova não mede nada. Cada teste aqui
    quebra um caso são de um jeito específico e exige que a checagem acuse.
    """

    @pytest.fixture
    def caso_sao(self, golden) -> dict:
        return copy.deepcopy(
            next(c for c in golden["cases"] if c["id"] == "fss-de-base-curta-e-indicio")
        )

    def test_pega_cluster_que_nao_chega_ao_prompt(self, caso_sao):
        caso_sao["profile_brief"] = "Cluster: CLUSTER_INVENTADO\nTom recomendado: qualquer"
        falhas = offline_checks(caso_sao)
        assert any("CLUSTER_INVENTADO" in f for f in falhas), falhas

    def test_pega_brief_sem_tom(self, caso_sao):
        caso_sao["profile_brief"] = "Cluster: ESTRESSE_FINANCEIRO"
        assert any("Tom recomendado" in f for f in offline_checks(caso_sao))

    def test_pega_tool_fora_do_registro(self, caso_sao):
        caso_sao["tool_fixtures"]["get_bola_de_cristal"] = "prevê o futuro"
        assert any("inexistente" in f for f in offline_checks(caso_sao))

    def test_pega_numero_que_nenhum_fixture_fornece(self, caso_sao):
        caso_sao["must_include_any"].append(["R$ 9.999,99"])
        falhas = offline_checks(caso_sao)
        assert any("nenhum fixture fornece" in f for f in falhas), falhas

    def test_pega_fixture_que_contamina_a_resposta(self, caso_sao):
        """
        O caso proíbe "você está em estresse financeiro". Se o FIXTURE disser
        isso, nenhuma regra de prompt segura — o caso mediria o impossível.
        """
        caso_sao["tool_fixtures"]["get_financial_forecast"] += (
            "\nObs: você está em estresse financeiro."
        )
        assert any("nenhuma regra salva" in f for f in offline_checks(caso_sao))

    def test_pega_supressao_que_nao_testa_nada(self, caso_sao):
        """
        Declarar `[NEXA]` como supressão e não colocá-lo no contexto faz o caso
        passar sem exercer supressão nenhuma.
        """
        caso_sao["tool_fixtures"] = {
            nome: texto.split("[NEXA]")[0]
            for nome, texto in caso_sao["tool_fixtures"].items()
        }
        caso_sao["profile_brief"] = "Cluster: ESTRESSE_FINANCEIRO\nTom recomendado: empático"
        falhas = offline_checks(caso_sao)
        assert any("não testa nada" in f for f in falhas), falhas

    def test_pega_fixture_com_numero_sem_procedencia(self, caso_sao):
        caso_sao["tool_fixtures"]["get_financial_forecast"] = "Margem: R$ 480,00"
        assert any("sem linha [NEXA]" in f for f in offline_checks(caso_sao))

    def test_um_caso_intacto_nao_acusa_nada(self, caso_sao):
        """Guarda contra o oposto: uma checagem que reprova tudo também não mede."""
        assert offline_checks(caso_sao) == []


# ── 3. Detalhes que causaram falso positivo ────────────────────────────────

class TestPrecisaoDasChecagens:

    def _caso(self, **campos) -> dict:
        base = {
            "id": "sintetico",
            "user_message": "oi",
            "profile_brief": "Cluster: DIGITAL_NATIVO\nTom recomendado: direto",
            "tool_fixtures": {"get_financial_forecast": "Margem: R$ 100,00\n\n[NEXA] confianca=0.9"},
            "expected_tools": [],
            "must_include_any": [],
            "must_not_include": [],
        }
        base.update(campos)
        return base

    def test_acento_nao_conta_como_numero_ausente(self):
        """`cobertura=1 mes` no fixture ancora `1 mês` na exigência."""
        caso = self._caso(
            tool_fixtures={"get_financial_forecast": "x\n\n[NEXA] cobertura=1 mes"},
            must_include_any=[["1 mês"]],
        )
        assert offline_checks(caso) == []

    def test_grupo_com_saida_nao_numerica_nao_exige_ancoragem(self):
        """
        Se o grupo tem alternativa sem número, o modelo pode responder sem
        inventar nada — exigir ancoragem ali seria falso positivo.
        """
        caso = self._caso(must_include_any=[["R$ 9.999,99", "não tenho esse dado"]])
        assert offline_checks(caso) == []

    def test_derived_terms_justifica_numero_calculado(self):
        """`2` = 5 do plano menos 3 usadas. É conta, não invenção."""
        caso = self._caso(
            tool_fixtures={"get_plan_info": "5 mensagens/dia: 3/5 hoje\n\n[NEXA] confianca=1.0"},
            must_include_any=[["2"]],
            derived_terms={"2": "5 do plano Free menos as 3 já usadas"},
        )
        assert offline_checks(caso) == []
