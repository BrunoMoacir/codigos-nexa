# 10 — Defesa do Consumidor (D1–D6)

> O diferencial que nenhum banco ou app comissionado pode copiar: procurar
> ativamente cobranças ilegais/abusivas e montar o dossiê para o usuário
> reclamar — com base legal citada.

## Em palavras simples

Seguro que você nunca contratou, tarifa cobrada duas vezes, juros de rotativo
muito acima da média de mercado, tarifa que subiu sem aviso. A Nexa varre seu
extrato atrás desses padrões e, quando encontra, não só avisa: monta o dossiê
com as evidências, a base legal e o passo a passo — do "ligue e conteste" ao
ZIP pronto para o PROCON ou Juizado Especial Cível.

**Linguagem importa**: o sistema fala "forte indício", "acima da média",
"pode contestar" — nunca "você tem direito a R$ X" ou "é ilegal". Indício não
é sentença, e o código foi escrito para nunca prometer o que só um juiz decide.

---

## Como é calculado — os 6 detectores

### D1 — Venda casada (`tied_sale_detector.py`)

Três caminhos independentes de detecção:

**(a) Correlação temporal** — o mais forte. Procura um lançamento de produto
vinculado dentro de **7 dias** (`_CORRELATION_WINDOW_DAYS`) após a liberação de
um crédito **do mesmo banco**. Dois regex governam:

```
crédito:  \b(emprestimo|financiamento|credito|liberacao|credconsig|consig|pessoal|veicular|imob)\b
vinculado: \b(seguro|prestamista|capitalizacao|capitaliz|assistencia|protect|assisten|garantia)\b
```

Severidade `high`; a evidência registra o intervalo exato em dias.

A correlação é por **conta** (`account_id`), não por nome de banco. Crédito
caindo na conta X e débito saindo da conta X é um vínculo mais apertado que
"mesmo banco", e `account_id` está disponível — `bank_name` não. O nome legível
vem do enriquecimento do F5 (`institution_id` via `account_balances`) quando dá
para resolver; quando não dá, o achado sai com rótulo genérico em vez de não
sair.

> **Correção de 2026-08.** A guarda exigia a coluna `bank_name`, que
> `transactions_clean` não tem e `get_transactions_for_user` não devolve —
> `if not all([...]): return []`. D1a, o caminho mais forte, era **inteiramente
> morto em produção**: o caso de manual do Tema 972 (empréstimo de R$ 15 mil
> seguido de seguro prestamista três dias depois) não gerava achado nenhum.

**(b) Tipos de tarifa suspeitos** vindos do FeeDetector (doc 06):
`SEGURO_EMBUTIDO`, `SEGURO_PRESTAMISTA`, `TARIFA_CADASTRO`.

**(c) Histórico de tarifas** (`bank_fee_history`).

**Base legal citada**: CDC art. 39, I (venda casada) · CDC art. 51 (nulidade
de pleno direito) · **Tema 972/STJ** (abusividade do seguro prestamista sem
liberdade de escolha da seguradora) · Res. CMN 3.919/2010, art. 2º · Súmula
297/STJ + ADI 2.591/STF (CDC aplica-se a instituições financeiras).

**Disclaimer específico do D1**, embutido no achado:

> ⚠️ Este achado é um PRÉ-INDÍCIO que requer confirmação. Se você contratou
> livremente este produto, arquive este achado.

A ação recomendada começa por *"confirme se você escolheu livremente"* — o
detector não pode saber se houve imposição, só que houve correlação.

### D2 — Cobranças indevidas (`wrongful_charge_detector.py`)

Quatro verificações:

**(a) Duplicidade** — SQL sobre `bank_fee_history` agrupando por
`(banco, tipo)` no mês corrente com `HAVING COUNT(*) > 1`:

```
excedente   = total × (cnt − 1) / cnt        ← só o que passou de 1 cobrança
contestável = excedente × multiplicador
```

**A regra do dobro é datada** (`_multiplicador_dobro`), seguindo o **EAREsp
676.608/STJ**:

```
cobrança ≥ 30/03/2021  → multiplicador 2,0  ("em dobro")
cobrança  < 30/03/2021 → multiplicador 1,0  ("simples, sem dobro")
```

O rótulo apresentado ao usuário explicita qual regra se aplicou e por quê.
Esse tipo de precisão é o que separa um dossiê utilizável de um chute.

**(b) Serviços essenciais** — cobranças que deveriam ser gratuitas.

**(c) Bancos "stale"** — tarifa cobrada por banco **sem nenhuma transação nos
últimos 60 dias** (`_STALE_DAYS`): conta inativa continuando a gerar tarifa.

**(d) Tarifas novas** sem histórico anterior (severidade `medium`).

**Base legal**: CDC art. 42, parágrafo único (repetição do indébito).

### D3 — Juros abusivos (`abusive_interest_detector.py`)

Compara a taxa do usuário com a média de mercado **como múltiplo**:

```
multiple = taxa_usuário / taxa_mercado
```

| Múltiplo | Severidade | Rótulo apresentado |
|---|---|---|
| ≥ 3,0× | `high` | **"forte indício"** |
| ≥ 1,5× | `medium` | **"indício relevante"** |
| ≥ 1,0× | `low` | **"atenção"** |
| < 1,0× | — | nenhum achado |

Os rótulos são o vocabulário calibrado do produto — nunca "ilegal", nunca
"você tem direito a".

Taxas de mercado vivas via BACEN Olinda (`taxaJuros` por instituição) com
fallback nas séries SGS. **Fallback fixo** (mar/2026):

| Modalidade | Taxa mensal |
|---|---|
| Rotativo | 15,67% |
| Rotativo (máximo) | 17,70% |
| Cheque especial | 10,80% |
| Consignado | 1,75% |

> O próprio código carrega um alerta: *"validar unidade da série 20714 antes de
> usar em produção — pode ser % a.a."*. É um risco conhecido e anotado, não
> resolvido.

> **Duas correções de 2026-08 no D3.**
>
> 1. `_INTEREST_PATTERN` procurava `\bjuro\b` e `\bencargo\b` no **singular**.
>    Extrato escreve "JUROS", "ENCARGOS" — "JUROS EMPRESTIMO", "ENCARGOS FATURA"
>    e "JUROS SOBRE SALDO DEVEDOR" não casavam. Só passava quando havia
>    "rotativo" na mesma descrição.
>
>    O padrão é deliberadamente **mais largo** que o `JUROS_ROTATIVO` do F5 e os
>    dois não devem ser unificados: lá o objetivo é classificar uma *tarifa* de
>    rotativo (e por isso exige contexto de cartão/fatura, para não capturar
>    juro de empréstimo, que é custo legítimo); aqui é encontrar *qualquer*
>    encargo para comparar com o mercado.
>
> 2. As três fontes de taxa falavam vocabulários diferentes: o Olinda devolve
>    `rotativo`, o BacenCredit e o fallback devolvem `rotativo_monthly`, e o
>    consumidor lia `market["rotativo_monthly"]`. Com o Olinda respondendo, o
>    KeyError era engolido pelo `except` e o detector devolvia lista vazia — ou
>    seja, **o D3 só funcionava quando o dado de mercado falhava**. Agora
>    `_normalizar_taxas()` põe tudo no mesmo sufixo na fronteira.

**Base legal**: CDC art. 51, IV · Tema 27/STJ (REsp 1.061.530/RS) · STJ 3ª
Turma 2023 · Súmula 297/STJ · ADI 2.591.

### D4 — Mudança unilateral de tarifa (`unilateral_change_detector.py`)

Compara mês a mês a mesma `(user, banco, fee_type)` em `bank_fee_history`:

```
se cur_amt ≤ prev_amt  → não é achado
increase_pct = (cur_amt − prev_amt) / prev_amt
disputed     = cur_amt − prev_amt
```

| Aumento | Severidade |
|---|---|
| ≥ 25% | `high` |
| ≥ 10% | `medium` |
| > 0% | `low` |

O docstring é explícito sobre a semântica: *"o percentual decide SEVERIDADE,
não existência do achado. Qualquer aumento sem aviso prévio é contestável."*

Verificação adicional: tarifa **acima do teto BACEN** (`high`).

### D5 — Central de Evidências (`evidence_builder.py`)

Consolida D1–D4 num dossiê e gera **4 documentos**, empacotados num ZIP:

```
00_LEIA_ME.txt            — aviso legal + trilha de canais
01_carta_contestacao.txt  — carta para SAC/Ouvidoria
02_relato_procon.txt      — relato para PROCON / Consumidor.gov.br
03_peticao_jec.txt        — modelo de petição para o JEC
04_resumo_achados.txt     — resumo dos indícios
```

**Trilha de escalonamento embutida no LEIA-ME:**

1. SAC (5 dias úteis) → 2. Ouvidoria (10 dias úteis) → 3. Consumidor.gov.br →
4. BACEN (bcb.gov.br/meubc) → 5. PROCON → 6. **JEC sem advogado até R$ 28.200**

**Correção monetária** (`calc_monetary_correction`) — não é estimativa:

- **IPCA (SGS 433) / INPC (SGS 188)**: busca as taxas mensais reais da API e
  acumula período a período —
  `fator = Π (1 + taxa_mensal_i / 100)`;
- **SELIC**: taxa anual do BacenConnector elevada ao período em dias —
  `fator = (1 + selic_anual)^(dias/365)`;
- **Fallback** quando a API falha: taxa anual histórica proporcional aos dias
  (IPCA 5,12% a.a., INPC 5,60% a.a., SELIC 14,25% a.a.).

O resultado reporta `monthly_rates_used` — quantos meses reais entraram no
cálculo. Zero significa que o fallback foi usado, e isso fica visível.

### D6 — Portabilidade total (`portability_detector.py`)

Simula a economia de migrar conta + cartão + crédito para outro banco,
cruzando F5 (tarifas) + F2 (cartões) + OPP (rendimento). Duas entradas: os
empréstimos ativos do usuário (`_check_from_loans`, com inferência de
modalidade) e o histórico de negociação. Economia estimada por diferença
simples de juros contra a melhor taxa de mercado da modalidade.

**Base legal**: Res. CMN 5.057/2022 (portabilidade gratuita).

---

## Como funciona (técnico)

- **Endpoints**: `GET /defense/{user_id}` (análise consolidada),
  `/{user_id}/dossier`, `/{user_id}/zip` (download), `/{user_id}/portability`.
- 6 tools no agente (`detect_abusive_fees`, `detect_wrongful_charges`,
  `detect_abusive_interest`, `get_defense_analysis`, `get_evidence_dossier`,
  `get_portability_analysis`).
- Cada `DefenseFinding` carrega: `detector`, `severity`, `bank_name`, título,
  descrição, valor em discussão, **base legal**, disclaimer educacional e ação
  recomendada em 3 níveis (negociar → reclamar no BACEN → advogado/JEC).
- Gating: plano Total.

## O que NÃO faz

- **Não protocola nada** — o usuário leva o dossiê ao PROCON/JEC; a Nexa não
  peticiona nem representa juridicamente.
- **Não afirma ilegalidade** — entrega indícios documentados e orienta
  validação por advogado quando o caso é grande.
- **Não detecta fraude de terceiros** (cartão clonado) — o foco é a relação
  usuário × banco.

## Gaps e limitações

- **⚠️ Bloqueador de lançamento**: D5/D6 têm código pronto, mas os templates
  de dossiê/petição **nunca passaram por revisão de advogado** — política do
  projeto é não lançar D5 sem parecer jurídico (responsabilidade por
  orientação incorreta).
- **⚠️ Unidade da série BACEN 20714 não validada** — o código anota que pode
  ser % a.a. em vez de % a.m. Se for, o múltiplo do D3 sai errado por ordem de
  grandeza. Validar antes de produção.
- **D1 é correlação, não prova.** Sete dias entre crédito e seguro é um
  indício estatístico; o usuário pode ter contratado o seguro por vontade
  própria. Daí o disclaimer de "pré-indício" e a ação começando por
  "confirme".
- **D2 e D4 dependem de `bank_fee_history` populado** pelo job das 02h00 — um
  usuário novo não tem baseline pessoal e os dois detectores ficam mudos.
- **A correção monetária cai em fallback anual** quando a API do SGS falha,
  perdendo precisão mensal — o campo `monthly_rates_used = 0` denuncia isso,
  mas o valor ainda é apresentado.
- **D4 e o futuro ranking público de bancos (V3)** dependem de massa de dados
  em `bank_fee_trends`; com poucos usuários, o baseline é o curado.
- **Recuperações não são rastreadas automaticamente** — o usuário reporta o
  desfecho; não há integração com a resposta do banco.
