# Scripts SQL para Popular a Base Online

## Ordem de execucao

Execute na ordem:

1. `01_criar_usuario.sql`
2. `02_criar_transacoes.sql`
3. `03_criar_metas.sql`

Os scripts foram ajustados para o schema atual:
- `users`
- `transactions_clean`
- `financial_goals`
- `architect_simulations`
- `architect_simulation_metrics`
- `chat_messages`

## Como executar no Supabase

1. Abra o projeto no Supabase.
2. Entre em SQL Editor.
3. Rode o conteudo de cada arquivo, um por vez, na ordem acima.
4. Valide com as queries abaixo.

## Massa de dados criada

- Usuario: `teste@nexa.com` / `teste123`
- ~760+ transacoes em `transactions_clean` cobrindo:
    - receitas recorrentes e extras
    - despesas de varias categorias
    - assinaturas recorrentes
    - parcelamentos (`is_installment = true`)
    - mistura PF/PJ em `context_type`
- 5 metas em `financial_goals`
- 2 simulacoes em `architect_simulations`
- trilha de conversa em `chat_messages`

## Queries de verificacao

```sql
-- Usuario criado
SELECT user_id, email, full_name, created_at
FROM users
WHERE email = 'teste@nexa.com';

-- Cobertura de transacoes
SELECT
    COUNT(*) AS total_transacoes,
    MIN(date) AS dt_inicio,
    MAX(date) AS dt_fim,
    ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END)::numeric, 2) AS entradas,
    ROUND(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END))::numeric, 2) AS saidas
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com';

-- Diversidade de categorias
SELECT category, COUNT(*) AS qtd
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com'
GROUP BY category
ORDER BY qtd DESC
LIMIT 20;

-- Mix PF/PJ
SELECT context_type, COUNT(*) AS qtd
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com'
GROUP BY context_type
ORDER BY qtd DESC;

-- Metas
SELECT name, target_amount, current_amount, status, target_date
FROM financial_goals g
JOIN users u ON u.user_id = g.user_id
WHERE u.email = 'teste@nexa.com'
ORDER BY target_date::date;

-- Architect
SELECT COUNT(*) AS qtd_simulacoes
FROM architect_simulations s
JOIN users u ON u.user_id = s.user_id
WHERE u.email = 'teste@nexa.com';

-- Chat
SELECT COUNT(*) AS qtd_msgs
FROM chat_messages c
JOIN users u ON u.user_id = c.user_id
WHERE u.email = 'teste@nexa.com';
```

## Queries para mapear processamento backend

```sql
-- Assinaturas detectaveis
SELECT description, COUNT(*) AS ocorrencias
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com'
    AND category = 'Assinaturas'
GROUP BY description
ORDER BY ocorrencias DESC;

-- Parcelamentos
SELECT COUNT(*) AS qtd_parceladas
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com'
    AND is_installment = true;

-- Base para fiscal/contexto
SELECT context_type, pj_subcategory, COUNT(*) AS qtd
FROM transactions_clean t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com'
GROUP BY context_type, pj_subcategory
ORDER BY qtd DESC;
```
