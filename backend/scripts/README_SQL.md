# 🗄️ Scripts SQL para Popular Banco Railway

## 📋 Ordem de Execução

Execute os scripts **nesta ordem exata**:

### 1️⃣ Criar Usuário
```bash
01_criar_usuario.sql
```
- Cria usuário: `teste@nexa.com` / `teste123`
- Cria conta bancária vinculada
- Remove dados antigos se existirem

### 2️⃣ Criar Transações
```bash
02_criar_transacoes.sql
```
- **~800-1000 transações** nos últimos 6 meses
- Salários mensais
- Assinaturas recorrentes (Netflix, Spotify, etc)
- Despesas variadas (alimentação, transporte, lazer, etc)
- Contas fixas (aluguel, luz, água, internet)
- Investimentos ocasionais

### 3️⃣ Criar Metas
```bash
03_criar_metas.sql
```
- 5 metas financeiras
- Status variados (ativa, concluída)
- Diferentes níveis de progresso

---

## 🚀 Como Executar no Railway

### Opção 1: Via Railway CLI (Recomendado)

```bash
# 1. Instalar Railway CLI
npm i -g @railway/cli

# 2. Login
railway login

# 3. Conectar ao projeto
railway link

# 4. Conectar ao banco PostgreSQL
railway connect postgres

# 5. Executar scripts em ordem
\i /caminho/para/01_criar_usuario.sql
\i /caminho/para/02_criar_transacoes.sql
\i /caminho/para/03_criar_metas.sql
```

### Opção 2: Via Editor SQL do Railway Dashboard

1. Acesse https://railway.app
2. Entre no seu projeto `codigos-nexa`
3. Clique no serviço **PostgreSQL**
4. Vá em **Data** → **Query**
5. Copie e cole cada script (em ordem)
6. Execute com `Ctrl+Enter` ou botão Run

### Opção 3: Via Cliente PostgreSQL Local

```bash
# 1. Obter DATABASE_URL do Railway
railway variables

# 2. Conectar usando psql
psql "postgresql://postgres:senha@host:port/railway"

# 3. Executar scripts
\i 01_criar_usuario.sql
\i 02_criar_transacoes.sql
\i 03_criar_metas.sql
```

---

## ✅ Verificação

Após executar, verifique os resultados:

```sql
-- Verificar usuário
SELECT * FROM users WHERE email = 'teste@nexa.com';

-- Contar transações
SELECT COUNT(*) FROM transactions t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com';

-- Ver distribuição por categoria
SELECT category, COUNT(*) as total
FROM transactions t
JOIN users u ON u.user_id = t.user_id
WHERE u.email = 'teste@nexa.com'
GROUP BY category
ORDER BY total DESC;

-- Ver metas
SELECT title, current_amount, target_amount, status
FROM goals g
JOIN users u ON u.user_id = g.user_id
WHERE u.email = 'teste@nexa.com';
```

---

## 📊 Dados Criados

### Usuário Mock
- **Email:** teste@nexa.com
- **Senha:** teste123
- **Nome:** Bruno Teste

### Transações (~900-1000)
- ✅ 6 salários (R$ 8.500/mês)
- ✅ ~4 freelances (R$ 500-3000 cada)
- ✅ 24 assinaturas (Netflix, Spotify, Amazon, iCloud)
- ✅ ~800 despesas variadas em 20+ categorias
- ✅ 36 contas fixas (aluguel, condomínio, luz, água, internet, telefone)
- ✅ ~5 investimentos (dividendos, tesouro, CDB)

### Categorias de Despesas
- Alimentação
- Transporte
- Restaurante
- Mercado
- Farmácia
- Lazer
- Vestuário
- Shopping
- Moradia
- Contas
- Assinaturas
- E mais...

### Metas (5)
1. 🌍 Viagem Europa - R$ 15.000 (57% completo)
2. 💰 Fundo Emergência - R$ 30.000 (73% completo)
3. 🚗 Carro Novo - R$ 60.000 (25% completo)
4. ✅ Curso Inglês - R$ 5.000 (CONCLUÍDA)
5. 💻 Setup Home Office - R$ 8.000 (29% completo)

---

## 🎯 Testando no Frontend

Após popular o banco:

1. **Acesse:** https://codigos-nexa-production.up.railway.app
2. **Faça login:** teste@nexa.com / teste123
3. **Navegue pelas páginas:**
   - **Dashboard:** Ver transações, gráficos, metas
   - **Estratégias:** Testar Optimizer, Architect, Fiscal
   - **Chat IA:** Fazer perguntas sobre finanças
   - **Conexões:** Ver conta conectada

---

## 🔧 Troubleshooting

### Erro: "Usuário não encontrado"
Execute o script `01_criar_usuario.sql` primeiro

### Erro: "Permission denied"
Verifique se está conectado ao banco correto no Railway

### Transações duplicadas
Os scripts limpam dados antigos automaticamente ao executar

### Queries lentas
Normal! São ~1000 operações. Aguarde 10-30 segundos.

---

## 🗑️ Limpar Dados

Para remover tudo e recomeçar:

```sql
DO $$
DECLARE
    v_user_id UUID;
BEGIN
    SELECT user_id INTO v_user_id
    FROM users WHERE email = 'teste@nexa.com';

    DELETE FROM transactions WHERE user_id = v_user_id;
    DELETE FROM goals WHERE user_id = v_user_id;
    DELETE FROM accounts WHERE user_id = v_user_id;
    DELETE FROM users WHERE user_id = v_user_id;
END $$;
```

---

**Pronto!** 🚀 Agora você tem um banco completo para testar todas as funcionalidades do Nexa!
