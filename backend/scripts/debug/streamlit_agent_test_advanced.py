"""
streamlit_agent_test_advanced.py — Teste Avançado do Nexa Agent (Com Memória e Custos)

Funcionalidades:
- Mantém histórico da conversa de forma robusta e passa o contexto completo para a LLM.
- Rastreamento de Tokens e Custos (API GPT-4o-mini).
- Inclui cenários avançados ("Perguntas de Ouro") com múltiplas tools.
- Funciona via chamada "Direta" (Python) ou "HTTP" (API).
"""

import os
import time
import requests
import streamlit as st
from dotenv import load_dotenv
from langchain_community.callbacks import get_openai_callback
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Carrega as variáveis (como OPENAI_API_KEY) do backend/.env
load_dotenv("backend/.env")

# Preços base do gpt-4o-mini em USD (Dez 2024 / Mar 2026 precos ficticios estaveis)
# USD 0.150 per 1M input tokens
# USD 0.600 per 1M output tokens
PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.00060

st.set_page_config(
    page_title="Nexa Agent — Teste Avançado",
    page_icon="🧠",
    layout="wide",
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CENÁRIOS DE TESTE E "PERGUNTAS DE OURO"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOOL_SCENARIOS = {
    "1. get_financial_forecast (F1)": {
        "icon": "📊",
        "descricao": "Resumo financeiro, safe-to-spend, health score",
        "mensagens": [
            "Como estão minhas finanças este mês?",
            "Quanto posso gastar hoje com segurança?",
            "Me dê um diagnóstico completo do meu fluxo de caixa atual.",
        ],
    },
    "2. get_budget_advice (M1.3)": {
        "icon": "📋",
        "descricao": "Plano inteligente 50/30/20 adaptável",
        "mensagens": [
            "Minha renda é R$ 8.500. Como devo organizar meu orçamento?",
            "Estou gastando bem para quem ganha R$ 6.000 por mês?",
            "O que é a regra 50/30/20 e como posso aplicar na minha renda de R$ 10.000?",
        ],
    },
    "3. get_card_optimization (F2)": {
        "icon": "💳",
        "descricao": "Recomendação de cartão, valoração de milhas (M2.3) e promoções (M2.6)",
        "mensagens": [
            "Minha renda é R$ 8.500. Qual cartão de crédito devo pedir?",
            "Quero maximizar minhas milhas. Qual cartão me indica?",
            "Vale a pena transferir pontos agora pensando nos bônus do mercado?",
            "Como minhas milhas estão sendo precificadas hoje?",
        ],
    },
    "4. get_spending_alerts (MX.3)": {
        "icon": "🔔",
        "descricao": "Alertas proativos, burn-rate e anomalias",
        "mensagens": [
            "Tem algum alerta nas minhas finanças ou gastos com assinatura?",
            "O que devo me preocupar financeiramente agora?",
            "Meu ritmo de gastos está muito alto neste mês?",
        ],
    },
    "5. get_goals_summary (MX.2)": {
        "icon": "🎯",
        "descricao": "Progresso de metas financeiras",
        "mensagens": [
            "Como estão minhas metas financeiras?",
            "Quanto falta para minha reserva de emergência?",
        ],
    },
    "6. get_financing_simulation (F3)": {
        "icon": "🏠",
        "descricao": "Simulação completa, ajuste de inflação (M3.1) e 'E se eu esperar?' (M3.4)",
        "mensagens": [
            "Quero comprar um carro de R$ 60.000. Vale a pena financiar ou poupar?",
            "Vou dar entrada de R$ 80.000 num apê de 400 mil. E se eu esperar 6 meses rendendo a entrada?",
            "Considerando a inflação (IPCA), ainda vale a pena esperar e investir antes de comprar a casa?",
            "Pensando em fazer uma reforma de R$ 30.000, financio pelo banco ou faço consórcio?",
        ],
    },
    "7. get_fiscal_report (F4)": {
        "icon": "📑",
        "descricao": "Relatório PJ/MEI, categorização granular (M4.2) e Uso Misto (M4.3)",
        "mensagens": [
            "Quanto vou pagar de DAS esse mês como MEI?",
            "Me dá um relatório detalhado das despesas de marketing e software do meu negócio.",
            "Acho que passei compras de mercado no cartão da empresa. Pode conferir meu uso misto?",
        ],
    },
    "8. get_peer_comparison (MX.4)": {
        "icon": "👥",
        "descricao": "Comparação de gastos com a base e IBGE/POF",
        "mensagens": [
            "Minha renda é R$ 8.000. Estou gastando mais que a média em moradia?",
            "Comparado a pessoas da mesma faixa, meu gasto no mercado é considerado alto?",
            "Qual o percentil das pessoas que conseguem guardar mais de R$ 2000 por mês ganhando 10k?",
        ],
    },
    "🏆 PERGUNTAS DE OURO": {
        "icon": "🚀",
        "descricao": "Testes complexos transversais de alto raciocínio",
        "mensagens": [
            "Minha renda é R$ 12.000. Tem algum gasto anormal este mês? E como meu perfil de gastos se compara com pessoas da mesma faixa de renda? Além disso, qual cartão você recomenda para mim?",
            "Sou PJ. Qual será meu DAS estimado de impostos neste mês? E aliás, estou querendo financiar um carro de R$ 90 mil para empresa, dando 30 mil de entrada... Vale mais a pena pegar o carro agora ou esperar 1 ano rendendo essa entrada em 100% do CDI?",
            "Me dê um safe-to-spend atualizado considerando que minha renda é R$ 8.500. Também quero saber se o meu cartão atual está sendo otimizado para a minha realidade financeira ou se estou perdendo dinheiro com anuidade.",
        ],
    },
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ESTADO DA SESSÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if "messages" not in st.session_state:
    st.session_state.messages = []      # {"role": ..., "content": ..., "latency": ..., "cost": ..., "tokens": ...}
if "total_cost_usd" not in st.session_state:
    st.session_state.total_cost_usd = 0.0
if "total_tokens" not in st.session_state:
    st.session_state.total_tokens = 0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES DE CHAMADA (AGORA COM MEMÓRIA)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_messages_history() -> list:
    """Converte o state do Streamlit para objetos Message do Langchain."""
    history = []
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            history.append(AIMessage(content=msg["content"]))
    return history

def call_agent_direct(user_id: str, new_message: str) -> tuple[str, float, int, float]:
    """
    Chama o agente via Python e inclui o get_openai_callback para tokens/custos.
    O histórico armazenado no Streamlit é repassado pro Agente.
    Retorna: (resposta, latencia_ms, total_tokens_chamada, custo_usd_chamada)
    """
    t0 = time.time()
    try:
        from app.agent.graph import build_financial_agent
        agent = build_financial_agent()
        
        # 1. Pega histórico existente + a nova mensagem
        messages = get_messages_history()
        # Injeta o contexto do usuário para as tools
        messages.append(SystemMessage(content=f"INFORMAÇÃO DE SISTEMA: O seu user_id atual é '{user_id}'. Sempre use este user_id quando chamar as ferramentas, a menos que especificado de outra forma."))
        messages.append(HumanMessage(content=new_message))
        
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        cost_usd = 0.0
        
        # 2. Rastreia custo
        with get_openai_callback() as cb:
            result = agent.invoke(
                {"messages": messages},
                config={"configurable": {"thread_id": user_id}},
            )
            # Em versoes mais novas/antigas o callback pega ou nao as sub-chamadas,
            # mas o LangGraph as vezes retorna o token usage no proprio AI message retornado!
            ai_message = result["messages"][-1]
            if hasattr(ai_message, "usage_metadata") and ai_message.usage_metadata:
                usage = ai_message.usage_metadata
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
            else:
                input_tokens = cb.prompt_tokens
                output_tokens = cb.completion_tokens
        
        # 3. Calculo do custo em USD baseado em GPT-4o-mini
        if input_tokens > 0 or output_tokens > 0:
            total_tokens = input_tokens + output_tokens
            cost_usd = (input_tokens / 1000.0) * PRICE_PER_1K_INPUT + \
                       (output_tokens / 1000.0) * PRICE_PER_1K_OUTPUT
        else:
            total_tokens = cb.total_tokens
            cost_usd = cb.total_cost  # Fallback caso a API do Callback consiga calcular

        latency = (time.time() - t0) * 1000
        return ai_message.content, latency, total_tokens, cost_usd

    except Exception as e:
        latency = (time.time() - t0) * 1000
        return f"Erro ao chamar agente diretamente: {e}", latency, 0, 0.0

def call_agent_http(user_id: str, new_message: str, api_url: str) -> tuple[str, float, int, float]:
    """
    Para o teste HTTP, a API REST atual não recebe histórico completo na rota `/chat/`,
    então seria stateless. Para testar COM memória, a rota precisa receber as mensagens ou 
    usar o checkpointer interno com o `user_id`. O Nexa no momento usa checkpointer SQLite nativo do LangGraph?
    
    A rota POST /chat/ envia message + user_id.
    O backend já mantém o estado atrelado a esse user_id se persistido.
    Vamos simplesmente enviar e inferir tokens caso possivel (a rota no backend não devolve custo hoje).
    """
    t0 = time.time()
    try:
        resp = requests.post(f"{api_url}/api/v1/chat/", json={"user_id": user_id, "message": new_message}, timeout=120)
        latency = (time.time() - t0) * 1000
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "(sem resposta)"), latency, 0, 0.0
        return f"Erro HTTP {resp.status_code}: {resp.text[:300]}", latency, 0, 0.0
    except Exception as e:
        return f"Erro HTTP inesperado: {e}", (time.time() - t0) * 1000, 0, 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INFERÊNCIA DA TOOL E UX
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _infer_tool(response: str) -> str:
    r = response.lower()
    tools_used = []
    if "simulacao de aquisicao" in r or "financiamento" in r or "consorcio" in r:
        tools_used.append("F3 - Financing")
    if "das " in r or "relatorio fiscal" in r or "receita bruta" in r:
        tools_used.append("F4 - Fiscal Report")
    if "comparacao com pares" in r or "poupanca" in r or "acima da media" in r:
        tools_used.append("MX.4 - Peers Compare")
    if "plano de acao" in r or "50/30/20" in r or "orcamento inteligente" in r:
        tools_used.append("M1.3 - Budget")
    if "card" in r or "cartao" in r or "anuidade" in r or "pontos" in r:
        tools_used.append("F2 - Cards")
    if "alerta" in r or "anomalia" in r:
        tools_used.append("MX.3 - Alerts")
    if "meta" in r or "progresso" in r:
        tools_used.append("MX.2 - Goals")
    if "diagnostico" in r or "safe-to-spend" in r or ("saude" in r and "score" in r):
        tools_used.append("F1 - Forecast")
    
    return " · ".join(tools_used)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIDEBAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with st.sidebar:
    st.title("🧠 Nexa Advanced Test")
    st.caption("Teste de Memória, Tools Múltiplas e Custos LLM.")

    st.subheader("Configurações")
    modo = st.radio("Integração", ["Direto (Python + Memória + Token Tracker)", "HTTP FastAPI (Rotas)"])
    
    api_url = "http://localhost:8000"
    if "HTTP" in modo:
        st.caption("Nota: No modo HTTP, tokens e custos não constam aqui. A memória depende do Checkpointer no Backend.")
        api_url = st.text_input("URL Backend", value="http://localhost:8000")

    user_id = st.text_input("UserID de Teste", value="golden_user_777")
    
    st.subheader("📊 Métricas de Custo")
    c1, c2 = st.columns(2)
    c1.metric("Custo Total", f"${st.session_state.total_cost_usd:.4f}")
    c2.metric("Tokens Usados", f"{st.session_state.total_tokens:,}")
    
    if st.button("🗑 Limpar Memória"):
        st.session_state.messages = []
        st.session_state.total_cost_usd = 0.0
        st.session_state.total_tokens = 0
        st.rerun()

    st.divider()
    st.subheader("Cenários de Teste")
    
    for category, config in TOOL_SCENARIOS.items():
        with st.expander(f"{config['icon']} {category}"):
            st.caption(config["descricao"])
            for i, msg in enumerate(config["mensagens"]):
                # Create a unique key using both category name (hash/truncated) and index
                btn_key = f"btn_{category[:5].strip()}_{i}_{hash(msg) % 10000}"
                if st.button(msg[:60] + "...", key=btn_key):
                    st.session_state["pending_message"] = msg

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHAT PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.title("Agente Nexa Inteligente")
st.markdown("Interface para validar a __proatividade__ do agente, **retenção de memória** e os **múltiplos chamados (tools)**.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            meta = f"⏱ {msg['latency']:.0f}ms"
            if "Direto" in modo and msg.get("tokens", 0) > 0:
                meta += f" | 🪙 {msg['tokens']} tokens | 💰 ${msg['cost']:.5f}"
            if msg.get("tool_hint"):
                meta += f" | 🛠️ {msg['tool_hint']}"
            st.caption(meta)

pending = st.session_state.pop("pending_message", None)
user_input = st.chat_input("Digite sua pergunta ou clique em um Cenário...")
message_to_send = pending or user_input

if message_to_send:
    st.session_state.messages.append({
        "role": "user", "content": message_to_send, "latency": 0, "cost": 0.0, "tokens": 0
    })
    
    with st.chat_message("user"):
        st.markdown(message_to_send)
        
    with st.chat_message("assistant"):
        with st.spinner("Nexa consultando o Cérebro Financeiro..."):
            if "HTTP" in modo:
                response, lat, toks, cost = call_agent_http(user_id, message_to_send, api_url)
            else:
                response, lat, toks, cost = call_agent_direct(user_id, message_to_send)
                # Acumula metricas da sessão
                st.session_state.total_tokens += toks
                st.session_state.total_cost_usd += cost
        
        st.markdown(response)
        hint = _infer_tool(response)
        
        meta = f"⏱ {lat:.0f}ms"
        if "Direto" in modo and toks > 0:
            meta += f" | 🪙 {toks} tokens | 💰 ${cost:.5f}"
        if hint:
            meta += f" | 🛠️ Tools inferidas: {hint}"
        st.caption(meta)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response,
        "latency": lat,
        "cost": cost,
        "tokens": toks,
        "tool_hint": hint
    })
    st.rerun()
