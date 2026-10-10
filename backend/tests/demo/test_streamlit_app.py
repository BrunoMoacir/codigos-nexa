from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

_APP = str(Path(__file__).parents[2] / "demo" / "streamlit_app.py")
_DASHBOARD = {
    "ok": True,
    "current_balance": 1250.0,
    "min_projected_balance": 900.0,
    "safe_to_spend_daily": 42.5,
    "monthly_income": 8500.0,
    "income_pattern": "SALARY",
    "n_transactions": 12,
    "health_score": {"score": 78, "level": "SAUDÁVEL", "resilience": 64},
    "profile": {
        "cluster": "DIGITAL_NATIVO",
        "secondary": [],
        "source": "rules",
        "ml_confidence": 0.9,
        "fss_level": "ATENÇÃO",
        "savings_rate": 12.5,
        "is_mei": False,
    },
    "by_category": [{"category": "alimentacao", "total": 320.0, "n": 4}],
    "pf_pj": {"PF": 320.0},
    "recent": [
        {
            "date": "2026-10-01",
            "description": "MERCADO",
            "amount": -120.0,
            "category": "alimentacao",
            "context_type": "PF",
        }
    ],
    "cashflow_forecast": None,
}


@pytest.fixture
def app() -> AppTest:
    with (
        patch("demo.services.dashboard_data", return_value=_DASHBOARD),
        patch("demo.services.build_feed", return_value=[]),
        patch("demo.data_readers.accounts", return_value=[]),
        patch("demo.data_readers.score_history", return_value=[]),
        patch("demo.data_readers.fee_history", return_value=[]),
        patch("demo.data_readers.negotiations", return_value=[]),
        patch("demo.data_readers.challenges", return_value=[]),
        patch("demo.data_readers.badges", return_value=[]),
        patch("demo.data_readers.context_overrides", return_value=[]),
        patch("demo.data_readers.chat_history", return_value=[]),
        patch("demo.data_readers.goals", return_value=[]),
        patch(
            "demo.data_readers.learning_loops",
            return_value={"calibration": {}, "feedback": [], "metrics": []},
        ),
    ):
        yield AppTest.from_file(_APP, default_timeout=30)


def _abrir(app: AppTest, page: str) -> AppTest:
    app = app.run()
    app.sidebar.radio[0].set_value(page)
    return app.run()


@pytest.mark.parametrize(
    "page",
    ["📊 Dashboard", "🔔 Feed", "💬 Chat", "🗄️ Meus Dados", "🧬 Aprendizado"],
)
def test_todas_as_superficies_renderizam_sem_excecao(app: AppTest, page: str) -> None:
    rendered = _abrir(app, page)

    assert not rendered.exception
    assert not rendered.error


def test_dashboard_exibe_kpis_do_servico(app: AppTest) -> None:
    rendered = _abrir(app, "📊 Dashboard")

    text = " ".join(item.value for item in rendered.metric)
    assert "R$ 42,50" in text
    assert "78/100" in text
    assert "12" in text


def test_feed_vazio_exibe_estado_explicitamente(app: AppTest) -> None:
    rendered = _abrir(app, "🔔 Feed")

    assert any("Nenhum card relevante" in item.value for item in rendered.info)


def test_chat_sem_llm_explica_como_ativar(app: AppTest) -> None:
    rendered = _abrir(app, "💬 Chat")

    assert any("Nenhuma chave de LLM" in item.value for item in rendered.warning)


def test_chat_envia_identidade_da_persona_e_persiste_resposta(app: AppTest) -> None:
    agent = SimpleNamespace()
    captured: dict[str, object] = {}

    def invoke(inputs, config):
        captured["inputs"] = inputs
        captured["config"] = config
        return {"messages": [SimpleNamespace(content="Seu saldo está positivo.")]}

    agent.invoke = invoke

    with (
        patch("app.agent.singleton.get_agent", return_value=agent),
        patch("app.core.config.settings.LLM_PROVIDER", "openai"),
        patch("app.core.config.settings.OPENAI_API_KEY", "test-key"),
    ):
        rendered = _abrir(app, "💬 Chat")
        rendered.chat_input[0].set_value("Como está meu saldo?").run()

    assert not rendered.exception
    assert any("Seu saldo está positivo." in item.value for item in rendered.markdown)
    assert captured["config"] == {"configurable": {"thread_id": "demo-ana"}}
    assert captured["inputs"]["messages"][0].content == (  # type: ignore[index]
        "[user_id=demo-ana] Como está meu saldo?"
    )
