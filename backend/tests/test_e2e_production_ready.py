"""
SUÍTE E2E "PRODUCTION READY" — roda contra um ambiente SEMEADO.

Diferença para test_e2e_full_pipeline.py:
  - full_pipeline valida CONTRATOS com um usuário recém-criado (aceita os
    404 de onboarding);
  - esta suíte valida DADOS REAIS fluindo: exige um "golden user" com
    transações semeadas e faz asserções estritas (200 + conteúdo).

Comportamento por ambiente:
  - Sem dados semeados para o golden user → testes de dados são SKIPPED
    com razão explícita (a suíte nunca fica vermelha por falta de seed).
  - Com seed (scripts/seed ou ambiente de staging) → asserções completas.

Modernização (2026-07): o modelo de segurança passou a exigir Bearer token
com require_owner — o antigo GOLDEN_USER_ID fixo em path sem token não
funciona mais. Agora o user_id vem do próprio token do golden user
(sub do JWT), e todos os requests são autenticados.

Como semear: registre golden@nexa.com via API e insira transações em
transactions_clean com o user_id retornado (ver data/seed/).
"""

import logging
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from dotenv import load_dotenv
load_dotenv("backend/.env")

from app.main import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOLDEN_EMAIL = "golden@nexa.com"
GOLDEN_PASSWORD = "nexa_secure_password_123"


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def auth(client: AsyncClient) -> dict:
    """Registra (ou reutiliza) o golden user e retorna {headers, user_id}.

    O user_id é extraído do sub do JWT — é ele (e não um ID fixo) que o
    require_owner aceita nos paths.
    """
    await client.post("/api/v1/auth/register", json={
        "email": GOLDEN_EMAIL,
        "password": GOLDEN_PASSWORD,
        "full_name": "Nexa Golden User",
    })   # 201 na primeira vez, 400 se já existe — ambos ok

    login = await client.post("/api/v1/auth/token", data={
        "username": GOLDEN_EMAIL,
        "password": GOLDEN_PASSWORD,
    })
    assert login.status_code == 200, f"Falha no login: {login.text}"
    token = login.json()["access_token"]

    from jose import jwt
    user_id = jwt.get_unverified_claims(token)["sub"]

    return {"headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id}


@pytest_asyncio.fixture
async def seeded(client: AsyncClient, auth: dict) -> dict:
    """Gate de seed: skip quando o golden user não tem transações."""
    resp = await client.get(
        f"/api/v1/transactions/{auth['user_id']}", headers=auth["headers"]
    )
    has_data = (
        resp.status_code == 200
        and len(resp.json().get("transactions", [])) > 0
    )
    if not has_data:
        pytest.skip(
            "Golden user sem transações semeadas — esta suíte valida dados "
            "reais; rode o seed (data/seed/) para executá-la por completo."
        )
    return auth


def _skip_if_llm_unavailable(resp):
    if resp.status_code in (500, 502, 503):
        pytest.skip(f"LLM indisponível neste ambiente (HTTP {resp.status_code})")


# ── Sempre executáveis (não dependem de seed) ────────────────────────

@pytest.mark.asyncio
async def test_01_healthcheck(client: AsyncClient):
    """API de pé e docs acessíveis."""
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_05_reconnect(client: AsyncClient, auth: dict):
    """Geração de URL do Pluggy para reconexão — rota deve existir e tentar."""
    response = await client.post(
        f"/api/v1/reconnect/{auth['user_id']}", headers=auth["headers"]
    )
    # Sem credenciais Pluggy reais, 400/500/503 são aceitáveis; 404 = rota sumiu
    assert response.status_code in [200, 400, 500, 503]


@pytest.mark.asyncio
async def test_08_architect_simulate(client: AsyncClient, auth: dict):
    """F3 — simulação não depende de transações semeadas."""
    payload = {
        "user_id": auth["user_id"],
        "target_amount": 100000.0,
        "down_payment": 20000.0,
        "asset_type": "VEICULO",
    }
    response = await client.post(
        "/api/v1/architect/simulate", json=payload, headers=auth["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "action_plan" in data


@pytest.mark.asyncio
async def test_10_agent_chat_with_memory_and_auth(client: AsyncClient, auth: dict):
    """Chat protegido com JWT — B3+B4. Skip sem LLM configurado."""
    payload = {
        "user_id": auth["user_id"],
        "message": "Fale apenas 'ESTOU FUNCIONANDO' e nada a mais.",
    }
    response = await client.post(
        "/api/v1/chat/", json=payload, headers=auth["headers"]
    )
    _skip_if_llm_unavailable(response)
    assert response.status_code == 200, response.text[:300]
    assert "ESTOU FUNCIONANDO" in response.json()["response"].upper()


# ── Dependentes de seed (skip explícito sem dados) ───────────────────

@pytest.mark.asyncio
async def test_02_forecast(client: AsyncClient, seeded: dict):
    """B1: forecast roda o pipeline inteiro sobre os dados semeados."""
    response = await client.get(
        f"/api/v1/forecast/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "cashflow" in data
    assert "safe_to_spend" in data
    assert "financial_health" in data
    assert "burn_rate_ratio" in data["financial_health"]
    assert "horizon_days" in data["cashflow"]


@pytest.mark.asyncio
async def test_03_shadow_invoices(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/shadow_invoice/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "invoices" in data
    assert isinstance(data["invoices"], list)


@pytest.mark.asyncio
async def test_04_alerts(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/alerts/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


@pytest.mark.asyncio
async def test_06_transactions_workflow(client: AsyncClient, seeded: dict):
    """B2: webhook aceita evento e as transações são legíveis pela API."""
    webhook_payload = {
        "event": "transaction.created",
        "item": {"id": "mock_item_pluggy_123"},
        "data": {"id": "mock_transaction_123"},
    }
    wf_res = await client.post(
        f"/api/v1/transactions/webhook?user_id={seeded['user_id']}",
        json=webhook_payload,
        headers=seeded["headers"],
    )
    # Sem transação real na Pluggy o processamento pode falhar graceful
    assert wf_res.status_code in [200, 404, 422, 500]

    get_res = await client.get(
        f"/api/v1/transactions/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert get_res.status_code == 200
    data = get_res.json()
    assert len(data["transactions"]) > 0
    assert "amount" in data["transactions"][0]


@pytest.mark.asyncio
async def test_07_context_override(client: AsyncClient, seeded: dict):
    """F4 — override de contexto PF/PJ usando uma transação real via API."""
    get_res = await client.get(
        f"/api/v1/transactions/{seeded['user_id']}", headers=seeded["headers"]
    )
    txn_id = get_res.json()["transactions"][0].get("transaction_id") \
        or get_res.json()["transactions"][0].get("id")
    assert txn_id, "transação sem id na resposta da API"

    payload = {
        "transaction_id": txn_id,
        "corrected_context": "PJ",
        "reason": "Gasto corporativo",
    }
    response = await client.post(
        f"/api/v1/context/override?user_id={seeded['user_id']}",
        json=payload,
        headers=seeded["headers"],
    )
    assert response.status_code == 200, response.text[:300]
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_09_optimizer_analyze(client: AsyncClient, seeded: dict):
    payload = {
        "user_id": seeded["user_id"],
        "current_card_id": "nubank_roxinho",
        "monthly_income": 8000.0,
    }
    response = await client.post(
        "/api/v1/optimizer/analyze", json=payload, headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "cards" in data
    assert "best_card_id" in data


@pytest.mark.asyncio
async def test_11_health_score_history(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/health-score/history/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "history" in data
    assert "current_score" in data
    assert isinstance(data["history"], list)


@pytest.mark.asyncio
async def test_12_subscriptions(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/subscriptions/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "subscriptions" in data
    assert "total_monthly_cost" in data


@pytest.mark.asyncio
async def test_13_goals(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/goals/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    if len(data["goals"]) == 0:
        pytest.skip("Golden user sem metas cadastradas")
    assert "predicted_completion" in data["goals"][0]


@pytest.mark.asyncio
async def test_14_budget(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/budget/{seeded['user_id']}?monthly_income=12000.0&history_months=3",
        headers=seeded["headers"],
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "group_summary" in data
    assert "allocations" in data
    assert "actionable_cuts" in data


@pytest.mark.asyncio
async def test_15_notifications(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/notifications/{seeded['user_id']}", headers=seeded["headers"]
    )
    assert response.status_code == 200, response.text[:300]
    assert "by_priority" in response.json()


@pytest.mark.asyncio
async def test_16_fiscal_report(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/fiscal-report/{seeded['user_id']}?year=2024",
        headers=seeded["headers"],
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert "month" in data
    assert "lucro_estimado" in data
    assert "rbt12_anualizado" in data
    assert "das_estimado" in data


@pytest.mark.asyncio
async def test_17_peers_comparison(client: AsyncClient, seeded: dict):
    response = await client.get(
        f"/api/v1/peers/compare/{seeded['user_id']}?monthly_income=12000.0",
        headers=seeded["headers"],
    )
    assert response.status_code == 200, response.text[:300]
    assert "savings_percentile_label" in response.json()
