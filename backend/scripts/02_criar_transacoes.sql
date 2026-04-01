-- ================================================================
-- SCRIPT 2: CRIAR TRANSACOES RICAS PARA COBRIR PROCESSAMENTO
-- ================================================================
-- Gera base ampla para forecast, health score, optimizer, fiscal e alertas.
-- ================================================================

DO $$
DECLARE
	v_user_id TEXT;
BEGIN
	SELECT user_id INTO v_user_id
	  FROM users
	 WHERE email = 'teste@nexa.com';

	IF v_user_id IS NULL THEN
		RAISE EXCEPTION 'Usuario teste@nexa.com nao encontrado. Rode 01_criar_usuario.sql primeiro.';
	END IF;

	DELETE FROM transactions_clean WHERE user_id = v_user_id;

	-- 1) Salarios mensais (6 meses)
	INSERT INTO transactions_clean (
		transaction_id,
		user_id,
		account_id,
		description,
		amount,
		date,
		transaction_type,
		category,
		is_recurring,
		is_installment,
		context_type,
		context_confidence,
		context_override_by_user,
		pj_subcategory,
		processed_at
	)
	SELECT
		md5(v_user_id || ':salary:' || gs::text || ':' || clock_timestamp()::text),
		v_user_id,
		'acc_mock_main',
		'Salario - Empresa Alpha Tech',
		9800.00,
		(date_trunc('month', CURRENT_DATE) - (gs || ' months')::interval + interval '4 days')::date,
		'CREDIT',
		'Salario',
		true,
		false,
		'PF',
		0.99,
		false,
		NULL,
		NOW()
	FROM generate_series(0, 5) AS gs;

	-- 2) Receitas extras (freelas/dividendos)
	INSERT INTO transactions_clean (
		transaction_id, user_id, account_id, description, amount, date,
		transaction_type, category, is_recurring, is_installment,
		context_type, context_confidence, context_override_by_user, pj_subcategory, processed_at
	)
	SELECT
		md5(v_user_id || ':extra:' || gs::text || ':' || random()::text),
		v_user_id,
		'acc_mock_main',
		CASE WHEN random() > 0.5 THEN 'Freelance - Projeto de BI' ELSE 'Dividendos - Carteira XP' END,
		round((700 + random() * 3800)::numeric, 2)::float,
		(CURRENT_DATE - ((10 + random() * 160)::int || ' days')::interval)::date,
		'CREDIT',
		CASE WHEN random() > 0.5 THEN 'Freelance' ELSE 'Investimentos' END,
		false,
		false,
		CASE WHEN random() > 0.65 THEN 'PJ' ELSE 'PF' END,
		round((0.70 + random() * 0.29)::numeric, 2)::float,
		false,
		CASE WHEN random() > 0.65 THEN 'servicos_profissionais' ELSE NULL END,
		NOW()
	FROM generate_series(1, 28) AS gs;

	-- 3) Assinaturas recorrentes
	WITH plans AS (
		SELECT *
		  FROM (VALUES
			  ('Netflix', 39.90, 2),
			  ('Spotify', 21.90, 5),
			  ('Amazon Prime', 19.90, 10),
			  ('iCloud', 9.90, 15),
			  ('YouTube Premium', 24.90, 20)
		  ) AS p(name, price, day_of_month)
	)
	INSERT INTO transactions_clean (
		transaction_id, user_id, account_id, description, amount, date,
		transaction_type, category, is_recurring, is_installment,
		context_type, context_confidence, context_override_by_user, pj_subcategory, processed_at
	)
	SELECT
		md5(v_user_id || ':sub:' || p.name || ':' || gs::text || ':' || clock_timestamp()::text),
		v_user_id,
		'acc_mock_main',
		p.name || ' - Assinatura Mensal',
		-p.price,
		(date_trunc('month', CURRENT_DATE) - (gs || ' months')::interval + (p.day_of_month || ' days')::interval)::date,
		'DEBIT',
		'Assinaturas',
		true,
		false,
		'PF',
		0.98,
		false,
		NULL,
		NOW()
	FROM plans p
	CROSS JOIN generate_series(0, 5) AS gs;

	-- 4) Alto volume de despesas variadas (720 transacoes)
	WITH cats AS (
		SELECT ARRAY[
			'Alimentacao','Mercado','Restaurante','Transporte','Uber','Gasolina',
			'Moradia','Contas','Saude','Farmacia','Lazer','Streaming','Vestuario',
			'Shopping','Educacao','Academia','Viagem','Pet','Impostos','Seguros'
		] AS c
	)
	INSERT INTO transactions_clean (
		transaction_id, user_id, account_id, description, amount, date,
		transaction_type, category, is_recurring, is_installment,
		context_type, context_confidence, context_override_by_user, pj_subcategory, processed_at
	)
	SELECT
		md5(v_user_id || ':expense:' || gs::text || ':' || random()::text || ':' || clock_timestamp()::text),
		v_user_id,
		'acc_mock_main',
		'Compra ' || (c.c[1 + floor(random() * array_length(c.c, 1))::int]),
		-round((15 + random() * 1600)::numeric, 2)::float,
		(CURRENT_DATE - ((random() * 179)::int || ' days')::interval)::date,
		'DEBIT',
		c.c[1 + floor(random() * array_length(c.c, 1))::int],
		false,
		(random() < 0.08),
		CASE WHEN random() < 0.20 THEN 'PJ' ELSE 'PF' END,
		round((0.55 + random() * 0.44)::numeric, 2)::float,
		false,
		CASE WHEN random() < 0.20 THEN 'despesas_operacionais' ELSE NULL END,
		NOW()
	FROM generate_series(1, 720) AS gs
	CROSS JOIN cats c;

	-- 5) Parcelamentos para estressar deteccao de installment/shadow invoice
	INSERT INTO transactions_clean (
		transaction_id, user_id, account_id, description, amount, date,
		transaction_type, category, is_recurring, is_installment,
		context_type, context_confidence, context_override_by_user, pj_subcategory, processed_at
	)
	SELECT
		md5(v_user_id || ':parcelado:' || gs::text || ':' || i::text),
		v_user_id,
		'acc_mock_main',
		'Notebook parcelado ' || i || '/10',
		-899.90,
		(CURRENT_DATE - ((10 - i) * 30 || ' days')::interval)::date,
		'DEBIT',
		'Eletronicos',
		false,
		true,
		'PF',
		0.93,
		false,
		NULL,
		NOW()
	FROM generate_series(1, 10) AS i
	CROSS JOIN generate_series(1, 1) AS gs;

END $$;

-- Verificacao rapida
SELECT
	COUNT(*) AS total_transacoes,
	ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END)::numeric, 2) AS total_entradas,
	ROUND(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END))::numeric, 2) AS total_saidas,
	MIN(date) AS data_min,
	MAX(date) AS data_max
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com';

SELECT
	category,
	COUNT(*) AS qtd,
	ROUND(AVG(amount)::numeric, 2) AS media_valor
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com'
GROUP BY category
ORDER BY qtd DESC
LIMIT 15;
