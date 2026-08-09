# 12 — Impostos e Calendário Fiscal (T1, T2, R2.c, M4.1)

> Pagar menos imposto legalmente, nunca perder prazo fiscal, e dar ao MEI o
> relatório que o contador cobraria para fazer.

## Em palavras simples

Quatro entregas nesta área: (1) o **Otimizador de IR** encontra jeitos legais
de pagar menos imposto sobre investimentos; (2) o **Modo Imposto Zero** mostra
quando um LCI/LCA isento ganha de um CDB tributado; (3) o **Calendário Fiscal**
avisa dos prazos que geram multa, personalizado por perfil; (4) o **Relatório
Fiscal MEI** consolida faturamento e estima o DAS.

---

## T1 — Otimizador de IR (`app/tax/`)

### Tabela de brackets (a base de tudo)

```
≤  6 meses (180 dias)  → 22,5%
≤ 12 meses (360 dias)  → 20,0%
≤ 24 meses (720 dias)  → 17,5%
> 24 meses             → 15,0%
```

### Tax-loss harvesting (`services/tax_loss_harvesting.py`)

Só dispara quando existem **as duas coisas**: posições com perda não realizada
**e** IR a pagar sobre posições com ganho. Sem ganho tributável, não há o que
abater — e o detector fica em silêncio.

```
total_loss        = |Σ perdas não realizadas (não isentas)|
effective_offset  = min(total_loss,  Σ ganhos não realizados)
avg_rate          = alíquota do prazo MÉDIO das posições com ganho
tax_saving        = effective_offset × avg_rate
```

A economia total é **rateada entre as posições com perda**, proporcionalmente:

```
saving_share_i = tax_saving × (perda_i / total_loss)
```

Confiança: `medium` — a compensação depende de as posições serem do mesmo tipo
no mesmo ano-calendário, o que a recomendação diz explicitamente.

### Hold-longer — esperar o bracket cair

Para cada posição com ganho não isenta:

```
current_rate = alíquota(holding_months)
next_bracket, next_rate = próximo degrau da tabela
months_to_wait = next_bracket − holding_months
ir_saving = ganho_não_realizado × (current_rate − next_rate)
```

**Três filtros que evitam ruído:**

| Filtro | Motivo |
|---|---|
| `months_to_wait ≤ 6` | esperar mais de 6 meses não é conselho acionável |
| `ir_saving ≥ R$ 50` | economia menor não justifica interromper o usuário |
| `next_rate < current_rate` | óbvio, mas explícito |

Confiança `high` (é aritmética determinística) e um `action_deadline` na
forma *"não resgatar nas próximas N semanas"*.

### Portfólio via Open Finance (`services/investment_profiler.py`)

Puxa as posições dos `item_id` conectados do usuário e mapeia para
`InvestmentPosition`, calculando `holding_months` a partir da data de
aplicação.

---

## T2 — Modo Imposto Zero (`services/zero_tax_mode.py`)

### CDB → LCI

Para cada posição CDB, calcula o breakeven (mesmo motor do doc 09):

```
cdb_net_rate  = taxa_bruta × (1 − alíquota_do_prazo)
lci_breakeven = cdb_net_rate
```

Se a melhor LCI disponível supera o breakeven:

```
advantage_pct  = lci_rate − lci_breakeven
annual_saving  = valor_aplicado × (advantage_pct / 100)
```

A recomendação vem com o alerta de **carência** — resgatar o CDB antes do prazo
pode custar mais do que a vantagem.

### Come-cotas → CDB

Identifica fundos sujeitos a come-cotas e calcula quantos meses faltam para a
próxima incidência (`_months_to_next_come_cotas`), sugerindo a migração antes
dela.

Endpoint: `POST /tax/breakeven`, `GET /tax/optimize/{user_id}` (plano Total).

---

## R2.c — Sazonalidade Fiscal (`app/seasonality/`)

### Calendário codificado (`fiscal_calendar.py`)

| Evento | Janela |
|---|---|
| `IR_DECLARACAO` | 01/03 – 31/05 (DIRPF) |
| `IR_RESTITUICAO` | lotes mensais mai–set, no último dia de cada mês |
| `IPVA_IPTU` | 02/01 – 28/02 |
| `DAS_MEI` | dia **13 a 20** de todo mês |
| `DASN_SIMEI` | 01/01 – 31/05 |

Os textos carregam a informação acionável, não só a data: o IPVA/IPTU menciona
que **pagar à vista dá 3–10% de desconto**; o DAS menciona que **atraso gera
multa de 0,33% ao dia**.

### Personalização por perfil (`profile_probe.py`) — o detalhe mais interessante

Mostrar DAS para quem é CLT é ruído. A detecção de MEI usa **duas etapas**,
por um motivo concreto:

**Etapa 1 — pré-filtro SQL barato** (recall alto, precisão baixa):
`LIKE '%das%'`, `'%simei%'`, `'%simples%'`, `'%pgmei%'`.

**Etapa 2 — decisão final por regex com fronteira de palavra:**

```python
MEI_REGEX = re.compile(
    r"\bdas\b.*(simples|mei|nacional)"        # "das simples nacional"
    r"|(imposto|guia|pagamento|pgto)\s+das\b" # "guia das"
    r"|\bdas\s+\d{2}/\d{4}\b"                 # "das 06/2026"
    r"|\bpgmei\b|\bsimei\b|simples\s+nacional",
    re.IGNORECASE)
```

O comentário no código explica o porquê: `LIKE '%das %'` casava com
**"polegadas 2x"** e **"lojas das..."**. Fazer o filtro barato no banco e a
decisão precisa em Python é a solução — e a regex foi *calibrada contra corpora
reais* (DuckDB 12k transações + `transactions_clean` do Postgres de dev).

Regra final: **MEI/PJ = pagou DAS alguma vez OU tem ≥ 5 transações PJ nos
últimos 90 dias** (`_MIN_PJ_TXNS`).

A detecção de salário segue a mesma filosofia, com métrica reportada:
*"a calibração mostrou 317/323 créditos de salário capturados no corpus 12k"*
(~98% de recall).

Entregas: card `FISCAL_SEASON` no feed, tool `get_fiscal_calendar` no chat,
prazos urgentes no daily digest.

---

## M4.1 — Relatório Fiscal MEI (`app/fiscal/fiscal_report.py`)

Consolida as transações PJ (rótulo do doc 05) por **subcategoria**:

**Receitas**: `receita_servicos`, `receita_produtos`.
**Despesas**: software/SaaS, marketing, transporte, equipamentos, pessoal
(pró-labore/RH), impostos, tarifas bancárias, outros PJ.

```
lucro_estimado = total_receita − total_despesa
```

### Cálculo do DAS — Simples Nacional Anexo III (Serviços)

**Determinação da faixa** — usa o **RBT12 real** (soma dos últimos 12 meses),
não o mês anualizado:

```
relatório mensal → rbt12 = soma real dos últimos 12 meses
                   (fallback: receita_do_mês × 12 se histórico insuficiente)
relatório anual  → rbt12 = receita total do ano
```

**Teto do Simples**: `rbt12 > R$ 4.800.000` → não calcula DAS e devolve a
mensagem *"Fora do Simples Nacional — regime Lucro Presumido ou Real"*.

**Alíquota efetiva** — a fórmula oficial, com parcela a deduzir:

```
alíquota_efetiva = max(0, (RBT12 × alíquota_nominal − parcela_dedução) / RBT12)
DAS = receita_do_período × alíquota_efetiva
```

O ponto crítico, e que o código acerta: **a faixa é determinada pelo RBT12, mas
o DAS incide sobre a receita do período** — não sobre o RBT12. Errar isso é o
equívoco mais comum em calculadoras de Simples.

**Versionamento da tabela por ano** (`_get_simples_table`): as tabelas do
Anexo III são indexadas por ano. Ano não cadastrado → usa a mais recente
`≤ ano` com **log de warning** pedindo atualização; ano anterior a todas → usa
a mais antiga. Degrada com aviso, não silenciosamente.

Saída: `rbt12_anualizado`, `das_aliquota_efetiva` (em %), `das_estimado`,
`das_faixa` ("Faixa N — Simples Nacional Anexo III").

---

## O que NÃO faz

- **Não declara IR** — não preenche nem transmite DIRPF/DASN.
- **Não é consultoria tributária formal** — as otimizações são as consagradas
  e legais; casos complexos → contador (dito ao usuário).
- **Não executa resgates nem migrações** — recomenda e explica.

## Gaps e limitações

- **Só o Anexo III (Serviços)** é implementado. MEI de comércio (Anexo I) ou
  indústria (Anexo II) teria alíquota diferente — o relatório assumiria
  Serviços de qualquer forma.
- **O DAS do MEI real é valor fixo mensal (SIMEI)**, não percentual. O cálculo
  aqui é do Simples Nacional Anexo III — apropriado para ME/EPP, mas para o MEI
  estrito o número correto é a guia fixa. O usuário precisa saber qual regime
  o descreve.
- **Tabelas do Simples são constantes por ano no código** — exigem manutenção
  anual (o warning avisa, mas o cálculo continua com a tabela velha).
- **Datas do calendário são constantes anuais** — sem fonte automática oficial;
  ~1h de manutenção por ano.
- **Tax-loss harvesting usa a alíquota do prazo MÉDIO** das posições com ganho,
  não a de cada posição individualmente — aproximação que erra quando a
  carteira tem prazos muito dispersos.
- **A compensação de perdas tem regras por tipo de ativo** que o detector não
  modela: a recomendação diz "do mesmo tipo no mesmo ano-calendário", mas não
  verifica se as posições realmente são compensáveis entre si.
- **Depende de dados de investimento via Open Finance** — a cobertura varia por
  corretora, e sem posições conectadas T1/T2 ficam vazios.
- **MEI caminhoneiro e regimes especiais** não são diferenciados.
