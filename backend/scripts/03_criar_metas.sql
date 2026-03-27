-- ================================================================
-- SCRIPT 3: CRIAR METAS E DADOS COMPLEMENTARES
-- ================================================================
-- Cria metas financeiras, simulações do Architect, etc.
-- ================================================================

DO $$
DECLARE
    v_user_id UUID;
BEGIN
    -- Buscar user_id
    SELECT user_id INTO v_user_id
    FROM users
    WHERE email = 'teste@nexa.com';

    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Usuário teste@nexa.com não encontrado!';
    END IF;

    -- ========================================
    -- 1. CRIAR METAS FINANCEIRAS
    -- ========================================

    -- Meta 1: Viagem Europa (em progresso)
    INSERT INTO goals (
        goal_id, user_id, title, target_amount, current_amount,
        deadline, status, created_at, updated_at
    ) VALUES (
        gen_random_uuid(), v_user_id,
        'Viagem para Europa',
        15000.00,
        8500.00,
        CURRENT_DATE + INTERVAL '6 months',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    );

    -- Meta 2: Fundo de Emergência (em progresso)
    INSERT INTO goals (
        goal_id, user_id, title, target_amount, current_amount,
        deadline, status, created_at, updated_at
    ) VALUES (
        gen_random_uuid(), v_user_id,
        'Fundo de Emergência',
        30000.00,
        22000.00,
        CURRENT_DATE + INTERVAL '12 months',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    );

    -- Meta 3: Comprar Carro (em progresso)
    INSERT INTO goals (
        goal_id, user_id, title, target_amount, current_amount,
        deadline, status, created_at, updated_at
    ) VALUES (
        gen_random_uuid(), v_user_id,
        'Comprar Carro Novo',
        60000.00,
        15000.00,
        CURRENT_DATE + INTERVAL '24 months',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    );

    -- Meta 4: Curso de Inglês (concluída)
    INSERT INTO goals (
        goal_id, user_id, title, target_amount, current_amount,
        deadline, status, created_at, updated_at
    ) VALUES (
        gen_random_uuid(), v_user_id,
        'Curso de Inglês Avançado',
        5000.00,
        5000.00,
        CURRENT_DATE - INTERVAL '1 month',
        'completed',
        CURRENT_TIMESTAMP - INTERVAL '7 months',
        CURRENT_TIMESTAMP - INTERVAL '1 month'
    );

    -- Meta 5: Setup Home Office (nova)
    INSERT INTO goals (
        goal_id, user_id, title, target_amount, current_amount,
        deadline, status, created_at, updated_at
    ) VALUES (
        gen_random_uuid(), v_user_id,
        'Setup Home Office Completo',
        8000.00,
        2300.00,
        CURRENT_DATE + INTERVAL '4 months',
        'active',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    );

    RAISE NOTICE '✅ 5 metas criadas com sucesso!';

END $$;

-- Verificar metas criadas
SELECT
    g.title,
    g.target_amount,
    g.current_amount,
    ROUND((g.current_amount / g.target_amount * 100)::NUMERIC, 1) as progress_pct,
    g.deadline,
    g.status,
    CASE
        WHEN g.deadline < CURRENT_DATE AND g.status = 'active' THEN 'ATRASADA'
        WHEN g.deadline - CURRENT_DATE <= INTERVAL '30 days' AND g.status = 'active' THEN 'URGENTE'
        ELSE 'OK'
    END as urgency
FROM goals g
JOIN users u ON u.user_id = g.user_id
WHERE u.email = 'teste@nexa.com'
ORDER BY g.deadline ASC;
