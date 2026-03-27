-- ================================================================
-- SCRIPT 1: CRIAR USUÁRIO MOCK NO BANCO RAILWAY
-- ================================================================
-- Email: teste@nexa.com
-- Senha: teste123 (hash bcrypt já incluído)
-- Nome: Bruno Teste
-- ================================================================

-- Limpar dados antigos (se existir)
DO $$
DECLARE
    v_user_id UUID;
BEGIN
    -- Buscar user_id do usuário teste
    SELECT user_id INTO v_user_id
    FROM users
    WHERE email = 'teste@nexa.com';

    IF v_user_id IS NOT NULL THEN
        -- Deletar transações
        DELETE FROM transactions WHERE user_id = v_user_id;

        -- Deletar metas
        DELETE FROM goals WHERE user_id = v_user_id;

        -- Deletar contas
        DELETE FROM accounts WHERE user_id = v_user_id;

        -- Deletar simulações do Architect
        DELETE FROM architect_simulations WHERE user_id = v_user_id;

        -- Deletar outras tabelas relacionadas
        DELETE FROM pluggy_items WHERE user_id = v_user_id;

        -- Deletar usuário
        DELETE FROM users WHERE user_id = v_user_id;

        RAISE NOTICE 'Usuário antigo removido: %', v_user_id;
    END IF;
END $$;

-- Criar novo usuário
INSERT INTO users (
    user_id,
    email,
    hashed_password,
    full_name,
    is_active,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'teste@nexa.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5RA0qTMqK3K9W', -- Hash de "teste123"
    'Bruno Teste',
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
) RETURNING user_id, email, full_name;

-- Criar conta bancária para o usuário
INSERT INTO accounts (
    account_id,
    user_id,
    name,
    type,
    balance,
    currency,
    institution,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    user_id,
    'Conta Corrente Nubank',
    'CONTA_CORRENTE',
    12500.00,
    'BRL',
    'Nubank',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM users
WHERE email = 'teste@nexa.com';

-- Verificar criação
SELECT
    u.user_id,
    u.email,
    u.full_name,
    u.is_active,
    a.account_id,
    a.name as account_name,
    a.balance
FROM users u
LEFT JOIN accounts a ON a.user_id = u.user_id
WHERE u.email = 'teste@nexa.com';
