-- ================================================================
-- SCRIPT 1: CRIAR USUARIO MOCK NO BANCO ONLINE (SUPABASE/POSTGRES)
-- ================================================================
-- Email: teste@nexa.com
-- Senha: teste123 (hash bcrypt abaixo)
-- Nome : Bruno Teste
-- ================================================================

DO $$
DECLARE
    v_user_id TEXT;
BEGIN
    SELECT user_id INTO v_user_id
      FROM users
     WHERE email = 'teste@nexa.com';

    IF v_user_id IS NOT NULL THEN
        DELETE FROM transactions_clean WHERE user_id = v_user_id;
        DELETE FROM financial_goals WHERE user_id = v_user_id;
        DELETE FROM architect_simulations WHERE user_id = v_user_id;
        DELETE FROM architect_simulation_metrics WHERE user_id = v_user_id;
        DELETE FROM optimization_reports WHERE user_id = v_user_id;
        DELETE FROM context_overrides WHERE user_id = v_user_id;
        DELETE FROM health_score_history WHERE user_id = v_user_id;
        DELETE FROM chat_messages WHERE user_id = v_user_id;
        DELETE FROM users WHERE user_id = v_user_id;

        RAISE NOTICE 'Usuario antigo removido: %', v_user_id;
    END IF;

    INSERT INTO users (
        user_id,
        email,
        hashed_password,
        full_name,
        created_at
    ) VALUES (
        gen_random_uuid()::text,
        'teste@nexa.com',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5RA0qTMqK3K9W',
        'Bruno Teste',
        NOW()
    );
END $$;

SELECT user_id, email, full_name, created_at
  FROM users
 WHERE email = 'teste@nexa.com';
