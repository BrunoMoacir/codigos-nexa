from __future__ import annotations

import polars as pl

from demo.services import (
    _pf_pj_split,
    _recent_transactions,
    _spend_by_category,
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
