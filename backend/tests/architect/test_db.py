"""
tests/architect/test_db.py - Testes de Persistência da F3

Feature: F3 - Nexa Architect
Version: 1.0.0

Estratégia de Testes:
    Todos os testes usam DuckDB em memória (':memory:') injetado via
    parâmetro `db_path`. Isso garante:
      - Isolamento total do banco de produção (finance.duckdb)
      - Cada teste começa com banco limpo (sem estado compartilhado)
      - Sem necessidade de cleanup manual após cada teste
      - Execução rápida (sem I/O de disco)

Fixtures:
    - in_memory_db(path): cria banco :memory:, executa a migration e
      retorna o path (":memory:") para ser passado como db_path nas funções.

Cobertura:
    - save_simulation: INSERT + retorno de UUID válido
    - get_simulation: SELECT por ID, campos e JSONs desserializados
    - get_user_simulations: listagem com limit e filtro por asset_type
    - get_user_latest_simulation: ordem DESC por created_at
    - update_simulation_metrics / get_user_metrics: contadores e agregados
    - _ensure_tables_exist: comportamento em banco sem tabelas
"""

import json
import pathlib
import uuid
from unittest.mock import MagicMock

import duckdb
import pytest

from app.db.queries.architect_queries import (
    _ensure_tables_exist,
    get_simulation,
    get_user_latest_simulation,
    get_user_metrics,
    get_user_simulations,
    save_simulation,
    update_simulation_metrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

# Caminho da migration — relativo ao diretório backend/
_MIGRATION_PATH = pathlib.Path(__file__).parent.parent.parent / (
    "app/db/migrations/003_create_architect_tables.sql"
)

# Constante usada nos testes para não repetir o db_path ":memory:"
IN_MEMORY = ":memory:"


def _make_db() -> str:
    """
    Cria um banco DuckDB in-memory, executa a migration e retorna ':memory:'.

    Problema: cada duckdb.connect(':memory:') abre uma NOVA instância vazia.
    Para testes, precisamos de uma instância compartilhada por teste.
    Solução: usamos um arquivo temporário único por teste via tmp_path fixture
    do pytest, ou usamos uma string de path única por session.

    Neste caso usamos um arquivo temporário por função de teste para garantir
    isolamento. A variável db_path retornada é passada para as funções.
    """
    # Lê a migration do arquivo real (garante que o SQL está correto)
    migration_sql = _MIGRATION_PATH.read_text(encoding="utf-8")

    # Cria banco em arquivo temporário único
    tmp_path = f"/tmp/test_architect_{uuid.uuid4().hex}.duckdb"

    con = duckdb.connect(tmp_path)
    try:
        con.execute(migration_sql)
    finally:
        con.close()

    return tmp_path


@pytest.fixture
def db_path(tmp_path):
    """
    Fixture que provisiona um banco DuckDB isolado para cada teste.

    Usa `tmp_path` do pytest (diretório temporário único por teste),
    o que garante que cada teste tem seu banco completamente limpo.
    A migration 003 é executada automaticamente antes do teste.
    """
    # Usar o diretório temporário do pytest (limpo automaticamente)
    db_file = str(tmp_path / "test_architect.duckdb")

    migration_sql = _MIGRATION_PATH.read_text(encoding="utf-8")

    con = duckdb.connect(db_file)
    try:
        con.execute(migration_sql)
    finally:
        con.close()

    return db_file


@pytest.fixture
def mock_request():
    """
    Mock de SimulationRequest com todos os campos necessários para persist.

    Usa MagicMock com atributos configurados para simular o objeto Pydantic
    sem precisar importar o modelo completo (mais rápido, mais isolado).
    Simula um request de financiamento de veículo de R$ 50.000.
    """
    req = MagicMock()
    req.target_amount = 50_000.0
    req.down_payment = 5_000.0
    req.max_monthly_budget = 2_000.0
    req.financing_months = 48

    # Enums simulados via MagicMock com .value
    req.asset_type.value = "VEICULO"
    req.amortization_type.value = "PRICE"

    # model_dump() retorna o dict que será serializado para JSON
    req.model_dump.return_value = {
        "user_id": "user_test",
        "target_amount": 50_000.0,
        "asset_type": "VEICULO",
        "amortization_type": "PRICE",
        "financing_months": 48,
        "down_payment": 5_000.0,
        "max_monthly_budget": 2_000.0,
    }
    return req


@pytest.fixture
def mock_response():
    """
    Mock de SimulationResponse com os campos de resultado.

    Simula uma recomendação de FINANCING com confidence_score de 0.80
    e custo esperado de R$ 63.000 (principal + juros simulados).
    """
    resp = MagicMock()
    resp.confidence_score = 0.80
    resp.liquidity_impact = -0.22
    resp.months_to_achieve = 1           # FINANCING: aquisição imediata
    resp.recommended_strategy.value = "FINANCING"

    # Custo esperado encapsulado em objeto costs
    resp.costs.expected_cost = 63_000.0

    # model_dump() retorna o dict que será serializado para JSON
    resp.model_dump.return_value = {
        "recommended_strategy": "FINANCING",
        "confidence_score": 0.80,
        "liquidity_impact": -0.22,
        "months_to_achieve": 1,
        "costs": {"expected_cost": 63_000.0, "min_cost": 60_000.0, "max_cost": 66_000.0},
        "action_plan": [{"step": 1, "action": "Assinar contrato"}],
    }
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# TESTES: _ensure_tables_exist
# ─────────────────────────────────────────────────────────────────────────────

class TestEnsureTablesExist:
    """Testa o guard interno que verifica se as tabelas existem."""

    def test_retorna_true_quando_tabelas_existem(self, db_path):
        """Banco com migration executada → True."""
        con = duckdb.connect(db_path)
        try:
            result = _ensure_tables_exist(con)
            assert result is True
        finally:
            con.close()

    def test_retorna_false_em_banco_sem_tabelas(self, tmp_path):
        """Banco vazio (sem migration) → False e não lança exceção."""
        empty_db = str(tmp_path / "empty.duckdb")
        con = duckdb.connect(empty_db)
        try:
            # Não executamos nenhuma migration — banco completamente vazio
            result = _ensure_tables_exist(con)
            assert result is False
        finally:
            con.close()


# ─────────────────────────────────────────────────────────────────────────────
# TESTES: save_simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveSimulation:
    """Testa a persistência de uma simulação."""

    def test_retorna_uuid_valido(self, db_path, mock_request, mock_response):
        """save_simulation deve retornar uma string UUID válida."""
        sim_id = save_simulation(
            user_id="user_test",
            request=mock_request,
            response=mock_response,
            db_path=db_path,
        )

        assert sim_id is not None
        assert isinstance(sim_id, str)
        # UUID v4 tem exatamente 36 caracteres (32 hex + 4 hifens)
        assert len(sim_id) == 36

    def test_persiste_no_banco(self, db_path, mock_request, mock_response):
        """Após save, um SELECT deve encontrar o registro."""
        sim_id = save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        # Verificar diretamente no banco (sem usar get_simulation)
        con = duckdb.connect(db_path)
        try:
            row = con.execute(
                "SELECT id, user_id FROM architect_simulations WHERE id = ?",
                [sim_id],
            ).fetchone()
        finally:
            con.close()

        assert row is not None
        assert row[0] == sim_id
        assert row[1] == "user_test"

    def test_campos_indexaveis_salvos_corretamente(self, db_path, mock_request, mock_response):
        """Os campos extraídos do response devem estar corretos na tabela."""
        sim_id = save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        con = duckdb.connect(db_path)
        try:
            row = con.execute(
                """
                SELECT target_amount, asset_type, recommended_strategy,
                       confidence_score, liquidity_impact
                FROM architect_simulations WHERE id = ?
                """,
                [sim_id],
            ).fetchone()
        finally:
            con.close()

        assert row[0] == 50_000.0           # target_amount
        assert row[1] == "VEICULO"          # asset_type
        assert row[2] == "FINANCING"        # recommended_strategy
        assert abs(row[3] - 0.80) < 0.001  # confidence_score
        assert abs(row[4] - (-0.22)) < 0.001  # liquidity_impact

    def test_json_request_salvo(self, db_path, mock_request, mock_response):
        """request_json deve ser JSON válido e conter os dados do request."""
        sim_id = save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        con = duckdb.connect(db_path)
        try:
            row = con.execute(
                "SELECT request_json FROM architect_simulations WHERE id = ?",
                [sim_id],
            ).fetchone()
        finally:
            con.close()

        # JSON deve ser válido e parseable
        parsed = json.loads(row[0])
        assert "target_amount" in parsed
        assert parsed["asset_type"] == "VEICULO"

    def test_retorna_none_em_banco_invalido(self, mock_request, mock_response):
        """Se o banco não tiver as tabelas, retorna None sem lançar exceção."""
        result = save_simulation(
            "user_test",
            mock_request,
            mock_response,
            db_path=":memory:",  # banco sem migration, tabelas não existem
        )
        # Deve retornar None graciosamente (não lançar exceção)
        assert result is None

    def test_atualiza_metricas_automaticamente(self, db_path, mock_request, mock_response):
        """save_simulation deve atualizar architect_simulation_metrics."""
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        con = duckdb.connect(db_path)
        try:
            row = con.execute(
                "SELECT total_simulations FROM architect_simulation_metrics WHERE user_id = ?",
                ["user_test"],
            ).fetchone()
        finally:
            con.close()

        assert row is not None
        assert row[0] == 1  # primeira simulação


# ─────────────────────────────────────────────────────────────────────────────
# TESTES: get_simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestGetSimulation:
    """Testa a recuperação de uma simulação por ID."""

    def test_recupera_simulacao_existente(self, db_path, mock_request, mock_response):
        """Dado um ID válido, deve retornar dict com todos os campos."""
        sim_id = save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        sim = get_simulation(sim_id, db_path=db_path)

        assert sim is not None
        assert sim["id"] == sim_id
        assert sim["user_id"] == "user_test"
        assert sim["recommended_strategy"] == "FINANCING"

    def test_retorna_response_desserializado(self, db_path, mock_request, mock_response):
        """O campo 'response' deve ser um dict Python (não string JSON)."""
        sim_id = save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        sim = get_simulation(sim_id, db_path=db_path)

        # Deve ser dict, não string
        assert isinstance(sim["response"], dict)
        assert "recommended_strategy" in sim["response"]

    def test_retorna_request_desserializado(self, db_path, mock_request, mock_response):
        """O campo 'request' deve ser um dict Python."""
        sim_id = save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        sim = get_simulation(sim_id, db_path=db_path)

        assert isinstance(sim["request"], dict)
        assert "target_amount" in sim["request"]

    def test_retorna_none_para_id_inexistente(self, db_path):
        """ID que não existe → None (não lança exceção)."""
        resultado = get_simulation(str(uuid.uuid4()), db_path=db_path)
        assert resultado is None


# ─────────────────────────────────────────────────────────────────────────────
# TESTES: get_user_simulations
# ─────────────────────────────────────────────────────────────────────────────

class TestGetUserSimulations:
    """Testa a listagem de simulações de um usuário."""

    def _save_n(self, n, db_path, request, response, user_id="user_test"):
        """Helper: salva N simulações para o usuário."""
        ids = []
        for _ in range(n):
            sim_id = save_simulation(user_id, request, response, db_path=db_path)
            ids.append(sim_id)
        return ids

    def test_retorna_lista_de_dicts(self, db_path, mock_request, mock_response):
        """Resultado deve ser lista de dicts."""
        self._save_n(3, db_path, mock_request, mock_response)
        sims = get_user_simulations("user_test", db_path=db_path)

        assert isinstance(sims, list)
        assert len(sims) == 3
        assert isinstance(sims[0], dict)

    def test_respita_limit(self, db_path, mock_request, mock_response):
        """limit=2 deve retornar no máximo 2 registros mesmo com 5 salvos."""
        self._save_n(5, db_path, mock_request, mock_response)
        sims = get_user_simulations("user_test", limit=2, db_path=db_path)

        assert len(sims) == 2

    def test_retorna_lista_vazia_para_usuario_sem_simulacoes(self, db_path):
        """Usuário sem simulações → lista vazia (não None)."""
        sims = get_user_simulations("usuario_novo", db_path=db_path)
        assert sims == []

    def test_nao_mistura_usuarios(self, db_path, mock_request, mock_response):
        """Simulações de user_A não devem aparecer na listagem de user_B."""
        save_simulation("user_A", mock_request, mock_response, db_path=db_path)
        save_simulation("user_B", mock_request, mock_response, db_path=db_path)

        sims_a = get_user_simulations("user_A", db_path=db_path)
        sims_b = get_user_simulations("user_B", db_path=db_path)

        assert len(sims_a) == 1
        assert len(sims_b) == 1

    def test_filtro_por_asset_type(self, db_path, mock_request, mock_response):
        """asset_type filter deve retornar apenas simulações do tipo correto."""
        # Salvar com VEICULO (padrão do mock_request)
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        # Filtrar por IMOVEL — não deve encontrar nenhum
        sims = get_user_simulations("user_test", asset_type="IMOVEL", db_path=db_path)
        assert sims == []

        # Filtrar por VEICULO — deve encontrar 1
        sims = get_user_simulations("user_test", asset_type="VEICULO", db_path=db_path)
        assert len(sims) == 1


# ─────────────────────────────────────────────────────────────────────────────
# TESTES: get_user_latest_simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestGetUserLatestSimulation:
    """Testa a recuperação da simulação mais recente."""

    def test_retorna_a_mais_recente(self, db_path, mock_request, mock_response):
        """Com 3 simulações, deve retornar a última (maior created_at)."""
        # Salvar 3 simulações em sequência
        id1 = save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        id2 = save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        id3 = save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        latest = get_user_latest_simulation("user_test", db_path=db_path)

        # A mais recente deve ser a última inserida
        assert latest is not None
        assert latest["id"] == id3

    def test_retorna_none_para_usuario_sem_historico(self, db_path):
        """Usuário que nunca simulou → None."""
        latest = get_user_latest_simulation("usuario_novo", db_path=db_path)
        assert latest is None

    def test_retorna_campos_completos(self, db_path, mock_request, mock_response):
        """A resposta deve incluir os JSONs desserializados."""
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        latest = get_user_latest_simulation("user_test", db_path=db_path)

        assert "request" in latest
        assert "response" in latest
        assert isinstance(latest["request"], dict)
        assert isinstance(latest["response"], dict)


# ─────────────────────────────────────────────────────────────────────────────
# TESTES: update_simulation_metrics / get_user_metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulationMetrics:
    """Testa o sistema de métricas agregadas por usuário."""

    def test_metricas_criadas_apos_primeira_simulacao(self, db_path, mock_request, mock_response):
        """Após salvar a primeira simulação, as métricas do usuário devem existir."""
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        metrics = get_user_metrics("user_test", db_path=db_path)

        assert metrics is not None
        assert metrics["user_id"] == "user_test"

    def test_contador_total_simulacoes(self, db_path, mock_request, mock_response):
        """total_simulations deve incrementar a cada save."""
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        metrics = get_user_metrics("user_test", db_path=db_path)
        assert metrics["total_simulations"] == 3

    def test_estrategia_favorita_correta(self, db_path, mock_request, mock_response):
        """favorite_strategy deve ser a mais frequente."""
        # Salvar 3x FINANCING (via mock padrão)
        for _ in range(3):
            save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        metrics = get_user_metrics("user_test", db_path=db_path)
        assert metrics["favorite_strategy"] == "FINANCING"

    def test_avg_confidence_score(self, db_path, mock_request, mock_response):
        """avg_confidence_score deve ser a média dos confidence_scores salvos."""
        # mock_response tem confidence_score = 0.80
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        metrics = get_user_metrics("user_test", db_path=db_path)
        # Média de 0.80 + 0.80 = 0.80
        assert abs(metrics["avg_confidence_score"] - 0.80) < 0.01

    def test_retorna_none_para_usuario_sem_simulacoes(self, db_path):
        """Usuário sem simulações → None (não cria linha vazia na tabela)."""
        metrics = get_user_metrics("usuario_sem_simulacoes", db_path=db_path)
        assert metrics is None

    def test_update_simulation_metrics_publico(self, db_path, mock_request, mock_response):
        """update_simulation_metrics (versão pública) deve retornar True."""
        save_simulation("user_test", mock_request, mock_response, db_path=db_path)

        resultado = update_simulation_metrics("user_test", db_path=db_path)
        assert resultado is True

    def test_update_metrics_sem_simulacoes_retorna_false(self, db_path):
        """Usuário sem simulações → update retorna False (não cria linha vazia)."""
        resultado = update_simulation_metrics("usuario_vazio", db_path=db_path)
        assert resultado is False
