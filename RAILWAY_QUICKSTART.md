# 🚀 Deploy Rápido no Railway

## Setup Rápido (5 minutos)

### 1. Preparar Código ✓
```bash
# Já feito! Os arquivos necessários já foram criados:
# - Dockerfile (otimizado)
# - railway.toml (configuração)
# - .railway-ignore (arquivos a ignorar)
```

### 2. Railway Dashboard

1. Acesse [railway.app](https://railway.app/)
2. **New Project** → **Deploy from GitHub repo**
3. Selecione o repositório `codigos-nexa`
4. **Add PostgreSQL** (no mesmo projeto)
5. **Add Redis** (opcional, para cache)

### 3. Variáveis de Ambiente

No painel da API, adicione:

```bash
# Auto-preenchido pelo Railway
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Gerar com: openssl rand -hex 32
SECRET_KEY=sua-chave-secreta-forte

# Ambiente
APP_ENV=production
LOG_LEVEL=INFO

# APIs (se usar)
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
```

### 4. Deploy Automático

- Railway faz deploy automaticamente após conectar o repo
- Cada push na `main` gera novo deploy
- URL pública gerada automaticamente

### 5. Testar

```bash
# Health check
curl https://sua-url.railway.app/health

# Ver logs
railway logs
```

## Comandos Úteis

```bash
# Instalar Railway CLI
npm install -g @railway/cli

# Login
railway login

# Ver logs
railway logs --tail

# Link projeto existente
railway link

# Deploy manual
railway up
```

## Custos ($5/mês grátis)

- PostgreSQL: ~$5/mês
- Redis: ~$5/mês
- API: baseado em uso

## URL da API

Após deploy: `https://nexa-api-production.up.railway.app`

Configure no frontend:
```env
VITE_API_URL=https://nexa-api-production.up.railway.app/api/v1
```

## Troubleshooting

| Problema | Solução |
|----------|---------|
| Deploy falha | `railway logs --build` |
| Erro de DB | Verificar `DATABASE_URL` |
| Port error | Railway usa `$PORT` automaticamente |
| 500 errors | `railway logs --tail` |

## Links

- 📖 [Guia Completo](./DEPLOY_RAILWAY.md)
- 🧪 [Testar Build Local](./test-railway-build.sh)
- 🔐 [Variáveis de Ambiente](./env.railway.example)
- 📚 [Railway Docs](https://docs.railway.app/)

---

**Pronto para deploy!** 🎉

Basta conectar o repositório no Railway e configurar as variáveis de ambiente.
