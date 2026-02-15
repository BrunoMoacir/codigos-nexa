-- 002_create_context_overrides.sql
--
-- DATA: 2026-02-15
-- AUTOR: Nexa AI Agent
-- DESCRIÇÃO:
-- Cria a tabela `context_overrides` para armazenar as correções manuais do usuário.
-- Funcionalidade 4 - Nexa Divider.

-- Criação da tabela de Overrides
-- Armazena o histórico de correções para:
-- 1. Aplicar em tempo real no ETL
-- 2. Servir de dados de treino (Active Learning) para o modelo ML futuro
CREATE TABLE context_overrides (
    -- ID único do override (UUID v4)
    -- Nota: gen_random_uuid() é Postgres. Em DuckDB use uuid().
    -- O código da aplicação deve tratar diferenças de dialeto se necessário.
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Referência à transação original
    -- VARCHAR(255) para garantir compatibilidade com IDs de transação externos
    transaction_id VARCHAR(255) NOT NULL,

    -- Usuário dono da transação (Partition Key em sistemas distribuídos)
    user_id VARCHAR(100) NOT NULL,

    -- O que o sistema achava que era (para métricas de erro)
    original_context VARCHAR(20),

    -- O que o usuário diz que é (A Verdade)
    corrected_context VARCHAR(20) NOT NULL,

    -- Motivo opcional (ex: "Era almoço de negócios")
    reason TEXT,

    -- Auditoria: quando a correção foi feita
    -- TIMESTAMPTZ garante fuso horário correto
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign Key para garantir integridade
    -- Se a transação sumir, o override também deve sumir (CASCADE)
    CONSTRAINT fk_transaction 
        FOREIGN KEY (transaction_id)
        REFERENCES transactions_clean(transaction_id) 
        ON DELETE CASCADE
);

-- Índices para Performance

-- 1. Busca rápida de overrides por usuário (para o endpoint GET /overrides)
CREATE INDEX idx_context_overrides_user 
    ON context_overrides(user_id, created_at DESC);

-- 2. Busca rápida por transação (para o ETL aplicar o override)
CREATE INDEX idx_context_overrides_txn 
    ON context_overrides(transaction_id);
