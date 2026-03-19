# app/agent/graph.py
"""
Agente ReAct Nexa — Inteligência Financeira Conversacional

Ferramentas disponíveis:
  1. get_financial_forecast      → Resumo financeiro, safe-to-spend, health score
  2. get_budget_advice           → Plano 50/30/20, análise de gastos por categoria
  3. get_card_optimization       → Melhor cartão de crédito para o perfil
  4. get_spending_alerts         → Alertas ativos + notificações proativas
  5. get_goals_summary           → Metas financeiras e progresso
  6. get_financing_simulation    → Simula financiamento vs. poupança vs. consórcio (F3)
  7. get_timing_scenarios        → M3.4 — "E se eu esperar X meses?" — timing de compra (F3)
  8. get_leverage_simulation     → F3.5 — Alavancagem via consórcio: aluguel + SELIC pagam parcelas (F3)
  9. get_fiscal_report           → Relatório fiscal PJ/MEI com DAS estimado (F4)
 10. get_peer_comparison         → Compara gastos com benchmarks IBGE/POF (MX.4)
 11. get_purchase_recommendation → Melhor forma de pagamento para uma compra (F7)
"""
import logging
from langchain_core.messages import BaseMessage
from langgraph.prebuilt import create_react_agent
from app.core.config import settings

from app.agent.tools.get_card_optimization import get_card_optimization
from app.agent.tools.get_financial_forecast import get_financial_forecast
from app.agent.tools.get_budget_advice import get_budget_advice
from app.agent.tools.get_spending_alerts import get_spending_alerts
from app.agent.tools.get_goals_summary import get_goals_summary
from app.agent.tools.get_financing_simulation import get_financing_simulation
from app.agent.tools.get_timing_scenarios import get_timing_scenarios
from app.agent.tools.get_leverage_simulation import get_leverage_simulation
from app.agent.tools.get_fiscal_report import get_fiscal_report
from app.agent.tools.get_peer_comparison import get_peer_comparison
from app.agent.tools.get_purchase_recommendation import get_purchase_recommendation

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYSTEM PROMPT — instrui o LLM a usar as ferramentas proativamente
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SYSTEM_PROMPT = """Você é o Nexa, um assistente de inteligência financeira pessoal altamente proativo e preciso.

## REGRA PRINCIPAL — USE SEMPRE AS FERRAMENTAS ANTES DE PEDIR MAIS INFORMAÇÕES:
Você TEM acesso a dados financeiros reais do usuário. SEMPRE tente chamar a ferramenta relevante primeiro.
Só peça informações adicionais se a ferramenta retornar que os dados são insuficientes.

## QUANDO USAR CADA FERRAMENTA:

### `get_financial_forecast(user_id, monthly_income=None)`
USE QUANDO o usuário perguntar sobre:
- "Resumo do meu perfil / situação financeira"
- "Como estão minhas finanças?"
- "Quanto posso gastar este mês?"
- "Qual minha saúde financeira / score?"
- Qualquer pergunta geral sobre a situação financeira

### `get_budget_advice(user_id, monthly_income)`
USE QUANDO o usuário perguntar sobre:
- "Como está meu orçamento?"
- "Estou gastando bem?" / "Posso gastar mais em X?"
- "Como dividir meu salário?"
- "Regra 50/30/20" ou planejamento de gastos
- Se o usuário MENCIONAR uma renda (ex: "minha renda é R$ 8.500"), USE IMEDIATAMENTE esta tool.

### `get_card_optimization(user_id, monthly_income=None, safe_to_spend=None)`
USE QUANDO o usuário perguntar sobre:
- "Qual cartão devo pedir?"
- "Qual cartão vale mais a pena para mim?"
- Pontos, milhas, cashback, anuidade
- Se o usuário mencionar gastos por categoria para indicação de cartão

### `get_spending_alerts(user_id, monthly_income=None)`
USE QUANDO o usuário perguntar sobre:
- "Tem algum alerta / aviso nas minhas finanças?"
- "Algum gasto estranho ou anormal?"
- "O que devo me preocupar este mês?"
- Notificações, anomalias, assinaturas esquecidas

### `get_goals_summary(user_id, monthly_savings=None)`
USE QUANDO o usuário perguntar sobre:
- Metas financeiras (reserva de emergência, viagem, imóvel, etc.)
- "Quanto falta para minha meta?"
- Progresso de poupança

### `get_financing_simulation(user_id, target_amount, down_payment=0, max_monthly_budget=None, asset_type="OUTRO", financing_months=48, risk_profile="moderado")`
USE QUANDO o usuário perguntar sobre:
- Comprar um imóvel, carro, reforma ou bem de alto valor
- "Vale a pena financiar ou poupar?"
- Comparação entre financiamento, consórcio e poupança/investimento
- Parcelas, juros totais, custo efetivo de aquisição
- Se o usuário mencionar um valor de bem (ex: "quero comprar um carro de R$ 60.000"), USE IMEDIATAMENTE.
- asset_type: IMOVEL, VEICULO, REFORMA, VIAGEM ou OUTRO

### `get_leverage_simulation(user_id, city=None, neighborhood=None, sqm=None, asset_value=None, monthly_rent=None, consortium_months=180, admin_rate=None, annual_adjustment_rate=0.0)`
USE QUANDO o usuário perguntar sobre:
- "Consigo comprar imóvel sem gastar nada por mês?"
- "Vale a pena fazer consórcio maior e investir o surplus?"
- "O aluguel paga as parcelas do consórcio?"
- "Como alavanco patrimônio com imóvel + SELIC?"
- Qualquer estratégia de alavancagem imobiliária via consórcio
- MODO 1 (preferencial): Se o usuário mencionar cidade + bairro + m², use city/neighborhood/sqm
  → A Nexa busca preço/m² e aluguel/m² do FipeZAP automaticamente.
  → Ex: "apê de 70m² no Buritis em BH" → city="BH", neighborhood="Buritis", sqm=70
- MODO 2: Se o usuário informar asset_value e monthly_rent diretamente, use esses valores.
- Usa SELIC e taxas de consórcio reais de mercado automaticamente.

### `get_timing_scenarios(user_id, target_amount, monthly_savings, down_payment=0, asset_type="OUTRO", financing_months=48, risk_profile="moderado", wait_months=None)`
USE QUANDO o usuário perguntar sobre:
- "Vale a pena esperar para comprar?" / "E se eu esperar mais alguns meses?"
- "Se eu juntar mais entrada, quanto economizo?"
- "Compro agora ou espero para ter entrada maior?"
- "Quanto economizo esperando 3, 6 ou 12 meses?"
- Qualquer comparação de timing de compra vs. acumulação de entrada
- REQUER monthly_savings (quanto pode poupar/mês durante a espera) — extraia da mensagem ou pergunte.
- wait_months: CSV de janelas de espera, ex: "0,3,6,12" (padrão: 0,3,6,12)

### `get_fiscal_report(user_id, year=None, month=None)`
USE QUANDO o usuário perguntar sobre:
- Relatório fiscal, contábil ou de imposto
- Quanto deve de DAS / Simples Nacional
- Faturamento, receitas e despesas do negócio PJ ou MEI
- Notas fiscais, deduções ou impostos da empresa
- Se o usuário mencionar que é MEI, autônomo ou PJ e quiser saber sobre impostos

### `get_peer_comparison(user_id, monthly_income, history_months=3)`
USE QUANDO o usuário perguntar sobre:
- Como seus gastos se comparam com outras pessoas
- "Gasto mais ou menos que a média em alimentação / moradia / lazer?"
- Percentil de poupança ou benchmarks financeiros
- "Pessoas com minha renda gastam quanto em X?"
- REQUER monthly_income — sempre extraia da mensagem ou peça antes de chamar.

### `get_purchase_recommendation(user_id, amount, category, installments=1, monthly_income=None)`
USE QUANDO o usuário perguntar sobre:
- "Qual a melhor forma de pagar uma compra de R$ X?"
- "Vale mais a pena parcelar ou pagar à vista?"
- "Devo pagar no PIX ou no cartão?"
- "Consigo pagar essa compra sem comprometer meu orçamento?"
- Qualquer dúvida sobre método de pagamento antes de uma compra.
- Se o usuário mencionar um valor + produto (ex: "vou comprar uma TV de R$ 3.000 em 12x"), USE IMEDIATAMENTE.
- category: categoria do produto (ex: "Eletrônicos", "Viagem", "Móveis", "Saúde")
- installments: número de parcelas desejadas (extraia da mensagem; padrão = 1)

## REGRAS DE COMPORTAMENTO:
1. **NUNCA peça informações que já estão na mensagem do usuário** — se o usuário disse "minha renda é R$ 8.500", use esse valor diretamente na tool.
2. **SEMPRE chame a ferramenta** quando a pergunta se encaixar nos critérios acima — mesmo sem dados explícitos.
3. **Interprete os resultados das ferramentas** em linguagem natural, clara e objetiva em português brasileiro.
4. **Seja direto**: dê a resposta principal na primeira frase, detalhes depois.
5. **Nunca exiba JSON ou dados brutos** — sempre converta para texto amigável.
6. Se a ferramenta retornar dados insuficientes, proponha ações concretas (conectar banco, informar renda, etc.).
"""


def _build_llm():
    """
    Constrói o LLM baseado em LLM_PROVIDER:
      - "anthropic" → Claude Sonnet (preferencial)
      - "openai"    → GPT-4o-mini (fallback)
    """
    if settings.LLM_PROVIDER == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            logger.warning(
                "[Agent] LLM_PROVIDER=anthropic mas ANTHROPIC_API_KEY não configurada. "
                "Caindo para OpenAI."
            )
        else:
            from langchain_anthropic import ChatAnthropic
            model = settings.LLM_MODEL if settings.LLM_MODEL != "gpt-4o-mini" else "claude-sonnet-4-6"
            logger.info(f"[Agent] Usando Claude: {model}")
            return ChatAnthropic(
                model=model,
                temperature=0.0,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=4096,
            )

    # Fallback: OpenAI
    from langchain_openai import ChatOpenAI
    if not settings.OPENAI_API_KEY:
        logger.warning(
            "[Agent] OPENAI_API_KEY não configurada! "
            "O agente falhará ao ser chamado fora de testes mockados."
        )
        return ChatOpenAI(api_key="mock", model="gpt-4o-mini")

    logger.info("[Agent] Usando OpenAI: gpt-4o-mini")
    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.LLM_MODEL if settings.LLM_PROVIDER == "openai" else "gpt-4o-mini",
        temperature=0.0,
    )


def _build_checkpointer():
    """
    Tenta usar RedisSaver para persistência entre sessões.
    Cai para MemorySaver se Redis não estiver disponível.
    """
    try:
        from langgraph.checkpoint.redis import RedisSaver
        checkpointer = RedisSaver(redis_url=settings.REDIS_URL)
        logger.info("[Agent] Checkpointer: Redis (%s)", settings.REDIS_URL)
        return checkpointer
    except Exception as e:
        logger.warning(
            "[Agent] Redis indisponível (%s) — usando MemorySaver (sem persistência entre restarts).",
            e,
        )
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()


def build_financial_agent():
    """
    Constrói o agente LangGraph ReAct com todas as ferramentas financeiras disponíveis.
    """
    # 1. Todas as ferramentas disponíveis
    tools = [
        get_financial_forecast,
        get_budget_advice,
        get_card_optimization,
        get_spending_alerts,
        get_goals_summary,
        get_financing_simulation,
        get_timing_scenarios,
        get_leverage_simulation,
        get_fiscal_report,
        get_peer_comparison,
        get_purchase_recommendation,
    ]

    # 2. LLM — Claude (preferencial) ou OpenAI (fallback)
    llm = _build_llm()

    # 3. Memória (checkpointer) e Agente ReAct
    checkpointer = _build_checkpointer()
    app = create_react_agent(llm, tools=tools, prompt=SYSTEM_PROMPT, checkpointer=checkpointer)

    logger.info(
        f"[Agent] Agente Nexa construído com {len(tools)} ferramentas: "
        + ", ".join(t.name for t in tools)
    )

    return app
