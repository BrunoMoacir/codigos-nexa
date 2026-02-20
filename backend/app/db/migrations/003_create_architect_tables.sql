-- =============================================================================
-- 003_create_architect_tables.sql
--
-- DATA:    2026-02-20
-- AUTOR:   Nexa AI Agent
-- FEATURE: F3 - Nexa Architect
--
-- DESCRIÇÃO:
--   Cria as tabelas necessárias para persistência das simulações da F3.
--   O Nexa Architect compara 3 estratégias (Financiamento x Consórcio x Poupar)
--   e persiste o resultado completo para:
--     1. Histórico do usuário (consultar simulações passadas)
--     2. Dashboard de métricas (quantas simulações, estratégia favorita)
--     3. Auditoria e rastreabilidade de recomendações
--
-- DEPENDÊNCIAS:
--   Nenhuma (não referencia outras tabelas via FK para manter portabilidade
--   entre ambientes de desenvolvimento — o user_id é coordenado em nível
--   de aplicação).
--
-- BANCO:    DuckDB (finance.duckdb)
--
-- ROLLBACK (caso precise desfazer esta migration):
--   DROP TABLE IF EXISTS architect_simulation_metrics;
--   DROP TABLE IF EXISTS architect_simulations;
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA PRINCIPAL: architect_simulations
--
-- Uma linha por chamada a POST /api/v1/architect/simulate.
-- Armazena tanto os parâmetros de entrada (request_json) quanto o resultado
-- completo (response_json) para que a simulação possa ser reproduzida e
-- inspecionada sem recalcular.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS architect_simulations (

    -- ── Identificação ───────────────────────────────────────────────────────
    -- UUID v4 gerado pela aplicação Python (str(uuid.uuid4())).
    -- VARCHAR(36) é exato para UUIDs com hifens (ex: "550e8400-...").
    id VARCHAR(36) PRIMARY KEY,

    -- Usuário que solicitou a simulação.
    -- Deve coincidir com o user_id do Core Engine (F1).
    user_id VARCHAR(100) NOT NULL,

    -- Timestamp de quando a simulação foi executada (com fuso horário).
    -- DuckDB: TIMESTAMPTZ armazena em UTC internamente.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),


    -- ── Parâmetros de entrada (colunas indexáveis) ─────────────────────────
    -- Guardamos os campos mais relevantes como colunas próprias para permitir
    -- filtragem e agregação eficiente sem parsear o JSON.

    -- Valor da meta financeira (ex: R$ 100.000,00)
    target_amount DOUBLE NOT NULL,

    -- Tipo de bem: IMOVEL, VEICULO, REFORMA, VIAGEM, OUTRO
    -- VARCHAR(20) é suficiente para todos os valores do enum AssetType
    asset_type VARCHAR(20) NOT NULL,

    -- Tipo de amortização solicitado: PRICE ou SAC
    amortization_type VARCHAR(10),

    -- Prazo de financiamento em meses (se FINANCING foi simulado)
    financing_months INTEGER,

    -- Entrada/sinal dado pelo usuário (R$)
    down_payment DOUBLE,

    -- Orçamento mensal máximo informado pelo usuário (R$)
    max_monthly_budget DOUBLE,


    -- ── Resultado da simulação (colunas indexáveis) ────────────────────────
    -- Assim como os parâmetros, os campos mais consultados ficam em colunas
    -- para facilitar relatórios sem desserializar o JSON a cada query.

    -- Estratégia recomendada pelo motor: FINANCING, CONSORTIUM ou SAVE_INVEST
    recommended_strategy VARCHAR(20) NOT NULL,

    -- Score de confiança da recomendação [0.0, 1.0]
    -- 1.0 = dados completos e consistentes; < 0.5 = muitas incertezas
    confidence_score FLOAT NOT NULL,

    -- Impacto no fluxo de caixa mensal (valor negativo por convenção)
    -- Ex: -0.22 significa que a estratégia compromete 22% do safe_to_spend
    liquidity_impact FLOAT,

    -- Prazo calculado até ter o bem (em meses)
    months_to_achieve INTEGER,

    -- Custo total esperado da estratégia recomendada (R$)
    expected_cost DOUBLE,


    -- ── Payload completo (para auditoria e recálculo) ──────────────────────
    -- JSON serializado do SimulationRequest completo
    request_json TEXT NOT NULL,

    -- JSON serializado do SimulationResponse completo (inclui action_plan, NPV, etc.)
    response_json TEXT NOT NULL
);


-- ─────────────────────────────────────────────────────────────────────────────
-- ÍNDICES: architect_simulations
--
-- 1. Busca do histórico de simulações de um usuário (endpoint GET /simulations)
--    Ordenado por data DESC pois o usuário vê as mais recentes primeiro.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_arch_sim_user_date
    ON architect_simulations(user_id, created_at DESC);

-- 2. Filtro por tipo de bem (ex: "todas as simulações de imóvel deste usuário")
CREATE INDEX IF NOT EXISTS idx_arch_sim_user_asset
    ON architect_simulations(user_id, asset_type);


-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA DE MÉTRICAS: architect_simulation_metrics
--
-- Agregado por usuário — atualizado (UPSERT) a cada nova simulação.
-- Permite exibir um dashboard rápido sem precisar de GROUP BY a cada request:
--   - "Você já fez X simulações"
--   - "Sua estratégia mais recomendada é X"
--   - "Última simulação em X"
--
-- Uma linha por usuário (user_id é PK).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS architect_simulation_metrics (

    -- Chave primária: um registro por usuário
    user_id VARCHAR(100) PRIMARY KEY,

    -- Contador acumulado de simulações realizadas
    total_simulations INTEGER NOT NULL DEFAULT 0,

    -- Timestamp da última simulação (para exibir "X dias atrás")
    last_simulated_at TIMESTAMPTZ,

    -- Estratégia mais frequentemente recomendada pelo motor
    -- Calculado como MODE(recommended_strategy) sobre as últimas simulações
    favorite_strategy VARCHAR(20),

    -- Confiança média das últimas simulações (indicador de qualidade dos dados)
    avg_confidence_score FLOAT,

    -- Timestamp de quando este registro foi criado pela primeira vez
    first_simulated_at TIMESTAMPTZ
);
