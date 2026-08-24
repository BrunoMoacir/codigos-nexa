# 14 — Engajamento e Retenção (MX, R, V)

> O conjunto que faz o usuário VOLTAR: um número que resume sua vida
> financeira, metas com projeção, desafios com badges, comparação com pares,
> notificações que chegam sozinhas e o "Wrapped" compartilhável.

## Em palavras simples

Apps financeiros morrem no mês 4: o usuário arruma a casa e não volta. Esta
camada existe para criar razões de retorno diário (margem do dia na
homescreen, digest matinal), semanal (desafios, score) e anual (Wrapped
estilo Spotify).

---

## Como é calculado

### MX.1 — Health Score e Resilience Score (`etl/profiles.py`)

Existem **dois scores**, e a distinção importa. (Havia um terceiro, calculado
inline no `forecast/router.py`, removido em 2026-08-23 — ver a seção de
correções.)

**`financial_health_score` (0–100) — 3 fatores**, mantido por
retrocompatibilidade com o banco:

| Fator | Pontos |
|---|---|
| **Taxa de poupança** (50 pts) | ≥25% → 50 · ≥15% → 45 · ≥10% → 40 · ≥5% → 30 · ≥0% → 20 · <0 → 0 |
| **Renda > despesa** (30 pts) | renda > despesa → 30 · diferença < 2% → 20 · renda ≥ 95% da despesa → 10 · senão 0 |
| **Proporção despesa/renda** (20 pts) | <60% → 20 · <75% → 15 · <85% → 10 · <95% → 7 · <100% → 5 · ≥100% → 0 |

**`resilience_score` (0–100) — 6 fatores**, o que efetivamente alimenta o
`pressure_score` e o FSS:

| # | Fator | Pontos | Faixas |
|---|---|---|---|
| 1 | Taxa de poupança | 25 | ≥20% → 25 · ≥10% → 20 · ≥5% → 12 · ≥0 → 5 · <0 → 0 |
| 2 | Equilíbrio renda/gasto | 20 | folga ≥5% → 20 · positivo → 15 · ±2% → 8 · leve déficit → 3 |
| 3 | Proporção gasto/renda | 15 | <60% → 15 · <75% → 12 · <85% → 8 · <95% → 4 · ≥95% → 0 |
| 4 | **Tendência dos gastos** | 20 | DECRESCENTE → 20 · ESTÁVEL → 15 · **CRESCENTE → 0** |
| 5 | Obrigações comprometidas | 10 | <30% → 10 · <50% → 7 · <70% → 4 · <90% → 1 · ≥90% → 0 |
| 6 | Estabilidade da renda | 10 | `round(income_stability × 10)`; sem `confidence ≥ 0,4` → 0,5 neutro (5 pts) |

O fator 4 é o mais opinativo: gastos crescendo zeram 20 dos 100 pontos, com a
justificativa no código — *"gastos crescendo = piora iminente"*. Direção pesa
tanto quanto nível.

**Tendência do score** (`_compute_trend`): IMPROVING se subiu ≥ 3 pontos vs.
3 meses atrás; DECLINING se caiu ≥ 3; senão STABLE. Snapshot diário via job
04h00 → `health_score_history`. Card `SCORE_IMPROVED` quando varia ≥ 5 pontos.

**Perfil derivado**: poupança ≥ 20% → CONSERVADOR · ≥ 10% → EQUILIBRADO ·
< 10% → GASTADOR.

### MX.2 — Metas (`app/goals/tracker.py`)

```
progress_pct = min(100, current_amount / target_amount × 100)
monthly_needed = (target − current) / meses_restantes
gap = monthly_needed − contribuição_mensal_real
```

**Viabilidade** (`_derive_feasibility`), pela razão do gap:

| Viabilidade | Condição |
|---|---|
| EASY | no ritmo, ou `gap ≤ 0` |
| MODERATE | `gap / monthly_needed ≤ 25%` |
| HARD | `≤ 50%` |
| UNREALISTIC | `> 50%` |

Dizer "UNREALISTIC" é uma decisão de produto — a meta impossível é sinalizada
como impossível, não maquiada.

**Concorrência otimista**: coluna `version` na tabela; o tracker detecta se a
coluna existe (`_detect_version_column`) e degrada se não. Cards
`GOAL_PROGRESS` em 50/75/100%.

### R2.b — Desafios mensais (`health_score/challenge_service.py`)

**Máximo 3 desafios por mês** (`_MAX_CHALLENGES_PER_MONTH`), de 4 tipos:

| Tipo | Alvo | Progresso / falha |
|---|---|---|
| `SEM_TARIFAS` | 0 tarifas no mês | % do mês decorrido sem tarifa; **FAILED na 1ª tarifa** |
| `REDUZIR_CATEGORIA` | gastar **15% menos** que a média trimestral (`_CATEGORY_CUT_PCT`), só em categorias com **≥ R$ 200/mês** | % do mês dentro do teto; FAILED ao estourar |
| `GUARDAR_VALOR` | **10% da renda mensal** (`_SAVE_TARGET_INCOME_PCT`), piso R$ 50 | % do alvo poupado; COMPLETED ao atingir, mesmo antes do fim do mês |
| `SUBIR_SCORE` | **+3 pontos** no health score (`_SCORE_TARGET_DELTA`) | % dos pontos-alvo ganhos |

O filtro de gasto mínimo tem justificativa explícita no código: *"desafio de
R$ 40/mês não motiva ninguém"*. Categorias fixas/não-discricionárias são
excluídas do `REDUZIR_CATEGORIA`.

Ciclo completo: geração no início do mês → progresso → conclusão → fechamento
na virada → badges (incluindo streaks), persistidos em `user_badges`.

**Quarto status: `SEM_DADOS`.** No fechamento, desafio cuja janela não teve
NENHUMA transação não é julgado — não vira COMPLETED nem FAILED. Sem isso, os
dois desafios que medem *ausência* de coisa ruim (`SEM_TARIFAS`,
`REDUZIR_CATEGORIA`) fechavam como vitória quando o banco estava desconectado,
enquanto os que medem *presença* de coisa boa fechavam como derrota. O notifier
só emite card para `COMPLETED` e `ACTIVE`, então `SEM_DADOS` não gera
recompensa nem conta como concluído.

O alvo do `GUARDAR_VALOR` usa a **renda filtrada pelo `IncomeProfiler`**, não a
soma bruta dos créditos — Pix recebido, estorno e transferência entre contas
próprias inflavam o denominador e produziam meta inalcançável.

### MX.4 — Peer Comparison (`app/peers/peer_comparison.py`)

Benchmarks da **POF/IBGE 2022-2023** (% da renda líquida), por 4 faixas de
renda. Exemplo da faixa BAIXA (até R$ 3.000/mês):

```
moradia 40% · alimentação 27% · transporte 11% · saúde 6%
lazer 3% · educação 2% · vestuário 2% · …
```

**Offsets por cluster** somados ao benchmark de faixa: o mesmo perfil de renda
gasta diferente conforme o estilo de vida, então o benchmark efetivo é
`benchmark_da_faixa + offset_do_cluster`. A fonte reportada muda de
`"IBGE/POF 2022-2023"` para `"IBGE/POF 2022-2023 + cluster X"` — o usuário sabe
contra o que está sendo comparado.

Percentil de poupança estimado pelo desvio vs. a faixa
(`_savings_percentile_label`). **Anônimo por construção**: é benchmark público
agregado, nunca dados de outros usuários.

### MX.5 — Budget Advisor (`app/budget/budget_advisor.py`)

Regra 50/30/20 como padrão (essenciais / desejos / poupança), com
**tolerância de ±3 p.p.** antes de sinalizar OVER/UNDER.

**5 clusters têm meta própria**, e cada um traz a justificativa mostrada ao
usuário:

| Cluster | Regra | Racional codificado |
|---|---|---|
| `EXPLORADOR_GLOBAL` | **47/35/18** | "viagem é estilo de vida, não desperdício" |
| `INVESTIDOR_CAUTELOSO` | **50/20/30** | poupança elevada para alimentar aportes |
| `ESTRESSE_FINANCEIRO` | **55/15/30** | ⚠️ desejos cortados a 15%, reserva priorizada — "estabilize antes de qualquer gasto discricionário" |
| `FAMILIA_ESTRUTURADA` | **55/25/20** | "escola, saúde e alimentação naturalmente ultrapassam os 50%" |
| `MICROEMPREENDEDOR` | **50/30/20** | ⚠️ "considera SOMENTE o fluxo pessoal (PF)" |

Clusters não listados herdam o 50/30/20 padrão. O caso do
`ESTRESSE_FINANCEIRO` é notável: o orçamento **aumenta** a meta de poupança
para 30% justamente para quem está apertado — porque o objetivo ali é reserva
de emergência, não conforto.

### MX.3 + R1.b — Notificações proativas (`app/notifications/`)

**17 tipos de card**, gerados a cada 6h pelo `NotificationEngine`, filtrados
pelo Filtro de Relevância (doc 13) e entregues por e-mail / in-app / Web Push
(VAPID — WARNING e CRITICAL sobem para push quando há inscrição PWA).

**A dedup é por TTL específico do tipo** (`state_store._SEEN_TTL_DAYS`), e cada
valor é uma decisão de produto:

| Tipo | TTL (dias) | Racional |
|---|---|---|
| `SAFE_TO_SPEND_LOW` | 1 | muda todo dia |
| `BURN_RATE_HIGH` | 3 | |
| `TRANSFER_PROMO` | 3 | promoção é efêmera |
| `ANOMALY_DETECTED` | 7 | |
| `WAIVER_ALERT` | 7 | |
| `CHALLENGE_PROGRESS` | 7 | "no máx. 1 empurrão por semana" |
| `FISCAL_SEASON` | 10 | "~2–3 lembretes por janela fiscal" |
| `CARD_OPPORTUNITY` | 14 | |
| `IDLE_MONEY_DETECTED` | 14 | "oportunidade persiste; não martelar diariamente" |
| `SUBSCRIPTION_INCREASE` | 30 | |
| `SCORE_IMPROVED` | 30 | |
| `GOAL_PROGRESS` | 30 | |
| `LIFE_EVENT` | 30 | |
| `SAVINGS_BELOW_CDI` | 30 | "dado macro, um lembrete por mês basta" |
| `CHALLENGE_COMPLETED` | 30 | "conclusão é evento único no mês" |
| `PURCHASE_FOLLOWUP` | 30 | "cada compra gera no máx. 1 card" |
| (default) | 7 | |

A dedup usa **fingerprint** do conteúdo, não só o tipo — a mesma anomalia não
reaparece, mas uma anomalia nova passa.

Guarda extra contra retrabalho: `_has_recent_idle_snapshot` exige um snapshot
recente com saldo ocioso ≥ R$ 500 antes de recalcular — *"sem isso, cada
rodada de 6h refaria"* a análise inteira.

### R1.c / R1.d / V1 / V2 / R3

- **Daily Digest** (job 07h00): e-mail com score, tarifas, oportunidades,
  prazos fiscais e desafios. Idempotente via `daily_digest_log`.
- **Widget PWA**: página `/widget` instalável + Web Push; payload ~200 bytes
  (fórmula no doc 02).
- **V1 Placar de Economia** e **V2 Nexa Wrapped**: SVG compartilhável — quanto
  cada banco lucrou com você, tarifas evitáveis, evolução do score. CAC zero
  por compartilhamento.
- **R3 Histórico acumulado**: DuckDB + séries temporais — quanto mais tempo de
  uso, mais insight; custo de troca crescente (retenção estrutural).

---

### As correções de 2026-08-23

**Havia três health scores, não dois.** Além do `financial_health_score`
(3 fatores) e do `resilience_score` (6 fatores), o `forecast/router.py`
calculava um terceiro inline:

```python
savings_score  = min(70.0, savings_rate * 5.0 * 70.0)
spending_score = (1.0 - income_ratio) * 30.0
```

Divergência de até **47 pontos** contra o oficial:

| poupança | 3 fatores | fórmula inline |
|---|---|---|
| 2% | 55 | **8** |
| 10% | 77 | 38 |
| 20% | 85 | 76 |

O pior não era existir: era *quando* entrava. O inline era calculado e depois
sobrescrito sempre que o `UserProfileAnalyzer` funcionava — código morto no
caminho feliz. Ele só chegava ao usuário quando `analyze()` levantava exceção,
engolida num `logger.debug`. Um erro silencioso mudava o score em meia escala.

E o `profile_type` **nunca** era sobrescrito, então o payload saía com score de
uma régua e rótulo de outra: poupança de 22% aparecia como "EQUILIBRADO"
(régua do router) com score de "CONSERVADOR" (régua do analyzer). O rótulo
`POUPADOR`, que o router emitia acima de 40%, nem existe no vocabulário do
analyzer.

O `trend` vinha de `income_stability`: renda instável virava "CRESCENTE", muito
instável virava "DECRESCENTE" — palavras que em todo o resto do produto
significam direção de **gasto**.

Agora há `_perfil_e_score()`: com o analyzer, usa o resultado dele; sem ele,
aplica os **mesmos métodos** sobre o que sobrou, em vez de uma segunda fórmula.
O `except` subiu de `debug` para `warning`.

**O card compartilhável somava unidades diferentes.**
`negotiation_history.potential_gain` recebe `opp.potential_saving_monthly` —
valor MENSAL. As outras três fontes do consolidador anualizam; esta somava o
mensal direto em `annual_savings_brl`:

```
Otimizador   R$ 1.200,00/ano   (já anual)
Raio-X       R$   780,00/ano   (65/mês × 12)
Radar        R$ 1.080,00/ano   (90/mês × 12)
Negociador   R$   180,00/ano   ← 180/mês SEM ×12

anunciado R$ 3.240,00   |   correto R$ 5.220,00
```

**E somava a mesma coisa duas vezes.** O Raio-X mede tarifas efetivamente
cobradas, entre elas `ANUIDADE_CARTAO` e `JUROS_ROTATIVO`; o Negociador estima
o que se pouparia negociando exatamente essa anuidade e esses juros
(`ANUIDADE_ALTA`, `JUROS_ROTATIVO_ALTO`). Os dois erros apontavam em direções
opostas e se mascaravam no total. Ficou o Raio-X, que é medição e não
estimativa, e a exclusão está declarada na descrição mostrada ao usuário.

**Desconectar o banco ganhava dois dos quatro desafios** — ver `SEM_DADOS`
acima. O teste que existia afirmava o defeito: passava lista vazia de
transações e esperava `COMPLETED`.

### A revalidação de 2026-08-24

As quatro correções acima seguem travadas (mutações M1–M4, todas pegas: 15, 2,
1 e 5 testes falham ao reverter cada uma). Três coisas a mais foram verificadas
em vez de supostas:

**As outras três fontes do consolidador estão na unidade certa** — o
Negociador era o único caso, e agora está medido, não presumido:

| fonte | campo | unidade na origem | o consolidador faz |
|---|---|---|---|
| F2 Optimizer | `best_card.net_gain_expected` | **anual** (todo consumidor divide por 12) | usa direto ✅ |
| F5 Raio-X | `savings_opportunity` | **mensal** | × 12 ✅ |
| OPP Radar | `top_gain_brl` ← `top.monthly_gain_brl` | **mensal** | × 12 ✅ |
| F13 Negociador | `potential_gain` ← `potential_saving_monthly` | **mensal** | × 12 (corrigido) |

**`SEM_DADOS` não vaza por nenhuma porta lateral.** `_close_past_months` só
converte `ACTIVE` em `FAILED` e preserva `SEM_DADOS`; `_completed_months`, que
alimenta streak e badge, conta apenas `COMPLETED`. O comentário de contrato em
`health_score/router.py` (`ChallengeItem.status`) ainda listava três estados —
era o que o cliente lê — e passou a listar os quatro.

**O que não é de engajamento e apareceu aqui:** o teste instável de
`tests/purchase/` que ficou registrado na rodada anterior tinha causa real, e é
de conector — ver "A correção de 2026-08-24" em
[04-architect-simulacoes.md](04-architect-simulacoes.md#10-taxas-vivas-e-fallback).
A SELIC vinha da série SGS 4390 (% ao **mês**) tratada como % ao ano quando a
série 432 dava timeout: `0,0078` no lugar de `0,14`. Não tem nada a ver com o
estado compartilhado do banco, que era a suspeita anterior.

## O que NÃO faz

- **Sem dark patterns**: nenhuma notificação de "volte para o app" vazia —
  todo card precisa passar no filtro de relevância com valor em R$ ou prazo.
- Peer comparison não expõe dados de outros usuários (só benchmark público).
- Wrapped não posta sozinho — gera a imagem; compartilhar é decisão do
  usuário.

## Gaps e limitações

- **Dois scores coexistem** (`financial_health_score` de 3 fatores e
  `resilience_score` de 6). O primeiro só existe por compatibilidade com o
  banco, mas ainda é o que aparece como "health score" em parte da API —
  fonte de confusão real. O terceiro, inline no router, foi removido.
- **`ProfileType` tem dois literais divergentes**: o schema aceita
  `POUPADOR`, o analyzer só produz `CONSERVADOR | EQUILIBRADO | GASTADOR`. O
  valor extra deixou de ser emitido, mas o literal segue no schema por
  compatibilidade com dado já gravado.
- **As faixas de pontuação são calibradas por julgamento**, não por
  correlação com desfecho financeiro observado. "Poupança ≥ 25% vale 50
  pontos" é uma escolha de produto, não um achado empírico.
- **Peer comparison usa benchmarks IBGE hardcoded** — precisam de atualização
  manual a cada nova POF, e os offsets por cluster são estimativas internas
  sem validação externa.
- **As metas de orçamento por cluster também são julgamento** (47/35/18 para
  viajante etc.) — plausíveis, não validadas.
- **R4.a relatório trimestral**: falta (job pequeno; scheduler pronto).
- **R5 anti-churn** (tela de cancelamento com impacto, modo pausa, win-back):
  depende do billing estar ativo.
- **V3 ranking público de bancos**: aguarda massa de dados D1–D3.
- **Push nativo mobile (FCM) não existe** — Web Push cobre PWA; retenção de
  massa pedirá app nativo.
- **Share rate do Wrapped/Placar não é medido** (analytics de
  compartilhamento é frontend).
