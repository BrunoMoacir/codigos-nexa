# Deploy da API Nexa no Railway

Este guia mostra como fazer o deploy da API da Nexa no Railway usando Docker.

## Pré-requisitos

1. Conta no [Railway](https://railway.app/)
2. Repositório Git configurado (GitHub, GitLab ou Bitbucket)
3. Railway CLI instalado (opcional, mas recomendado)

```bash
npm install -g @railway/cli
```

## Passo a Passo

### 1. Preparar o Repositório

Certifique-se de que os seguintes arquivos estão no repositório:
- `Dockerfile` (já configurado)
- `railway.toml` (já criado)
- `.railway-ignore` (já criado)
- `backend/requirements.txt`

### 2. Criar Projeto no Railway

#### Opção A: Via Dashboard Web

1. Acesse [railway.app](https://railway.app/) e faça login
2. Clique em **"New Project"**
3. Selecione **"Deploy from GitHub repo"**
4. Escolha o repositório **codigos-nexa**
5. O Railway detectará automaticamente o Dockerfile

#### Opção B: Via CLI

```bash
# Login no Railway
railway login

# Navegar até a pasta do projeto
cd /caminho/para/codigos-nexa

# Inicializar projeto
railway init

# Link com o projeto (se já existir)
railway link
```

### 3. Adicionar Banco de Dados PostgreSQL

1. No dashboard do seu projeto Railway, clique em **"New"**
2. Selecione **"Database"** > **"Add PostgreSQL"**
3. O Railway criará automaticamente um banco e variáveis de ambiente

### 4. Configurar Variáveis de Ambiente

No painel do serviço da API, adicione as seguintes variáveis:

```bash
# Obrigatórias
DATABASE_URL=${{Postgres.DATABASE_URL}}  # Será preenchido automaticamente pelo Railway
SECRET_KEY=seu-secret-key-super-seguro-aqui  # Gere uma chave forte
APP_ENV=production
LOG_LEVEL=INFO

# APIs externas (se usar)
PLUGGY_CLIENT_ID=seu-pluggy-client-id
PLUGGY_CLIENT_SECRET=seu-pluggy-client-secret
PLUGGY_BASE_URL=https://api.pluggy.ai

# LLMs (OpenAI ou Anthropic)
OPENAI_API_KEY=sua-chave-openai
ANTHROPIC_API_KEY=sua-chave-anthropic
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini

# Frontend (ajustar após deploy)
FRONTEND_BASE_URL=https://seu-frontend.vercel.app
```

**Dica:** O Railway preenche automaticamente `${{Postgres.DATABASE_URL}}` se você adicionar o PostgreSQL primeiro.

### 5. Configurar Redis (Opcional, mas recomendado)

Se você usa Redis para cache/sessões:

1. No dashboard, clique em **"New"** > **"Database"** > **"Add Redis"**
2. Adicione a variável de ambiente:
```bash
REDIS_URL=${{Redis.REDIS_URL}}
```

### 6. Deploy

#### Via Dashboard
- O Railway fará deploy automaticamente após conectar o repositório
- Cada push na branch principal acionará um novo deploy

#### Via CLI
```bash
# Deploy manual
railway up

# Ou para CI/CD
railway up --detach
```

### 7. Verificar Deploy

Após o deploy:

1. O Railway fornecerá uma URL pública (ex: `https://nexa-api-production.up.railway.app`)
2. Teste o health check:
```bash
curl https://sua-url.railway.app/health
```

3. Verifique os logs:
```bash
railway logs
```

## Configurações Importantes

### Dockerfile Otimizado
O Dockerfile já está configurado com:
- Python 3.12 slim
- Multi-stage build para otimizar tamanho
- Variáveis de ambiente corretas

### Port Binding
O Railway automaticamente define a variável `$PORT`. O `railway.toml` já está configurado para usar essa variável.

### Health Check
A API tem um endpoint `/health` que o Railway usa para monitorar o serviço.

## Conectar Frontend ao Backend

Após o deploy, você terá uma URL tipo:
```
https://nexa-api-production.up.railway.app
```

No seu frontend React (Vercel, Netlify, etc.), configure:
```env
VITE_API_URL=https://nexa-api-production.up.railway.app/api/v1
```

## Troubleshooting

### Deploy falha
```bash
# Ver logs detalhados
railway logs --tail

# Verificar build
railway logs --build
```

### Erro de conexão com banco
- Verifique se a variável `DATABASE_URL` está correta
- Certifique-se que o PostgreSQL está rodando
- O Railway pode levar alguns segundos para conectar serviços

### Erro "Port already in use"
- O Railway gerencia a porta automaticamente via `$PORT`
- Não hardcode porta 8000 no comando de start

## Custos

- Railway oferece $5 de crédito gratuito/mês
- PostgreSQL: ~$5/mês
- Redis (opcional): ~$5/mês
- Aplicação: baseado em uso (CPU/RAM)

## Próximos Passos

1. Configure domínio customizado (se quiser)
2. Configure webhooks para CI/CD
3. Configure alertas de erro
4. Monitore métricas no dashboard

## Links Úteis

- [Railway Docs](https://docs.railway.app/)
- [Railway CLI](https://docs.railway.app/develop/cli)
- [PostgreSQL no Railway](https://docs.railway.app/databases/postgresql)
- [Variáveis de Ambiente](https://docs.railway.app/develop/variables)
