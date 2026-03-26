-- =============================================================================
-- 004_create_health_score_history.sql
--
-- DATA:    2026-03-03
-- FEATURE: MX.1 - Score Financeiro com Evolução Temporal
--
-- DESCRIÇÃO:
--   Persiste o health_score do usuário a cada análise, permitindo exibir
--   a evolução temporal (gráfico de linha + tendência IMPROVING/STABLE/DECLINING).
--
-- BANCO:    DuckDB (finance.duckdb)
--
-- ROLLBACK:
--   DROP TABLE IF EXISTS health_score_history;
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- TABELA: health_score_history
--
-- Uma linha por (user_id, mês). Se a análise for rodada mais de uma vez
-- no mesmo mês, o INSERT OR REPLACE atualiza o registro existente.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS health_score_history (

    -- Identificação do usuário (mesmo user_id do Core Engine)
    user_id      VARCHAR NOT NULL,

    -- Mês de referência no formato 'YYYY-MM' (ex: '2026-03').
    -- Granularidade mensal: uma leitura por mês por usuário.
    date         VARCHAR NOT NULL,

    -- Score de saúde financeira [0-100] calculado pelo UserProfileAnalyzer
    health_score INTEGER NOT NULL,

    -- Taxa de poupança (%) usada para calcular o score
    savings_rate DOUBLE,

    -- Tipo de perfil: CONSERVADOR | EQUILIBRADO | GASTADOR
    profile_type VARCHAR,

    -- Safe-to-spend diário (R$) calculado pelo CashflowEngine (opcional)
    safe_to_spend DOUBLE,

    -- Timestamp de quando este snapshot foi gerado
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Chave primária composta: uma linha por usuário por mês
    PRIMARY KEY (user_id, date)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- ÍNDICE: leitura rápida do histórico de um usuário ordenado por data
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_health_score_history_user_date
    ON health_score_history(user_id, date DESC);
