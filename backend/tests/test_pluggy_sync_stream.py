"""
Testes do sync assíncrono da Pluggy (job + long-polling + SSE).

Rodam sem Postgres e sem rede: o job store é apontado para um SQLite
temporário e a Pluggy é substituída por um cliente falso que reproduz o
comportamento real que motivou tudo isto — o item nasce UPDATING e só
vira UPDATED alguns instantes depois.

    pytest backend/tests/test_pluggy_sync_stream.py -v
"""

import asyncio
import json
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.core.models.pluggy_item import PluggyItem
from app.core.security import get_current_user
from app.main import app
from app.pluggy_sync import service as sync_service
from app.pluggy_sync.models_orm import (
    JOB_ERROR,
    JOB_PENDING,
    JOB_RUNNING,
    JOB_SUCCESS,
    PHASE_WAITING_BANK,
    PluggySyncJob,
)
from app.pluggy_sync.runner import (
    ItemNotReady,
    fetch_all_accounts,
    fetch_all_transactions,
    wait_item_ready,
)

USER_ID = "user-sync-test"
OTHER_USER_ID = "user-intruso"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture
def db_factory(tmp_path, monkeypatch):
    """SQLite isolado no lugar do SessionLocal global."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sync_jobs.db'}",
        connect_args={"check_same_thread": False},
    )
    PluggySyncJob.__table__.create(engine, checkfirst=True)
    PluggyItem.__table__.create(engine, checkfirst=True)

    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # O job roda em outra thread e os esperadores releem fora do request:
    # ambos usam o SessionLocal do módulo, não a sessão do Depends.
    monkeypatch.setattr(sync_service, "SessionLocal", factory)

    yield factory
    engine.dispose()


@pytest.fixture
def db(db_factory):
    session = db_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PLUGGY_CLIENT_ID", "test-id")
    monkeypatch.setattr(settings, "PLUGGY_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(settings, "PLUGGY_WEBHOOK_SECRET", "")

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: USER_ID
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def no_autostart(monkeypatch):
    """Cria o job sem disparar a thread (o teste controla o progresso)."""
    monkeypatch.setattr(sync_service, "start_job", lambda job_id, user_id: None)


def _make_item(db, item_id: str = "item-1", user_id: str = USER_ID) -> PluggyItem:
    item = PluggyItem(id=str(uuid.uuid4()), user_id=user_id, item_id=item_id)
    db.add(item)
    db.commit()
    return item


class FakePluggy:
    """Item que fica UPDATING nas primeiras consultas e depois UPDATED."""

    def __init__(self, updating_calls: int = 2, final_status: str = "UPDATED"):
        self.updating_calls = updating_calls
        self.final_status = final_status
        self.calls = 0

    def get_item(self, item_id: str) -> dict:
        self.calls += 1
        if self.calls <= self.updating_calls:
            return {"id": item_id, "status": "UPDATING"}
        return {"id": item_id, "status": self.final_status}


class FakePaginado:
    """Cliente que pagina como a Pluggy real (results + totalPages)."""

    def __init__(self, total: int = 1250, page_size_servidor: int = 500):
        self.total = total
        self.page_size_servidor = page_size_servidor
        self.paginas_pedidas: list[int] = []
        self.janelas: list[str] = []

    def get_transactions(
        self,
        account_id: str,
        page: int | None = None,
        page_size: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        tamanho = min(page_size or 20, self.page_size_servidor)
        atual = page or 1
        self.paginas_pedidas.append(atual)
        if date_from:
            self.janelas.append(date_from)

        inicio = (atual - 1) * tamanho
        fim = min(inicio + tamanho, self.total)
        total_pages = max(1, -(-self.total // tamanho))  # ceil

        return {
            "total": self.total,
            "totalPages": total_pages,
            "page": atual,
            "results": [{"id": f"tx-{i}"} for i in range(inicio, fim)],
        }


class FakeSemPaginacao:
    """Assinatura antiga — é o que os mocks do projeto implementam."""

    def get_transactions(self, account_id: str) -> dict:
        return {"results": [{"id": "tx-1"}, {"id": "tx-2"}]}

    def get_accounts(self, item_id: str) -> dict:
        return {"results": [{"id": "acc-1"}]}


class FakeContasPaginadas:
    """Contas paginadas como a Pluggy real."""

    def __init__(self, total: int = 45):
        self.total = total
        self.paginas_pedidas: list[int] = []

    def get_accounts(self, item_id: str, page: int | None = None, page_size: int | None = None) -> dict:
        tamanho = page_size or 20
        atual = page or 1
        self.paginas_pedidas.append(atual)

        inicio = (atual - 1) * tamanho
        fim = min(inicio + tamanho, self.total)
        return {
            "totalPages": max(1, -(-self.total // tamanho)),
            "results": [{"id": f"acc-{i}"} for i in range(inicio, fim)],
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ESPERA DO ITEM (o problema de origem)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestWaitItemReady:

    def test_espera_ate_o_item_ficar_updated(self):
        pluggy = FakePluggy(updating_calls=2)
        status_str = wait_item_ready(pluggy, "item-1", timeout=5, poll_interval=0.05)

        assert status_str == "UPDATED"
        assert pluggy.calls == 3  # duas vezes UPDATING, uma UPDATED

    def test_login_error_aborta_sem_esperar_o_timeout(self):
        pluggy = FakePluggy(updating_calls=0, final_status="LOGIN_ERROR")

        started = time.monotonic()
        with pytest.raises(ItemNotReady) as exc:
            wait_item_ready(pluggy, "item-1", timeout=30, poll_interval=0.05)

        assert exc.value.item_status == "LOGIN_ERROR"
        assert time.monotonic() - started < 1.0  # não ficou 30s pendurado

    def test_timeout_vira_item_not_ready(self):
        pluggy = FakePluggy(updating_calls=10_000)

        with pytest.raises(ItemNotReady) as exc:
            wait_item_ready(pluggy, "item-1", timeout=0.2, poll_interval=0.05)

        assert exc.value.item_status == "UPDATING"

    def test_webhook_acorda_a_espera_antes_do_proximo_poll(self):
        """O evento do webhook encurta o poll_interval de 5s."""
        from app.pluggy_sync import events

        pluggy = FakePluggy(updating_calls=1)

        def publicar_depois():
            # Espera o waiter se registrar antes de publicar.
            for _ in range(100):
                if events.subscriber_count(events.item_key("item-1")):
                    break
                time.sleep(0.01)
            events.publish(events.item_key("item-1"))

        threading.Thread(target=publicar_depois, daemon=True).start()

        started = time.monotonic()
        status_str = wait_item_ready(pluggy, "item-1", timeout=10, poll_interval=5.0)
        elapsed = time.monotonic() - started

        assert status_str == "UPDATED"
        assert elapsed < 3.0, "deveria ter acordado pelo webhook, não pelo poll de 5s"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAGINAÇÃO (a Pluggy devolve 20 por página por padrão)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPaginacao:

    def test_percorre_todas_as_paginas(self):
        pluggy = FakePaginado(total=1250)

        resultados = fetch_all_transactions(pluggy, "acc-1")

        assert len(resultados) == 1250, "o sync não pode parar na primeira página"
        assert resultados[0]["id"] == "tx-0"
        assert resultados[-1]["id"] == "tx-1249"
        assert pluggy.paginas_pedidas == [1, 2, 3]

    def test_uma_pagina_so_nao_pede_a_segunda(self):
        pluggy = FakePaginado(total=10)

        resultados = fetch_all_transactions(pluggy, "acc-1")

        assert len(resultados) == 10
        assert pluggy.paginas_pedidas == [1]

    def test_cliente_com_assinatura_antiga_continua_funcionando(self):
        """Mocks do projeto expõem get_transactions(account_id) e uma página só."""
        resultados = fetch_all_transactions(FakeSemPaginacao(), "acc-1")

        assert len(resultados) == 2

    def test_mock_oficial_do_projeto_segue_compativel(self):
        from app.core.integrations.pluggy_mock import MockPluggyClient

        pluggy = MockPluggyClient()
        item = pluggy.create_sandbox_item()
        account_id = pluggy.get_accounts(item["id"])["results"][0]["id"]

        assert fetch_all_transactions(pluggy, account_id)
        assert fetch_all_accounts(pluggy, item["id"])

    def test_contas_tambem_percorrem_as_paginas(self):
        """Item PJ com dezenas de contas não pode perder as contas do fim."""
        pluggy = FakeContasPaginadas(total=45)

        contas = fetch_all_accounts(pluggy, "item-1")

        assert len(contas) == 45
        assert contas[-1]["id"] == "acc-44"
        assert pluggy.paginas_pedidas == [1]  # pageSize=500 cobre tudo numa página

    def test_contas_com_cliente_antigo_continuam_funcionando(self):
        assert len(fetch_all_accounts(FakeSemPaginacao(), "item-1")) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYNC INCREMENTAL (janela from/to)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSyncIncremental:

    def test_conta_com_historico_pede_so_a_janela_nova(self, monkeypatch):
        """Webhook de 3 transações não pode rebaixar um ano de extrato."""
        import app.core.db.queries as queries
        from app.pluggy_sync.runner import _incremental_start

        monkeypatch.setattr(
            queries, "get_last_transaction_date",
            lambda db, user_id, account_id: date(2026, 8, 10),
        )

        inicio = _incremental_start(object(), USER_ID, "acc-1")

        # última salva (10/08) menos os 7 dias de margem
        assert inicio == "2026-08-03"

    def test_conta_nova_puxa_o_extrato_inteiro(self, monkeypatch):
        import app.core.db.queries as queries
        from app.pluggy_sync.runner import _incremental_start

        monkeypatch.setattr(
            queries, "get_last_transaction_date",
            lambda db, user_id, account_id: None,
        )

        assert _incremental_start(object(), USER_ID, "acc-nova") is None

    def test_lookback_zero_desliga_o_incremental(self, monkeypatch):
        import app.core.db.queries as queries
        from app.core.config import settings
        from app.pluggy_sync.runner import _incremental_start

        monkeypatch.setattr(settings, "PLUGGY_SYNC_LOOKBACK_DAYS", 0)
        monkeypatch.setattr(
            queries, "get_last_transaction_date",
            lambda db, user_id, account_id: date(2026, 8, 10),
        )

        assert _incremental_start(object(), USER_ID, "acc-1") is None

    def test_janela_chega_na_chamada_da_pluggy(self):
        pluggy = FakePaginado(total=10)

        fetch_all_transactions(pluggy, "acc-1", date_from="2026-08-03")

        assert pluggy.janelas == ["2026-08-03"]

    def test_falha_ao_ler_a_ultima_data_cai_em_sync_completo(self, monkeypatch):
        """Degradar para completo é caro; pular a conta perderia lançamento."""
        import app.core.db.queries as queries
        from app.pluggy_sync.runner import _incremental_start

        def explode(*args, **kwargs):
            raise RuntimeError("banco fora")

        monkeypatch.setattr(queries, "get_last_transaction_date", explode)

        assert _incremental_start(object(), USER_ID, "acc-1") is None

    def test_get_last_transaction_date_nao_levanta_com_sessao_quebrada(self):
        """A blindagem mora na query, onde o db de verdade é usado."""
        from app.core.db.queries import get_last_transaction_date

        class SessaoQuebrada:
            def query(self, *a, **k):
                raise RuntimeError("conexão caiu")

        assert get_last_transaction_date(SessaoQuebrada(), USER_ID, "acc-1") is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRIAÇÃO DO JOB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestStartJob:

    def test_retorna_202_com_cursor_inicial(self, client, db, no_autostart):
        _make_item(db)

        resp = client.post("/api/v1/pluggy/sync/jobs")

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == JOB_PENDING
        assert body["cursor"] >= 1
        assert body["items"]["total"] == 1
        assert body["done"] is False
        assert body["reused"] is False

    def test_segundo_clique_reaproveita_o_job_em_andamento(self, client, db, no_autostart):
        _make_item(db)

        primeiro = client.post("/api/v1/pluggy/sync/jobs").json()
        segundo = client.post("/api/v1/pluggy/sync/jobs").json()

        assert segundo["job_id"] == primeiro["job_id"]
        assert segundo["reused"] is True

    def test_force_cria_job_novo(self, client, db, no_autostart):
        _make_item(db)

        primeiro = client.post("/api/v1/pluggy/sync/jobs").json()
        segundo = client.post("/api/v1/pluggy/sync/jobs?force=true").json()

        assert segundo["job_id"] != primeiro["job_id"]

    def test_usuario_sem_conexao_recebe_job_vazio(self, client, no_autostart):
        resp = client.post("/api/v1/pluggy/sync/jobs")

        assert resp.status_code == 202
        assert resp.json()["items"]["total"] == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LONG-POLLING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestLongPolling:

    def test_cursor_atrasado_responde_na_hora(self, client, db, no_autostart):
        _make_item(db)
        job = client.post("/api/v1/pluggy/sync/jobs").json()

        started = time.monotonic()
        resp = client.get(f"/api/v1/pluggy/sync/jobs/{job['job_id']}?cursor=0&timeout=25")
        elapsed = time.monotonic() - started

        assert resp.status_code == 200
        assert resp.json()["changed"] is True
        assert elapsed < 2.0

    def test_sem_novidade_pendura_ate_o_timeout(self, client, db, no_autostart):
        _make_item(db)
        job = client.post("/api/v1/pluggy/sync/jobs").json()

        started = time.monotonic()
        resp = client.get(
            f"/api/v1/pluggy/sync/jobs/{job['job_id']}"
            f"?cursor={job['cursor']}&timeout=1"
        )
        elapsed = time.monotonic() - started

        body = resp.json()
        assert body["changed"] is False
        assert body["cursor"] == job["cursor"]
        assert elapsed >= 0.9, "deveria ter segurado a resposta até o timeout"

    def test_update_no_meio_do_wait_responde_antes_do_timeout(self, client, db, no_autostart):
        _make_item(db)
        job = client.post("/api/v1/pluggy/sync/jobs").json()

        def avancar():
            time.sleep(0.3)
            sync_service.update_job(
                job["job_id"],
                status=JOB_RUNNING,
                phase=PHASE_WAITING_BANK,
                message="Falando com o banco...",
            )

        threading.Thread(target=avancar, daemon=True).start()

        started = time.monotonic()
        resp = client.get(
            f"/api/v1/pluggy/sync/jobs/{job['job_id']}"
            f"?cursor={job['cursor']}&timeout=20"
        )
        elapsed = time.monotonic() - started

        body = resp.json()
        assert body["changed"] is True
        assert body["status"] == JOB_RUNNING
        assert body["cursor"] > job["cursor"]
        assert elapsed < 5.0, "o long-poll não acordou com o evento do job"

    def test_job_terminado_responde_na_hora_mesmo_sem_mudanca(self, client, db, no_autostart):
        _make_item(db)
        job = client.post("/api/v1/pluggy/sync/jobs").json()
        final = sync_service.update_job(job["job_id"], status=JOB_SUCCESS, progress=100)

        started = time.monotonic()
        resp = client.get(
            f"/api/v1/pluggy/sync/jobs/{job['job_id']}?cursor={final['cursor']}&timeout=20"
        )
        elapsed = time.monotonic() - started

        assert resp.json()["done"] is True
        assert elapsed < 2.0

    def test_job_de_outro_usuario_da_404(self, client, db_factory, no_autostart):
        """IDOR: o job pertence a outro dono — não existe para este usuário."""
        session = db_factory()
        job = sync_service.create_job(session, OTHER_USER_ID, ["item-x"])
        session.close()

        resp = client.get(f"/api/v1/pluggy/sync/jobs/{job.id}?timeout=0")

        assert resp.status_code == 404

    def test_job_inexistente_da_404(self, client, no_autostart):
        resp = client.get(f"/api/v1/pluggy/sync/jobs/{uuid.uuid4()}?timeout=0")

        assert resp.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STREAMING (SSE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _collect_sse(gen) -> list[str]:
    """Consome o gerador async do SSE até ele terminar."""

    async def run():
        return [chunk async for chunk in gen]

    return asyncio.run(run())


class TestStreaming:

    def test_stream_emite_state_e_done(self, client, db, db_factory, no_autostart):
        _make_item(db)
        job = client.post("/api/v1/pluggy/sync/jobs").json()
        sync_service.update_job(job["job_id"], status=JOB_RUNNING, progress=42)
        sync_service.update_job(job["job_id"], status=JOB_SUCCESS, progress=100)

        chunks = _collect_sse(
            sync_service.stream_job(job_id=job["job_id"], user_id=USER_ID, cursor=0)
        )
        body = "".join(chunks)

        assert body.startswith("retry: 3000")
        assert "event: state" in body
        assert "event: done" in body
        # Estado final chega completo (progresso, totais, contadores).
        payload = json.loads(body.split("event: done\ndata: ")[1].split("\n\n")[0])
        assert payload["status"] == JOB_SUCCESS
        assert payload["progress"] == 100
        assert payload["done"] is True

    def test_stream_respeita_o_cursor_de_retomada(self, client, db, no_autostart):
        _make_item(db)
        job = client.post("/api/v1/pluggy/sync/jobs").json()
        final = sync_service.update_job(job["job_id"], status=JOB_SUCCESS, progress=100)

        chunks = _collect_sse(
            sync_service.stream_job(
                job_id=job["job_id"], user_id=USER_ID, cursor=final["cursor"]
            )
        )
        body = "".join(chunks)

        # Nada novo desde o cursor: só o `done` final, sem reenviar `state`.
        assert "event: state" not in body
        assert "event: done" in body

    def test_stream_de_job_alheio_nao_vaza_estado(self, db_factory, no_autostart):
        session = db_factory()
        job = sync_service.create_job(session, OTHER_USER_ID, ["item-x"])
        session.close()

        chunks = _collect_sse(
            sync_service.stream_job(job_id=job.id, user_id=USER_ID, cursor=0)
        )
        body = "".join(chunks)

        assert "event: error" in body
        assert "event: state" not in body

    def test_endpoint_devolve_content_type_de_sse(self, client, db, no_autostart):
        _make_item(db)
        job = client.post("/api/v1/pluggy/sync/jobs").json()
        sync_service.update_job(job["job_id"], status=JOB_SUCCESS, progress=100)

        with client.stream("GET", f"/api/v1/pluggy/sync/jobs/{job['job_id']}/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers["x-accel-buffering"] == "no"
            body = "".join(resp.iter_text())

        assert "event: done" in body


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXECUÇÃO DO JOB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRunJob:

    def test_fluxo_completo_avanca_o_cursor_e_soma_totais(self, db_factory, monkeypatch):
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        session.close()

        import app.core.integrations.pluggy as pluggy_module

        monkeypatch.setattr(pluggy_module, "PluggyClient", lambda: FakePluggy(updating_calls=1))
        monkeypatch.setattr(
            sync_service,
            "sync_item_transactions",
            lambda db, user_id, item_id, on_progress=None: {
                "item_id": item_id,
                "accounts": 2,
                "received": 30,
                "valid": 28,
                "saved": 28,
                "errors": [],
            },
        )

        final = sync_service.run_job(job.id, USER_ID, item_timeout=5, poll_interval=0.05)

        assert final["status"] == JOB_SUCCESS
        assert final["progress"] == 100
        assert final["totals"]["saved"] == 28
        assert final["totals"]["accounts"] == 2
        assert final["items"]["done"] == 1
        # Cada passo publicou um estado novo — é isso que o SSE/long-poll consome.
        assert final["cursor"] > job.version
        assert final["done"] is True

    def test_item_bloqueado_termina_o_job_em_erro_com_mensagem_util(self, db_factory, monkeypatch):
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        session.close()

        import app.core.integrations.pluggy as pluggy_module

        monkeypatch.setattr(
            pluggy_module,
            "PluggyClient",
            lambda: FakePluggy(updating_calls=0, final_status="LOGIN_ERROR"),
        )

        final = sync_service.run_job(job.id, USER_ID, item_timeout=2, poll_interval=0.05)

        assert final["status"] == JOB_ERROR
        assert final["detail"][0]["item_status"] == "LOGIN_ERROR"
        assert "reconecte" in final["detail"][0]["error"].lower()

    def test_um_item_falho_e_outro_ok_vira_partial(self, db_factory, monkeypatch):
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-ok", "item-ruim"])
        session.close()

        import app.core.integrations.pluggy as pluggy_module

        class PorItem:
            def get_item(self, item_id: str) -> dict:
                status_str = "UPDATED" if item_id == "item-ok" else "LOGIN_ERROR"
                return {"id": item_id, "status": status_str}

        monkeypatch.setattr(pluggy_module, "PluggyClient", PorItem)
        monkeypatch.setattr(
            sync_service,
            "sync_item_transactions",
            lambda db, user_id, item_id, on_progress=None: {
                "item_id": item_id, "accounts": 1, "received": 5,
                "valid": 5, "saved": 5, "errors": [],
            },
        )

        final = sync_service.run_job(job.id, USER_ID, item_timeout=2, poll_interval=0.05)

        assert final["status"] == "PARTIAL"
        assert final["totals"]["saved"] == 5


class TestRuidoDeProgresso:
    """O long-polling só vale se o cursor andar quando algo muda de verdade."""

    def test_espera_longa_nao_publica_estado_repetido(self, db_factory, monkeypatch):
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        session.close()

        import app.core.integrations.pluggy as pluggy_module

        # 12 consultas seguidas devolvendo UPDATING antes de liberar.
        pluggy = FakePluggy(updating_calls=12)
        monkeypatch.setattr(pluggy_module, "PluggyClient", lambda: pluggy)
        monkeypatch.setattr(
            sync_service,
            "sync_item_transactions",
            lambda db, user_id, item_id, on_progress=None: {
                "item_id": item_id, "accounts": 1, "received": 3,
                "valid": 3, "saved": 3, "errors": [],
            },
        )

        final = sync_service.run_job(job.id, USER_ID, item_timeout=10, poll_interval=0.01)

        assert final["status"] == JOB_SUCCESS
        assert pluggy.calls == 13, "o poller precisa ter rodado várias vezes"
        # Sem a correção, cada tique do poller virava uma versão nova e o
        # long-poll voltava a cada 10ms com um estado idêntico.
        assert final["cursor"] - job.version <= 8, (
            f"cursor subiu {final['cursor'] - job.version} vezes em 13 polls — "
            "o job está republicando estado repetido"
        )

    def test_touch_mantem_o_job_vivo_sem_mexer_no_cursor(self, db_factory):
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        session.close()

        antes = sync_service.get_job_state(job.id, USER_ID)
        sync_service.touch_job(job.id)
        depois = sync_service.get_job_state(job.id, USER_ID)

        assert depois["cursor"] == antes["cursor"]
        assert depois["updated_at"] >= antes["updated_at"]


class TestJobOrfao:

    def test_job_parado_ha_muito_tempo_vira_erro_para_quem_espera(self, db_factory):
        """Deploy no meio do sync não pode deixar o cliente esperando para sempre."""
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        job_id = job.id
        job.status = JOB_RUNNING
        job.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()
        session.close()

        state = sync_service.get_job_state(job_id, USER_ID)

        assert state["status"] == JOB_ERROR
        assert state["done"] is True
        assert "interrompida" in state["error"].lower()

    def test_boot_retoma_job_que_ficou_sem_executor(self, db_factory, monkeypatch):
        """Deploy no meio do sync: o job volta a rodar em vez de esperar 15min."""
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        job_id = job.id
        job.status = JOB_RUNNING
        job.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.commit()
        session.close()

        retomados: list[tuple[str, str]] = []
        monkeypatch.setattr(
            sync_service, "start_job",
            lambda jid, uid: retomados.append((jid, uid)),
        )

        assert sync_service.resume_orphan_jobs() == 1
        assert retomados == [(job_id, USER_ID)]

        state = sync_service.get_job_state(job_id, USER_ID)
        assert state["status"] == JOB_RUNNING
        assert "retomando" in state["message"].lower()

    def test_boot_nao_rouba_job_vivo_em_outro_worker(self, db_factory, monkeypatch):
        """Job vivo renova o updated_at a cada tique — não pode ser reenfileirado."""
        session = db_factory()
        sync_service.create_job(session, USER_ID, ["item-1"])
        session.close()

        retomados: list[str] = []
        monkeypatch.setattr(sync_service, "start_job", lambda jid, uid: retomados.append(jid))

        assert sync_service.resume_orphan_jobs() == 0
        assert retomados == []

    def test_dois_workers_no_boot_so_um_assume_o_job(self, db_factory, monkeypatch):
        """O CAS na version decide a corrida entre workers que sobem juntos."""
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        job_id, version = job.id, job.version
        job.status = JOB_RUNNING
        job.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        session.commit()
        session.close()

        assert sync_service._claim_job(job_id, version) is True
        # Segundo worker chega com a mesma version que leu antes: perde.
        assert sync_service._claim_job(job_id, version) is False

    def test_job_ja_terminado_nao_e_retomado(self, db_factory, monkeypatch):
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        job_id = job.id
        job.status = JOB_SUCCESS
        job.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.commit()
        session.close()

        monkeypatch.setattr(sync_service, "start_job", lambda jid, uid: None)

        assert sync_service.resume_orphan_jobs() == 0
        assert sync_service.get_job_state(job_id, USER_ID)["status"] == JOB_SUCCESS

    def test_falha_inesperada_na_thread_fecha_o_job(self, db_factory, monkeypatch):
        session = db_factory()
        job = sync_service.create_job(session, USER_ID, ["item-1"])
        session.close()

        def explode(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(sync_service, "run_job", explode)
        sync_service._run_job_with_slot(job.id, USER_ID)

        state = sync_service.get_job_state(job.id, USER_ID)
        assert state["status"] == JOB_ERROR
        assert state["done"] is True
        # O slot precisa voltar para o pool, senão a fila trava depois de N falhas.
        assert sync_service._job_slots.acquire(blocking=False)
        sync_service._job_slots.release()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEBHOOK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestItemWebhook:

    def test_item_desconhecido_e_ignorado_sem_404(self, client, monkeypatch):
        """Item de outro ambiente não pode virar retentativa infinita na Pluggy."""
        import app.api.v1.routes.pluggy as routes

        monkeypatch.setattr(routes, "resolve_user_from_item", lambda item_id: None)

        resp = client.post(
            "/api/v1/pluggy/webhook",
            json={"event": "item/updated", "itemId": "item-desconhecido"},
        )

        assert resp.status_code == 200
        assert resp.json()["ignored"] is True

    def test_item_updated_dispara_job_quando_ninguem_esta_sincronizando(
        self, client, db, monkeypatch, no_autostart
    ):
        import app.api.v1.routes.pluggy as routes

        _make_item(db, item_id="item-1")
        monkeypatch.setattr(routes, "resolve_user_from_item", lambda item_id: USER_ID)

        resp = client.post(
            "/api/v1/pluggy/webhook",
            json={"event": "item/updated", "itemId": "item-1"},
        )

        body = resp.json()
        assert body["started_job"] is True
        assert sync_service.get_job_state(body["job_id"], USER_ID)["status"] == JOB_PENDING

    def test_nao_duplica_job_quando_ja_ha_um_em_andamento(
        self, client, db, monkeypatch, no_autostart
    ):
        import app.api.v1.routes.pluggy as routes

        _make_item(db, item_id="item-1")
        monkeypatch.setattr(routes, "resolve_user_from_item", lambda item_id: USER_ID)
        existente = client.post("/api/v1/pluggy/sync/jobs").json()

        body = client.post(
            "/api/v1/pluggy/webhook",
            json={"event": "item/updated", "itemId": "item-1"},
        ).json()

        assert body["started_job"] is False
        assert body["job_id"] == existente["job_id"]

    def test_evento_irrelevante_nao_dispara_job(self, client, db, monkeypatch, no_autostart):
        import app.api.v1.routes.pluggy as routes

        _make_item(db, item_id="item-1")
        monkeypatch.setattr(routes, "resolve_user_from_item", lambda item_id: USER_ID)

        body = client.post(
            "/api/v1/pluggy/webhook",
            json={"event": "item/deleted", "itemId": "item-1"},
        ).json()

        assert body["started_job"] is False
