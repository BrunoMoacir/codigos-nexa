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
≤ 180 dias   → 22,5%
181–360      → 20,0%
361–720      → 17,5%
> 720 dias   → 15,0%
```

Lei 11.033/2004, art. 1º. A tabela mora em `app/tax/parametros_fiscais.py` e é
contada em **dias** — a lei conta dias, e a conversão por meses×30 erra até meio
mês, o suficiente para dizer que uma posição de 181 dias ainda está em 22,5%.

### Tax-loss harvesting (`services/tax_loss_harvesting.py`)

**Só nas classes em que a lei permite compensar.** Compensação de prejuízo não
existe em renda fixa: o IR do CDB e do Tesouro é retido na fonte sobre o
rendimento de cada operação, e a perda de um papel não abate o ganho de outro.
Onde existe:

| Classe | Compensa com |
|---|---|
| Ações, ETF, BDR | entre si, saldo carregado indefinidamente |
| FII | **apenas** com FII — categoria separada |
| Fundos | fundos da **mesma administradora** e mesma classificação tributária |
| CDB, Tesouro, debêntures, LCI/LCA | nada |

O agrupamento acontece nessas fronteiras, e só dentro de um grupo a perda abate
o ganho:

```
ir_dos_ganhos   = Σ IR estimado das posições com ganho do grupo
abatimento      = min(Σ perdas, Σ ganhos)
economia        = ir_dos_ganhos × (abatimento / Σ ganhos)
parcela_i       = economia × (perda_i / Σ perdas)
```

A economia sai da fração do ganho que a perda cobre vezes o IR **efetivamente
apurado por posição** — substitui a "alíquota do prazo médio", que errava
quando a carteira tinha prazos dispersos.

**Guarda da isenção de bolsa**: se a venda inteira das posições com ganho em
ações couber nos R$ 20.000 mensais isentos (Lei 11.033/2004, art. 3º, I), não
há IR a abater e o detector se cala — realizar prejuízo para compensar um ganho
isento é perda pura.

### Hold-longer — esperar o bracket cair

Para cada posição com ganho não isenta:

A conta é em **dias**, que é a unidade da lei:

```
dias                  = hoje − data_de_aplicação
faltam, nova_alíquota = proximo_degrau(dias)      # parametros_fiscais
ir_saving             = ganho_não_realizado × (alíquota_atual − nova_alíquota)
```

**Dois filtros:** `faltam ≤ 180 dias` e `ir_saving ≥ R$ 50`. Só entram produtos
cujo IR segue a tabela regressiva — ação e ETF são 15% lineares e FII é 20%
linear, e não há degrau a esperar.

Confiança `high` quando a fonte informa a data de aplicação, `medium` quando o
prazo vem de `holding_months` (aritmética de mês-calendário, que erra até ~15
dias — e aí a mensagem fala em "cerca de N meses" em vez de prometer dias).

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

Identifica fundos sujeitos a come-cotas, projeta o IR que será antecipado até a
próxima incidência (último dia útil de maio ou novembro) e sugere avaliar a
migração antes dela.

**O benefício é diferimento, não economia.** O IR sai no resgate de qualquer
forma; o ganho é o rendimento do dinheiro que não foi antecipado — calculado
sobre o semestre que a troca garante pular. Vai marcado como
`benefit_kind="deferral"` e é somado em `total_estimated_deferral_gain`,
separado de `total_estimated_tax_saving`.

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

**Determinação da faixa** — usa o RBT12 real dos **doze meses ANTERIORES** ao
período de apuração (LC 123/2006, art. 18, § 1º), que não inclui o próprio mês:

```
relatório mensal → rbt12 = soma dos 12 meses anteriores ao mês de apuração
                   (fallback: receita_do_mês × 12 se histórico insuficiente)
relatório anual  → rbt12 = receita total do ano
```

**Teto do Simples**: `rbt12 > R$ 4.800.000` → não calcula DAS e devolve a
mensagem *"Fora do Simples Nacional — regime Lucro Presumido ou Real"*.

**Anexo III ou V — o Fator R decide.** Serviço só é Anexo III quando a folha de
salários dos 12 meses anteriores representa 28% ou mais da receita bruta do
mesmo período (LC 123/2006, art. 18, §§ 5º-J e 5º-M); abaixo disso é Anexo V,
cuja primeira faixa é **15,5%** contra 6% — 2,6× mais. A folha vem de
`despesa_pessoal_pj`, na mesma janela do RBT12.

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

### As correções de 2026-08-22

O calendário fiscal e o `IRPFCalculator` não precisaram de nada. Os defeitos
estavam no otimizador de IR e no cálculo do DAS.

**`hold_longer` disparava em 1 de 29 prazos.** `_next_bracket` devolvia a faixa
em que a posição JÁ estava, não a seguinte. Varredura de 1 a 29 meses: só
`holding_months == 6` passava — e nesse dizia *"em 6 mês(es) a alíquota cai"*
com `action_deadline` de *"não resgatar nas próximas 24 semanas"*, quando aos
180 dias falta **um dia** para os 181 que mudam a faixa. Todo caso útil
(faltando um ou dois meses para o degrau) era descartado em silêncio.

**`harvest_loss` estava invertido em relação à lei.** Não filtrava por classe de
ativo, e o efeito era duplo: ficava **mudo** em ação/FII/ETF, onde a compensação
existe — porque o `estimated_ir` só era calculado quando havia taxa anual
contratada, que a Pluggy não informa para renda variável — e **disparava** em
renda fixa, onde não existe. A recomendação mandava resgatar realizando
prejuízo por um benefício fiscal inexistente naquela classe: ação irreversível,
prejuízo real.

**A alíquota de ganho ignorava a classe.** Tudo passava por `calc_ir_on_cdb`,
ou seja, pela tabela regressiva: uma ação com 3 meses saía com 22,5% quando o
devido é 15% linear, e um FII com a regressiva quando o devido é 20%. E a base
era um rendimento hipotético recalculado da taxa sobre o principal, não o ganho
real da posição.

**O come-cotas apontava o mês errado em sete dos doze meses do ano.** O rótulo
vinha de `meses_restantes <= 5 → "maio"`, e de junho a outubro a distância até
novembro é ≤ 5. A data impressa para maio era a string `"31/{ano}"`, sem mês:
o usuário lia *"Antes de 31/2026"*.

**A janela do RBT12 incluía o próprio mês de apuração.** Era `data_ref − 330
dias` até o fim do mês de referência — começava cinco dias depois do 12º mês
anterior, incluía o mês corrente e alcançava os primeiros dias do seguinte. Com
R$ 15.000/mês e um junho de R$ 30.000, o RBT12 saía R$ 195.000 (Faixa 2) quando
o legal era R$ 170.000 (Faixa 1): um mês forte empurrava a si mesmo para cima.

**Crédito PJ sem subcategoria virava despesa.** O default era
`despesa_outros_pj` para qualquer lançamento sem classificação, inclusive
crédito. Uma receita não reconhecida pelo classificador reduzia a receita,
aumentava a despesa e **subestimava o DAS** — a direção que gera multa.

**Estorno maior que a venda virava receita positiva.** `abs()` sobre o total do
grupo: R$ 2.000 de venda com R$ 5.000 de estorno viravam R$ 3.000 de receita, e
o DAS era cobrado sobre devoluções.

**O Fator R não existia.** Ver acima — a diferença entre os anexos é de 2,6× na
primeira faixa, e a folha necessária para decidir já estava no relatório.

**Dois módulos mortos removidos**, com 13 testes que os mantinham verdes:
`app/fiscal/services/tax_radar.py` e `app/fiscal/services/tax_loss_harvesting.py`
não eram importados por router, service ou tool nenhum. O segundo calculava
DARF de 15% sobre qualquer ganho, ignorando a isenção de R$ 20 mil.

**74 testes novos.** Não havia nenhum para `FiscalReportService`,
`TaxLossHarvester`, `ZeroTaxMode` ou `InvestmentProfiler`.

## O que NÃO faz

- **Não declara IR** — não preenche nem transmite DIRPF/DASN.
- **Não é consultoria tributária formal** — as otimizações são as consagradas
  e legais; casos complexos → contador (dito ao usuário).
- **Não executa resgates nem migrações** — recomenda e explica.

## Gaps e limitações

- **Anexos III e V (Serviços)** são implementados, com o Fator R decidindo
  entre eles. MEI de comércio (Anexo I) ou indústria (Anexo II) teria alíquota
  diferente — o relatório assume Serviços de qualquer forma.
- **O DAS do MEI real é valor fixo mensal (SIMEI)**, não percentual. O cálculo
  aqui é do Simples Nacional Anexo III — apropriado para ME/EPP, mas para o MEI
  estrito o número correto é a guia fixa. O usuário precisa saber qual regime
  o descreve.
- **Tabelas do Simples são constantes por ano no código** — exigem manutenção
  anual (o warning avisa, mas o cálculo continua com a tabela velha).
- **Datas do calendário são constantes anuais** — sem fonte automática oficial;
  ~1h de manutenção por ano.
- **A isenção de R$ 20.000 em bolsa é avaliada pela carteira, não pelas vendas
  do mês.** A Nexa não sabe quanto o usuário já vendeu; a guarda só sabe dizer
  que a venda das posições com ganho, sozinha, caberia na isenção.
- **A duração da carteira dos fundos não vem da Pluggy**, então o come-cotas é
  projetado a 15% (fundo de longo prazo). Fundo de curto prazo sofre 20%.
- **`unrealized_gain` depende de a fonte informar o saldo atual.** Quando o
  conector devolve saldo igual ao valor aplicado, o IR estimado cai no
  rendimento projetado pela taxa contratada — aproximação que só existe para
  renda fixa.
- **Depende de dados de investimento via Open Finance** — a cobertura varia por
  corretora, e sem posições conectadas T1/T2 ficam vazios.
- **MEI caminhoneiro e regimes especiais** não são diferenciados.
