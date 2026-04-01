-- ================================================================
-- SCRIPT 3: CRIAR METAS E DADOS COMPLEMENTARES
-- ================================================================
-- Cria metas financeiras + amostras de architect/chat para auditoria.
-- ================================================================

DO $$
DECLARE
    v_user_id TEXT;
BEGIN
    -- Buscar user_id
    SELECT user_id INTO v_user_id
    FROM users
    WHERE email = 'teste@nexa.com';

    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Usuário teste@nexa.com não encontrado!';
    END IF;

    DELETE FROM financial_goals WHERE user_id = v_user_id;
    DELETE FROM architect_simulations WHERE user_id = v_user_id;
    DELETE FROM architect_simulation_metrics WHERE user_id = v_user_id;
    DELETE FROM optimization_reports WHERE user_id = v_user_id;
    DELETE FROM chat_messages WHERE user_id = v_user_id;

    -- ========================================
    -- 1) METAS FINANCEIRAS
    -- ========================================

    -- Meta 1: Viagem Europa (em progresso)
    INSERT INTO financial_goals (
        goal_id, user_id, name, goal_type, target_amount, current_amount,
        target_date, monthly_contribution_needed, monthly_contribution_actual,
        status, created_at, updated_at
    ) VALUES (
        gen_random_uuid()::text, v_user_id,
        'Viagem para Europa',
        'travel',
        15000.00,
        8500.00,
        (CURRENT_DATE + INTERVAL '6 months')::date::text,
        1083.33,
        950.00,
        'active',
        NOW()::text,
        NOW()::text
    );

    -- Meta 2: Fundo de Emergência (em progresso)
    INSERT INTO financial_goals (
        goal_id, user_id, name, goal_type, target_amount, current_amount,
        target_date, monthly_contribution_needed, monthly_contribution_actual,
        status, created_at, updated_at
    ) VALUES (
        gen_random_uuid()::text, v_user_id,
        'Fundo de Emergência',
        'emergency',
        30000.00,
        22000.00,
        (CURRENT_DATE + INTERVAL '12 months')::date::text,
        666.67,
        700.00,
        'active',
        NOW()::text,
        NOW()::text
    );

    -- Meta 3: Comprar Carro (em progresso)
    INSERT INTO financial_goals (
        goal_id, user_id, name, goal_type, target_amount, current_amount,
        target_date, monthly_contribution_needed, monthly_contribution_actual,
        status, created_at, updated_at
    ) VALUES (
        gen_random_uuid()::text, v_user_id,
        'Comprar Carro Novo',
        'vehicle',
        60000.00,
        15000.00,
        (CURRENT_DATE + INTERVAL '24 months')::date::text,
        1875.00,
        1200.00,
        'active',
        NOW()::text,
        NOW()::text
    );

    -- Meta 4: Curso de Inglês (concluída)
    INSERT INTO financial_goals (
        goal_id, user_id, name, goal_type, target_amount, current_amount,
        target_date, monthly_contribution_needed, monthly_contribution_actual,
        status, created_at, updated_at
    ) VALUES (
        gen_random_uuid()::text, v_user_id,
        'Curso de Inglês Avançado',
        'education',
        5000.00,
        5000.00,
        (CURRENT_DATE - INTERVAL '1 month')::date::text,
        0,
        0,
        'completed',
        (NOW() - INTERVAL '7 months')::text,
        (NOW() - INTERVAL '1 month')::text
    );

    -- Meta 5: Setup Home Office (nova)
    INSERT INTO financial_goals (
        goal_id, user_id, name, goal_type, target_amount, current_amount,
        target_date, monthly_contribution_needed, monthly_contribution_actual,
        status, created_at, updated_at
    ) VALUES (
        gen_random_uuid()::text, v_user_id,
        'Setup Home Office Completo',
        'asset',
        8000.00,
        2300.00,
        (CURRENT_DATE + INTERVAL '4 months')::date::text,
        1425.00,
        900.00,
        'active',
        NOW()::text,
        NOW()::text
    );

    -- ========================================
    -- 2) SIMULACOES ARCHITECT
    -- ========================================
    INSERT INTO architect_simulations (
        id, user_id, created_at, target_amount, asset_type, amortization_type,
        financing_months, down_payment, max_monthly_budget, recommended_strategy,
        confidence_score, liquidity_impact, months_to_achieve, expected_cost,
        request_json, response_json
    ) VALUES
    (
        gen_random_uuid()::text, v_user_id, NOW() - INTERVAL '2 days',
        85000, 'car', 'PRICE',
        48, 15000, 2200, 'financing',
        0.81, -0.18, 48, 102000,
        '{"asset_type":"car","target_amount":85000,"financing_months":48}',
        '{"winner":"financing","npv":-102000,"confidence":0.81}'
    ),
    (
        gen_random_uuid()::text, v_user_id, NOW() - INTERVAL '1 day',
        420000, 'real_estate', 'SAC',
        240, 80000, 3800, 'consortium',
        0.74, -0.31, 240, 590000,
        '{"asset_type":"real_estate","target_amount":420000,"financing_months":240}',
        '{"winner":"consortium","npv":-575000,"confidence":0.74}'
    );

    INSERT INTO architect_simulation_metrics (
        user_id, total_simulations, last_simulated_at,
        favorite_strategy, avg_confidence_score, first_simulated_at
    ) VALUES (
        v_user_id, 2, NOW() - INTERVAL '1 day',
        'financing', 0.775, NOW() - INTERVAL '2 days'
    );

    -- ========================================
    -- 3) CHAT (TRILHA DE AUDITORIA)
    -- ========================================
    INSERT INTO chat_messages (user_id, role, content, created_at) VALUES
    (v_user_id, 'user', 'Como esta meu safe-to-spend hoje?', NOW() - INTERVAL '5 hours'),
    (v_user_id, 'assistant', 'Analisei seu fluxo de caixa e sua margem de seguranca.', NOW() - INTERVAL '5 hours' + INTERVAL '4 seconds'),
    (v_user_id, 'user', 'Posso comprar um notebook de 9 mil em 10x?', NOW() - INTERVAL '2 hours'),
    (v_user_id, 'assistant', 'Com base na projeção, a compra cabe com ajuste de lazer.', NOW() - INTERVAL '2 hours' + INTERVAL '5 seconds');

    RAISE NOTICE 'Dados complementares criados (metas + architect + chat).';

END $$;

-- Verificar metas criadas
SELECT
    g.name,
    g.target_amount,
    g.current_amount,
    ROUND((g.current_amount / g.target_amount * 100)::NUMERIC, 1) as progress_pct,
    g.target_date,
    g.status,
    CASE
        WHEN g.target_date::date < CURRENT_DATE AND g.status = 'active' THEN 'ATRASADA'
        WHEN g.target_date::date - CURRENT_DATE <= 30 AND g.status = 'active' THEN 'URGENTE'
        ELSE 'OK'
    END as urgency
FROM financial_goals g
JOIN users u ON u.user_id = g.user_id
WHERE u.email = 'teste@nexa.com'
ORDER BY g.target_date::date ASC;

SELECT COUNT(*) AS qtd_simulacoes
FROM architect_simulations s
JOIN users u ON u.user_id = s.user_id
WHERE u.email = 'teste@nexa.com';

SELECT COUNT(*) AS qtd_msgs_chat
FROM chat_messages c
JOIN users u ON u.user_id = c.user_id
WHERE u.email = 'teste@nexa.com';
