# 06 — Raio-X de Custos (F5)

> Encontra as cobranças que o banco faz e você não sabia que tinha — e, quando
> dá para saber de qual banco vieram, mostra se estão acima do mercado.

## Em palavras simples

Tarifa bancária é desenhada para passar despercebida: R$ 24,90 aqui, R$ 12 de
"manutenção" ali, um seguro prestamista que ninguém lembra de ter contratado.
O Raio-X varre o extrato e devolve **cada cobrança, itemizada**.

O output que move o produto é essa lista, não o total anual. "Seu banco te cobra
um seguro prestamista de R$ 38,90 que você não pediu" é acionável; "você paga
R$ 487/ano em tarifas" é interessante uma vez e não muda comportamento nenhum.
A lista é o insumo da Defesa do Consumidor (doc 10) e do Negociador (doc 08) —
o Raio-X é infraestrutura delas antes de ser uma tela.

**O que ele deliberadamente NÃO promete**: economia em reais por trocar de banco
quando a instituição não foi identificada. Comparar o custo de alguém contra a
média de bancos que talvez nem sejam os dele não é benchmark, é ruído com casas
decimais — ver "Reposicionamento de 2026-08" nos gaps.

---

## Como é calculado

### 1. Detecção de tarifas (`costs/fee_detector.py`)

Filtra `amount < −R$ 0,50` (`_MIN_FEE_VALUE` — descarta micro-cobranças
isoladas) e roda **9 padrões regex em ordem, do mais específico ao mais
genérico**; o primeiro que casar define o tipo:

| # | Tipo | Regex |
|---|---|---|
| 1 | `ANUIDADE_CARTAO` | `\banuidade\b\|\bannual.?fee\b` |
| 2 | `SEGURO_PRESTAMISTA` | `\bseguro\s+(prestamista\|vida\|credito\|credit)\b` |
| 3 | `SEGURO_EMBUTIDO` | `\bseguro\s+(habitacional\|automovel\|residencial\|protecao\|garantia\|cobertura)\b` |
| 4 | `PACOTE_SERVICOS` | `\bpacote\s+(de\s+)?(servicos?\|tarifas?)\b` |
| 5 | `JUROS_ROTATIVO` | `\bjuros\b\|\bencargo\b\|\brotativo\b` |
| 6 | `IOF` | `\biof\b\|\bimposto\s+sobre\s+operac` |
| 7 | `SAQUE` | `\bsaque\b` |
| 8 | `TED_DOC` | `\b(ted\|doc)\b(?!.*pix)` ← **exclui quando o contexto é PIX** |
| 9 | `TARIFA_MANUTENCAO` | `\btarifa\b\|\btaxa\s+(de\s+)?(manutencao\|conta\|servico\|cadastro)\b\|\bcusto\s+(de\s+)?conta\b\|\bmensalidade\s+(conta\|cartao)\b` |

A ordem é o mecanismo de desambiguação: "seguro prestamista" casaria também em
`TARIFA_MANUTENCAO` se a genérica viesse antes. E o negative lookahead do
`TED_DOC` evita classificar "DOC PIX" como tarifa de DOC.

**Resolução do banco**, em duas camadas:
1. `INSTITUTION_ID_MAP` — mapeia o `institution_id` do Pluggy (aceitando tanto
   o slug quanto o código COMPE: `"291"`/`"nubank"` → Nubank, `"341"`/`"itau"`
   → Itaú, `"001"` → Banco do Brasil, `"104"` → Caixa, `"077"` → Inter,
   `"336"` → C6…);
2. **Fallback por keyword na descrição** — 11 regex com fronteira de palavra
   (`\bnubank\b`, `\bitau\b`, `\bc6\b`…).

### 2. Consolidação (`costs/bank_fee_analyzer.py`)

```
monthly_avg      = total_de_tarifas / meses_analisados
annual_projection = monthly_avg × 12
```

Agrega por banco e por tipo de tarifa, e calcula a **economia potencial**:

```
economia = Σ max(0, media_mensal_do_usuário_no_banco − benchmark_do_banco)
```

Só as diferenças **positivas** entram. Exemplo do próprio docstring: usuário
paga R$ 45/mês no Nubank contra R$ 30 de mercado → excesso R$ 15; paga R$ 80
no Itaú contra R$ 90 de mercado → excesso R$ 0 (já está bem). O total é
R$ 15, não R$ 5 — bancos onde o usuário já está abaixo do mercado não
"compensam" os outros.

**Confiança do relatório** (`_compute_confidence`), soma de 3 componentes,
limitada a `[0,10 · 1,00]`:

| Componente | Pontos |
|---|---|
| Histórico ≥ 6 meses | +0,40 |
| Histórico 3–5 meses | +0,25 |
| Histórico < 3 meses | +0,10 |
| ≥ 5 tarifas encontradas | +0,35 |
| 1–4 tarifas | +0,20 |
| `institution_id` disponível | +0,25 |

O peso de 0,25 no `institution_id` reflete que, sem ele, a agregação por banco
depende de keyword na descrição — menos confiável.

### 3. Benchmark de mercado — três fontes em cascata

`compare_to_market_baseline` escolhe nesta ordem:

**(1) `bank_fee_trends` — baseline coletivo anonimizado.** Query direta:

```sql
-- média do usuário nos últimos 3 meses
SELECT AVG(amount) FROM bank_fee_history
 WHERE user_id = :uid AND bank_name = :bank
   AND month >= to_char(NOW() - INTERVAL '3 months', 'YYYY-MM')

-- benchmark de mercado mais recente
SELECT market_avg FROM bank_fee_trends
 WHERE bank_name = :bank ORDER BY month DESC LIMIT 1
```

É o embrião do "flywheel de dados": quanto mais usuários, melhor o benchmark —
e ele captura o que os bancos **não publicam** (tarifas avulsas cobradas na
prática).

**(2) Catálogo vivo do Open Finance** (`connectors/open_finance_fees.py`,
job 02h15 → `data/fees/market_fees_live.json`). O detalhe importante é como o
"preço típico" é calculado — **não é o teto de tabela**:

```
typical = Σ (valor_da_faixa × fração_de_clientes_na_faixa) / Σ frações
```

O Open Finance Dados Abertos obriga cada participante a publicar, para cada
serviço, as faixas de preço **e a proporção de clientes em cada faixa**
(`prices[].customers.rate`). A média ponderada por essa proporção responde "o
que o cliente típico paga", não "o máximo que pode ser cobrado". Para pacotes
mensais, o valor final é a **mediana** dos típicos dos pacotes da instituição,
com sanidade `0 ≤ v ≤ 500`.

**(3) Tabela estática curada** (`_BANK_FEES_DB`) — fallback sempre disponível:

| Banco | Custo mensal de referência |
|---|---|
| Nubank / Inter / C6 / Next / PicPay / XP | R$ 0,00 |
| Santander | R$ 44,00 |
| Itaú | R$ 42,90 |
| Bradesco | R$ 38,50 |
| Banco do Brasil | R$ 31,00 |
| Caixa Econômica | R$ 24,50 |

Além do benchmark do banco específico, **todo relatório inclui uma referência
universal**: `"Melhor banco digital (Nubank / Inter / C6)" = R$ 0,00`. Essa é
uma decisão de produto — o usuário sempre vê que existe a opção de custo zero,
mesmo quando seu banco está na média do próprio segmento.

O `MarketFeesDB` recarrega o arquivo vivo **por mtime**, então o job diário
atualiza o benchmark sem restart da aplicação.

### 4. Histórico e baseline coletivo

Dois jobs complementares, e a distinção entre eles é o ponto:

| Job | Horário | O que mede |
|---|---|---|
| `fee_snapshot` | 02h00 | O que os usuários **pagam** de fato → `bank_fee_history` (por usuário) + `bank_fee_trends` (agregado anônimo por banco) |
| `market_fees_refresh` | 02h15 | O que os bancos **publicam** → `market_fees_live.json` |

`detect_new_fees` compara as tarifas atuais contra o histórico do usuário para
identificar cobrança nova sem precedente — é o insumo do detector D2 (doc 10).

---

## Como funciona (técnico)

- **Endpoint**: `GET /costs/{user_id}` — relatório com cada tarifa, total por
  período, comparação com benchmark, economia potencial e bandeiras de atenção.
- Detecção via Polars sobre `transactions_clean` (regex compilado + filtro de
  valor mínimo).
- `persist_snapshot()` grava o resultado para o histórico.
- Tool no agente: `get_bank_cost_analysis`.
- Gating: plano Pro.

## O que NÃO faz

- **Não classifica legalidade** — dizer se a tarifa é *indevida* é papel dos
  detectores de Defesa (D1/D2); o Raio-X mostra o custo e o desvio do mercado.
- **Não lê o contrato do usuário** — não sabe qual pacote foi contratado; o
  benchmark é por perfil típico, não pelo contrato específico.

## Reposicionamento de 2026-08

Três defeitos, todos encontrados de uma vez porque não existia teste algum de
`BankFeeAnalyzer` nem de `FeeDetector` — `tests/costs/` só cobria o conector do
Open Finance, e o único teste da rota checava presença de chaves, nunca valores.

**1. O valor da operação era contado como tarifa.** `\b(ted|doc)\b` e
`\bsaque\b` casavam o TIPO DE OPERAÇÃO, e o valor da linha é o dinheiro
transferido ou sacado. Uma TED de R$ 2.500 virava "tarifa de R$ 2.500"; num
extrato realista de 6 meses o relatório reportava R$ 29.357,40 contra R$ 901,80
de tarifa real — **114x**. Agora TED/DOC e SAQUE exigem marcador explícito de
cobrança (`TARIFA TED`, não `TED`), `JUROS` só casa em contexto de rotativo de
cartão, e há teto de plausibilidade por tipo como segunda linha de defesa —
descartando **com log**, porque falso negativo silencioso também é defeito.

Vale notar quais padrões estavam quebrados: os três genéricos do fim da lista de
prioridade. Os seis específicos — anuidade, seguro prestamista, seguro embutido,
pacote, IOF, tarifa de manutenção — são sadios por construção, porque quando a
descrição diz "anuidade" o valor da linha *é* a cobrança. São também exatamente
os que a Defesa consome.

**2. `analysis_months` era sempre 1.** `get_transactions_for_user` entrega a
coluna `date`; o `FeeDetector` renomeava para `transaction_date` só na sua cópia
local, e o `_calc_period` recebia o DataFrame original, não achava a coluna e
devolvia 1 mês para qualquer histórico. A projeção anual saía multiplicada pelo
número de meses de dados — **12x para quem tem um ano** — e `period_start`
voltava nulo. É a mesma deriva `date`/`transaction_date` que zerava a renda no
ETL. Agora `normalizar_extrato()` normaliza uma vez, antes de tudo.

**3. Nenhum banco era identificado.** `transactions_clean` não tem coluna de
instituição e a query não devolve nenhuma, então as duas camadas de resolução
colapsavam em keyword na descrição — e extrato do Itaú diz "TARIFA MANUTENCAO
CONTA", não "TARIFA ITAU". Tudo caía em "Banco desconhecido", que recebia a
média dos tradicionais como proxy e virava promessa de economia em reais,
inclusive para quem já está num banco digital.

A correção já existia no repositório: `BankMatchService._enrich_institution_id`
deriva a instituição de `account_id` → `account_balances`, e era usada por 1 dos
8 consumidores do analyzer. Foi promovida para
`app/costs/fee_detector.enriquecer_institution_id`. Onde ainda assim não dá para
identificar, o relatório **não inventa benchmark**: a economia fica em zero e um
aviso explica quanto ficou sem atribuição e por quê.

## Gaps e limitações

- **A detecção é puramente textual.** Uma tarifa com descrição atípica
  ("DEB AUT CONV 4471") não casa em nenhum dos 9 padrões e simplesmente não
  aparece no relatório — falso negativo silencioso.
- **Exigir marcador troca um erro por outro, de propósito.** Um banco que
  descreva a tarifa de TED só como "TED 4471", sem palavra de cobrança, agora
  passa despercebido. É a troca certa: falso positivo de R$ 2.500 num relatório
  de tarifas destrói a confiança no produto inteiro; falso negativo de R$ 11,90
  não.
- **Os tetos de plausibilidade são sanidade, não calibração.** Vieram de ordem
  de grandeza de mercado, não de medição. IOF e rotativo ficam de fora porque
  escalam com o principal da operação.
- **O flywheel acumulou dados errados.** `fee_snapshot` roda pelo mesmo caminho,
  então `bank_fee_history` e `bank_fee_trends` guardam os números inflados de
  antes desta correção. O baseline coletivo precisa ser reconstruído.
- **A tabela estática é curada manualmente** e representa "o pacote padrão mais
  contratado", não o contrato do usuário. Os R$ 0,00 dos digitais ignoram
  anuidade de cartão, que varia por produto (o próprio comentário no código
  anota isso).
- **`bank_fee_trends` precisa de massa de usuários** para ser um benchmark
  honesto; com poucos usuários, o baseline efetivo é o curado.
- **Cobertura do baseline vivo** = participantes do Open Finance que publicam
  `opendata-accounts/personal-accounts` (~28 instituições hoje). Bancos fora do
  diretório caem na tabela estática.
- **`INSTITUTION_ID_MAP` cobre 11 instituições** (com chaves duplicadas por
  slug e código COMPE, ex.: `"nubank"` e `"291"`). Um banco fora do mapa
  depende do fallback por keyword na descrição; falhando os dois, a tarifa é
  contabilizada sem banco atribuído.
