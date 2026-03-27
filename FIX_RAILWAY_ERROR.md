# ⚠️ COMO RESOLVER O ERRO DE HEALTH CHECK NO RAILWAY

## O Erro que Você Está Vendo

```
❌ The health check endpoint didn't respond as expected.
   Check the Deploy Logs tab for startup errors
```

---

## 🎯 SOLUÇÃO EM 4 PASSOS

### PASSO 1: Fazer Commit das Correções

As correções já foram feitas no código. Agora você precisa fazer commit e push:

```bash
# Na pasta do projeto
cd "/home/bruno/Área de trabalho/nexa/codigos-nexa"

# Adicionar as mudanças
git add .

# Commit
git commit -m "Fix: Railway deployment - health check e database connection

- Aumentado timeout de conexão do DB para 60s
- Removido fail-fast no startup (não trava mais se DB demorar)
- Adicionado endpoint /readiness para check completo
- Melhorado logging para debug
- Ajustado railway.toml para usar CMD do Dockerfile
- Adicionado guias de troubleshooting"

# Push para o GitHub
git push origin main
```

### PASSO 2: Verificar PostgreSQL no Railway

1. Abra seu projeto no [Railway](https://railway.app)
2. Verifique se tem um serviço **"Postgres"** ou **"PostgreSQL"**
3. Se **NÃO tem**:
   - Clique em **"New"**
   - Selecione **"Database"**
   - Escolha **"Add PostgreSQL"**
   - Aguarde ficar verde ✅

### PASSO 3: Configurar Variáveis de Ambiente

No painel do serviço da **API** (não do Postgres), clique em **"Variables"** e adicione:

#### ✅ Obrigatórias:

```bash
DATABASE_URL = ${{Postgres.DATABASE_URL}}
```
⚠️ **IMPORTANTE**: Use `${{Postgres.DATABASE_URL}}` exatamente assim - é uma referência automática!

```bash
SECRET_KEY = <clique em "Generate" ou cole uma chave forte>
APP_ENV = production
LOG_LEVEL = INFO
```

#### 💡 Recomendadas (se usar LLM):

```bash
OPENAI_API_KEY = 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
LLM_PROVIDER = openai
LLM_MODEL = gpt-4o-mini
```

### PASSO 4: Redesploy

Depois de configurar as variáveis:

1. O Railway vai **automaticamente fazer redesploy**
2. Aguarde **2-3 minutos** (é normal demorar)
3. Acompanhe os logs em **"Deployments" → "View Logs"**

---

## ✅ LOGS DE SUCESSO

Quando funcionar, você verá isso nos logs:

```
🚀 Starting Nexa API
🌍 APP_ENV: production
🔗 DATABASE_URL configured: True
🔑 SECRET_KEY configured: True
...
INFO: DB schema ready
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:XXXX
```

---

## 🔍 VERIFICAR SE FUNCIONOU

### Teste 1: Health Check Básico
```bash
curl https://SUA-URL.railway.app/health
```

**Resposta esperada:**
```json
{"status":"ok","service":"nexa-api"}
```

### Teste 2: Readiness Check (com DB)
```bash
curl https://SUA-URL.railway.app/readiness
```

**Resposta esperada:**
```json
{"status":"ready","database":"connected"}
```

### Teste 3: Versão
```bash
curl https://SUA-URL.railway.app/version
```

**Resposta esperada:**
```json
{"version":"0.1.0"}
```

---

## ⏱️ TIMELINE ESPERADA

| Tempo | O que acontece |
|-------|----------------|
| 0s | Push para GitHub |
| ~10s | Railway detecta mudança e inicia build |
| ~60s | Build de Docker completo |
| ~90s | Deploy iniciado, API tentando conectar ao DB |
| ~120s | ✅ **API online e saudável** |

---

## 🚨 SE AINDA NÃO FUNCIONAR

### Ver os Logs Detalhados

No Railway:
1. Vá em **"Deployments"**
2. Clique no deployment mais recente
3. Clique em **"View Logs"**
4. Procure por mensagens de erro em vermelho

### Problemas Comuns:

#### ❌ "ValidationError: DATABASE_URL"
**Causa:** Variável `DATABASE_URL` não configurada
**Solução:** Adicionar `DATABASE_URL=${{Postgres.DATABASE_URL}}`

#### ❌ "could not connect to server"
**Causa:** PostgreSQL não existe ou nome do serviço está errado
**Solução:**
- Verificar se PostgreSQL está criado
- Se renomeou o Postgres para "nexa-db", usar `${{nexa-db.DATABASE_URL}}`

#### ❌ "WARNING: DB connection attempt 60/60 failed"
**Causa:** DATABASE_URL inválida ou PostgreSQL offline
**Solução:**
- Verificar se Postgres está verde ✅
- Verificar se `DATABASE_URL` está preenchida corretamente

#### ❌ "Port already in use"
**Causa:** Problema no Dockerfile (mas já foi corrigido)
**Solução:** Fazer commit e push das correções (Passo 1)

---

## 📋 CHECKLIST FINAL

Antes de chamar ajuda, verifique:

- [ ] Fez commit e push das correções?
- [ ] PostgreSQL está criado no Railway?
- [ ] PostgreSQL está online (verde ✅)?
- [ ] Variável `DATABASE_URL=${{Postgres.DATABASE_URL}}` está configurada?
- [ ] Variável `SECRET_KEY` está configurada?
- [ ] Variável `APP_ENV=production` está configurada?
- [ ] Aguardou pelo menos 3 minutos após o deploy?
- [ ] Verificou os logs em "View Logs"?

---

## 🆘 PRECISA DE AJUDA?

Se depois de seguir TODOS os passos ainda não funcionar:

1. **Copie os logs completos** do Railway (todo o output em "View Logs")
2. **Tire um print** da tela de "Variables" da API (esconda valores sensíveis)
3. **Tire um print** da tela principal mostrando os serviços (Postgres e API)
4. **Me envie** essas informações

---

## 📚 Documentos Relacionados

- **Guia Rápido:** `RAILWAY_QUICKSTART.md`
- **Guia Completo:** `DEPLOY_RAILWAY.md`
- **Troubleshooting Detalhado:** `TROUBLESHOOTING_RAILWAY.md`
- **Template de Variáveis:** `.env.railway.example`

---

**🎉 Boa sorte com o deploy!**
