# 🔧 Troubleshooting Railway - Health Check Failed

## Problema
```
Error: The health check endpoint didn't respond as expected
```

## Causa Raiz
A API está levando muito tempo para iniciar porque está tentando conectar ao banco de dados durante o startup.

## ✅ Solução Rápida

### 1. Verificar se o PostgreSQL está criado
No Railway:
- Certifique-se que você **ADICIONOU** o PostgreSQL ao projeto
- Vá em **"New"** → **"Database"** → **"Add PostgreSQL"**
- Espere o PostgreSQL ficar online (demora ~30 segundos)

### 2. Configurar Variáveis de Ambiente CORRETAMENTE

No painel do serviço da API, adicione estas variáveis **EXATAMENTE** assim:

```bash
# ⚠️ CRITICAL - Deve referenciar o serviço Postgres
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Outras obrigatórias
SECRET_KEY=substitua-por-uma-chave-forte-aqui
APP_ENV=production
LOG_LEVEL=INFO

# Opcional (mas recomendado se usa LLM)
OPENAI_API_KEY=sua-chave-aqui
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
```

**IMPORTANTE:**
- `${{Postgres.DATABASE_URL}}` é uma referência AUTOMÁTICA que o Railway preenche
- O nome `Postgres` deve corresponder ao nome do serviço PostgreSQL no Railway
- Se você renomeou o serviço Postgres, ajuste: `${{SeuNomePostgres.DATABASE_URL}}`

### 3. Verificar a Ordem de Deploy

O PostgreSQL deve estar **ONLINE** antes da API:

1. Primeiro: PostgreSQL fica verde ✅
2. Depois: API tenta conectar (pode levar até 60 segundos na primeira vez)

### 4. Checar os Logs

No Railway, vá em **"Deployments"** → **"View Logs"**:

**Logs de Sucesso:**
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:XXXX
DB schema ready
```

**Logs de Erro Comum:**
```
WARNING: DB connection attempt 1/60 failed: could not connect to server
```
- Se aparecer tentando conectar (attempt 1/60, 2/60...) → é normal, aguarde
- Se falhar todas as 60 tentativas → problema na DATABASE_URL

### 5. Comandos de Debug

Se você tem Railway CLI instalado:

```bash
# Ver logs em tempo real
railway logs --tail

# Ver variáveis de ambiente (verificar se DATABASE_URL está setado)
railway variables

# Verificar se o Postgres está rodando
railway status
```

## 🔍 Checklist de Diagnóstico

- [ ] PostgreSQL está criado e online no Railway?
- [ ] A variável `DATABASE_URL=${{Postgres.DATABASE_URL}}` está configurada?
- [ ] O nome `Postgres` corresponde ao nome do serviço no Railway?
- [ ] Outras variáveis obrigatórias estão configuradas? (SECRET_KEY, APP_ENV)
- [ ] O deploy mais recente terminou? (não está em "Building...")
- [ ] Você esperou pelo menos 2-3 minutos após o deploy?

## 📊 Entendendo os Logs

### Normal (aguarde):
```
INFO:     Started server process
WARNING: DB connection attempt 5/60 failed
WARNING: DB connection attempt 6/60 failed
INFO:     DB schema ready  ← SUCESSO!
INFO:     Application startup complete
```

### Erro - DATABASE_URL inválida:
```
WARNING: DB connection attempt 60/60 failed: could not connect
ERROR: Failed to connect to database after 60 attempts
```
**Solução:** Verificar se `DATABASE_URL` está correta

### Erro - Faltando variável:
```
ValidationError: 1 validation error for Settings
  DATABASE_URL
    Field required
```
**Solução:** Adicionar a variável DATABASE_URL

## 🎯 Teste Manual do Health Check

Depois que o deploy finalizar com sucesso:

```bash
# Pegar a URL do Railway (ex: https://nexa-production.up.railway.app)
curl https://SUA-URL.railway.app/health

# Deve retornar:
{"status":"ok","service":"nexa-api"}

# Verificar banco de dados:
curl https://SUA-URL.railway.app/readiness

# Se tudo ok:
{"status":"ready","database":"connected"}
```

## 🚨 Erros Comuns

### 1. "Service Unavailable" por 5+ minutos
**Causa:** DATABASE_URL não está configurada ou PostgreSQL não existe
**Solução:** Criar PostgreSQL e adicionar variável `DATABASE_URL=${{Postgres.DATABASE_URL}}`

### 2. "Build succeeded but deployment failed"
**Causa:** Falta variável obrigatória (SECRET_KEY, APP_ENV)
**Solução:** Adicionar todas as variáveis do `.env.railway.example`

### 3. "Health check timeout"
**Causa:** API está presa tentando conectar ao banco
**Solução:** Código já foi corrigido para não travar (commit mais recente)

### 4. Nome do serviço Postgres diferente
Se você renomeou o PostgreSQL no Railway para outro nome (ex: "nexa-db"):
```bash
DATABASE_URL=${{nexa-db.DATABASE_URL}}
```

## ✅ Configuração Correta Final

Depois das correções, seu Railway deve ter:

**Serviços:**
1. ✅ **Postgres** (online)
2. ✅ **nexa-api** (online)

**Variáveis da API:**
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=sua-chave-forte
APP_ENV=production
LOG_LEVEL=INFO
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
```

**Resultado esperado:**
```
✅ PostgreSQL: Active
✅ API: Active
✅ Health check: Passing
```

## 💡 Dica Final

Se ainda assim não funcionar:

1. **Delete o deployment atual**
2. **Faça commit das correções mais recentes**
3. **Push para o GitHub**
4. **Redesploy no Railway**
5. **Aguarde 2-3 minutos**

O Railway pode cachear configurações antigas. Um redesploy limpo resolve isso.

---

**Ainda com problemas?** Copie os logs completos do Railway e me mande!
