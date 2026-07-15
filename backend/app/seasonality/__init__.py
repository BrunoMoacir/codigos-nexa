"""
app/seasonality — R2.c: Sazonalidade Fiscal

Calendário de obrigações e direitos fiscais brasileiros (IR, restituição,
IPVA/IPTU, DAS/DASN-SIMEI, 13º salário, lucro do FGTS), personalizado com
o perfil financeiro do usuário (renda, MEI/PJ, histórico de transações).

Superfícies:
  - GET /seasonality/{user_id}          — lista de eventos ativos/próximos
  - Feed: card FISCAL_SEASON            — via ProactiveNotifier
  - Chat: tool get_fiscal_calendar      — agente LangGraph
"""
