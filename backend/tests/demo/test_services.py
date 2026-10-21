from __future__ import annotations

import polars as pl

from demo.services import (
    _note_to_dict,
    _pf_pj_split,
    _recent_transactions,
    _safe,
    _safe_to_spend,
    _spend_by_category,
    _health_score,
    _behavioral_profile,
    dashboard_data,
)


def test_spend_by_category_ignora_creditos_e_ordena_por_total() -> None:
    frame = pl.DataFrame(
        {
            "amount": [-30.0, -100.0, 50.0, -20.0],
            "category": ["lazer", "moradia", "renda", "lazer"],
        }
    )

    assert _spend_by_category(frame) == [
        {"category": "moradia", "total": 100.0, "n": 1},
        {"category": "lazer", "total": 50.0, "n": 2},
    ]


def test_pf_pj_split_retorna_apenas_debitos_por_contexto() -> None:
    frame = pl.DataFrame(
        {
            "amount": [-80.0, -20.0, 100.0, -50.0],
            "context_type": ["PF", "PF", "PF", "PJ"],
        }
    )

    assert _pf_pj_split(frame) == {"PF": 100.0, "PJ": 50.0}


def test_recent_transactions_usa_data_disponivel_e_limita_resultado() -> None:
    frame = pl.DataFrame(
        {
            "transaction_date": [
                "2026-10-01",
                "2026-10-03",
                "2026-10-02",
            ],
            "description": ["antiga", "recente", "meio"],
            "amount": [-10.0, -30.0, -20.0],
        }
    )

    result = _recent_transactions(frame, n=2)

    assert [row["description"] for row in result] == ["recente", "meio"]


def test_dashboard_data_explica_quando_persona_nao_tem_transacoes(monkeypatch) -> None:
    class EmptyFrame:
        def is_empty(self) -> bool:
            return True

    class Queries:
        @staticmethod
        def get_transactions_for_user(_user_id: str):
            return EmptyFrame()

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.core.db.queries",
        Queries,
    )

    result = dashboard_data("sem-dados")

    assert result == {
        "user_id": "sem-dados",
        "ok": False,
        "error": "Sem transações — rode `python3 -m demo.seed` primeiro.",
    }


def test_note_to_dict_preserva_procedencia_e_valores_opcionais() -> None:
    class Note:
        type = "idle_money"
        priority = "INFO"
        title = "Dinheiro parado"
        message = "Há saldo sem rendimento."
        action_hint = None
        metadata = {"source": "engine"}

    assert _note_to_dict(Note()) == {
        "type": "idle_money",
        "priority": "INFO",
        "title": "Dinheiro parado",
        "message": "Há saldo sem rendimento.",
        "action_hint": None,
        "metadata": {"source": "engine"},
    }


def test_safe_isola_falha_de_um_detector() -> None:
    called = False

    def detector_falho() -> None:
        nonlocal called
        called = True
        raise RuntimeError("falha externa")

    assert _safe(detector_falho) is None
    assert called


def test_spend_by_category_sem_colunas_necessarias_retorna_lista_vazia() -> None:
    assert _spend_by_category(pl.DataFrame({"amount": [10.0]})) == []


def test_pf_pj_split_sem_contexto_retorna_dict_vazio() -> None:
    frame = pl.DataFrame({"amount": [-10.0]})

    assert _pf_pj_split(frame) == {}


def test_health_score_degrada_quando_pipeline_de_score_falha(monkeypatch) -> None:
    from app.forecast.etl.profiles import UserProfileAnalyzer

    frame = pl.DataFrame({"amount": [-10.0]})
    monkeypatch.setattr(
        UserProfileAnalyzer,
        "analyze",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("score indisponível")),
    )

    result = _health_score("demo-ana", frame)

    assert result["score"] is None
    assert result["level"] is None


def test_behavioral_profile_degrada_quando_profiler_falha() -> None:
    frame = pl.DataFrame({"amount": [-10.0]})

    result = _behavioral_profile(frame)

    assert result["cluster"] == "NAO_CLASSIFICADO"
    assert "error" in result


def test_safe_to_spend_usa_total_e_diario_do_resultado() -> None:
    from app.notifications.notifier import SafeToSpendInput

    class SafeToSpend:
        safe_to_spend_daily = 25.0
        safe_to_spend_total = 750.0

    class Context:
        safe_to_spend = None

    ctx = Context()
    _safe_to_spend(ctx, {"projections": {"safe_to_spend": SafeToSpend()}}, SafeToSpendInput)

    assert ctx.safe_to_spend.daily_safe_amount == 25.0
    assert ctx.safe_to_spend.monthly_safe_amount == 750.0
