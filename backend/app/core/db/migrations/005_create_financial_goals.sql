-- =============================================================================
-- 005_create_financial_goals.sql
--
-- DATA:    2026-03-03
-- FEATURE: MX.2 - Sistema de Metas Financeiras
--
-- DESCRIÇÃO:
--   Persiste metas financeiras do usuário (ex: entrada do apartamento, viagem)
--   e seu progresso ao longo do tempo.
--
-- BANCO:    DuckDB (finance.duckdb)
--
-- ROLLBACK:
--   DROP TABLE IF EXISTS financial_goals;
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA: financial_goals
--
-- Uma linha por meta. Status: ACTIVE | COMPLETED | ABANDONED
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS financial_goals (

    -- Identificador único da meta (UUID v4 gerado pela aplicação)
    goal_id                    VARCHAR PRIMARY KEY,

    -- Dono da meta (mesmo user_id do Core Engine)
    user_id                    VARCHAR NOT NULL,

    -- Nome amigável dado pelo usuário
    name                       VARCHAR NOT NULL,

    -- Tipo opcional para integração com F2/F3 (ex: "imovel", "viagem", "carro")
    goal_type                  VARCHAR DEFAULT 'outros',

    -- Valor alvo em R$
    target_amount              DOUBLE NOT NULL,

    -- Valor já acumulado em R$ (atualizado manualmente ou via update_progress)
    current_amount             DOUBLE DEFAULT 0.0,

    -- Data alvo no formato 'YYYY-MM-DD' (NULL = sem prazo)
    target_date                VARCHAR,

    -- Contribuição mensal necessária (calculada automaticamente)
    monthly_contribution_needed DOUBLE,

    -- Contribuição mensal atual detectada nas transações (opcional)
    monthly_contribution_actual DOUBLE,

    -- Status: ACTIVE | COMPLETED | ABANDONED
    status                     VARCHAR DEFAULT 'ACTIVE',

    -- Timestamp de criação
    created_at                 VARCHAR NOT NULL,

    -- Última vez que o progresso foi atualizado
    updated_at                 VARCHAR NOT NULL
);


-- ─────────────────────────────────────────────────────────────────────────────
-- ÍNDICE: listagem rápida das metas ativas de um usuário
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_financial_goals_user_status
    ON financial_goals(user_id, status);
