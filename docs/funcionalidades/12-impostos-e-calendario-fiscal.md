# 12 — Impostos e Calendário Fiscal (T1, T2, R2.c, M4.1)

> Pagar menos imposto legalmente, nunca perder prazo fiscal, e dar ao MEI o
> relatório que o contador cobraria para fazer.

## Em palavras simples

Quatro entregas nesta área: (1) o **Otimizador de IR** encontra jeitos legais
de pagar menos imposto sobre investimentos (esperar a alíquota regressiva
cair, compensar prejuízos); (2) o **Modo Imposto Zero** mostra quando um
LCI/LCA isento ganha de um CDB tributado; (3) o **Calendário Fiscal** avisa
dos prazos que geram multa (IR, DAS, IPVA/IPTU) — personalizado: MEI vê DAS,
CLT não; (4) o **Relatório Fiscal MEI** consolida faturamento e alerta sobre
o limite anual.

## O que faz

### T1 — Otimizador de IR (`app/tax/`)
- Tax loss harvesting (compensar prejuízos realizados), timing de resgate
  (alíquota regressiva: 22,5% → 15% após 720 dias), análise do portfólio via
  Open Finance. Endpoint: `GET /tax/optimize/{user_id}` (plano Total).

### T2 — Modo Imposto Zero
- Breakeven CDB vs LCI/LCA (`POST /tax/breakeven`): a partir de qual taxa o
  isento ganha do tributado, considerando prazo e IR regressivo real
  (`fiscal/ir_pf_calculator.py` — o mesmo motor usado pelo Radar OPP).

### R2.c — Sazonalidade Fiscal (`app/seasonality/`)
- Calendário brasileiro codificado (`fiscal_calendar.py`): IR (01/03–31/05),
  lotes de restituição (mai–set), IPVA/IPTU (jan–fev), DAS mensal do MEI
  (dia 13–20), DASN-SIMEI, 13º, lucro do FGTS.
- **Personalização por perfil** (`profile_probe.py`): detecta MEI/CLT pelas
  transações e mostra só o que se aplica. Card `FISCAL_SEASON` no feed, tool
  `get_fiscal_calendar` no chat, prazos urgentes no daily digest.

### M4.1 — Relatório Fiscal MEI (`app/fiscal/fiscal_report.py`)
- Faturamento acumulado (via classificação PF/PJ), projeção anual, alerta de
  proximidade do teto do MEI, DAS estimado.

## O que NÃO faz

- **Não declara IR** — não preenche nem transmite DIRPF/DASN.
- **Não é consultoria tributária formal** — otimizações são as consagradas e
  legais; casos complexos → contador (dito ao usuário).
- Tax loss harvesting depende de dados de investimento via Open Finance —
  cobertura varia por corretora.

## Gaps e limitações

- Datas do calendário são atualizadas por código (constantes anuais) — sem
  fonte automática oficial; requer manutenção anual (~1h/ano).
- O relatório MEI cobre o regime SIMEI padrão; MEI caminhoneiro e regras
  especiais não são diferenciados.
