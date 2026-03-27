# 🔍 DEBUG RAILWAY - Health Check Falhando

## Situação Atual

O health check está falhando após 11 tentativas em 5 minutos. Isso indica que:
- ✅ O build está completando com sucesso
- ❌ A API não está respondendo no endpoint `/health`

Possíveis causas:
1. Erro no startup (imports, dependências)
2. Porta incorreta
3. API crashando antes de responder

---

## 🎯 SOLUÇÃO: Testar com Versão Minimal

Criei uma versão minimalista da API para isolar o problema.

### Opção 1: Testar Localmente PRIMEIRO (Recomendado)

```bash
cd "/home/bruno/Área de trabalho/nexa/codigos-nexa"

# Testar a versão minimal localmente
docker build -f Dockerfile.minimal -t nexa-minimal .
docker run -p 8000:8000 -e PORT=8000 nexa-minimal

# Em outro terminal, testar:
curl http://localhost:8000/health
```

**Resultado esperado:**
```json
{"status":"ok","service":"nexa-api-minimal","env":"unknown"}
```

Se funcionar localmente mas não no Railway → problema nas variáveis de ambiente
Se NÃO funcionar localmente → problema no Dockerfile/código

---

### Opção 2: Deploy da Versão Minimal no Railway

Veja exatamente onde está o problema:

1. **Edite o `railway.toml`** temporariamente:
```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile.minimal"  # ← MUDAR AQUI

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

2. **Commit e push:**
```bash
git add railway.toml Dockerfile.minimal backend/app/main_minimal.py
git commit -m "Debug: versão minimal para identificar problema"
git push
```

3. **Aguarde o deploy** e veja os logs

**Se a versão minimal FUNCIONAR:**
→ O problema está no código completo (imports, dependências, banco de dados)

**Se a versão minimal FALHAR:**
→ O problema está nas variáveis de ambiente ou configuração do Railway

---

## 🔍 Investigar Logs do Railway

Enquanto isso, **CRUCIAL**: Me envie os logs completos do deploy!

No Railway:
1. **Deployments** → selecione o deploy mais recente
2. **Build Logs** → copie TUDO
3. **Deploy Logs** → copie TUDO (principalmente as últimas 50 linhas)

### O que procurar nos logs:

#### ✅ Build bem-sucedido:
```
Successfully built <image-id>
Successfully tagged <tag>
```

#### ❌ Erro no Build:
```
ERROR: failed to solve
Could not find a version that satisfies
ModuleNotFoundError
```

#### ❌ Erro no Startup:
```
Traceback (most recent call last):
ImportError: cannot import name
ModuleNotFoundError: No module named
```

#### ❌ Erro de Porta:
```
OSError: [Errno 98] Address already in use
```

---

## 🚨 Problemas Comuns e Soluções

### 1. "build-essential" demora muito
**Solução:** Algumas dependências (scikit-learn, pyarrow) precisam compilar
- Tempo normal de build: 3-5 minutos
- Se exceder 10 minutos → timeout

### 2. Imports falhando
**Problema:** Algum módulo não instalou corretamente
**Logs mostram:**
```python
ModuleNotFoundError: No module named 'langgraph'
```
**Solução:** Verificar `requirements.railway.txt`

### 3. Banco de dados travando startup
**Problema:** API trava tentando conectar ao DB
**Logs mostram:**
```
DB connection attempt 60/60 failed
```
**Solução:** Já corrigido no código (não deve mais travar)

### 4. Variáveis não configuradas
**Problema:** `DATABASE_URL` ou `SECRET_KEY` faltando
**Logs mostram:**
```
ValidationError: Field required
```
**Solução:** Adicionar variáveis no Railway

---

## 📋 Checklist de Debug

Marque tudo que você já verificou:

### No Railway:
- [ ] PostgreSQL está criado e online (verde)?
- [ ] Variável `DATABASE_URL=${{Postgres.DATABASE_URL}}` configurada?
- [ ] Variável `SECRET_KEY` configurada (não vazia)?
- [ ] Variável `APP_ENV=production` configurada?
- [ ] Build terminou com "Successfully built"?
- [ ] Aguardou 3+ minutos após "Build complete"?

### Logs:
- [ ] Vi os "Build Logs" completos?
- [ ] Vi os "Deploy Logs" completos?
- [ ] Há mensagens de erro em vermelho?
- [ ] Há "Traceback" ou "Exception"?

### Testes:
- [ ] Testei o Dockerfile.minimal localmente?
- [ ] Funcionou no Docker local?
- [ ] Testei a versão minimal no Railway?

---

## 🆘 Se Nada Funcionar

Tente esta sequência de diagnóstico:

### 1. Teste Local Primeiro
```bash
# Versão minimal
docker build -f Dockerfile.minimal -t test .
docker run -p 8000:8000 test

# Se funcionar, teste a versão normal
docker build -f Dockerfile -t test-full .
docker run -p 8000:8000 -e DATABASE_URL=sqlite:///./test.db -e SECRET_KEY=test test-full
```

### 2. Se Local Funciona mas Railway Não

O problema é nas variáveis de ambiente do Railway.

**Ação:** Copie e cole EXATAMENTE estas variáveis no Railway:

```bash
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=change-this-to-a-random-string-at-least-32-chars-long
APP_ENV=production
LOG_LEVEL=INFO
```

### 3. Se Nada Funciona (Nem Local)

O problema é no código ou dependências.

**Ação:** Use a versão minimal:
1. Mude `railway.toml` para usar `Dockerfile.minimal`
2. Push e deploy
3. Depois que funcionar, adicione features gradualmente

---

## 📤 Me Envie:

Para eu ajudar melhor, preciso de:

1. **Build Logs** (últimas 100 linhas)
```bash
# Se tiver Railway CLI:
railway logs --build > build_logs.txt
```

2. **Deploy Logs** (últimas 100 linhas)
```bash
railway logs > deploy_logs.txt
```

3. **Screenshot das Variáveis**
- Vá em Variables no serviço da API
- Screenshot (esconda valores sensíveis com uma tarja)

4. **Status dos Serviços**
- Screenshot mostrando se Postgres e API estão verdes/vermelhos

---

## 🎯 Próximo Passo

**Escolha um:**

### A) Teste Local (Mais Rápido)
```bash
# Na pasta do projeto
docker build -f Dockerfile.minimal -t nexa-test .
docker run -p 8000:8000 nexa-test

# Teste
curl http://localhost:8000/health
```

### B) Deploy Minimal no Railway
```bash
# Editar railway.toml para usar Dockerfile.minimal
# Depois:
git add .
git commit -m "Test: minimal version"
git push
```

### C) Me Enviar Logs Completos
- Build logs
- Deploy logs
- Screenshot de variables

**Qual você prefere tentar primeiro?**
