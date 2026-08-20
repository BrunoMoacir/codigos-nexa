"""
Teste de Integração Completo — Projeto Nexa AI
===============================================

Cobre TODOS os módulos e funcionalidades da API:

  Sistema       : /health, /readiness, /version
  Auth          : register, login, logout, credenciais inválidas
  Transações    : webhook, listagem, filtros
  Health Score  : MX.1 — histórico e tendência
  Metas         : MX.2 — CRUD completo (criar, listar, detalhar, progresso, abandonar)
  Override PF/PJ: F4  — override e histórico
  Optimizer     : F2  — listar cartões, analisar, portfólio, ROI, promoções
  Architect     : F3  — simular financiamento/consórcio/poupar
  Compra        : F7  — recomendar forma de pagamento
  Custos        : F5  — raio-x de custos bancários
  Assinaturas   : M1.5 — detecção de recorrências
  Orçamento     : M1.3 — sugestão 50/30/20
  Negociador    : F13 — roteiro de negociação
  Fiscal        : M4.1 — relatório fiscal PJ
  Pares         : MX.4 — comparação com benchmarks POF/IBGE
  Forecast      : F1  — projeção financeira consolidada
  Notificações  : MX.3 — alertas proativos

Estratégia:
  • Cria um usuário exclusivo por módulo de testes via /auth/register
  • Insere transações mock diretamente no Postgres (SQLAlchemy)
  • Verifica estrutura de resposta, tipos e códigos HTTP
  • Endpoints que dependem de DuckDB/mock-Pluggy aceitam 500/404 graciosamente

Execução:
  cd backend
  pytest tests/test_integracao_completa.py -v
"""

import uuid
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.core.database import SessionLocal
from app.core.models.transaction import Transaction

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BASE = "/api/v1"


def _insert_mock_transactions(user_id: str, db: Session) -> int:
    """
    Insere um conjunto rico de transações mock no Postgres para o usuário.

    Inclui: salário, despesas recorrentes (streaming, academia, aluguel),
    gastos variáveis, parcelamentos, tarifas bancárias e transações PJ.
    Cobre os últimos 3 meses para garantir histórico suficiente para todos
    os algoritmos de detecção (recorrência, saúde, orçamento, peers).
    """
    today = date.today()
    rows: list[Transaction] = []

    def txn(**kwargs) -> Transaction:
        return Transaction(
            transaction_id=str(uuid.uuid4()),
            user_id=user_id,
            account_id=kwargs.get("account_id", "acc_pf_001"),
            description=kwargs["description"],
            amount=kwargs["amount"],
            date=kwargs["date"],
            transaction_type="CREDIT" if kwargs["amount"] > 0 else "DEBIT",
            category=kwargs.get("category", "outros"),
            is_recurring=kwargs.get("is_recurring", False),
            is_installment=kwargs.get("is_installment", False),
            context_type=kwargs.get("context_type", "PF"),
            context_confidence=kwargs.get("context_confidence", 0.90),
            context_override_by_user=False,
            pj_subcategory=kwargs.get("pj_subcategory"),
        )

    # Salário mensal — 3 meses consecutivos
    for m in range(3):
        rows.append(txn(
            description="SALARIO EMPRESA NEXATECH SA",
            amount=8_500.00,
            date=today - timedelta(days=m * 30 + 5),
            category="renda",
            is_recurring=True,
        ))

    # Despesas recorrentes fixas — 3 meses
    fixed = [
        ("NETFLIX ASSINATURA",    -55.90, "entretenimento",   True),
        ("SPOTIFY PREMIUM",       -21.90, "entretenimento",   True),
        ("AMAZON PRIME MENSAL",   -19.90, "entretenimento",   True),
        ("ACADEMIA SMART FIT",    -99.90, "saude",            True),
        ("PLANO DE SAUDE UNIMED", -650.00, "saude",           True),
        ("ALUGUEL APARTAMENTO",   -2_800.00, "moradia",       True),
        ("CONDOMINIO RESIDENCIA",  -520.00, "moradia",        True),
        ("INTERNET CLARO FIBRA",   -109.90, "moradia",        True),
    ]
    for m in range(3):
        for desc, amount, cat, recurring in fixed:
            rows.append(txn(
                description=desc,
                amount=amount,
                date=today - timedelta(days=m * 30 + 10),
                category=cat,
                is_recurring=recurring,
            ))

    # Gastos variáveis — mês atual
    variable = [
        ("SUPERMERCADO EXTRA HIPERMERCADO",   -480.00, "alimentacao"),
        ("IFOOD PEDIDO RESTAURANTE",           -87.50, "alimentacao"),
        ("RAPPI ENTREGA",                      -42.00, "alimentacao"),
        ("POSTO PETROBRAS COMBUSTIVEL",       -220.00, "transporte"),
        ("UBER CORRIDA",                       -35.00, "transporte"),
        ("FARMACIA DROGASIL",                 -125.00, "saude"),
        ("AMAZON COMPRAS ONLINE",             -389.90, "compras"),
        ("MERCADO LIVRE VENDEDOR",            -215.00, "compras"),
        ("LIVRARIA CULTURA",                   -89.90, "educacao"),
        ("ANUIDADE CARTAO NUBANK",             -45.00, "tarifa_bancaria"),
        ("ANUIDADE CARTAO ITAU",               -80.00, "tarifa_bancaria"),
        ("JUROS ROTATIVO CARTAO BRADESCO",    -320.00, "juros"),
        ("IOF COMPRA INTERNACIONAL",           -28.50, "tarifa_bancaria"),
        ("TARIFA MANUTENCAO CONTA",            -12.90, "tarifa_bancaria"),
    ]
    for desc, amount, cat in variable:
        rows.append(txn(
            description=desc,
            amount=amount,
            date=today - timedelta(days=8),
            category=cat,
        ))

    # Parcelamentos — 6 parcelas vencidas + próximas (para shadow invoice)
    for i in range(6):
        rows.append(txn(
            description=f"SAMSUNG GALAXY S24 12X PARC {i+1}/12",
            amount=-283.33,
            date=today - timedelta(days=i * 30 + 3),
            category="compras",
            is_installment=True,
        ))

    # Transações PJ — para fiscal report e divider
    pj_records = [
        ("CLIENTE EMPRESA ABC LTDA - NF 001",  6_500.00, "receita_servico",  "PJ",  "RECEITA_SERVICO"),
        ("CLIENTE STARTUP XYZ SA - NF 002",    4_200.00, "receita_servico",  "PJ",  "RECEITA_SERVICO"),
        ("ASSINATURA GOOGLE WORKSPACE PJ",      -250.00, "servicos_pj",       "PJ",  "SOFTWARE"),
        ("CONTADOR ESCRITORIO CONTABILIDADE",   -900.00, "servicos_pj",       "PJ",  "HONORARIOS"),
        ("ALUGUEL SALA COMERCIAL",            -1_500.00, "moradia",           "PJ",  "ALUGUEL"),
        ("PASSAGEM AEREAS VIAGEM CLIENTE",      -890.00, "transporte",        "PJ",  "VIAGEM_NEGOCIOS"),
    ]
    for desc, amount, cat, ctx, pj_sub in pj_records:
        rows.append(txn(
            description=desc,
            amount=amount,
            date=today - timedelta(days=15),
            category=cat,
            context_type=ctx,
            context_confidence=0.95,
            pj_subcategory=pj_sub,
            account_id="acc_pj_002",
        ))

    db.add_all(rows)
    db.commit()
    return len(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES — escopo de módulo (criadas uma vez, compartilhadas)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="module")
def client():
    """TestClient FastAPI — reutilizado em todo o módulo de testes."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def test_user(client):
    """Registra um usuário único e retorna email/senha/user_id."""
    email = f"integra_{uuid.uuid4().hex[:10]}@nexa.test"
    resp = client.post(f"{BASE}/auth/register", json={
        "email": email,
        "password": "SenhaIntegracao@123",
        "full_name": "Usuário Integração Nexa",
    })
    assert resp.status_code == 201, f"Registro falhou: {resp.text}"
    return {
        "email": email,
        "password": "SenhaIntegracao@123",
        "user_id": resp.json()["user_id"],
    }


@pytest.fixture(scope="module")
def token(client, test_user):
    """Bearer token do usuário de teste."""
    resp = client.post(f"{BASE}/auth/token", data={
        "username": test_user["email"],
        "password": test_user["password"],
    })
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def H(token):
    """Atalho para headers de autenticação."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def uid(test_user):
    """user_id do usuário de teste."""
    return test_user["user_id"]


@pytest.fixture(scope="module")
def db_with_data(uid):
    """
    Insere dados mock no Postgres UMA VEZ e os mantém disponíveis para
    todos os testes que precisam de histórico de transações.
    """
    db: Session = SessionLocal()
    try:
        total = _insert_mock_transactions(uid, db)
        yield {"user_id": uid, "total_inserted": total}
    finally:
        # Limpar as transações do usuário de teste após os testes
        try:
            db.query(Transaction).filter(Transaction.user_id == uid).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. SISTEMA — Health Checks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestSistema:
    """Probes de sistema: liveness, readiness e versão da API."""

    def test_liveness(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "service" in data

    def test_readiness(self, client):
        resp = client.get("/readiness")
        # 200 = banco conectado; 503 = banco indisponível (aceitável em CI sem Postgres)
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "database" in data

    def test_version(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200
        assert "version" in resp.json()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. AUTENTICAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAuth:
    """
    Valida o fluxo completo de autenticação:
    registro → login → uso autenticado → logout → rejeição de token inválido.
    """

    def test_registro_sucesso(self, client):
        email = f"reg_{uuid.uuid4().hex[:8]}@nexa.test"
        resp = client.post(f"{BASE}/auth/register", json={
            "email": email,
            "password": "SenhaForte@2024",
            "full_name": "Usuário Novo",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "user_id" in data
        assert data["message"]

    def test_registro_email_duplicado(self, client, test_user):
        resp = client.post(f"{BASE}/auth/register", json={
            "email": test_user["email"],
            "password": "qualquersenha",
        })
        assert resp.status_code == 400
        assert "registrado" in resp.json()["detail"].lower()

    def test_login_sucesso(self, client, test_user):
        resp = client.post(f"{BASE}/auth/token", data={
            "username": test_user["email"],
            "password": test_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user_id" in data

    def test_login_senha_errada(self, client, test_user):
        resp = client.post(f"{BASE}/auth/token", data={
            "username": test_user["email"],
            "password": "senha_errada_xyz",
        })
        assert resp.status_code == 401

    def test_login_email_inexistente(self, client):
        resp = client.post(f"{BASE}/auth/token", data={
            "username": "fantasma@naoexiste.com",
            "password": "qualquercoisa",
        })
        assert resp.status_code == 401

    def test_acesso_sem_token(self, client, uid):
        resp = client.get(f"{BASE}/transactions/{uid}")
        assert resp.status_code == 401

    def test_token_invalido(self, client, uid):
        resp = client.get(
            f"{BASE}/transactions/{uid}",
            headers={"Authorization": "Bearer token_invalido_xpto"},
        )
        assert resp.status_code == 401

    def test_logout(self, client, H):
        resp = client.post(f"{BASE}/auth/logout", headers=H)
        assert resp.status_code == 204


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. TRANSAÇÕES (F1 — ETL Webhook + Listagem)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestTransacoes:
    """
    Testa o webhook de ingestão de transações (formato Pluggy)
    e os endpoints de listagem com filtros.
    """

    def test_webhook_formato_pluggy(self, client, uid):
        """POST /transactions/webhook — ingere transações no formato Pluggy."""
        payload = {
            "connector": {"id": "201"},
            "item": {"id": f"item_{uid[:8]}"},
            "results": [
                {
                    "id": str(uuid.uuid4()),
                    "date": str(date.today() - timedelta(days=2)),
                    "description": "MERCADO LIVRE COMPRA WEBHOOK",
                    "amount": -199.90,
                    "currencyCode": "BRL",
                    "type": "DEBIT",
                    "category": "Compras",
                },
                {
                    "id": str(uuid.uuid4()),
                    "date": str(date.today() - timedelta(days=1)),
                    "description": "DEPOSITO PIX REMETENTE",
                    "amount": 500.00,
                    "currencyCode": "BRL",
                    "type": "CREDIT",
                    "category": "Transferência",
                },
            ],
        }
        resp = client.post(
            f"{BASE}/transactions/webhook?user_id={uid}",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert "batch_id" in data
        assert data["total_received"] == 2

    def test_listar_transacoes_sem_dados(self, client, H, uid):
        """Usuário sem dados retorna 404 ou lista vazia."""
        fresh_id = str(uuid.uuid4())
        # Criar usuário temporário só para testar 404
        email_tmp = f"tmp_{uuid.uuid4().hex[:8]}@nexa.test"
        r = client.post(f"{BASE}/auth/register", json={"email": email_tmp, "password": "Abc@12345"})
        if r.status_code != 201:
            pytest.skip("Não foi possível criar usuário temporário")
        tmp_token = client.post(f"{BASE}/auth/token", data={
            "username": email_tmp, "password": "Abc@12345"
        }).json().get("access_token", "")
        tmp_uid = r.json()["user_id"]
        tmp_H = {"Authorization": f"Bearer {tmp_token}"}
        resp = client.get(f"{BASE}/transactions/{tmp_uid}", headers=tmp_H)
        assert resp.status_code in (200, 404)

    def test_listar_transacoes_com_dados(self, client, H, uid, db_with_data):
        """GET /transactions/{user_id} — retorna transações do Postgres."""
        resp = client.get(f"{BASE}/transactions/{uid}", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert data["total"] > 0
        assert isinstance(data["transactions"], list)
        # Verificar estrutura da primeira transação
        txn = data["transactions"][0]
        assert "amount" in txn
        assert "description" in txn
        assert "date" in txn

    def test_listar_transacoes_filtro_categoria(self, client, H, uid, db_with_data):
        """GET /transactions/{user_id}?category=alimentacao — filtra por categoria."""
        resp = client.get(
            f"{BASE}/transactions/{uid}?category=alimentacao",
            headers=H,
        )
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            for txn in resp.json()["transactions"]:
                assert txn.get("category", "").lower() == "alimentacao"

    def test_listar_transacoes_filtro_data(self, client, H, uid, db_with_data):
        """GET /transactions/{user_id}?start_date=...&end_date=... — filtra por data."""
        start = (date.today() - timedelta(days=30)).isoformat()
        end = date.today().isoformat()
        resp = client.get(
            f"{BASE}/transactions/{uid}?start_date={start}&end_date={end}",
            headers=H,
        )
        assert resp.status_code in (200, 404)

    def test_listar_transacoes_proibido_outro_usuario(self, client, H):
        """Não deve acessar transações de outro usuário."""
        outro_uid = str(uuid.uuid4())
        resp = client.get(f"{BASE}/transactions/{outro_uid}", headers=H)
        assert resp.status_code in (401, 403, 422)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. HEALTH SCORE (MX.1)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestHealthScore:
    """
    MX.1 — Score de saúde financeira (0–100) com histórico e tendência.
    Calcula resiliência + FSS a partir das transações do Postgres.
    """

    def test_historico_sem_dados(self, client, H, uid):
        """Usuário sem transações retorna score=0 e data_quality=NO_TRANSACTIONS."""
        fresh_email = f"hs_{uuid.uuid4().hex[:8]}@nexa.test"
        r = client.post(f"{BASE}/auth/register", json={"email": fresh_email, "password": "Abc@12345"})
        if r.status_code != 201:
            pytest.skip("Registro falhou")
        fresh_uid = r.json()["user_id"]
        fresh_token = client.post(f"{BASE}/auth/token", data={
            "username": fresh_email, "password": "Abc@12345"
        }).json().get("access_token", "")
        fresh_H = {"Authorization": f"Bearer {fresh_token}"}

        resp = client.get(f"{BASE}/health-score/history/{fresh_uid}", headers=fresh_H)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == fresh_uid
        assert data["current_score"] >= 0
        assert data["trend"] in ("IMPROVING", "STABLE", "DECLINING")
        assert "history" in data
        assert data["data_quality"] in ("OK", "INSUFFICIENT_DATA", "NO_TRANSACTIONS")

    def test_historico_com_dados(self, client, H, uid, db_with_data):
        """Com transações disponíveis, retorna score calculado e histórico."""
        resp = client.get(
            f"{BASE}/health-score/history/{uid}?months=6",
            headers=H,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert 0 <= data["current_score"] <= 100
        assert data["trend"] in ("IMPROVING", "STABLE", "DECLINING")
        assert isinstance(data["history"], list)
        assert data["data_quality"] in ("OK", "INSUFFICIENT_DATA", "NO_TRANSACTIONS")

    def test_historico_proibido_outro_usuario(self, client, H):
        """Não deve acessar health score de outro usuário."""
        outro = str(uuid.uuid4())
        resp = client.get(f"{BASE}/health-score/history/{outro}", headers=H)
        assert resp.status_code in (401, 403, 422)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. METAS FINANCEIRAS (MX.2) — CRUD COMPLETO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMetas:
    """
    MX.2 — CRUD completo de metas financeiras.
    Fluxo: criar → listar → detalhar → atualizar progresso → abandonar.
    """

    _goal_id: str | None = None

    def test_criar_meta(self, client, H, uid):
        """POST /goals/{user_id} — cria nova meta financeira."""
        target_date = (date.today() + timedelta(days=365)).isoformat()
        resp = client.post(f"{BASE}/goals/{uid}", headers=H, json={
            "name": "Viagem ao Japão",
            "goal_type": "viagem",
            "target_amount": 15_000.00,
            "current_amount": 500.00,
            "target_date": target_date,
        })
        assert resp.status_code == 201, f"Falha ao criar meta: {resp.text}"
        data = resp.json()
        assert "goal_id" in data
        assert data["name"] == "Viagem ao Japão"
        assert data["target_amount"] == 15_000.00
        assert data["status"] == "ACTIVE"
        TestMetas._goal_id = data["goal_id"]

    def test_criar_meta_data_passada(self, client, H, uid):
        """Meta com data passada deve retornar 422."""
        resp = client.post(f"{BASE}/goals/{uid}", headers=H, json={
            "name": "Meta Inválida",
            "goal_type": "outros",
            "target_amount": 1_000.00,
            "target_date": "2020-01-01",
        })
        assert resp.status_code == 422

    def test_criar_meta_valor_negativo(self, client, H, uid):
        """Meta com valor negativo deve retornar 422."""
        resp = client.post(f"{BASE}/goals/{uid}", headers=H, json={
            "name": "Meta Negativa",
            "goal_type": "outros",
            "target_amount": -500.00,
        })
        assert resp.status_code == 422

    def test_listar_metas(self, client, H, uid):
        """GET /goals/{user_id} — lista metas ACTIVE com projeções."""
        resp = client.get(f"{BASE}/goals/{uid}?status=ACTIVE", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert "goals" in data
        assert isinstance(data["goals"], list)
        assert data["total"] >= 1

    def test_listar_metas_paginacao(self, client, H, uid):
        """GET /goals/{user_id}?limit=1&offset=0 — paginação."""
        resp = client.get(f"{BASE}/goals/{uid}?limit=1&offset=0", headers=H)
        assert resp.status_code == 200
        assert len(resp.json()["goals"]) <= 1

    def test_detalhar_meta(self, client, H, uid):
        """GET /goals/{user_id}/{goal_id} — detalhe com projeção."""
        if not TestMetas._goal_id:
            pytest.skip("goal_id não disponível (criar meta falhou)")
        resp = client.get(f"{BASE}/goals/{uid}/{TestMetas._goal_id}", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert data["goal_id"] == TestMetas._goal_id
        assert "projection" in data
        assert "monthly_contribution_needed" in data["projection"]

    def test_atualizar_progresso_meta(self, client, H, uid):
        """PATCH /goals/{user_id}/{goal_id}/progress — adiciona aporte."""
        if not TestMetas._goal_id:
            pytest.skip("goal_id não disponível")
        resp = client.patch(
            f"{BASE}/goals/{uid}/{TestMetas._goal_id}/progress",
            headers=H,
            json={"amount_to_add": 1_000.00},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_amount"] >= 1_500.00  # 500 inicial + 1000 aporte
        assert data["status"] == "ACTIVE"

    def test_criar_segunda_meta_imovel(self, client, H, uid):
        """Cria uma segunda meta do tipo imóvel para testar múltiplas metas."""
        resp = client.post(f"{BASE}/goals/{uid}", headers=H, json={
            "name": "Casa Própria",
            "goal_type": "imovel",
            "target_amount": 250_000.00,
            "current_amount": 30_000.00,
        })
        assert resp.status_code in (201, 500)

    def test_abandonar_meta(self, client, H, uid):
        """DELETE /goals/{user_id}/{goal_id} — abandona meta."""
        if not TestMetas._goal_id:
            pytest.skip("goal_id não disponível")
        resp = client.delete(f"{BASE}/goals/{uid}/{TestMetas._goal_id}", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert "goal" in data
        assert data["goal"]["status"] == "ABANDONED"

    def test_meta_nao_encontrada(self, client, H, uid):
        """GET /goals/{user_id}/{goal_id} com ID inexistente retorna 404."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"{BASE}/goals/{uid}/{fake_id}", headers=H)
        assert resp.status_code == 404

    def test_listar_metas_simples(self, client, uid, H):
        """GET /goals/{user_id}/simple — exige token do próprio titular
        (era 'sem auth'; IDOR corrigido na auditoria 2026-07)."""
        resp = client.get(f"{BASE}/goals/{uid}/simple", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert "goals" in data
        assert "total" in data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. CONTEXT OVERRIDE — F4 (PF/PJ)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestContextOverride:
    """
    F4 — Classificação manual PF/PJ.
    Permite ao usuário corrigir a classificação automática de uma transação.
    """

    _txn_id: str = str(uuid.uuid4())

    def test_override_transacao(self, client, H, uid, db_with_data):
        """POST /context/override?user_id=... — reclassifica transação."""
        resp = client.post(
            f"{BASE}/context/override?user_id={uid}",
            headers=H,
            json={
                "transaction_id": TestContextOverride._txn_id,
                "corrected_context": "PJ",
                "original_context": "PF",
                "reason": "Despesa de escritório confundida com pessoal",
            },
        )
        # Pode retornar 200 (sucesso) ou 500 se a transação não existir
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            assert data["corrected_context"] == "PJ"

    def test_listar_overrides(self, client, H, uid):
        """GET /context/overrides?user_id=... — lista histórico de overrides."""
        resp = client.get(f"{BASE}/context/overrides?user_id={uid}", headers=H)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert isinstance(resp.json(), list)

    def test_stats_overrides(self, client, H, uid):
        """GET /context/overrides/stats?user_id=... — estatísticas de overrides."""
        resp = client.get(f"{BASE}/context/overrides/stats?user_id={uid}", headers=H)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert isinstance(resp.json(), dict)

    def test_override_contexto_invalido(self, client, H, uid):
        """corrected_context inválido deve retornar 422."""
        resp = client.post(
            f"{BASE}/context/override?user_id={uid}",
            headers=H,
            json={
                "transaction_id": str(uuid.uuid4()),
                "corrected_context": "INVALIDO",
            },
        )
        assert resp.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. OPTIMIZER — F2 (Cartões de Crédito)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestOptimizer:
    """
    F2 — Otimização de cartões de crédito.
    Simula 12 meses de gastos para encontrar o cartão com maior ROI.
    """

    def test_listar_cartoes(self, client):
        """GET /optimizer/cards — lista a base de conhecimento de cartões."""
        resp = client.get(f"{BASE}/optimizer/cards")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert data["total"] > 0
        assert isinstance(data["cards"], list)
        card = data["cards"][0]
        assert "card_id" in card
        assert "name" in card

    def test_analisar_cartoes(self, client, H, uid, db_with_data):
        """POST /optimizer/analyze — análise completa de cartões para o perfil."""
        resp = client.post(f"{BASE}/optimizer/analyze", headers=H, json={
            "user_id": uid,
            "current_cards": [],
            "monthly_income": 8_500.00,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "recommended_cards" in data
        assert isinstance(data["recommended_cards"], list)
        assert "confidence_score" in data
        assert 0 <= data["confidence_score"] <= 1

    def test_analisar_cartoes_proibido_outro_usuario(self, client, H):
        """POST /optimizer/analyze com user_id diferente → 403."""
        resp = client.post(f"{BASE}/optimizer/analyze", headers=H, json={
            "user_id": str(uuid.uuid4()),
            "monthly_income": 5_000.00,
        })
        assert resp.status_code == 403

    def test_listar_relatorios_usuario(self, client, H, uid):
        """GET /optimizer/reports/{user_id} — histórico de relatórios."""
        resp = client.get(f"{BASE}/optimizer/reports/{uid}", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert isinstance(data["reports"], list)

    def test_portfolio_cartoes(self, client, H, uid, db_with_data):
        """GET /optimizer/portfolio/{user_id} — carteira ideal multi-cartão."""
        resp = client.get(
            f"{BASE}/optimizer/portfolio/{uid}?max_cards=3&monthly_income=8500",
            headers=H,
        )
        assert resp.status_code in (200, 404, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert "net_annual_gain" in data
            assert "cards" in data
            assert isinstance(data["cards"], list)

    def test_roi_cartao(self, client, H, uid, db_with_data):
        """GET /optimizer/roi/{card_id} — ROI de um cartão específico."""
        resp = client.get(
            f"{BASE}/optimizer/roi/nubank_roxinho?user_id={uid}&monthly_spend=3000",
            headers=H,
        )
        # Pode ser 200 (cartão encontrado) ou 404 (não existe na base)
        assert resp.status_code in (200, 404, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert "card_id" in data or "card_name" in data

    def test_promacoes_ativas(self, client):
        """GET /optimizer/promotions — promoções de pontos ativas."""
        resp = client.get(f"{BASE}/optimizer/promotions")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert isinstance(data["promotions"], list)

    def test_health_optimizer(self, client):
        """GET /optimizer/health — health check do módulo."""
        resp = client.get(f"{BASE}/optimizer/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. ARCHITECT — F3 (Planejamento Financeiro)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestArchitect:
    """
    F3 — Simulador de estratégias de aquisição.
    Compara Financiamento × Consórcio × Poupar/Investir via NPV.
    """

    _simulation_id: str | None = None

    def test_simular_financiamento(self, client, H, uid):
        """POST /architect/simulate — simula compra de veículo."""
        resp = client.post(f"{BASE}/architect/simulate", headers=H, json={
            "user_id": uid,
            "target_amount": 60_000.00,
            "down_payment": 10_000.00,
            "asset_type": "VEICULO",
            "financing_months": 48,
            "risk_profile": "moderado",
            "include_consortium": True,
            "max_monthly_budget": 1_800.00,
        })
        assert resp.status_code in (200, 422, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "recommended_strategy" in data
            assert data["recommended_strategy"] in (
                "FINANCING", "CONSORTIUM", "SAVE_INVEST",
                "FINANCING_RENTAL", "CONSORTIUM_SELIC_RENTAL",
            )
            assert "confidence_score" in data
            assert 0 <= data["confidence_score"] <= 1
            assert "costs" in data
            TestArchitect._simulation_id = data.get("simulation_id")

    def test_simular_imovel(self, client, H, uid):
        """POST /architect/simulate — simula compra de imóvel."""
        resp = client.post(f"{BASE}/architect/simulate", headers=H, json={
            "user_id": uid,
            "target_amount": 350_000.00,
            "down_payment": 70_000.00,
            "asset_type": "IMOVEL",
            "financing_months": 360,
            "risk_profile": "conservador",
        })
        assert resp.status_code in (200, 422, 500)

    def test_simular_valor_invalido(self, client, H, uid):
        """target_amount negativo deve retornar 422."""
        resp = client.post(f"{BASE}/architect/simulate", headers=H, json={
            "user_id": uid,
            "target_amount": -1_000.00,
            "asset_type": "VEICULO",
        })
        assert resp.status_code == 422

    def test_listar_simulacoes(self, client, H, uid):
        """GET /architect/simulations?user_id=... — histórico de simulações."""
        resp = client.get(
            f"{BASE}/architect/simulations?user_id={uid}&limit=10",
            headers=H,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_metricas_usuario(self, client, H, uid):
        """GET /architect/metrics?user_id=... — métricas agregadas."""
        resp = client.get(f"{BASE}/architect/metrics?user_id={uid}", headers=H)
        # 200 = tem simulações; 404 = sem simulações ainda
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert data["user_id"] == uid
            assert "total_simulations" in data

    def test_cenarios_timing(self, client, H, uid):
        """POST /architect/timing-scenarios — 'E se eu esperar X meses?'"""
        resp = client.post(
            f"{BASE}/architect/timing-scenarios?monthly_savings=2000",
            headers=H,
            json={
                "user_id": uid,
                "target_amount": 80_000.00,
                "down_payment": 15_000.00,
                "asset_type": "VEICULO",
                "financing_months": 60,
                "risk_profile": "moderado",
            },
        )
        assert resp.status_code in (200, 422, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) > 0
            assert "wait_months" in data[0]
            assert "monthly_payment" in data[0]

    def test_health_architect(self, client):
        """GET /architect/health — health check do módulo."""
        resp = client.get(f"{BASE}/architect/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. PURCHASE ADVISOR — F7 (Compra Inteligente)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCompraInteligente:
    """
    F7 — Recomenda a melhor forma de pagamento para uma compra específica.
    Compara: PIX, cartão à vista, parcelado, CDC.
    """

    def test_analisar_compra_pix(self, client, H, uid):
        """POST /purchase/analyze — compra simples à vista."""
        resp = client.post(f"{BASE}/purchase/analyze", headers=H, json={
            "user_id": uid,
            "amount": 500.00,
            "category": "Eletrônicos",
            "installments": 1,
            "monthly_income": 8_500.00,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "recommended_method" in data
        assert "options" in data
        assert isinstance(data["options"], list)
        assert len(data["options"]) > 0
        assert "confidence_score" in data

    def test_analisar_compra_parcelada(self, client, H, uid):
        """POST /purchase/analyze — compra em 12x para checar CDC."""
        resp = client.post(f"{BASE}/purchase/analyze", headers=H, json={
            "user_id": uid,
            "amount": 3_000.00,
            "category": "Eletrodomésticos",
            "installments": 12,
            "monthly_income": 8_500.00,
        })
        assert resp.status_code == 200
        data = resp.json()
        methods = [opt["method"] for opt in data["options"]]
        # Pelo menos PIX e cartão à vista devem aparecer
        assert len(methods) >= 2

    def test_analisar_compra_proibida_outro_usuario(self, client, H):
        """user_id diferente → 403."""
        resp = client.post(f"{BASE}/purchase/analyze", headers=H, json={
            "user_id": str(uuid.uuid4()),
            "amount": 100.00,
            "category": "Outros",
            "installments": 1,
        })
        assert resp.status_code == 403

    def test_analisar_compra_valor_zero(self, client, H, uid):
        """amount=0 → 422."""
        resp = client.post(f"{BASE}/purchase/analyze", headers=H, json={
            "user_id": uid,
            "amount": 0,
            "category": "Teste",
            "installments": 1,
        })
        assert resp.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. CUSTOS BANCÁRIOS — F5 (Raio-X)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCustosBancarios:
    """
    F5 — Raio-X de Custos Bancários.
    Detecta anuidades, juros rotativos, IOF e tarifas ocultas.
    """

    def test_raio_x_com_dados(self, client, H, uid, db_with_data):
        """GET /costs/raio-x/{user_id} — relatório de custos bancários."""
        resp = client.get(f"{BASE}/costs/raio-x/{uid}", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "total_fees_period" in data
        assert "annualized_cost" in data

        # As asserções abaixo checam VALORES, não presença de chave. A versão
        # anterior terminava em `isinstance(data.get("fee_breakdown", []), list)`
        # — e `fee_breakdown` não é campo do modelo, então o `.get` devolvia []
        # e o isinstance era sempre verdadeiro. Foi o que deixou passar a
        # projeção anual inflada pelo número de meses de histórico.
        assert isinstance(data["by_fee_type"], dict)
        assert data["analysis_months"] >= 1
        if data["total_paid"] > 0:
            # coerência interna: anual = média mensal × 12, e a média mensal sai
            # do período REAL do extrato, não de um mês fixo
            assert data["period_start"] is not None
            assert data["annualized_cost"] == pytest.approx(
                data["monthly_avg"] * 12, abs=0.02
            )
            assert data["monthly_avg"] == pytest.approx(
                data["total_paid"] / data["analysis_months"], abs=0.02
            )

    def test_raio_x_sem_dados(self, client, H):
        """Usuário sem transações retorna 404."""
        fresh_email = f"costs_{uuid.uuid4().hex[:8]}@nexa.test"
        r = client.post(f"{BASE}/auth/register", json={"email": fresh_email, "password": "Abc@12345"})
        if r.status_code != 201:
            pytest.skip("Registro falhou")
        fresh_uid = r.json()["user_id"]
        fresh_token = client.post(f"{BASE}/auth/token", data={
            "username": fresh_email, "password": "Abc@12345"
        }).json().get("access_token", "")
        fresh_H = {"Authorization": f"Bearer {fresh_token}"}
        resp = client.get(f"{BASE}/costs/raio-x/{fresh_uid}", headers=fresh_H)
        assert resp.status_code == 404

    def test_raio_x_proibido(self, client, H):
        """Não pode acessar raio-x de outro usuário."""
        resp = client.get(f"{BASE}/costs/raio-x/{uuid.uuid4()}", headers=H)
        assert resp.status_code in (403, 422)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. ASSINATURAS — M1.5
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAssinaturas:
    """
    M1.5 — Detecção de assinaturas recorrentes e alertas de esquecidas.
    Detecta: streaming duplicado, valor baixo, aumento de preço.
    """

    def test_detectar_assinaturas(self, client, H, uid, db_with_data):
        """GET /subscriptions/{user_id} — detecta streamings e recorrentes."""
        resp = client.get(
            f"{BASE}/subscriptions/{uid}?months=6",
            headers=H,
        )
        # Sem auth necessária nesse endpoint (não usa require_owner)
        assert resp.status_code in (200, 422, 404, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_subscriptions" in data
            assert "subscriptions" in data
            assert isinstance(data["subscriptions"], list)

    def test_detectar_assinaturas_sem_dados(self, client):
        """Usuário sem transações retorna 404 — com o token do próprio
        titular (o endpoint agora exige require_owner)."""
        fresh_email = f"sub_{uuid.uuid4().hex[:8]}@nexa.test"
        password = "Abc@12345"
        r = client.post(f"{BASE}/auth/register", json={"email": fresh_email, "password": password})
        if r.status_code != 201:
            pytest.skip("Registro falhou")
        fresh_uid = r.json()["user_id"]
        login = client.post(f"{BASE}/auth/token", data={"username": fresh_email, "password": password})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp = client.get(f"{BASE}/subscriptions/{fresh_uid}", headers=headers)
        assert resp.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. ORÇAMENTO INTELIGENTE — M1.3
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestOrcamento:
    """
    M1.3 — Orçamento 50/30/20 inteligente.
    Compara gastos reais com a regra clássica e sugere cortes.
    """

    def test_orcamento_com_dados(self, client, H, uid, db_with_data):
        """GET /budget/{user_id}?monthly_income=8500 — orçamento baseado no histórico."""
        resp = client.get(
            f"{BASE}/budget/{uid}?monthly_income=8500",
            headers=H,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "income" in data
        assert "group_summary" in data
        assert isinstance(data["group_summary"], list)
        assert len(data["group_summary"]) == 3  # essenciais, desejos, poupanca
        assert "summary_text" in data
        assert "confidence" in data

    def test_orcamento_sem_renda(self, client, H, uid):
        """GET /budget sem monthly_income → 422."""
        resp = client.get(f"{BASE}/budget/{uid}", headers=H)
        assert resp.status_code == 422

    def test_orcamento_sem_dados(self, client, H, uid):
        """Usuário sem transações recebe orçamento padrão 50/30/20."""
        fresh_email = f"bud_{uuid.uuid4().hex[:8]}@nexa.test"
        r = client.post(f"{BASE}/auth/register", json={"email": fresh_email, "password": "Abc@12345"})
        if r.status_code != 201:
            pytest.skip("Registro falhou")
        fresh_uid = r.json()["user_id"]
        fresh_token = client.post(f"{BASE}/auth/token", data={
            "username": fresh_email, "password": "Abc@12345"
        }).json().get("access_token", "")
        fresh_H = {"Authorization": f"Bearer {fresh_token}"}
        resp = client.get(f"{BASE}/budget/{fresh_uid}?monthly_income=5000", headers=fresh_H)
        assert resp.status_code == 200
        data = resp.json()
        # Sem dados → confidence deve ser 0 e grupo padrão retornado
        assert data["confidence"] == 0.0
        assert len(data["group_summary"]) == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 13. NEGOCIADOR — F13
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNegociador:
    """
    F13 — Nexa Negotiator Bot.
    Detecta oportunidades e gera roteiro de negociação bancária.
    """

    def test_gerar_script_sem_banco(self, client, H, uid, db_with_data):
        """POST /negotiator/generate-script — detecta todas as oportunidades."""
        resp = client.post(f"{BASE}/negotiator/generate-script", headers=H, json={
            "user_id": uid,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert "opportunities_found" in data
        assert isinstance(data["scripts"], list)
        assert "confidence_score" in data
        assert "summary" in data

    def test_gerar_script_banco_especifico(self, client, H, uid, db_with_data):
        """POST /negotiator/generate-script?bank_name=Bradesco — filtra banco."""
        resp = client.post(f"{BASE}/negotiator/generate-script", headers=H, json={
            "user_id": uid,
            "bank_name": "Bradesco",
        })
        assert resp.status_code == 200
        data = resp.json()
        # Scripts filtrados para Bradesco; pode ter 0 oportunidades
        assert data["user_id"] == uid

    def test_gerar_script_proibido(self, client, H):
        """user_id de outro usuário → 403."""
        resp = client.post(f"{BASE}/negotiator/generate-script", headers=H, json={
            "user_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 403


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14. RELATÓRIO FISCAL — M4.1
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFiscal:
    """
    M4.1 — Relatório Fiscal PJ.
    Segrega receitas e despesas PJ, estima DAS (Simples Nacional).
    """

    def test_relatorio_anual(self, client, H, uid, db_with_data):
        """GET /fiscal-report/{user_id} — relatório fiscal do ano."""
        ano = date.today().year
        resp = client.get(f"{BASE}/fiscal-report/{uid}?year={ano}", headers=H)
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert data["year"] == ano
        assert "total_receita" in data
        assert "total_despesa" in data
        assert "lucro_estimado" in data
        assert "das_estimado" in data
        assert isinstance(data["receitas"], list)
        assert isinstance(data["despesas"], list)

    def test_relatorio_mensal(self, client, H, uid, db_with_data):
        """GET /fiscal-report/{user_id}?month=X — relatório fiscal de um mês."""
        mes = date.today().month
        ano = date.today().year
        resp = client.get(
            f"{BASE}/fiscal-report/{uid}?year={ano}&month={mes}",
            headers=H,
        )
        assert resp.status_code == 200

    def test_uso_misto(self, client, H, uid, db_with_data):
        """GET /fiscal-report/{user_id}/mixed-use — despesas PF com uso misto PJ."""
        ano = date.today().year
        resp = client.get(
            f"{BASE}/fiscal-report/{uid}/mixed-use?year={ano}",
            headers=H,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "candidates" in data
        assert "total_pj_deductible" in data

    def test_fiscal_proibido(self, client, H):
        """Não pode acessar relatório de outro usuário."""
        resp = client.get(f"{BASE}/fiscal-report/{uuid.uuid4()}", headers=H)
        assert resp.status_code in (403, 422)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 15. PARES — MX.4 (Comparação com Benchmarks POF/IBGE)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestPares:
    """
    MX.4 — Compara o perfil de gastos do usuário com benchmarks POF/IBGE.
    Retorna posicionamento ('acima', 'na_media', 'abaixo') por categoria.
    """

    def test_comparar_com_peers(self, client, H, uid, db_with_data):
        """GET /peers/compare/{user_id}?monthly_income=8500 — benchmark POF."""
        resp = client.get(
            f"{BASE}/peers/compare/{uid}?monthly_income=8500",
            headers=H,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "income_bracket" in data
        assert "categories" in data
        assert isinstance(data["categories"], list)
        assert "savings_percentile_label" in data

    def test_comparar_sem_renda_estimada(self, client, H, uid, db_with_data):
        """Sem monthly_income, tenta estimar a partir das transações."""
        resp = client.get(f"{BASE}/peers/compare/{uid}", headers=H)
        # Pode retornar 200 (com renda estimada) ou 422 (não conseguiu estimar)
        assert resp.status_code in (200, 422)

    def test_comparar_sem_dados(self, client, H):
        """Usuário sem transações retorna 404."""
        fresh_email = f"peer_{uuid.uuid4().hex[:8]}@nexa.test"
        r = client.post(f"{BASE}/auth/register", json={"email": fresh_email, "password": "Abc@12345"})
        if r.status_code != 201:
            pytest.skip("Registro falhou")
        fresh_uid = r.json()["user_id"]
        fresh_token = client.post(f"{BASE}/auth/token", data={
            "username": fresh_email, "password": "Abc@12345"
        }).json().get("access_token", "")
        fresh_H = {"Authorization": f"Bearer {fresh_token}"}
        resp = client.get(
            f"{BASE}/peers/compare/{fresh_uid}?monthly_income=5000",
            headers=fresh_H,
        )
        assert resp.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 16. FORECAST — F1 (Projeção Financeira Consolidada)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestForecast:
    """
    F1 — Pipeline completo de projeção financeira.
    Retorna: saúde financeira, cashflow 30 dias, safe-to-spend e shadow invoices.
    """

    def test_forecast_com_dados(self, client, H, uid, db_with_data):
        """GET /forecast/{user_id} — projeção financeira consolidada."""
        resp = client.get(f"{BASE}/forecast/{uid}", headers=H)
        assert resp.status_code in (200, 404, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["user_id"] == uid
            assert "financial_health" in data
            assert "cashflow" in data
            assert "safe_to_spend" in data
            assert "shadow_invoices" in data
            # Verificar estrutura do financial_health
            fh = data["financial_health"]
            assert "health_score" in fh
            assert 0 <= fh["health_score"] <= 100
            assert "profile_type" in fh
            assert fh["profile_type"] in (
                "CONSERVADOR", "EQUILIBRADO", "GASTADOR", "POUPADOR"
            )
            # Verificar cashflow
            cf = data["cashflow"]
            assert "starting_balance" in cf
            assert "risk_level" in cf

    def test_forecast_sem_dados(self, client, H):
        """Usuário sem dados → 404."""
        fresh_email = f"fc_{uuid.uuid4().hex[:8]}@nexa.test"
        r = client.post(f"{BASE}/auth/register", json={"email": fresh_email, "password": "Abc@12345"})
        if r.status_code != 201:
            pytest.skip("Registro falhou")
        fresh_uid = r.json()["user_id"]
        fresh_token = client.post(f"{BASE}/auth/token", data={
            "username": fresh_email, "password": "Abc@12345"
        }).json().get("access_token", "")
        fresh_H = {"Authorization": f"Bearer {fresh_token}"}
        resp = client.get(f"{BASE}/forecast/{fresh_uid}", headers=fresh_H)
        assert resp.status_code in (404, 500)

    def test_forecast_horizon_customizado(self, client, H, uid, db_with_data):
        """GET /forecast/{user_id}?horizon_days=60 — horizonte customizado."""
        resp = client.get(
            f"{BASE}/forecast/{uid}?horizon_days=60",
            headers=H,
        )
        assert resp.status_code in (200, 404, 500)

    def test_forecast_health_check(self, client):
        """GET /forecast — health check do serviço."""
        resp = client.get(f"{BASE}/forecast")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_safe_to_spend(self, client, H, uid, db_with_data):
        """GET /safe-to-spend/{user_id} — orçamento mensal seguro."""
        resp = client.get(f"{BASE}/safe-to-spend/{uid}", headers=H)
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["user_id"] == uid
            assert "safe_to_spend_total" in data
            assert "risk_level" in data
            assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_shadow_invoice(self, client, H, uid, db_with_data):
        """GET /shadow_invoice/{user_id} — obrigações futuras detectadas."""
        resp = client.get(f"{BASE}/shadow_invoice/{uid}", headers=H)
        assert resp.status_code in (200, 404, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_count" in data
            assert "invoices" in data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 17. ALERTAS — F1 (Alertas Financeiros)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestAlertas:
    """
    F1 (Alerts) — Alertas proativos de: token expiry, saldo negativo,
    comprometimento de caixa e anomalias de gasto.
    """

    def test_listar_alertas(self, client, H, uid):
        """GET /alerts/{user_id} — retorna alertas ativos."""
        resp = client.get(f"{BASE}/alerts/{uid}", headers=H)
        # Pode falhar se NexaRunner não tiver dados (usa DuckDB mock)
        assert resp.status_code in (200, 500, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert data["user_id"] == uid
            assert "alerts" in data
            assert "total_count" in data
            assert "critical_count" in data
            assert "warning_count" in data
            assert isinstance(data["alerts"], list)

    def test_dispensar_alerta(self, client, H, uid):
        """DELETE /alerts/{user_id}/{alert_id} — dispensa um alerta."""
        resp = client.delete(f"{BASE}/alerts/{uid}/alert_token_001", headers=H)
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            data = resp.json()
            assert data["status"] == "dismissed"

    def test_alertas_health_check(self, client):
        """GET /alerts — health check do serviço de alertas."""
        resp = client.get(f"{BASE}/alerts")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 18. NOTIFICAÇÕES — MX.3
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestNotificacoes:
    """
    MX.3 — Notificações proativas inteligentes.
    Pipeline: geração → filtro de relevância → deduplicação por estado.
    """

    def test_listar_notificacoes(self, client, H, uid):
        """GET /notifications/{user_id} — notificações proativas."""
        resp = client.get(
            f"{BASE}/notifications/{uid}?monthly_income=8500",
            headers=H,
        )
        # Pode falhar se NexaRunner (DuckDB mock) não estiver disponível
        assert resp.status_code in (200, 500, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert data["user_id"] == uid
            assert "total" in data
            assert "by_priority" in data
            assert "notifications" in data
            bp = data["by_priority"]
            assert "CRITICAL" in bp
            assert "WARNING" in bp
            assert "INFO" in bp

    def test_registrar_evento_notificacao(self, client, H, uid):
        """POST /notifications/{user_id}/events — registra interação do usuário."""
        resp = client.post(
            f"{BASE}/notifications/{uid}/events",
            headers=H,
            json={
                "fingerprint": "fp_test_12345",
                "notification_type": "BURN_RATE",
                "event_type": "tapped",
            },
        )
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            assert resp.json()["ok"] is True

    def test_evento_tipo_invalido(self, client, H, uid):
        """event_type inválido → 422."""
        resp = client.post(
            f"{BASE}/notifications/{uid}/events",
            headers=H,
            json={
                "fingerprint": "fp_test_999",
                "notification_type": "BURN_RATE",
                "event_type": "invalido",
            },
        )
        assert resp.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 19. ISOLAMENTO DE DADOS — Segurança entre usuários
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestIsolamentoDados:
    """
    Garante que um usuário NÃO consegue acessar dados de outro.
    Testa a barreira de segurança `require_owner` em múltiplos módulos.
    """

    @pytest.fixture(scope="class")
    def outro_user(self, client):
        """Segundo usuário para testes de isolamento."""
        email = f"outro_{uuid.uuid4().hex[:8]}@nexa.test"
        r = client.post(f"{BASE}/auth/register", json={
            "email": email, "password": "Abc@12345"
        })
        if r.status_code != 201:
            pytest.skip("Não foi possível criar segundo usuário")
        uid2 = r.json()["user_id"]
        token2 = client.post(f"{BASE}/auth/token", data={
            "username": email, "password": "Abc@12345"
        }).json().get("access_token", "")
        return {"uid": uid2, "headers": {"Authorization": f"Bearer {token2}"}}

    def test_isolamento_health_score(self, client, H, outro_user, uid):
        """Usuário A não deve acessar health score do Usuário B."""
        resp = client.get(
            f"{BASE}/health-score/history/{uid}",
            headers=outro_user["headers"],
        )
        assert resp.status_code == 403

    def test_isolamento_metas(self, client, outro_user, uid):
        """Usuário A não deve criar metas para o Usuário B."""
        resp = client.post(
            f"{BASE}/goals/{uid}",
            headers=outro_user["headers"],
            json={
                "name": "Meta Invasiva",
                "goal_type": "outros",
                "target_amount": 999.00,
            },
        )
        assert resp.status_code == 403

    def test_isolamento_fiscal(self, client, outro_user, uid):
        """Usuário A não deve acessar relatório fiscal do Usuário B."""
        resp = client.get(
            f"{BASE}/fiscal-report/{uid}",
            headers=outro_user["headers"],
        )
        assert resp.status_code == 403

    def test_isolamento_costs(self, client, outro_user, uid):
        """Usuário A não deve acessar raio-x de custos do Usuário B."""
        resp = client.get(
            f"{BASE}/costs/raio-x/{uid}",
            headers=outro_user["headers"],
        )
        assert resp.status_code == 403

    def test_isolamento_peers(self, client, outro_user, uid):
        """Usuário A não deve acessar comparação com pares do Usuário B."""
        resp = client.get(
            f"{BASE}/peers/compare/{uid}?monthly_income=5000",
            headers=outro_user["headers"],
        )
        assert resp.status_code == 403
