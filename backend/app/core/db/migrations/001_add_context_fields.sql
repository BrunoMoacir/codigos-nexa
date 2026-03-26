-- 001_add_context_fields.sql
-- 
-- DATA: 2026-02-15
-- AUTOR: Nexa AI Agent
-- DESCRIÇÃO: 
-- Adiciona colunas para suportar a Funcionalidade 4 (Nexa Divider).
-- Estas colunas armazenam a classificação PF/PJ (Pessoa Física / Jurídica)
-- e o nível de confiança dessa classificação.

-- 1. Adiciona coluna context_type (PF, PJ ou UNCERTAIN)
--    VARCHAR(20) é suficiente para os enums.
ALTER TABLE transactions_clean 
    ADD COLUMN context_type VARCHAR(20);

-- 2. Adiciona coluna context_confidence (0.0 a 1.0)
--    Armazena a certeza do modelo de ML.
ALTER TABLE transactions_clean 
    ADD COLUMN context_confidence FLOAT;

-- 3. Adiciona coluna context_override_by_user (Boolean)
--    Indica se esta classificação foi forçada manualmente pelo usuário.
--    Default FALSE pois a maioria será automática.
ALTER TABLE transactions_clean 
    ADD COLUMN context_override_by_user BOOLEAN DEFAULT FALSE;

-- 4. Adiciona Constraint de Verificação (Check Constraint)
--    Garante que apenas valores válidos sejam inseridos.
--    Nota: Em DuckDB/Postgres, verificar suporte a CHECK em ALTER TABLE.
--    Se falhar em bancos antigos, pode ser removido, mas é boa prática.
ALTER TABLE transactions_clean
    ADD CONSTRAINT chk_context_type
    CHECK (context_type IN ('PF', 'PJ', 'UNCERTAIN') OR context_type IS NULL);

-- 5. Criação de Índice para Performance
--    Acelera queries que filtram por tipo de contexto (ex: "quanto gastei como PJ?")
--    Ordenação por data DESC pois o usuário geralmente vê o mais recente.
CREATE INDEX idx_transactions_context 
    ON transactions_clean(account_id, context_type, transaction_date DESC);
