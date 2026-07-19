# 15 — Agente de IA (Chat)

> O consultor conversacional: você pergunta em português ("posso comprar um
> carro de R$ 60 mil?") e ele consulta os módulos do backend antes de
> responder — com tom adaptado ao seu perfil.

## Em palavras simples

O chat não é um chatbot que "acha" — é um agente que TEM as ferramentas: para
responder sobre o carro, ele consulta sua projeção de caixa, roda a simulação
de financiamento e olha seu perfil, e só então responde. Se você é do cluster
"estresse financeiro", o tom muda (empatia, foco em cortes, zero sugestão de
gasto). A conversa continua de onde parou (memória por sessão).

## O que faz

- **Agente ReAct via LangGraph** (`app/agent/graph.py`): o LLM pensa → decide
  qual ferramenta chamar → observa o resultado → repete → responde.
- **31 ferramentas** (`app/agent/tools/` — 1 arquivo por tool) cobrindo TODOS
  os domínios: perfil/forecast/alertas/metas, orçamento/pares,
  cartões (2), compras (2), simulações F3 (3), oportunidades (3),
  defesa (6), custos/negociação (2), fiscal/direitos (3),
  desafios/wrapped (2), promoções de transferência (1), plano/billing (1).
- **Regra de produto**: a primeira tool de toda sessão é
  `get_user_profile_context` — carrega o cluster comportamental e adapta o
  tom da conversa inteira.
- **Memória por sessão**: checkpointer Redis (histórico persistido;
  `chat_messages` no banco para histórico do usuário).
- **LLM**: Claude via `langchain-anthropic` (preferencial) com fallback
  OpenAI — configurável (`LLM_PROVIDER`).

## Segurança (mitigação de prompt injection)

- O `user_id` autenticado é **injetado pelo sistema** como prefixo `[user_id=...]` documentado no prompt como protocolo inegociável; o corpo da mensagem é **sanitizado** (qualquer `[user_id=...]` forjado pelo usuário é removido antes do LLM);
  o agente é instruído a IGNORAR qualquer user_id que apareça na mensagem do
  usuário — impossibilita "me mostra os dados do usuário X" via chat.
- O endpoint valida `chat_request.user_id == current_user` (403 se divergir)
  antes de qualquer processamento.
- Rate limit 20/min por usuário; sem chave de LLM configurada → 503 com
  mensagem clara (nunca resposta fabricada).

## Como funciona (técnico)

- **Endpoint**: `POST /chat/` (+ histórico por sessão).
- `graph.py::build_financial_agent()` monta o grafo; `singleton.py` mantém a
  instância; `state.py` o estado tipado.
- Gating: 5 mensagens/dia no plano Free (contador `chat_messages`).
- Padrão feed+chat: toda feature nova entra como card no feed E tool no chat —
  o agente nunca fica sabendo menos que a interface.

## O que NÃO faz

- **Não executa transações** — nenhuma tool movimenta dinheiro; todas são
  leitura/simulação.
- **Não responde fora do domínio financeiro do usuário** — sem tool para a
  pergunta, ele diz o que não sabe em vez de inventar.
- **Não dá recomendação de investimento regulada** (CVM) — compara produtos
  com disclaimer; decisão é do usuário.

## Gaps e limitações

- Custo por conversa depende do LLM externo (Claude/OpenAI) — cache de
  sessão reduz, mas chat ilimitado (Pro) precisa de monitoramento de custo
  por usuário (métrica ainda não instrumentada).
- Streaming de resposta (token a token) não implementado — resposta chega
  completa; UX de espera é do frontend.
- Avaliação sistemática de qualidade das respostas (evals) não existe — os
  testes cobrem o mecanismo (tools chamadas, contexto injetado), não a
  qualidade da prosa.
