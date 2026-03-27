-- ================================================================
-- SCRIPT COMPLETO: CRIAR TUDO DE UMA VEZ
-- ================================================================
-- Executa: Usuário + Transações + Metas
-- Tempo estimado: 10-30 segundos
-- ================================================================

-- ========================================
-- PARTE 1: CRIAR USUÁRIO E CONTA
-- ========================================
DO $$
DECLARE
    v_user_id UUID;
BEGIN
    -- Limpar dados antigos
    SELECT user_id INTO v_user_id FROM users WHERE email = 'teste@nexa.com';
    IF v_user_id IS NOT NULL THEN
        DELETE FROM transactions WHERE user_id = v_user_id;
        DELETE FROM goals WHERE user_id = v_user_id;
        DELETE FROM accounts WHERE user_id = v_user_id;
        DELETE FROM architect_simulations WHERE user_id = v_user_id;
        DELETE FROM pluggy_items WHERE user_id = v_user_id;
        DELETE FROM users WHERE user_id = v_user_id;
        RAISE NOTICE '🗑️  Dados antigos removidos';
    END IF;

    -- Criar usuário
    INSERT INTO users (user_id, email, hashed_password, full_name, is_active, created_at, updated_at)
    VALUES (
        gen_random_uuid(),
        'teste@nexa.com',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5RA0qTMqK3K9W',
        'Bruno Teste',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    );

    -- Criar conta bancária
    INSERT INTO accounts (account_id, user_id, name, type, balance, currency, institution, created_at, updated_at)
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
    FROM users WHERE email = 'teste@nexa.com';

    RAISE NOTICE '✅ Usuário e conta criados';
END $$;

-- ========================================
-- PARTE 2: CRIAR TRANSAÇÕES
-- ========================================
DO $$
DECLARE
    v_user_id UUID;
    v_account_id UUID;
    v_date DATE;
    v_month_offset INT;
    v_day_offset INT;
    v_category TEXT;
    v_amount DECIMAL(15, 2);
    v_description TEXT;
    v_merchant TEXT;
    v_count INT := 0;
BEGIN
    SELECT u.user_id, a.account_id INTO v_user_id, v_account_id
    FROM users u JOIN accounts a ON a.user_id = u.user_id
    WHERE u.email = 'teste@nexa.com' LIMIT 1;

    RAISE NOTICE '💰 Criando transações...';

    -- Salários (6 meses)
    FOR v_month_offset IN 0..5 LOOP
        v_date := DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' * v_month_offset + INTERVAL '4 days';
        INSERT INTO transactions (transaction_id, user_id, account_id, description, amount, date, category, type, merchant, created_at, updated_at)
        VALUES (gen_random_uuid(), v_user_id, v_account_id, 'Salário - Empresa XYZ S.A.', 8500.00, v_date, 'Salário', 'CREDIT', 'Empresa XYZ', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        v_count := v_count + 1;

        -- Freelance (40% chance)
        IF RANDOM() < 0.4 THEN
            INSERT INTO transactions VALUES (gen_random_uuid(), v_user_id, v_account_id, 'Freelance - Projeto Web', 500 + (RANDOM() * 2500)::DECIMAL(10, 2),
                v_date + INTERVAL '10 days', 'Freelance', 'CREDIT', 'Cliente', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            v_count := v_count + 1;
        END IF;
    END LOOP;

    -- Assinaturas (6 meses x 4 serviços)
    FOR v_month_offset IN 0..5 LOOP
        v_date := DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' * v_month_offset;
        INSERT INTO transactions VALUES
            (gen_random_uuid(), v_user_id, v_account_id, 'Netflix', -29.90, v_date + 1, 'Assinaturas', 'DEBIT', 'Netflix', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'Spotify', -21.90, v_date + 4, 'Assinaturas', 'DEBIT', 'Spotify', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'Amazon Prime', -19.90, v_date + 7, 'Assinaturas', 'DEBIT', 'Amazon', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'iCloud 200GB', -9.90, v_date + 10, 'Assinaturas', 'DEBIT', 'Apple', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        v_count := v_count + 4;
    END LOOP;

    -- Contas fixas (6 meses)
    FOR v_month_offset IN 0..5 LOOP
        v_date := DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' * v_month_offset;
        INSERT INTO transactions VALUES
            (gen_random_uuid(), v_user_id, v_account_id, 'Aluguel', -2200.00, v_date + 1, 'Moradia', 'DEBIT', 'Imobiliária', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'Condomínio', -580.00, v_date + 5, 'Moradia', 'DEBIT', 'Condomínio', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'Luz - Enel', -(120 + RANDOM() * 80)::DECIMAL(10,2), v_date + 8, 'Contas', 'DEBIT', 'Enel', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'Água - Sabesp', -(60 + RANDOM() * 40)::DECIMAL(10,2), v_date + 10, 'Contas', 'DEBIT', 'Sabesp', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'Internet Vivo', -119.90, v_date + 15, 'Contas', 'DEBIT', 'Vivo', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), v_user_id, v_account_id, 'Celular Tim', -89.90, v_date + 18, 'Contas', 'DEBIT', 'TIM', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        v_count := v_count + 6;
    END LOOP;

    -- Despesas diárias (180 dias)
    FOR v_day_offset IN 0..179 LOOP
        v_date := CURRENT_DATE - v_day_offset;

        FOR i IN 1..(CASE WHEN EXTRACT(DOW FROM v_date) IN (0,6) THEN 2 ELSE 5 END) LOOP
            CASE (RANDOM() * 9)::INT
                WHEN 0 THEN v_category := 'Alimentação'; v_description := 'Mercado Extra'; v_amount := -(20 + RANDOM() * 130);
                WHEN 1 THEN v_category := 'Transporte'; v_description := 'Uber'; v_amount := -(15 + RANDOM() * 65);
                WHEN 2 THEN v_category := 'Restaurante'; v_description := 'McDonald''s'; v_amount := -(25 + RANDOM() * 155);
                WHEN 3 THEN v_category := 'Mercado'; v_description := 'Carrefour'; v_amount := -(100 + RANDOM() * 500);
                WHEN 4 THEN v_category := 'Farmácia'; v_description := 'Drogasil'; v_amount := -(20 + RANDOM() * 160);
                WHEN 5 THEN v_category := 'Lazer'; v_description := 'Cinema'; v_amount := -(40 + RANDOM() * 260);
                WHEN 6 THEN v_category := 'Vestuário'; v_description := 'Zara'; v_amount := -(50 + RANDOM() * 350);
                WHEN 7 THEN v_category := 'Shopping'; v_description := 'Magazine Luiza'; v_amount := -(80 + RANDOM() * 420);
                ELSE v_category := 'Outros'; v_description := 'Compra Diversos'; v_amount := -(20 + RANDOM() * 180);
            END CASE;

            v_merchant := SPLIT_PART(v_description, ' - ', 1);
            INSERT INTO transactions VALUES (gen_random_uuid(), v_user_id, v_account_id, v_description, v_amount::DECIMAL(10,2),
                v_date, v_category, 'DEBIT', v_merchant, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            v_count := v_count + 1;
        END LOOP;
    END LOOP;

    -- Investimentos
    FOR v_month_offset IN 0..5 LOOP
        IF RANDOM() < 0.6 THEN
            v_date := DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' * v_month_offset + (RANDOM() * 28)::INT;
            INSERT INTO transactions VALUES (gen_random_uuid(), v_user_id, v_account_id, 'Dividendos - ITSA4',
                (100 + RANDOM() * 700)::DECIMAL(10,2), v_date, 'Investimentos', 'CREDIT', 'XP Investimentos', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            v_count := v_count + 1;
        END IF;
    END LOOP;

    RAISE NOTICE '✅ % transações criadas', v_count;
END $$;

-- ========================================
-- PARTE 3: CRIAR METAS
-- ========================================
DO $$
DECLARE
    v_user_id UUID;
BEGIN
    SELECT user_id INTO v_user_id FROM users WHERE email = 'teste@nexa.com';

    INSERT INTO goals (goal_id, user_id, title, target_amount, current_amount, deadline, status, created_at, updated_at) VALUES
        (gen_random_uuid(), v_user_id, 'Viagem para Europa', 15000.00, 8500.00, CURRENT_DATE + 180, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        (gen_random_uuid(), v_user_id, 'Fundo de Emergência', 30000.00, 22000.00, CURRENT_DATE + 365, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        (gen_random_uuid(), v_user_id, 'Comprar Carro Novo', 60000.00, 15000.00, CURRENT_DATE + 730, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        (gen_random_uuid(), v_user_id, 'Curso de Inglês', 5000.00, 5000.00, CURRENT_DATE - 30, 'completed', CURRENT_TIMESTAMP - INTERVAL '7 months', CURRENT_TIMESTAMP - INTERVAL '1 month'),
        (gen_random_uuid(), v_user_id, 'Setup Home Office', 8000.00, 2300.00, CURRENT_DATE + 120, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

    RAISE NOTICE '✅ 5 metas criadas';
END $$;

-- ========================================
-- RESUMO FINAL
-- ========================================
SELECT
    '🎉 CRIAÇÃO CONCLUÍDA!' as status,
    u.email,
    u.full_name,
    COUNT(DISTINCT t.transaction_id) as total_transacoes,
    COUNT(DISTINCT g.goal_id) as total_metas,
    SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) as receitas,
    SUM(CASE WHEN t.amount < 0 THEN t.amount ELSE 0 END) as despesas
FROM users u
LEFT JOIN transactions t ON t.user_id = u.user_id
LEFT JOIN goals g ON g.user_id = u.user_id
WHERE u.email = 'teste@nexa.com'
GROUP BY u.user_id, u.email, u.full_name;
