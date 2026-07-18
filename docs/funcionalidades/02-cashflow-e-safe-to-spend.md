# 02 — Cashflow e Safe-to-Spend (F1)

> Responde a pergunta mais básica e mais difícil de finanças pessoais:
> **"quanto eu posso gastar hoje sem me enrolar no fim do mês?"**

## Em palavras simples

O saldo da conta mente: ele não sabe que sua fatura fecha dia 10, que o aluguel
sai dia 15 e que faltam 3 parcelas da geladeira. A Nexa projeta seu caixa 30
dias à frente considerando tudo isso e devolve **um número por dia** ("sua
margem segura hoje é R$ 87/dia"). É o coração do produto — aparece no
dashboard, no widget da homescreen e em praticamente todas as outras análises.

## O que faz

- **Projeção de fluxo de caixa 30 dias** (`cashflow/projector.py`): saldo
  projetado dia a dia = saldo atual + rendas recorrentes esperadas − gastos
  recorrentes − shadow invoices (parcelas/assinaturas futuras).
- **Safe-to-spend** (`cashflow/safe_to_spend.py`): margem segura diária e
  total, com buffer de proteção — o mínimo projetado do período nunca pode
  ficar negativo.
- **Burn rate** (`cashflow/burn_rate.py`): velocidade de gasto por categoria
  vs orçamento; alimenta os cards `BURN_RATE_HIGH`.
- **Alertas** (`router_alerts.py`): gastos anômalos, categorias estourando.
- **Widget PWA** (`GET /safe-to-spend/{user_id}/widget`): payload de ~200
  bytes com a margem do dia, para a homescreen do celular.
- **Explicabilidade** (`core/explain.py`): o número vem com explicação em
  português de como foi calculado.

## Como funciona (técnico)

- `CashflowEngine` (`cashflow/engine.py`) orquestra: `CashflowProjector` →
  `SafeToSpendCalculator` → `BurnRateAnalyzer` → `BudgetAdvisor`.
- A renda usada respeita hierarquia de confiança: renda declarada → 
  `IncomeProfile` com confiança ≥ 0,5 → estimativa bruta de créditos.
- **Endpoints**: `GET /forecast/{user_id}` (análise completa),
  `GET /safe_to_spend/{user_id}`, `GET /shadow_invoice/{user_id}`,
  `GET /alerts/{user_id}`, `GET /dashboard/summary`.
- Consome o resultado do ETL via runner (`app/runner.py` → cache por usuário).

## O que NÃO faz

- **Não prevê rendas irregulares com ML** — a projeção assume recorrência
  detectada; um autônomo com renda caótica recebe projeção conservadora, não
  um modelo probabilístico de renda.
- **Não considera limite do cartão/cheque especial** como "dinheiro
  disponível" (decisão de produto: crédito não é margem).
- **Não faz replanejamento automático** quando o usuário estoura a margem —
  gera alerta, mas a decisão é do usuário.

## Gaps e limitações

- Horizonte fixo de 30 dias (90/180 dias exigiria modelagem de sazonalidade).
- A qualidade é refém do ETL: conta recém-conectada (< 3 meses de histórico)
  produz margens com confiança baixa — o produto sinaliza, mas o número
  aparece mesmo assim.
- Multi-conta parcial: a projeção soma contas conectadas, mas não modela
  transferências programadas entre elas.
