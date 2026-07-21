# 14 — Engajamento e Retenção (MX, R, V)

> O conjunto que faz o usuário VOLTAR: um número que resume sua vida
> financeira, metas com projeção, desafios com badges, comparação com pares,
> notificações que chegam sozinhas e o "Wrapped" compartilhável.

## Em palavras simples

Apps financeiros morrem no mês 4: o usuário arruma a casa e não volta. Esta
camada existe para criar razões de retorno diário (margem do dia na
homescreen, digest matinal), semanal (desafios, score) e anual (Wrapped
estilo Spotify: "seu banco lucrou R$ 3.200 com você em 2026").

## O que faz

### MX.1 Health Score (`app/health_score/`)
- Score 0–100 da saúde financeira com tendência (30/90 dias) e histórico
  (snapshot diário via job 04h00 → `health_score_history`).
- Card `SCORE_IMPROVED` quando varia ≥5 pontos.

### MX.2 Metas (`app/goals/`)
- CRUD de metas com projeção de prazo ("nesse ritmo, sua reserva fica pronta
  em 7 meses"), progresso automático via transações, controle de concorrência
  otimista (coluna `version`). Cards `GOAL_PROGRESS` em 50/75/100%.

### R2.b Desafios mensais e badges (`health_score/challenge_service.py`)
- 4 tipos personalizados pelos dados: `SEM_TARIFAS`, `REDUZIR_CATEGORIA` (a
  categoria que mais cresce), `GUARDAR_VALOR`, `SUBIR_SCORE`. Ciclo completo:
  geração no início do mês → progresso → conclusão → fechamento na virada →
  badges (streaks incluídos). Validado por e2e contra Postgres real.

### MX.4 Peer Comparison (`app/peers/`)
- "Você gasta 40% mais em delivery que pares da sua renda" — benchmarks da
  POF/IBGE 2022-23 ajustados, por 4 faixas de renda (até 3k, 3–8k, 8–20k,
  20k+). Anônimo por construção (benchmark agregado, não dados de outros
  usuários).

### MX.5 Budget Advisor (`app/budget/`)
- Orçamento 50/30/20 adaptado ao padrão REAL: "Essenciais em 58% (ideal 50%) —
  reduza R$ 380/mês em alimentação". Alimenta burn rate e cards.

### MX.3 + R1.b Notificações proativas (`app/notifications/`)
- **17 tipos de card** (burn rate, anomalia, assinatura que subiu, cashback
  perdido, isenção de anuidade próxima, score, metas, margem baixa, eventos de
  vida, tarifa unilateral, poupança sub-CDI, dinheiro parado, janela fiscal,
  desafios, compra subótima...), gerados a cada 6h pelo `NotificationEngine`,
  filtrados por relevância (doc 13), entregues por e-mail/in-app/**Web Push**
  (VAPID; WARNING/CRITICAL sobem para push quando há inscrição PWA), com dedup
  por TTL por tipo e idempotência.

### R1.c Daily Digest (job 07h00)
- E-mail diário: score, tarifas, oportunidades, prazos fiscais, desafios.
  Idempotente (`daily_digest_log`).

### R1.d Widget PWA
- Página `/widget` instalável na homescreen + Web Push. Payload ~200 bytes.

### V1/V2 Viral (`app/viral/`)
- **Placar de Economia** compartilhável (SVG): total economizado "contra os
  bancos". **Nexa Wrapped** anual (SVG): quanto cada banco lucrou com você,
  tarifas evitáveis, evolução do score. CAC zero por compartilhamento.

### R3 Histórico acumulado
- DuckDB + séries temporais: quanto mais tempo de uso, mais insight — custo
  de troca crescente (retenção estrutural).

## O que NÃO faz

- **Sem dark patterns**: nenhuma notificação de "volte para o app" vazia — 
  todo card precisa passar no filtro de relevância com valor em R$ ou prazo.
- Peer comparison não expõe dados de outros usuários (só benchmark público).
- Wrapped não posta sozinho — gera a imagem; compartilhar é decisão do
  usuário.

## Gaps e limitações

- **R4.a relatório trimestral**: falta (job pequeno; scheduler pronto).
- **R5 anti-churn** (tela de cancelamento com impacto, modo pausa, win-back):
  depende do billing estar ativo.
- **V3 ranking público de bancos**: aguarda massa de dados D1–D3.
- Push nativo mobile (FCM) não existe — Web Push cobre PWA; retenção de massa
  pedirá app nativo.
- Share rate do Wrapped/Placar ainda não é medido (analytics de
  compartilhamento é frontend).
