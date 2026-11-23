"""
E2E real do ciclo de vida dos desafios mensais (R2.b) contra Postgres.

Diferente dos testes unitários (que monkeypatcham a persistência), aqui o
fluxo completo roda contra um Postgres de verdade:

  1. `alembic upgrade head` aplicado do zero num schema isolado
     (valida inclusive a migration de merge a7c9e5f2b1d8 em PG real);
  2. transações semeadas em transactions_clean;
  3. ChallengeService.sync(): geração → progresso → conclusão no meio do
     mês → fechamento na virada → badges — tudo via SQL real;
  4. idempotência (sync duplo não duplica linhas).

Isolamento: schema `nexa_e2e` em nexa_db via search_path na URL — o schema
public (dados de dev) não é tocado; o teste ABORTA se current_schema não
for nexa_e2e. Sem Postgres alcançável, o módulo inteiro é SKIPPED — a
suíte continua verde em CI sem banco.

Override de URL: exporte NEXA_E2E_DATABASE_URL (precisa apontar para um
schema/banco descartável — ele é dropado a cada rodada).
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[2]

_E2E_URL = os.getenv(
    "NEXA_E2E_DATABASE_URL",
    "postgresql+psycopg2://nexa_user:nexa_secret@localhost/nexa_db"
    "?options=-csearch_path%3Dnexa_e2e",
)

_USER = "e2e_user"


def _try_engine():
    try:
        engine = create_engine(_E2E_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as con:
            schema = con.execute(text("select current_schema()")).scalar()
        return engine, schema
    except Exception:
        return None, None


_engine, _schema = _try_engine()

pytestmark = pytest.mark.skipif(
    _engine is None,
    reason="Postgres E2E indisponível (configure NEXA_E2E_DATABASE_URL ou suba o PG local)",
)


@pytest.fixture(scope="module")
def pg_engine():
    # Trava de segurança: nunca rodar drop/alembic fora do schema isolado
    assert _schema == "nexa_e2e", (
        f"current_schema={_schema!r} — abortando para não tocar dados reais"
    )

    with _engine.connect() as con:
        con.execute(text("DROP SCHEMA IF EXISTS nexa_e2e CASCADE"))
        con.execute(text("CREATE SCHEMA nexa_e2e"))
        con.commit()

    # Migração real do zero — valida a cadeia completa (incl. o merge de
    # heads) em Postgres
    result = subprocess.run(
        ["python3", "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": _E2E_URL},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"alembic falhou:\n{result.stderr[-2000:]}"

    with _engine.connect() as con:
        version = con.execute(text("SELECT version_num FROM alembic_version")).scalar()
        # A propriedade é "o schema está no head", não "o head é esta string".
        # Fixar a revisão fazia toda migração nova quebrar este teste e ensinava
        # a atualizar um valor mágico em vez de verificar a coisa — e ainda
        # esconderia um head duplicado, que é o problema de verdade.
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        # caminho absoluto: a suíte roda tanto de backend/ (CI) quanto da raiz do repo
        ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        heads = ScriptDirectory.from_config(Config(str(ini))).get_heads()
        assert len(heads) == 1, f"grafo de migração ramificado: {heads}"
        assert version == heads[0], f"schema em {version}, head é {heads[0]}"
        tables = {
            r[0] for r in con.execute(text(
                "SELECT table_name FROM information_schema.tables"
                " WHERE table_schema = 'nexa_e2e'"
            ))
        }
        assert "user_challenges" in tables
        assert "transactions_clean" in tables
        assert "pluggy_sync_jobs" in tables

    yield _engine


@pytest.fixture(scope="module")
def service(pg_engine):
    """ChallengeService com SessionLocal apontando para o PG de teste."""
    import app.core.database as db_module
    from app.health_score.challenge_service import ChallengeService

    mp = pytest.MonkeyPatch()
    mp.setattr(db_module, "SessionLocal", sessionmaker(bind=pg_engine))
    yield ChallengeService()
    mp.undo()


def _seed(engine, rows: list[tuple[str, date, float, str, str]]) -> None:
    with engine.connect() as con:
        for i, (uid, d, amount, desc, cat) in enumerate(rows):
            con.execute(
                text(
                    "INSERT INTO transactions_clean"
                    " (transaction_id, user_id, date, amount, description, category)"
                    " VALUES (:tid, :uid, :d, :a, :desc, :cat)"
                ),
                {"tid": f"e2e_{d}_{i}_{abs(hash(desc)) % 10_000}", "uid": uid,
                 "d": d, "a": amount, "desc": desc, "cat": cat},
            )
        con.commit()


@pytest.fixture(scope="module")
def seeded(pg_engine):
    """Abril–junho/2026: salário 5k/mês, tarifa mensal, Delivery crescente."""
    rows = []
    for month, delivery in ((4, 400.0), (5, 500.0), (6, 600.0)):
        rows += [
            (_USER, date(2026, month, 1), 5000.0, "SALARIO EMPRESA NEXA", "Renda"),
            (_USER, date(2026, month, 10), -29.9, "TARIFA MANUTENCAO CONTA", "Tarifas"),
            (_USER, date(2026, month, 5), -delivery, "IFOOD PEDIDO", "Delivery"),
            (_USER, date(2026, month, 15), -2000.0, "ALUGUEL APARTAMENTO", "Moradia"),
            (_USER, date(2026, month, 20), -1500.0, "GASTOS GERAIS", "Outros"),
        ]
    _seed(pg_engine, rows)
    return True


class TestCicloDeVidaCompleto:
    """Os testes deste módulo são sequenciais — cada um avança o relógio."""

    def test_1_geracao_no_inicio_do_mes(self, service, seeded, pg_engine):
        challenges = service.sync(_USER, today=date(2026, 7, 2))

        by_type = {c.challenge_type: c for c in challenges}
        assert set(by_type) == {"SEM_TARIFAS", "REDUZIR_CATEGORIA", "GUARDAR_VALOR"}

        # personalização vinda dos dados semeados
        assert by_type["SEM_TARIFAS"].metadata["baseline_fees_3m_qty"] == 3
        assert by_type["REDUZIR_CATEGORIA"].metadata["category"] == "Delivery"
        assert by_type["REDUZIR_CATEGORIA"].target_value == pytest.approx(425.0)
        assert by_type["GUARDAR_VALOR"].target_value == pytest.approx(500.0)

        # persistido de verdade no PG
        with pg_engine.connect() as con:
            n = con.execute(text(
                "SELECT COUNT(*) FROM user_challenges"
                " WHERE user_id = :u AND month = '2026-07'"
            ), {"u": _USER}).scalar()
        assert n == 3

    def test_2_sync_duplo_e_idempotente(self, service, pg_engine):
        service.sync(_USER, today=date(2026, 7, 2))
        with pg_engine.connect() as con:
            n = con.execute(text(
                "SELECT COUNT(*) FROM user_challenges WHERE user_id = :u"
            ), {"u": _USER}).scalar()
        assert n == 3

    def test_3_conclusao_no_meio_do_mes_e_badge(self, service, pg_engine):
        # Julho: sem tarifa, Delivery controlado, sobra de R$600 ≥ alvo 500
        _seed(pg_engine, [
            (_USER, date(2026, 7, 1), 5000.0, "SALARIO EMPRESA NEXA", "Renda"),
            (_USER, date(2026, 7, 5), -300.0, "IFOOD PEDIDO", "Delivery"),
            (_USER, date(2026, 7, 10), -4100.0, "GASTOS GERAIS", "Outros"),
        ])
        challenges = service.sync(_USER, today=date(2026, 7, 15))
        by_type = {c.challenge_type: c for c in challenges}

        assert by_type["GUARDAR_VALOR"].status == "COMPLETED"
        assert by_type["GUARDAR_VALOR"].pct_progress == 100.0
        assert by_type["SEM_TARIFAS"].status == "ACTIVE"
        assert by_type["SEM_TARIFAS"].pct_progress == pytest.approx(48.4, abs=0.1)
        assert by_type["REDUZIR_CATEGORIA"].status == "ACTIVE"
        assert by_type["REDUZIR_CATEGORIA"].progress_value == pytest.approx(300.0)

        with pg_engine.connect() as con:
            badges = {r[0] for r in con.execute(text(
                "SELECT badge_type FROM user_badges WHERE user_id = :u"
            ), {"u": _USER})}
        assert "PRIMEIRO_DESAFIO" in badges

    def test_4_feed_inputs_refletem_o_estado(self, service):
        inputs = service.get_feed_inputs(_USER, today=date(2026, 7, 15))
        by_type = {i.challenge_type: i for i in inputs}

        assert by_type["GUARDAR_VALOR"].status == "COMPLETED"
        # ACTIVE < 70% não vira card de progresso
        assert "SEM_TARIFAS" not in by_type
        assert "REDUZIR_CATEGORIA" not in by_type

    def test_5_fechamento_na_virada_do_mes(self, service, pg_engine):
        challenges_aug = service.sync(_USER, today=date(2026, 8, 3))

        with pg_engine.connect() as con:
            july = {
                r[0]: r[1] for r in con.execute(text(
                    "SELECT challenge_type, status FROM user_challenges"
                    " WHERE user_id = :u AND month = '2026-07'"
                ), {"u": _USER})
            }
            badges = {r[0] for r in con.execute(text(
                "SELECT badge_type FROM user_badges WHERE user_id = :u"
            ), {"u": _USER})}

        # julho fechado: sem tarifa e Delivery dentro do teto → COMPLETED
        assert july == {
            "SEM_TARIFAS": "COMPLETED",
            "REDUZIR_CATEGORIA": "COMPLETED",
            "GUARDAR_VALOR": "COMPLETED",
        }
        # 3 desafios concluídos → badge de marco
        assert "DESAFIO_TRIPLO" in badges

        # agosto já nasce com desafios novos
        assert challenges_aug
        assert all(c.month == "2026-08" for c in challenges_aug)
