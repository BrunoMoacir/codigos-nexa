"""
O agente com os dados como eles chegam em produção.

A cobertura que existia era de FORMA, não de conteúdo:

    assert isinstance(result, str)
    assert len(result) > 50
    assert any(kw in result for kw in ["Burn Rate", "R$", "transações",
                                       "Dados insuficientes"])

Qualquer string de erro passa nos dois primeiros, e o terceiro aceita
explicitamente a mensagem de indisponibilidade. Some-se a isso o usuário de
teste `golden_user_777`, que não tem transação nenhuma: os testes exercitavam
só o caminho vazio. Assim CINCO ferramentas quebradas ficaram verdes:

    get_financial_forecast   `df_a or df_b` → TypeError do polars. A tool nº 1
                             do agente respondia "Não consegui acessar os dados
                             financeiros agora" para TODO usuário com extrato —
                             o pipeline rodava inteiro e morria na última linha.
                             Só funcionava para quem NÃO tinha dados.
    get_budget_advice        seis atributos inventados em GroupSummary/BudgetCut
                             (`on_track`, `actual_spent`, `recommended_limit`,
                             `pct_of_income`, `suggested_cuts`, `suggested_limit`)
                             → AttributeError → sempre o 50/30/20 genérico, nunca
                             a análise dos gastos reais que o docstring promete.
    get_goals_summary        `GoalTracker()` sem sessão de banco, e o retorno é
                             `list[Goal]`, não `{"goals": [...]}`.
    detect_abusive_fees      `BankCostReport.entries` não existe (é
    detect_wrongful_charges  `fees_detected`) → AttributeError subindo para o
                             agente. D1 e D2 nunca produziram um achado.

O teste que faltava é o desta primeira classe: rodar toda tool com dados de
verdade e reprovar quem cair no próprio `except`.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

import polars as pl
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import AGENT_TOOLS, _trim_history, checkpointer_em_uso
from app.agent.identity import usuario_da_requisicao, vincular_ao_usuario
from app.agent.memoria import esquecer_conversas, thread_id_de

# Argumentos obrigatórios além de user_id, por tool.
_ARGS_EXTRA = {
    "get_purchase_recommendation": {"amount": 3000.0, "category": "Eletrônicos"},
    "get_financing_simulation": {"target_amount": 500_000.0},
    "get_timing_scenarios": {"target_amount": 500_000.0, "monthly_savings": 2_000.0},
    "get_leverage_simulation": {"target_amount": 500_000.0},
    "simulate_investment": {"amount": 10_000.0},
    "get_peer_comparison": {"monthly_income": 6_500.0},
    "get_expert_card_analysis": {"question": "qual cartão é melhor para mim?"},
}


@pytest.fixture(scope="module")
def usuario_com_extrato():
    """
    Usuário real em `transactions_clean` — seis meses de salário, moradia,
    alimentação, uma tarifa e um juro de rotativo.

    Precisa ser um usuário COM dados: as cinco tools quebradas passavam no
    caminho vazio e só falhavam quando havia extrato para processar.
    """
    from sqlalchemy import text

    from app.core.database import SessionLocal

    uid = f"teste-agente-{uuid.uuid4().hex[:8]}"
    linhas = []
    for mes in range(1, 7):
        base = dt.date(2026, mes, 1)
        linhas += [
            (base.replace(day=5), 6_500.0, "SALARIO EMPRESA XYZ", "Renda", "CREDIT"),
            (base.replace(day=10), -2_100.0, "ALUGUEL APTO", "Moradia", "DEBIT"),
            (base.replace(day=15), -890.0, "SUPERMERCADO BOM PRECO", "Alimentação", "DEBIT"),
            (base.replace(day=18), -55.0, "TARIFA PACOTE SERVICOS", "Tarifas", "DEBIT"),
            (base.replace(day=20), -180.0, "JUROS ROTATIVO CARTAO", "Juros", "DEBIT"),
            (base.replace(day=22), -320.0, "IFOOD DELIVERY", "Delivery", "DEBIT"),
        ]

    with SessionLocal() as db:
        for data, valor, descricao, categoria, tipo in linhas:
            db.execute(
                text(
                    "INSERT INTO transactions_clean "
                    "(transaction_id, user_id, account_id, description, amount, date,"
                    " transaction_type, category, is_recurring, is_installment) "
                    "VALUES (:tid, :uid, :acc, :desc, :amt, :dt, :tt, :cat, false, false)"
                ),
                {
                    "tid": str(uuid.uuid4()), "uid": uid, "acc": "acc-teste",
                    "desc": descricao, "amt": valor, "dt": data,
                    "tt": tipo, "cat": categoria,
                },
            )
        db.commit()

    yield uid

    with SessionLocal() as db:
        db.execute(text("DELETE FROM transactions_clean WHERE user_id = :uid"), {"uid": uid})
        db.commit()


class _ColetorDeErros(logging.Handler):
    """Guarda o que as tools mandam para o log em WARNING+."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.registros: list[str] = []

    def emit(self, rec):
        if rec.name.startswith("app.agent.tools"):
            try:
                self.registros.append(f"{rec.name}: {rec.getMessage()}")
            except Exception:  # pragma: no cover
                pass


# ── 1. Nenhuma tool pode cair no próprio except ────────────────────────────

class TestNenhumaToolMorreEmSilencio:
    """
    O `except Exception` de cada tool transforma um bug em "não consegui
    consultar agora". É a mensagem que o LLM repassa ao usuário, e é
    indistinguível de uma indisponibilidade real.
    """

    @pytest.mark.parametrize("tool", AGENT_TOOLS, ids=lambda t: t.name)
    def test_tool_nao_registra_erro_com_extrato_real(self, tool, usuario_com_extrato):
        coletor = _ColetorDeErros()
        raiz = logging.getLogger("app.agent.tools")
        raiz.addHandler(coletor)
        nivel, propaga = raiz.level, raiz.propagate
        raiz.setLevel(logging.WARNING)
        try:
            resultado = tool.invoke(
                {"user_id": usuario_com_extrato, **_ARGS_EXTRA.get(tool.name, {})}
            )
        finally:
            raiz.removeHandler(coletor)
            raiz.setLevel(nivel)
            raiz.propagate = propaga

        falhas = [r for r in coletor.registros if "erro" in r.lower() or "Error" in r]
        assert not falhas, f"{tool.name} caiu no except: {falhas}"
        assert isinstance(resultado, str) and resultado.strip()

    @pytest.mark.parametrize("tool", AGENT_TOOLS, ids=lambda t: t.name)
    def test_tool_nao_levanta_para_o_agente(self, tool, usuario_com_extrato):
        """
        `detect_abusive_fees` e `detect_wrongful_charges` levantavam
        AttributeError para FORA da tool — o agente recebia o traceback.
        """
        tool.invoke({"user_id": usuario_com_extrato, **_ARGS_EXTRA.get(tool.name, {})})


# ── 2. As cinco que estavam quebradas, uma a uma ───────────────────────────

class TestForecastComDadosReais:

    def test_entrega_o_diagnostico_e_nao_a_desculpa(self, usuario_com_extrato):
        from app.agent.tools.get_financial_forecast import get_financial_forecast

        r = get_financial_forecast.invoke({"user_id": usuario_com_extrato})
        assert "Diagnóstico Financeiro" in r
        assert "Não consegui acessar" not in r

    def test_o_helper_nao_usa_or_em_dataframe(self):
        """
        `df_a or df_b` levanta TypeError no polars. O helper resolve por
        `is_empty()`, e este teste trava a regra.
        """
        from app.agent.tools.get_financial_forecast import _primeiro_df_nao_vazio

        cheio = pl.DataFrame({"amount": [1.0]})
        vazio = pl.DataFrame({"amount": []})
        assert _primeiro_df_nao_vazio(cheio, vazio) is cheio
        assert _primeiro_df_nao_vazio(vazio, cheio) is cheio
        assert _primeiro_df_nao_vazio(None, cheio) is cheio
        assert _primeiro_df_nao_vazio(None, None).is_empty()
        assert _primeiro_df_nao_vazio(vazio, None).is_empty()

    def test_a_expressao_antiga_realmente_explodia(self):
        """Documenta o motivo: sem isto, alguém 'simplifica' de volta."""
        with pytest.raises(TypeError, match="ambiguous"):
            _ = pl.DataFrame({"a": [1]}) or pl.DataFrame()


class TestOrcamentoUsaOsGastosReais:

    def test_traz_a_analise_por_grupo_e_nao_o_template(self, usuario_com_extrato):
        from app.agent.tools.get_budget_advice import get_budget_advice

        r = get_budget_advice.invoke({"user_id": usuario_com_extrato})
        assert "Plano de Orçamento 50/30/20" in r, "caiu no fallback genérico"
        assert "Essenciais" in r and "recomendado" in r

    def test_os_campos_do_advisor_existem_de_verdade(self):
        """
        Eram seis nomes inventados. Se o BudgetAdvisor renomear qualquer um,
        este teste cai antes de o AttributeError virar 50/30/20 genérico.
        """
        from app.budget.budget_advisor import BudgetCut, GroupSummary

        assert {"group", "current_amount", "suggested_amount", "current_pct", "status"} <= set(
            GroupSummary.__dataclass_fields__
        )
        assert {"category", "current", "suggested", "saving"} <= set(
            BudgetCut.__dataclass_fields__
        )

    def test_renda_e_opcional_e_vem_do_extrato(self, usuario_com_extrato):
        from app.agent.tools.get_budget_advice import get_budget_advice

        r = get_budget_advice.invoke({"user_id": usuario_com_extrato})
        assert "renda estimada pelo seu extrato" in r

    def test_renda_declarada_e_rotulada_como_tal(self, usuario_com_extrato):
        from app.agent.tools.get_budget_advice import get_budget_advice

        r = get_budget_advice.invoke(
            {"user_id": usuario_com_extrato, "monthly_income": 9_000.0}
        )
        assert "renda informada por você" in r
        assert "9,000" in r or "9.000" in r

    def test_sem_renda_de_lugar_nenhum_manda_perguntar(self):
        from app.agent.tools.get_budget_advice import get_budget_advice

        r = get_budget_advice.invoke({"user_id": f"inexistente-{uuid.uuid4().hex[:6]}"})
        assert r.startswith("FALHA")
        assert "PERGUNTE" in r


class TestMetasEDefesa:

    def test_goals_nao_diz_que_nao_conseguiu_acessar(self, usuario_com_extrato):
        from app.agent.tools.get_goals_summary import get_goals_summary

        r = get_goals_summary.invoke({"user_id": usuario_com_extrato})
        assert "Não consegui acessar suas metas" not in r

    def test_list_goals_devolve_objetos_nao_dicionario(self):
        """A tool fazia `.get('goals', [])` sobre uma lista de dataclasses."""
        import inspect

        from app.goals.tracker import GoalTracker

        assert "list[Goal]" in str(inspect.signature(GoalTracker.list_goals).return_annotation)

    def test_o_relatorio_de_custos_expoe_fees_detected(self):
        from app.costs.models import BankCostReport

        assert "fees_detected" in BankCostReport.model_fields
        assert "entries" not in BankCostReport.model_fields

    @pytest.mark.parametrize("nome", ["detect_abusive_fees", "detect_wrongful_charges"])
    def test_d1_e_d2_produzem_relatorio(self, nome, usuario_com_extrato):
        tool = next(t for t in AGENT_TOOLS if t.name == nome)
        r = tool.invoke({"user_id": usuario_com_extrato})
        assert "DETECTOR" in r


# ── 3. O user_id das ferramentas vem do token ──────────────────────────────

class TestIdentidadeVinculada:
    """
    Nenhuma tool recebia o usuário autenticado — `user_id` era argumento do
    LLM. Medido antes da correção:
        get_bank_cost_analysis(user_id="demo-ana")
          → "Total pago em tarifas: R$ 174,50"
    """

    @staticmethod
    def _ferramenta_espia():
        from langchain_core.tools import tool

        vistos: list[str] = []

        @tool
        def espia(user_id: str) -> str:
            """Ferramenta de teste."""
            vistos.append(user_id)
            return f"dados de {user_id}"

        return espia, vistos

    def test_o_user_id_do_modelo_e_sobrescrito(self):
        espia, vistos = self._ferramenta_espia()
        vinculada = vincular_ao_usuario(espia)
        with usuario_da_requisicao("dono-real"):
            resultado = vinculada.invoke({"user_id": "vitima-alheia"})
        assert vistos == ["dono-real"]
        assert "dono-real" in resultado

    def test_sem_identidade_a_ferramenta_nao_roda(self):
        espia, vistos = self._ferramenta_espia()
        vinculada = vincular_ao_usuario(espia)
        resultado = vinculada.invoke({"user_id": "qualquer"})
        assert vistos == [], "a tool rodou sem usuário autenticado"
        assert "FALHA DE IDENTIDADE" in resultado

    def test_nome_descricao_e_schema_sobrevivem(self):
        """O grafo roteia por isso, e os evals reaproveitam o schema real."""
        for original in AGENT_TOOLS:
            vinculada = vincular_ao_usuario(original)
            assert vinculada.name == original.name
            assert vinculada.description == original.description
            assert vinculada.args_schema is original.args_schema

    def test_o_agente_construido_usa_as_tools_vinculadas(self):
        from unittest.mock import patch

        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

        import app.agent.tools.get_bank_cost_analysis as mod

        class _LLM(GenericFakeChatModel):
            def bind_tools(self, tools, **kw):
                return self

        recebidos: list[str] = []
        original = mod.get_bank_cost_analysis.func

        def espiao(user_id, *a, **k):
            recebidos.append(user_id)
            return "ok"

        mod.get_bank_cost_analysis.func = espiao
        try:
            respostas = iter([
                AIMessage(content="", tool_calls=[{
                    "name": "get_bank_cost_analysis",
                    "args": {"user_id": "vitima-alheia"},
                    "id": "c1",
                }]),
                AIMessage(content="pronto"),
            ])
            with patch("app.agent.graph._build_llm", return_value=_LLM(messages=respostas)):
                from app.agent.graph import build_financial_agent

                agente = build_financial_agent()

            import concurrent.futures as cf

            def rodar():
                with usuario_da_requisicao("dono-real"):
                    return agente.invoke(
                        {"messages": [("user", "oi")]},
                        config={"configurable": {"thread_id": "t-teste"}},
                    )

            with cf.ThreadPoolExecutor(1) as ex:
                ex.submit(rodar).result()
        finally:
            mod.get_bank_cost_analysis.func = original

        assert recebidos == ["dono-real"], (
            f"o LLM pediu 'vitima-alheia' e a tool recebeu {recebidos}"
        )


# ── 4. O thread do checkpointer pertence a um dono ─────────────────────────

class TestThreadPorDono:
    """
    `thread_id = session_id or user_id`, com `session_id` vindo do corpo da
    requisição. Dois usuários mandando "default" compartilhavam a conversa que
    o agente relê a cada turno — sem injeção nenhuma, só colisão de string.
    """

    def test_sessoes_iguais_de_usuarios_diferentes_nao_colidem(self):
        assert thread_id_de("ana", "default") != thread_id_de("bruno", "default")

    def test_o_thread_comeca_pelo_dono(self):
        assert thread_id_de("ana", "s1").startswith("ana")
        assert thread_id_de("ana") == "ana"

    def test_separador_no_session_id_nao_forja_prefixo(self):
        """Sem isso, session_id='::bruno::x' poderia imitar outro dono."""
        assert thread_id_de("ana", "::bruno") == "ana::_bruno"

    def test_user_id_vazio_e_recusado(self):
        with pytest.raises(ValueError):
            thread_id_de("")


# ── 5. Apagar a conversa alcança o que o agente lembra ─────────────────────

class TestEsquecerConversas:

    def test_apaga_o_thread_base_e_os_da_sessao(self):
        from app.agent.singleton import get_agent

        checkpointer = get_agent().checkpointer
        storage = getattr(checkpointer, "storage", None)
        if not isinstance(storage, dict):
            pytest.skip("checkpointer sem storage inspecionável")

        uid = f"esquecer-{uuid.uuid4().hex[:6]}"
        storage[uid] = {"": "conversa base"}
        storage[thread_id_de(uid, "s1")] = {"": "conversa 1"}
        storage[thread_id_de(uid, "s2")] = {"": "conversa 2"}
        storage["outro-usuario"] = {"": "não pode sumir"}

        resultado = esquecer_conversas(uid)

        assert resultado["apagados"] == 3
        assert not [t for t in storage if str(t).startswith(uid)]
        assert "outro-usuario" in storage
        storage.pop("outro-usuario", None)

    def test_nunca_levanta(self):
        assert esquecer_conversas(f"inexistente-{uuid.uuid4().hex[:6]}")["erro"] is None

    def test_a_eliminacao_lgpd_declara_o_resultado(self):
        from app.privacy.service import ErasureResult

        campos = ErasureResult.__dataclass_fields__
        assert "agent_threads_cleared" in campos
        assert "agent_memory_error" in campos


# ── 6. O corte de histórico respeita o contrato do provedor ────────────────

class TestCorteDeHistorico:
    """
    A regra antiga só descartava ToolMessages órfãs. Em 4.000 sessões longas
    com turnos de tamanho realista, 77,6% começavam com AIMessage — e a API da
    Anthropic exige role "user" na primeira mensagem.
    """

    @staticmethod
    def _turno(i: int, n_tools: int) -> list:
        msgs = [HumanMessage(content=f"pergunta {i}")]
        if n_tools:
            msgs.append(AIMessage(content="", tool_calls=[
                {"name": "t", "args": {}, "id": f"{i}-{k}"} for k in range(n_tools)
            ]))
            msgs += [ToolMessage(content="r", tool_call_id=f"{i}-{k}") for k in range(n_tools)]
        msgs.append(AIMessage(content=f"resposta {i}"))
        return msgs

    @pytest.mark.parametrize("formato", [
        [0], [1], [2], [3],
        [1, 0], [2, 1], [3, 2, 1], [0, 1, 2, 3],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        [3, 3, 3, 3, 3, 3],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    ])
    def test_a_janela_sempre_comeca_no_usuario(self, formato):
        msgs = []
        for repeticao in range(6):
            for i, n in enumerate(formato):
                msgs += self._turno(repeticao * 100 + i, n)
        janela = _trim_history(msgs)
        assert janela, "janela vazia"
        assert isinstance(janela[0], HumanMessage), (
            f"primeira mensagem é {type(janela[0]).__name__}"
        )

    def test_varredura_ampla_nao_produz_nenhum_inicio_invalido(self):
        import random

        random.seed(7)
        for _ in range(2_000):
            msgs = []
            for i in range(random.randint(8, 20)):
                msgs += self._turno(i, random.choice([0, 1, 1, 2, 2, 3]))
            janela = _trim_history(msgs)
            assert janela and isinstance(janela[0], HumanMessage)

    def test_nenhuma_toolmessage_fica_orfa(self):
        import random

        random.seed(11)
        for _ in range(500):
            msgs = []
            for i in range(random.randint(8, 20)):
                msgs += self._turno(i, random.choice([0, 1, 2, 3]))
            janela = _trim_history(msgs)
            pedidos: set[str] = set()
            for m in janela:
                if isinstance(m, AIMessage):
                    pedidos |= {tc["id"] for tc in (m.tool_calls or [])}
                elif isinstance(m, ToolMessage):
                    assert m.tool_call_id in pedidos, "ToolMessage sem o AIMessage que a pediu"

    def test_conversa_curta_passa_inteira(self):
        msgs = self._turno(0, 1) + self._turno(1, 0)
        assert _trim_history(msgs) == msgs

    def test_o_system_prompt_vem_antes_do_historico(self):
        from langchain_core.messages import SystemMessage

        from app.agent.graph import _prepare_model_messages

        msgs = []
        for i in range(15):
            msgs += self._turno(i, 2)
        preparadas = _prepare_model_messages({"messages": msgs})
        assert isinstance(preparadas[0], SystemMessage)
        assert isinstance(preparadas[1], HumanMessage)


# ── 7. O checkpointer diz o que é ──────────────────────────────────────────

class TestCheckpointerObservavel:
    """
    `langgraph-checkpoint-redis` está em requirements.txt e pyproject.toml e
    não estava instalado: a cadeia caía em MemorySaver com um único warning no
    startup, e nada mais no sistema sabia a diferença.
    """

    def test_o_agente_declara_qual_checkpointer_usa(self):
        from app.agent.singleton import get_agent

        get_agent()
        tipo, motivo = checkpointer_em_uso()
        assert tipo in {"redis", "memoria"}
        if tipo == "memoria":
            assert motivo, "queda para memória sem motivo registrado"

    def test_o_motivo_distingue_pacote_ausente_de_redis_fora(self):
        import inspect

        from app.agent import graph

        fonte = inspect.getsource(graph._build_checkpointer)
        assert "ImportError" in fonte
        assert "Redis inacessível" in fonte


# ── 8. O registro é a fonte única, e o teste tem de olhar para ele ─────────

class TestRegistroDeFerramentas:
    """
    O teste anterior escrevia 14 imports à mão e afirmava
    `assert len(tools) == 14` sobre a própria lista — tautologia, com o número
    parado em 14 enquanto o registro chegava a 31, e sem olhar `AGENT_TOOLS`.
    """

    def test_toda_tool_registrada_e_invocavel(self):
        for tool in AGENT_TOOLS:
            assert hasattr(tool, "invoke"), f"{tool} não é invocável"
            assert tool.name and tool.description

    def test_o_registro_cobre_todos_os_arquivos_de_tool(self):
        import pathlib

        pasta = pathlib.Path(__file__).resolve().parents[2] / "app" / "agent" / "tools"
        arquivos = {p.stem for p in pasta.glob("*.py") if p.stem != "__init__"}
        registradas = {t.name for t in AGENT_TOOLS}
        assert arquivos - registradas == set(), "arquivo de tool fora do registro"
        assert registradas - arquivos == set(), "tool registrada sem arquivo"

    def test_nao_ha_nome_duplicado(self):
        nomes = [t.name for t in AGENT_TOOLS]
        assert len(nomes) == len(set(nomes))

    def test_so_user_id_e_obrigatorio_alem_do_essencial(self):
        """
        Argumento obrigatório que o produto sabe derivar vira convite para o
        modelo inventar. `monthly_income` do orçamento saiu daqui.
        """
        import inspect

        exigem_extra = {}
        for tool in AGENT_TOOLS:
            sig = inspect.signature(tool.func)
            req = [
                n for n, p in sig.parameters.items()
                if p.default is inspect.Parameter.empty and n != "user_id"
            ]
            if req:
                exigem_extra[tool.name] = req

        # Só o que o usuário precisa dizer: o que ele quer comprar/simular.
        esperado = {
            "get_financing_simulation": ["target_amount"],
            "get_timing_scenarios": ["target_amount", "monthly_savings"],
            "get_purchase_recommendation": ["amount", "category"],
            "get_peer_comparison": ["monthly_income"],
            "get_expert_card_analysis": ["question"],
            "simulate_investment": ["amount"],
        }
        assert exigem_extra == esperado


# ── 9. O endpoint de chat ──────────────────────────────────────────────────

class TestEndpointDeChat:
    """
    Quatro coisas que o roteador fazia e não deveria: cobrar a cota antes de
    saber se dá para atender, devolver a exceção interna ao cliente, limitar
    por IP enquanto a doc prometia por usuário, e apagar histórico sem tocar
    no que o agente lembra.
    """

    USUARIO = "user_endpoint_teste"

    def _app(self, db=None):
        from unittest.mock import MagicMock

        from fastapi import FastAPI

        from app.agent.router import router
        from app.core.database import get_db
        from app.core.security import get_current_user, require_owner

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: self.USUARIO
        app.dependency_overrides[require_owner] = lambda user_id: self.USUARIO
        app.dependency_overrides[get_db] = lambda: (db or MagicMock())
        return app

    def _cliente(self, db=None):
        from fastapi.testclient import TestClient

        return TestClient(self._app(db), raise_server_exceptions=False)

    def test_sem_llm_configurado_a_cota_do_dia_nao_e_gasta(self):
        """
        `consume_usage` rodava ANTES do 503. No plano Free são 5 mensagens por
        dia: o usuário perdia uma para receber um erro de configuração nossa.
        """
        from unittest.mock import patch

        with patch("app.billing.gating.consume_usage") as cota, \
             patch("app.core.config.settings.LLM_PROVIDER", "anthropic"), \
             patch("app.core.config.settings.ANTHROPIC_API_KEY", ""):
            resposta = self._cliente().post(
                "/chat/", json={"user_id": self.USUARIO, "message": "oi"}
            )

        assert resposta.status_code == 503
        cota.assert_not_called()

    def test_erro_interno_nao_vaza_para_o_cliente(self):
        """
        O detail era `f"{type(e).__name__}: {str(e)[:300]}"` — mensagem de
        driver de banco, URL com credencial, trecho de SQL.
        """
        from unittest.mock import patch

        segredo = "OperationalError: could not connect to postgres://usuario:senha@host"

        with patch("app.billing.gating.consume_usage"), \
             patch("app.core.config.settings.LLM_PROVIDER", "anthropic"), \
             patch("app.core.config.settings.ANTHROPIC_API_KEY", "chave-de-teste"), \
             patch("app.agent.router._get_agent", side_effect=RuntimeError(segredo)):
            resposta = self._cliente().post(
                "/chat/", json={"user_id": self.USUARIO, "message": "oi"}
            )

        assert resposta.status_code == 503
        corpo = resposta.text
        assert "senha" not in corpo and "postgres://" not in corpo
        assert "RuntimeError" not in corpo
        assert "Tente novamente" in corpo

    def test_o_thread_enviado_ao_agente_pertence_ao_dono(self):
        from unittest.mock import MagicMock, patch

        agente = MagicMock()
        agente.invoke.return_value = {"messages": [AIMessage(content="pronto")]}

        with patch("app.billing.gating.consume_usage"), \
             patch("app.core.config.settings.LLM_PROVIDER", "anthropic"), \
             patch("app.core.config.settings.ANTHROPIC_API_KEY", "chave-de-teste"), \
             patch("app.agent.router._get_agent", return_value=agente):
            resposta = self._cliente().post(
                "/chat/",
                json={"user_id": self.USUARIO, "message": "oi", "session_id": "default"},
            )

        assert resposta.status_code == 200
        config = agente.invoke.call_args.kwargs["config"]
        thread = config["configurable"]["thread_id"]
        assert thread == thread_id_de(self.USUARIO, "default")
        assert thread.startswith(self.USUARIO)
        assert thread != "default", "session_id cru viraria thread compartilhado"

    def test_apagar_historico_tambem_esquece_a_conversa_do_agente(self):
        from unittest.mock import MagicMock, patch

        db = MagicMock()
        db.query.return_value.filter.return_value.delete.return_value = 7

        with patch(
            "app.agent.router.esquecer_conversas",
            return_value={"threads": ["a"], "apagados": 2, "metodo": "storage", "erro": None},
        ) as esquecer:
            resposta = self._cliente(db).delete(f"/chat/history?user_id={self.USUARIO}")

        assert resposta.status_code == 200
        esquecer.assert_called_once_with(self.USUARIO)
        assert resposta.json() == {"deleted_count": 7, "agent_threads_cleared": 2}

    def test_a_chave_do_rate_limit_e_o_usuario_e_nao_o_ip(self):
        """
        `key_func=get_remote_address` fazia um escritório inteiro dividir
        20 msg/min, e o mesmo usuário multiplicar o teto trocando de rede.
        """
        from unittest.mock import MagicMock

        from app.agent.router import _chave_do_limite
        from app.core.security import create_access_token

        token = create_access_token({"sub": self.USUARIO})
        requisicao = MagicMock()
        requisicao.headers = {"authorization": f"Bearer {token}"}
        assert _chave_do_limite(requisicao) == f"user:{self.USUARIO}"

    def test_sem_token_valido_a_chave_cai_no_ip(self):
        from unittest.mock import MagicMock

        from app.agent.router import _chave_do_limite

        requisicao = MagicMock()
        requisicao.headers = {"authorization": "Bearer token-invalido"}
        requisicao.client.host = "203.0.113.7"
        assert _chave_do_limite(requisicao) == "203.0.113.7"


# ── 10. O endpoint morto não voltou ────────────────────────────────────────

class TestGrafoAbandonado:
    """
    `POST /api/v1/analyze` estava montado e autenticado e dava 500 garantido:
    chamava o agente ReAct com `{"transactions": df}` e lia
    `final_state["safe_to_spend"]` — chaves de um grafo que não existe mais.
    Sem rate limit, sem cota, sem checagem de LLM.
    """

    def test_a_rota_de_analise_nao_existe_mais(self):
        from app.main import app

        caminhos = {getattr(r, "path", "") for r in app.routes}
        assert not [c for c in caminhos if c.rstrip("/").endswith("/v1/analyze")], caminhos

    @pytest.mark.parametrize("modulo", [
        "app.api.v1.routes.analyze",
        "app.agent.state",
        "app.agent.nodes.forecast",
        "app.agent.nodes.explain",
        "app.core.explain",
    ])
    def test_os_restos_do_grafo_antigo_sumiram(self, modulo):
        import importlib.util

        try:
            assert importlib.util.find_spec(modulo) is None, f"{modulo} ainda existe"
        except (ImportError, AttributeError, ValueError):
            pass  # pacote pai já removido — é o resultado esperado
