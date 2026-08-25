"""
A memória de conversa do agente: por que ela nunca existiu, e o que agora a impede.

A doc afirmava "Checkpointer Redis por `thread_id` … permite reiniciar a
conversa sem perder o histórico". Não era verdade em ambiente nenhum que se
pudesse observar, por três motivos empilhados — cada um escondendo o seguinte:

1. **`requirements.txt` era insatisfazível.** `langgraph==0.2.28` com
   `langgraph-checkpoint-redis==0.0.1`, que exige `langgraph>=0.2.70`.
   `pip install -r requirements.txt` terminava em `ResolutionImpossible`, então
   o pacote simplesmente não estava instalado — e o `except Exception` do
   `_build_checkpointer` transformava isso num aviso único no startup.

2. **`RedisSaver(conn)` passava o cliente na posição da URL.** A assinatura é
   `RedisSaver(redis_url=None, *, redis_client=None, connection_args=None)`.
   Só dava para descobrir com o pacote instalado.

3. **O checkpointer exige Redis STACK**, não Redis comum: ele indexa os
   checkpoints com RediSearch (módulo `search` >= 2.6). Um Redis gerenciado
   comum conecta, responde ao PING e falha só no `setup()`.

Com MemorySaver, a memória é POR PROCESSO: some a cada deploy, cresce sem teto
por thread_id e — com `WEB_CONCURRENCY > 1`, que o `Dockerfile.railway` prevê —
o usuário perde contexto entre turnos, aleatoriamente.
"""

from __future__ import annotations

import re
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from app.agent import graph as agent_graph
from app.agent.graph import _tem_modulo_search, checkpointer_em_uso


_RAIZ = pathlib.Path(__file__).resolve().parents[2]


# ── 1. A guarda que teria evitado tudo: os pins têm de conviver ────────────

class TestRequisitosConsistentes:
    """
    O defeito raiz não estava no código: estava num arquivo de dependências
    que não resolvia. Este teste é estático e não instala nada.
    """

    @staticmethod
    def _pin(arquivo: str, pacote: str) -> str | None:
        texto = (_RAIZ / arquivo).read_text(encoding="utf-8")
        for linha in texto.splitlines():
            linha = linha.split("#")[0].strip()
            if linha.lower().startswith(pacote.lower()) and re.match(
                rf"^{re.escape(pacote)}\s*[<>=!]", linha, re.IGNORECASE
            ):
                return linha
        return None

    @pytest.mark.parametrize("arquivo", ["requirements.txt", "requirements.railway.txt"])
    def test_langgraph_atende_o_minimo_do_checkpointer_redis(self, arquivo):
        """
        `langgraph-checkpoint-redis` 0.0.1 exige `langgraph>=0.2.70`. Um pin
        abaixo disso torna o arquivo insatisfazível e o Redis nunca instala.
        """
        pin = self._pin(arquivo, "langgraph")
        assert pin, f"{arquivo}: langgraph não pinado"

        versoes = re.findall(r"(\d+)\.(\d+)(?:\.(\d+))?", pin)
        assert versoes, pin
        maior, menor, patch_ = versoes[0]
        assert (int(maior), int(menor), int(patch_ or 0)) >= (0, 2, 70), (
            f"{arquivo}: {pin} é anterior a 0.2.70 — "
            f"`pip install -r` falharia com ResolutionImpossible"
        )

    @pytest.mark.parametrize("arquivo", ["requirements.txt", "requirements.railway.txt"])
    def test_o_checkpointer_redis_continua_declarado(self, arquivo):
        assert self._pin(arquivo, "langgraph-checkpoint-redis"), arquivo

    def test_a_exigencia_de_redis_stack_esta_escrita(self):
        """
        Um Redis comum conecta e não serve. Se isso não estiver no arquivo que
        a operação lê, o deploy vai para o ar em memória sem ninguém saber.
        """
        # Normaliza: o comentário quebra em várias linhas com "#" no meio, e
        # a exigência não pode depender de onde a linha foi cortada.
        bruto = (_RAIZ / "requirements.txt").read_text(encoding="utf-8")
        texto = re.sub(r"\s*#\s*", " ", bruto).lower()
        texto = re.sub(r"[*\s]+", " ", texto)
        assert "redis stack" in texto, "a exigência de Redis Stack não está no requirements.txt"
        assert "redisearch" in texto or "search >= 2.6" in texto


# ── 2. A construção do RedisSaver ──────────────────────────────────────────

class TestConstrucaoDoRedisSaver:

    def _redis_com_search(self) -> MagicMock:
        conn = MagicMock()
        conn.ping.return_value = True
        conn.execute_command.return_value = [[b"name", b"search", b"ver", 20600]]
        return conn

    def test_o_cliente_vai_por_NOME_nao_por_posicao(self):
        """
        `RedisSaver(redis_url=None, *, redis_client=None, ...)` — posicional
        entrega o cliente como se fosse a URL.
        """
        capturado = {}

        class _RedisSaverEspiao:
            def __init__(self, redis_url=None, *, redis_client=None, connection_args=None):
                capturado["url"] = redis_url
                capturado["client"] = redis_client

            def setup(self):
                capturado["setup"] = True

        conn = self._redis_com_search()
        with patch("redis.Redis.from_url", return_value=conn), \
             patch.dict("sys.modules", {"langgraph.checkpoint.redis": MagicMock(RedisSaver=_RedisSaverEspiao)}):
            agent_graph._build_checkpointer()

        assert capturado["url"] is None, "cliente foi passado na posição da URL"
        assert capturado["client"] is conn
        assert capturado.get("setup"), "setup() não foi chamado no build"
        assert checkpointer_em_uso()[0] == "redis"

    def test_falha_no_setup_registra_o_motivo_e_desce_a_cadeia(self):
        class _QueFalhaNoSetup:
            def __init__(self, redis_url=None, *, redis_client=None, connection_args=None):
                pass

            def setup(self):
                raise RuntimeError("índice não pôde ser criado")

        # Postgres fora de cena para isolar o motivo do Redis.
        with patch("redis.Redis.from_url", return_value=self._redis_com_search()), \
             patch("app.agent.graph._postgres_checkpointer", return_value=None), \
             patch.dict("sys.modules", {"langgraph.checkpoint.redis": MagicMock(RedisSaver=_QueFalhaNoSetup)}):
            agent_graph._build_checkpointer()

        tipo, motivo = checkpointer_em_uso()
        assert tipo == "memoria"
        assert "RedisSaver não pôde ser construído" in motivo
        assert "índice não pôde ser criado" in motivo


# ── 3. Os motivos de queda são distinguíveis ───────────────────────────────

class TestMotivosDeFallback:
    """
    Antes, os três caíam no mesmo `except Exception` com um `logger.warning`.
    Cada um exige uma ação diferente de quem opera.
    """

    def test_pacote_ausente_aponta_o_ambiente_incompleto(self):
        import builtins

        real = builtins.__import__

        def _sem_pacote(nome, *a, **kw):
            if nome == "langgraph.checkpoint.redis":
                raise ImportError("No module named 'langgraph.checkpoint.redis'")
            return real(nome, *a, **kw)

        with patch("builtins.__import__", side_effect=_sem_pacote), \
             patch("app.agent.graph._postgres_checkpointer", return_value=None):
            agent_graph._build_checkpointer()

        tipo, motivo = checkpointer_em_uso()
        assert tipo == "memoria"
        assert "langgraph-checkpoint-redis" in motivo and "ambiente" in motivo

    def test_redis_fora_do_ar_e_incidente_de_infra(self):
        with patch("redis.Redis.from_url", side_effect=OSError("connection refused")), \
             patch("app.agent.graph._postgres_checkpointer", return_value=None):
            agent_graph._build_checkpointer()
        assert "inacessível" in checkpointer_em_uso()[1]

    def test_redis_sem_redisearch_diz_que_precisa_de_stack(self):
        conn = MagicMock()
        conn.ping.return_value = True
        conn.execute_command.return_value = [[b"name", b"vectorset", b"ver", 1]]
        with patch("redis.Redis.from_url", return_value=conn), \
             patch("app.agent.graph._postgres_checkpointer", return_value=None):
            agent_graph._build_checkpointer()
        motivo = checkpointer_em_uso()[1]
        assert "RediSearch" in motivo and "STACK" in motivo

    def test_o_motivo_do_redis_sobrevive_a_queda_para_postgres(self):
        """
        Cair para Postgres é aceitável; perder o motivo pelo qual o Redis não
        foi usado não é — é o que a operação precisa para corrigir a infra.
        """
        saver = MagicMock()
        with patch("redis.Redis.from_url", side_effect=OSError("connection refused")), \
             patch("app.agent.graph._postgres_checkpointer", return_value=saver):
            agent_graph._build_checkpointer()
        tipo, motivo = checkpointer_em_uso()
        assert tipo == "postgres"
        assert "inacessível" in motivo


# ── 4. A detecção do módulo ────────────────────────────────────────────────

class TestDeteccaoDoModuloSearch:

    def _conn(self, resposta):
        conn = MagicMock()
        conn.execute_command.return_value = resposta
        return conn

    @pytest.mark.parametrize("resposta,esperado", [
        ([[b"name", b"search", b"ver", 20600]], True),
        ([[b"name", b"searchlight", b"ver", 21000]], True),
        ([[b"name", b"search", b"ver", 20400]], False),      # versão velha demais
        ([[b"name", b"vectorset", b"ver", 1]], False),
        ([], False),
        ([{b"name": b"search", b"ver": 20800}], True),        # forma de dicionário
    ])
    def test_formas_de_resposta_do_MODULE_LIST(self, resposta, esperado):
        assert _tem_modulo_search(self._conn(resposta)) is esperado

    def test_sem_conseguir_perguntar_deixa_o_setup_decidir(self):
        """Redis que recusa MODULE LIST (ACL) não deve ser descartado às cegas."""
        conn = MagicMock()
        conn.execute_command.side_effect = RuntimeError("NOPERM")
        assert _tem_modulo_search(conn) is True


# ── 5. Apagar conversa usa a API nativa quando existe ──────────────────────

class TestEsquecerConversas:

    def test_usa_delete_thread_quando_o_backend_oferece(self):
        from app.agent.memoria import esquecer_conversas

        checkpointer = MagicMock()
        checkpointer.storage = {"u1": {}, "u1::sessao": {}, "outro": {}}
        agente = MagicMock(checkpointer=checkpointer)

        with patch("app.agent.singleton.get_agent", return_value=agente):
            r = esquecer_conversas("u1")

        assert r["metodo"] == "delete_thread"
        apagados = {c.args[0] for c in checkpointer.delete_thread.call_args_list}
        assert apagados == {"u1", "u1::sessao"}, apagados
        assert "outro" not in apagados

    def test_backend_sem_forma_de_apagar_reporta_erro(self):
        from app.agent.memoria import esquecer_conversas

        class _Opaco:
            pass

        with patch("app.agent.singleton.get_agent", return_value=MagicMock(checkpointer=_Opaco())):
            r = esquecer_conversas("u1")

        assert r["apagados"] == 0
        assert r["erro"] and "apagar thread" in r["erro"]


# ── 6. Contra um Redis Stack de verdade, quando houver ─────────────────────

class TestRedisStackAoVivo:
    """
    Roda de verdade quando há um Redis com RediSearch alcançável. Pula quando
    não há — não vale falsear o teste com mock e chamar de "exercitado".

    Para rodar: `docker run -d -p 6380:6379 redis/redis-stack-server:latest`
    e `NEXA_TEST_REDIS_STACK_URL=redis://127.0.0.1:6380/0 pytest ...`
    """

    @pytest.fixture
    def url_stack(self):
        import os

        url = os.environ.get("NEXA_TEST_REDIS_STACK_URL")
        if not url:
            pytest.skip("NEXA_TEST_REDIS_STACK_URL não definida")
        try:
            from redis import Redis

            conn = Redis.from_url(url, socket_connect_timeout=2.0)
            conn.ping()
        except Exception as exc:
            pytest.skip(f"Redis Stack inacessível: {exc}")
        if not _tem_modulo_search(conn):
            pytest.skip("Redis alcançável, mas sem RediSearch")
        return url

    def test_o_checkpointer_persiste_e_esquece(self, url_stack):
        import uuid

        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(redis_client=None, connection_args=None) if False else RedisSaver(url_stack)
        saver.setup()

        thread = f"teste-{uuid.uuid4().hex[:8]}"
        cfg = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}
        ck = {"v": 1, "id": "c1", "ts": "2026-01-01T00:00:00",
              "channel_values": {}, "channel_versions": {}, "versions_seen": {},
              "pending_sends": []}
        saver.put(cfg, ck, {"source": "input", "step": 0, "writes": {}}, {})

        assert saver.get_tuple(cfg) is not None, "checkpoint não persistiu"
        saver.delete_thread(thread)
        assert saver.get_tuple(cfg) is None, "delete_thread não apagou"

    def test_o_build_escolhe_redis(self, url_stack):
        from app.core.config import settings

        original = settings.REDIS_URL
        settings.REDIS_URL = url_stack
        try:
            agent_graph._build_checkpointer()
            assert checkpointer_em_uso()[0] == "redis"
        finally:
            settings.REDIS_URL = original


# ── 7. Postgres: persistência real sem infra nova ──────────────────────────

class TestCheckpointerPostgres:
    """
    O Redis Stack é exigência de infra que muitos ambientes não atendem — um
    Redis gerenciado comum conecta, responde ao PING e não serve. A alternativa
    era MemorySaver, que não é persistência. Postgres já está em todo ambiente
    deste projeto.
    """

    @pytest.fixture
    def saver(self):
        from app.agent.graph import _postgres_checkpointer

        saver = _postgres_checkpointer()
        if saver is None:
            pytest.skip("Postgres indisponível neste ambiente")
        return saver

    @staticmethod
    def _checkpoint(ident: str) -> dict:
        return {
            "v": 1, "id": ident, "ts": "2026-01-01T00:00:00",
            "channel_values": {}, "channel_versions": {},
            "versions_seen": {}, "pending_sends": [],
        }

    def _cfg(self, thread: str) -> dict:
        return {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}

    def test_o_estado_sobrevive_a_outro_processo(self, saver):
        """
        É exatamente o que MemorySaver nunca deu: um segundo worker (ou o
        processo depois do deploy) enxergando a conversa.
        """
        import uuid as _uuid

        from app.agent.graph import _postgres_checkpointer

        thread = f"teste-pg-{_uuid.uuid4().hex[:8]}"
        saver.put(self._cfg(thread), self._checkpoint("c1"),
                  {"source": "input", "step": 0, "writes": {}}, {})
        try:
            outro = _postgres_checkpointer()
            assert outro.get_tuple(self._cfg(thread)) is not None, (
                "checkpoint não visível de outra conexão — sem persistência real"
            )
        finally:
            saver.delete_thread(thread)

    def test_apagar_alcanca_todas_as_sessoes_do_titular(self, saver):
        """
        LGPD art. 18 VI: sem enumerar por prefixo, só o thread base sumiria e o
        resto do histórico (perguntas do titular e todo retorno de ferramenta)
        sobreviveria à eliminação.
        """
        import uuid as _uuid
        from unittest.mock import MagicMock as _MagicMock
        from unittest.mock import patch as _patch

        from app.agent.memoria import esquecer_conversas, thread_id_de

        uid = f"lgpd-{_uuid.uuid4().hex[:8]}"
        alheio = f"outro-{_uuid.uuid4().hex[:8]}"
        threads = [thread_id_de(uid), thread_id_de(uid, "a"), thread_id_de(uid, "b"), alheio]
        for i, thread in enumerate(threads):
            saver.put(self._cfg(thread), self._checkpoint(f"c{i}"),
                      {"source": "input", "step": 0, "writes": {}}, {})
        try:
            with _patch("app.agent.singleton.get_agent",
                        return_value=_MagicMock(checkpointer=saver)):
                r = esquecer_conversas(uid)

            assert r["metodo"] == "delete_thread"
            assert set(r["threads"]) == {thread_id_de(uid), thread_id_de(uid, "a"),
                                         thread_id_de(uid, "b")}
            for thread in r["threads"]:
                assert saver.get_tuple(self._cfg(thread)) is None, thread
            assert saver.get_tuple(self._cfg(alheio)) is not None, (
                "apagou conversa de outro titular"
            )
        finally:
            saver.delete_thread(alheio)

    def test_a_cadeia_prefere_postgres_a_memoria(self):
        """
        Com Redis fora, o degrau seguinte é Postgres — nunca memória, enquanto
        houver banco.
        """
        with patch("app.agent.graph._tem_modulo_search", return_value=False):
            agent_graph._build_checkpointer()
        tipo, motivo = checkpointer_em_uso()
        if tipo == "memoria":
            pytest.skip(f"Postgres indisponível: {motivo}")
        assert tipo == "postgres"
        assert motivo, "queda do Redis sem motivo registrado"

    def test_memoria_so_quando_nem_postgres_responde(self):
        with patch("app.agent.graph._tem_modulo_search", return_value=False), \
             patch("app.agent.graph._postgres_checkpointer", return_value=None):
            agent_graph._build_checkpointer()
        assert checkpointer_em_uso()[0] == "memoria"


# ── 8. A promessa da doc, de ponta a ponta ─────────────────────────────────

class TestConversaSobreviveAoRestart:
    """
    "Checkpointer por `thread_id` … permite reiniciar a conversa sem perder o
    histórico" era o que a doc afirmava e o que nenhum ambiente entregava.
    Este teste constrói um agente, conversa, joga o agente fora e constrói
    outro — que é o que um deploy (ou um segundo worker) faz.
    """

    @pytest.fixture
    def agente_novo(self):
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage

        class _LLMFalso(GenericFakeChatModel):
            def bind_tools(self, tools, **kw):  # create_react_agent chama isto
                return self

        def _construir(resposta: str):
            from app.agent.graph import build_financial_agent

            with patch(
                "app.agent.graph._build_llm",
                return_value=_LLMFalso(messages=iter([AIMessage(content=resposta)])),
            ):
                return build_financial_agent()

        return _construir

    def test_o_historico_atravessa_processos(self, agente_novo):
        import uuid

        from app.agent.graph import checkpointer_em_uso
        from app.agent.identity import usuario_da_requisicao
        from app.agent.memoria import esquecer_conversas, thread_id_de

        primeiro = agente_novo("Anotado: sua meta é R$ 20 mil.")
        if checkpointer_em_uso()[0] == "memoria":
            pytest.skip(f"sem backend persistente: {checkpointer_em_uso()[1]}")

        uid = f"teste-restart-{uuid.uuid4().hex[:8]}"
        cfg = {"configurable": {"thread_id": thread_id_de(uid, "sessao-1")}}

        try:
            with usuario_da_requisicao(uid):
                primeiro.invoke({"messages": [("user", "minha meta é 20 mil")]}, config=cfg)

            # Agente novo, do zero — como depois de um deploy.
            segundo = agente_novo("Sua meta é R$ 20 mil.")
            with usuario_da_requisicao(uid):
                estado = segundo.invoke(
                    {"messages": [("user", "qual era mesmo minha meta?")]}, config=cfg
                )

            conteudos = [str(m.content) for m in estado["messages"]]
            assert len(conteudos) >= 4, conteudos
            assert any("minha meta é 20 mil" in c for c in conteudos), (
                "a primeira pergunta não sobreviveu ao restart"
            )
        finally:
            with patch("app.agent.singleton.get_agent",
                       return_value=MagicMock(checkpointer=primeiro.checkpointer)):
                esquecer_conversas(uid)
