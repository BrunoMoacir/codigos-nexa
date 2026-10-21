# HIVE — app web

O frontend oficial da HIVE: React 19 + TypeScript + Vite, ligado à API real em todas as telas. O visual é o redesenho HIVE da Beatriz Samaha (preto quente, ouro, Satoshi, hexágonos) e é a referência de design do produto — mudança visual se combina com ela antes.

## Rodando

Pré-requisitos: Node 20+ (desenvolvido com 22) e o backend no ar em `http://localhost:8000` (ver o [README da raiz](../README.md#-início-rápido)).

```bash
npm install
npm run dev          # http://localhost:3000 — /api é encaminhado ao backend
```

Para ter dados, popule as personas de demonstração no backend (`cd backend && python3 -m demo.seed`) e entre com `ana.demo@nexa.test`, `bruno.demo@nexa.test` ou `carla.demo@nexa.test` (senha `demo1234`, só no banco de desenvolvimento).

| Script | O que faz |
|:---|:---|
| `npm run dev` | Servidor de desenvolvimento com recarga automática |
| `npm run build` | Checagem de tipos + build de produção em `dist/` |
| `npm run preview` | Serve o `dist/` localmente |
| `npm run lint` | ESLint (precisa sair sem erros) |
| `npx tsc -b` | Só a checagem de tipos |
| `npm test` | Testes unitários (Vitest, modo observação) — `npx vitest run` roda uma vez |
| `npm run test:e2e` | Testes de ponta a ponta (Playwright) contra o app e a API de verdade |

### Variáveis

| Variável | Padrão | Para quê |
|:---|:---|:---|
| `VITE_API_URL` | `/api/v1` | Base da API no navegador. O padrão relativo funciona com o proxy do Vite e com o nginx |
| `VITE_DEV_BACKEND` | `http://localhost:8000` | Para onde o `npm run dev` encaminha `/api` |

## Como o app fala com a API

- **Um cliente só** ([src/api/client.ts](src/api/client.ts)): injeta o token, e quando várias requisições tomam 401 ao mesmo tempo faz **uma** renovação do access (o refresh é de uso único). Se o refresh falhar, limpa a sessão e manda para `/login?next=<tela>`; depois do login a pessoa volta para onde estava (só caminhos internos — ver [src/utils/destinoSeguro.ts](src/utils/destinoSeguro.ts)).
- **Sessão** ([src/api/session.ts](src/api/session.ts)): fonte única das chaves de `localStorage` (`jwt_token`, `refresh_token`, `user_id`…). O logout revoga no servidor e apaga também os dados locais do usuário.
- **Erros** ([src/api/errors.ts](src/api/errors.ts)): `describeError` traduz 401/402/403/404/422/429/503/504/timeout em mensagens em português; o 402 traz o plano necessário.
- **Tempo por tipo de chamada**: padrão 30 s, simulações e consultas oficiais 75 s, chat 95 s (o agente tem até 60 s no servidor).
- **Módulos por domínio** em [src/api/](src/api/): `nexa.ts` (chat por conversas, cartões, metas, lançamentos), `painel.ts`, `organizar.ts`, `estrategias.ts`, `conexoes.ts` + `pluggySync.ts` (sync com SSE e long-polling), `conta.ts`, `protecao.ts`. Os tipos foram escritos a partir das respostas reais da API.

## Telas

Navegação em três abas — **Chat IA**, **Oportunidades** e **Organização** — e o avatar abre o **Perfil**, onde fica o card **Ferramentas** com as demais telas.

| Rota | Tela | Principais endpoints |
|:---|:---|:---|
| `/login` · `/register` | Entrada e cadastro em 3 passos (aceite dos termos obrigatório) | `/auth/token`, `/auth/check-email`, `/auth/register` |
| `/forgot-password` · `/reset-password` · `/verify-email` | Conta | `/auth/forgot-password`, `/auth/reset-password`, `/auth/verify-email` |
| `/contact` | Contato (abre o WhatsApp com a mensagem pronta) | — |
| `/chat` | Chat IA com lista de conversas | `/chat/sessions`, `/chat/history`, `POST /chat/` |
| `/feed` | Oportunidades | `/alerts/{user_id}` |
| `/organizar` | Cartões, gasto mês a mês (12 meses) e por semana, categorias, metas e movimentações | `/transactions/{user_id}` (paginado), `/pluggy/cards`, `/goals/{user_id}` |
| `/organizar/cartao/novo` | Cadastro manual de cartão | `POST /pluggy/cards/manual` |
| `/profile` | Perfil, preferências, LGPD, modo demo, Ferramentas | `/settings`, `/billing/subscription`, `/privacy/*`, `/auth/logout-all` |
| `/strategies` | Cartões, grandes compras, MEI, pares, negociador | `/optimizer/*`, `/architect/*`, `/purchase/*`, `/fiscal-report/*`, `/peers/*`, `/negotiator/*` |
| `/goals` · `/connections` | Metas e desafios · Conexões Open Finance | `/goals/*`, `/health-score/*` · `/pluggy/*`, `/data-quality/*` |
| `/defesa` · `/direitos` · `/impostos` · `/wrapped` · `/planos` | Defesa do consumidor, direitos esquecidos, impostos, retrospectiva, planos | `/defense/*`, `/rights/*`, `/tax/*`, `/viral/*`, `/billing/*` |
| `/widget` | Margem do dia (PWA) | `/safe-to-spend/{user_id}/widget` |

Os caminhos seguem os que o backend gera em e-mails, cards de notificação e no retorno do Stripe — não renomeie sem mudar o backend junto. `/dashboard` e `/home` redirecionam para `/organizar`.

**Modo demo** (Perfil): um interruptor por conta que preenche Oportunidades e Organização com dados de exemplo **do próprio frontend**, só para mostrar como as telas ficam. Nunca vem ligado. Não confundir com as personas do backend, que têm extrato de verdade.

## PWA

`public/manifest.webmanifest`, `public/sw.js` e [src/pwa/](src/pwa/) (registro do service worker e Web Push). O service worker só é registrado no build de produção; a API nunca passa pelo cache.

## Testes

- **Unitários** (Vitest + Testing Library) em [src/tests/unit/](src/tests/unit/): páginas, componentes e a lógica de API (renovação do login, busca paginada da Organização).
- **Ponta a ponta** (Playwright) em [e2e/](e2e/), contra o backend local com as personas: todas as telas abrem sem erro de API nos três planos, as abas navegam no celular, a sessão renova sozinha e volta para a tela de origem, o cadastro envia `accepted_terms`. Um passo de preparação entra uma vez com cada persona e guarda a sessão em `e2e/.auth/` (fora do git); só os testes do próprio login entram de novo — a suíte faz 7 logins, e o backend aceita 10 por minuto por IP, então espere um minuto entre duas execuções seguidas. Rode `npx playwright install chromium` uma vez. O envio real ao agente só roda com `HIVE_E2E_CHAT=1` (gasta crédito de IA). Para usar um Chromium já instalado: `PLAYWRIGHT_CHROMIUM_PATH=/caminho/do/chrome`.

O CI roda lint, tipos, testes unitários e build a cada push.

## Produção

O `Dockerfile` tem três estágios: `development` (Vite, usado pelo `docker-compose.yml`), `build` e `production` (nginx). O [nginx.conf.template](nginx.conf.template) serve a SPA e encaminha `/api/` ao backend (`BACKEND_URL`, padrão `http://api:8000`), sem buffer para o SSE do sync e com 120 s de leitura para o chat.

A fonte Satoshi vem do Fontshare e é carregada sem bloquear a renderização: se o CDN cair, o app abre com a fonte do sistema. Para não depender do CDN, hospede os arquivos `.woff2` em `public/` (a licença da Fontshare permite).

## Pendências conhecidas

Ficaram como estão para não mudar o design; são decisões de produto:

- **"Continuar com Google"** no cadastro só mostra "OAuth Google em breve" — o backend não tem login com Google.
- **CPF** no cadastro é pedido mas não é enviado (o backend não guarda CPF).
- **Passo 2 do cadastro** diz que o Open Banking está "em construção" e que avisa quando o banco escolhido ficar pronto — a conexão real já existe (tela Conexões) e a escolha não é gravada.
- **Feed**: mostra os alertas de `/alerts`; o motor de notificações (`/notifications`, 17 tipos de card com valores em R$) e o radar de oportunidades ainda não aparecem nesta aba.
- `src/components/OpportunityRadarCard.tsx`, `ComparadorInvestimentos.tsx` e `src/api/chat.ts`/`feed.ts` não são usados pelas telas atuais.
