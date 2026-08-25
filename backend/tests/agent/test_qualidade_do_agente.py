"""
Procedência nas respostas de ferramenta, e o perfil deixando de depender de o
modelo lembrar.

Duas lacunas de qualidade que sobreviveram à auditoria e à revalidação:

**1. O modelo tinha de adivinhar pelo texto o que era medição.** As 31 tools
devolviam prosa livre. Estas três frases são idênticas para quem só lê texto:

    "Tarifas identificadas: R$ 174,50"   ← medido, 6 meses de extrato
    "Tarifas identificadas: R$ 0,00"     ← medido, sem tarifas
    "Tarifas identificadas: R$ 0,00"     ← o detector não rodou

A terceira vira "seu banco não cobra tarifas", que é falso. Uma ferramenta já
resolvia isso bem (`get_card_optimization`, com `[META]` e escalonamento para o
especialista abaixo de 0,50); `app/agent/procedencia.py` generaliza o padrão.

**2. A "Regra Zero" era instrução, não garantia.** O prompt mandava chamar
`get_user_profile_context` antes de tudo. Se o modelo pulasse — por economia,
por a pergunta parecer direta, ou porque o corte de histórico levou o resultado
anterior — a adaptação de tom não acontecia. Para `ESTRESSE_FINANCEIRO` isso
significa oferecer produto novo a quem está afundando, que é o que a regra 10
proíbe. Agora o brief entra no system prompt a partir do usuário AUTENTICADO.
"""

from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import patch

import pytest

from app.agent.graph import SYSTEM_PROMPT, AGENT_TOOLS, _system_prompt_da_requisicao
from app.agent.identity import usuario_da_requisicao
from app.agent.procedencia import (
    LIMIAR_CONFIANCA_BAIXA,
    com_procedencia,
    degradada,
    ler_procedencia,
)


# ── 1. O formato ───────────────────────────────────────────────────────────

class TestFormatoDaProcedencia:

    def test_ida_e_volta(self):
        texto = com_procedencia(
            "Tarifas: R$ 174,50",
            fontes=["transactions_db", "market_fees_db"],
            confianca=0.83,
            cobertura_meses=6,
        )
        lido = ler_procedencia(texto)
        assert lido["confianca"] == 0.83
        assert lido["cobertura"] == "6 meses"
        assert lido["fontes"] == ["transactions_db", "market_fees_db"]
        assert lido["degradado"] is None
        assert "Tarifas: R$ 174,50" in texto

    def test_sem_campo_nenhum_o_texto_fica_intacto(self):
        """Linha vazia não informa nada e custa token em toda mensagem."""
        assert com_procedencia("só texto") == "só texto"
        assert ler_procedencia("só texto") == {}

    def test_degradada_zera_a_confianca_e_declara_o_motivo(self):
        lido = ler_procedencia(degradada("R$ 0,00 em tarifas", "sem_extrato"))
        assert lido["confianca"] == 0.0
        assert lido["degradado"] == "sem_extrato"

    @pytest.mark.parametrize("entrada,esperado", [(1.7, 1.0), (-0.4, 0.0), (0.5, 0.5)])
    def test_confianca_e_presa_na_faixa(self, entrada, esperado):
        assert ler_procedencia(com_procedencia("x", confianca=entrada))["confianca"] == esperado

    @pytest.mark.parametrize("meses,esperado", [
        (0, "sem historico"), (1, "1 mes"), (6, "6 meses"), (0.5, "15 dias"),
    ])
    def test_cobertura_em_linguagem_util(self, meses, esperado):
        assert ler_procedencia(com_procedencia("x", cobertura_meses=meses))["cobertura"] == esperado

    def test_fontes_repetidas_nao_duplicam(self):
        lido = ler_procedencia(com_procedencia("x", fontes=["a", "b", "a"]))
        assert lido["fontes"] == ["a", "b"]


# ── 2. As ferramentas que carregam procedência ─────────────────────────────

_COM_PROCEDENCIA = [
    "get_user_profile_context",
    "get_financial_forecast",
    "get_budget_advice",
    "get_bank_cost_analysis",
    "get_purchase_recommendation",
    "detect_abusive_fees",
    "detect_wrongful_charges",
    "get_defense_analysis",
]

_ARGS = {"get_purchase_recommendation": {"amount": 3000.0, "category": "Eletrônicos"}}


@pytest.fixture(scope="module")
def usuario_com_extrato():
    from sqlalchemy import text

    from app.core.database import SessionLocal

    uid = f"qualidade-{uuid.uuid4().hex[:8]}"
    linhas = []
    for mes in range(1, 7):
        base = dt.date(2026, mes, 1)
        linhas += [
            (base.replace(day=5), 6_500.0, "SALARIO EMPRESA XYZ", "Renda"),
            (base.replace(day=10), -2_100.0, "ALUGUEL APTO", "Moradia"),
            (base.replace(day=18), -55.0, "TARIFA PACOTE SERVICOS", "Tarifas"),
        ]
    with SessionLocal() as db:
        for data, valor, descricao, categoria in linhas:
            db.execute(
                text(
                    "INSERT INTO transactions_clean (transaction_id, user_id, account_id,"
                    " description, amount, date, transaction_type, category,"
                    " is_recurring, is_installment)"
                    " VALUES (:t,:u,'acc',:d,:v,:dt,'DEBIT',:c,false,false)"
                ),
                {"t": str(uuid.uuid4()), "u": uid, "d": descricao,
                 "v": valor, "dt": data, "c": categoria},
            )
        db.commit()
    yield uid
    with SessionLocal() as db:
        db.execute(text("DELETE FROM transactions_clean WHERE user_id=:u"), {"u": uid})
        db.execute(text("DELETE FROM bank_fee_history WHERE user_id=:u"), {"u": uid})
        db.commit()


class TestFerramentasDeclaramProcedencia:

    @pytest.mark.parametrize("nome", _COM_PROCEDENCIA)
    def test_a_linha_esta_presente(self, nome, usuario_com_extrato):
        tool = next(t for t in AGENT_TOOLS if t.name == nome)
        lido = ler_procedencia(
            tool.invoke({"user_id": usuario_com_extrato, **_ARGS.get(nome, {})})
        )
        assert lido, f"{nome} respondeu sem linha [NEXA]"
        assert lido["fontes"], f"{nome} não declarou nenhuma fonte"

    @pytest.mark.parametrize("nome", _COM_PROCEDENCIA)
    def test_com_dados_reais_nada_sai_degradado(self, nome, usuario_com_extrato):
        tool = next(t for t in AGENT_TOOLS if t.name == nome)
        lido = ler_procedencia(
            tool.invoke({"user_id": usuario_com_extrato, **_ARGS.get(nome, {})})
        )
        assert lido.get("degradado") is None, f"{nome}: {lido['degradado']}"

    def test_usuario_sem_extrato_sai_marcado_como_degradado(self):
        """
        É o caso que motivou tudo: "R$ 0,00" sem marcação vira "seu banco não
        cobra tarifas".
        """
        from app.agent.tools.get_financial_forecast import get_financial_forecast

        lido = ler_procedencia(
            get_financial_forecast.invoke({"user_id": f"vazio-{uuid.uuid4().hex[:6]}"})
        )
        assert lido.get("degradado") == "sem_transacoes"
        assert lido["confianca"] == 0.0

    def test_excecao_no_pipeline_vira_degradado_e_nao_silencio(self):
        from app.agent.tools.get_financial_forecast import get_financial_forecast

        with patch("app.runner.get_runner", side_effect=RuntimeError("boom")):
            lido = ler_procedencia(get_financial_forecast.invoke({"user_id": "qualquer"}))
        assert lido.get("degradado") == "excecao_no_pipeline"

    def test_a_confianca_acompanha_a_cobertura(self, usuario_com_extrato):
        """Seis meses de extrato não podem valer o mesmo que um."""
        from app.agent.tools.get_financial_forecast import get_financial_forecast

        seis = ler_procedencia(
            get_financial_forecast.invoke({"user_id": usuario_com_extrato})
        )
        assert seis["confianca"] > LIMIAR_CONFIANCA_BAIXA
        assert seis["cobertura"] == "6 meses"


# ── 3. O FSS diz em que base se apoia ──────────────────────────────────────

class TestConfiancaDoFSS:
    """
    `fss_confidence` era calculado pelo `FSSCalculator` desde a rodada de
    inteligência comportamental e descartado por todos os consumidores. O FSS
    muda o TOM de toda resposta e saía igual para 3 meses de base e para 1 dia.
    """

    def _perfil(self, meses: int) -> str:
        from sqlalchemy import text

        import app.agent.tools.get_user_profile_context as mod
        from app.core.database import SessionLocal

        uid = f"fss-{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            for mes in range(1, meses + 1):
                for dia, valor, desc in ((3, 3_000.0, "SALARIO"), (5, -2_500.0, "ALUGUEL"),
                                         (12, -450.0, "JUROS ROTATIVO CARTAO")):
                    db.execute(
                        text(
                            "INSERT INTO transactions_clean (transaction_id,user_id,account_id,"
                            "description,amount,date,transaction_type,category,is_recurring,"
                            "is_installment) VALUES (:t,:u,'acc',:d,:v,:dt,'DEBIT','x',false,false)"
                        ),
                        {"t": str(uuid.uuid4()), "u": uid, "d": desc, "v": valor,
                         "dt": dt.date(2026, mes, dia)},
                    )
            db.commit()
        mod._MEM_CACHE.clear()
        try:
            return mod.get_user_profile_context.invoke({"user_id": uid})
        finally:
            with SessionLocal() as db:
                db.execute(text("DELETE FROM transactions_clean WHERE user_id=:u"), {"u": uid})
                db.commit()
            mod._MEM_CACHE.clear()

    def test_base_curta_e_declarada_ao_agente(self):
        texto = self._perfil(meses=1)
        assert "Confiança do FSS" in texto
        assert "BASE CURTA" in texto

    def test_base_longa_nao_carrega_o_aviso(self):
        texto = self._perfil(meses=6)
        assert "Confiança do FSS" in texto
        assert "BASE CURTA" not in texto

    def test_a_confianca_sobe_com_a_base(self):
        curta = ler_procedencia(self._perfil(meses=1))["confianca"]
        longa = ler_procedencia(self._perfil(meses=6))["confianca"]
        assert curta < longa, (curta, longa)


# ── 4. A Regra Zero deixou de depender de o modelo lembrar ─────────────────

class TestPerfilNoSystemPrompt:

    def test_sem_requisicao_o_prompt_fica_igual(self):
        assert _system_prompt_da_requisicao() == SYSTEM_PROMPT

    def test_com_requisicao_o_tom_do_cluster_entra(self, usuario_com_extrato):
        with usuario_da_requisicao(usuario_com_extrato):
            prompt = _system_prompt_da_requisicao()
        assert "PERFIL DESTE USUÁRIO" in prompt
        assert "Cluster:" in prompt
        assert "Tom recomendado:" in prompt

    def test_o_brief_vem_do_autenticado_e_nao_de_argumento(self):
        """
        Mesma regra da vinculação de identidade: o perfil que entra no prompt é
        o do dono da requisição. Não há caminho para o modelo influenciar isso.
        """
        import app.agent.graph as graph

        with patch(
            "app.agent.tools.get_user_profile_context.brief_do_perfil",
            side_effect=lambda uid: f"Cluster: PERFIL_DE_{uid}",
        ):
            with usuario_da_requisicao("dono-real"):
                prompt = graph._system_prompt_da_requisicao()
        assert "PERFIL_DE_dono-real" in prompt

    def test_sem_perfil_o_prompt_nao_inventa_secao(self):
        with patch(
            "app.agent.tools.get_user_profile_context.brief_do_perfil", return_value=None
        ):
            with usuario_da_requisicao("sem-perfil"):
                assert _system_prompt_da_requisicao() == SYSTEM_PROMPT

    def test_falha_no_brief_nao_derruba_o_chat(self):
        with patch(
            "app.agent.tools.get_user_profile_context.brief_do_perfil",
            side_effect=RuntimeError("boom"),
        ):
            with usuario_da_requisicao("qualquer"):
                assert _system_prompt_da_requisicao() == SYSTEM_PROMPT

    def test_o_brief_e_compacto(self, usuario_com_extrato):
        """Entra em TODA mensagem — o perfil completo (~530 chars) não cabe."""
        from app.agent.tools.get_user_profile_context import brief_do_perfil

        brief = brief_do_perfil(usuario_com_extrato)
        assert brief and len(brief) < 400, len(brief or "")

    def test_o_brief_reaproveita_o_cache_da_ferramenta(self, usuario_com_extrato):
        import time

        from app.agent.tools.get_user_profile_context import brief_do_perfil

        brief_do_perfil(usuario_com_extrato)  # aquece
        t0 = time.perf_counter()
        brief_do_perfil(usuario_com_extrato)
        assert time.perf_counter() - t0 < 0.05


# ── 5. O prompt sabe o que fazer com a linha ───────────────────────────────

class TestRegrasDeProcedenciaNoPrompt:

    @pytest.mark.parametrize("regra", [
        "[NEXA]",
        "degradado=",
        "confianca` < 0.50",
        "cobertura=sem historico",
        "nunca a repita",
        "NÃO significa",
        "get_expert_card_analysis",
    ])
    def test_a_regra_esta_escrita(self, regra):
        assert regra in SYSTEM_PROMPT, regra

    def test_o_limiar_do_codigo_e_o_do_prompt(self):
        """Se um mudar sem o outro, o agente passa a falar diferente do que mede."""
        assert f"{LIMIAR_CONFIANCA_BAIXA:.2f}" in SYSTEM_PROMPT

    def test_a_regra_zero_nao_manda_mais_chamar_a_ferramenta_primeiro(self):
        assert "O PERFIL JÁ ESTÁ COM VOCÊ" in SYSTEM_PROMPT
        assert "antes de qualquer outra ferramenta" not in SYSTEM_PROMPT
