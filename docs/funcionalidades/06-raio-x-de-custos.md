# 06 — Raio-X de Custos (F5)

> Mostra cada tarifa que o banco cobra de você — e se ela está acima do que o
> mercado cobra.

## Em palavras simples

Tarifa bancária é desenhada para passar despercebida: R$ 24,90 aqui, R$ 12 de
"manutenção" ali. O Raio-X varre o extrato, encontra todas as tarifas, soma o
custo anual ("você paga R$ 487/ano só de tarifas") e compara com um benchmark:
"a média de mercado para esse pacote é R$ 15 — o seu banco cobra R$ 25".
É a matéria-prima da indignação que move a Defesa do Consumidor (doc 10) e o
Negociador (doc 08).

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

## Gaps e limitações

- **A detecção é puramente textual.** Uma tarifa com descrição atípica
  ("DEB AUT CONV 4471") não casa em nenhum dos 9 padrões e simplesmente não
  aparece no relatório — falso negativo silencioso.
- **Regex genérico pode gerar falso positivo**: `\bjuros\b` casa em qualquer
  lançamento com a palavra "juros", inclusive juros **recebidos** — a proteção
  é só o filtro `amount < 0`.
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
