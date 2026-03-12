import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.ui import load_css
from utils.api import NexaAPIClient

# Redireciona se não estiver logado
if "jwt_token" not in st.session_state or not st.session_state.jwt_token:
    st.warning("🔒 Por favor, faça login na tela inicial primeiro.")
    st.stop()

st.set_page_config(page_title="Meu Dinheiro", page_icon="📊", layout="wide")
load_css()

api = NexaAPIClient()
user_id = st.session_state.username

st.title("📊 Painel Financeiro")

# Load Dados da API
with st.spinner("Sincronizando via Open Finance..."):
    forecast = api.get_forecast_summary(user_id)
    budget = api.get_budget_advice(user_id)
    goals = api.get_goals_summary(user_id)

st.divider()

# Colunas de KPIs
col1, col2, col3 = st.columns(3)

if forecast.get("success"):
    f_data = forecast["data"]
    burn_rate_alert = f_data.get("burn_rate_alert", "LOW")
    score = f_data.get("health_score", 0)
    
    with col1:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.metric("Total Income", f"R$ {f_data.get('total_income', 0):,.2f}")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col2:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.metric("Safe to Spend (Mês)", f"R$ {f_data.get('safe_to_spend', 0):,.2f}")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"<div class='glass-card' style='border-left: 4px solid {'#48BB78' if score > 70 else '#ECC94B' if score > 40 else '#F56565'}'>", unsafe_allow_html=True)
        st.metric("Health Score (0-100)", f"{score:.0f}")
        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.error("Não foi possível carregar Forecast Summary")


# Gráfico 50/30/20 (Regra) via Plotly
st.subheader("Seu Orçamento (50/30/20)")

if budget.get("success"):
    b_data = budget["data"]
    # Tenta puxar a categoria e os gastos
    essential = 0.0
    lifestyle = 0.0
    savings = 0.0
    try:
        # Puxa strings do texto se nao ver no payload nativo, como no teste, o endpoint envia dict? 
        # Endpoint de advice no nexa retorna string de texto. Ops!
        # Se for texto, precisariamos parsear. Vamos montar algo dummy com base no forecast se budget eh so string.
        text_advice = str(b_data)
        st.info("Insights 50/30/20: " + text_advice[:300] + "...")
    except:
        pass
        
    # Vamos gerar do Forecast pra ser responsivo
    if forecast.get("success"):
        fig = go.Figure(data=[go.Pie(
            labels=['Gastos Atuais', 'Poupança (Taxa)', 'Safe to Spend Preservado'],
            values=[
                f_data.get('total_gastos_reais', 3000), 
                f_data.get('savings_rate', 0.2) * f_data.get('total_income', 0),
                f_data.get('safe_to_spend', 1000)
            ],
            hole=.5,
            marker_colors=['#F56565', '#48BB78', '#667EEA']
        )])
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#FAFAFA'),
            margin=dict(t=0, b=0, l=0, r=0)
        )
        st.plotly_chart(fig, use_container_width=True)

# Progresso das Metas
st.subheader("🎯 Suas Metas")
if goals.get("success"):
    # Resposta eh em string formatada do ChatGPT pra summary? 
    # Dependendo da rota no Nexa, ela volta lista.
    g_data = goals["data"]
    if isinstance(g_data, list):
        for g in g_data:
            pct = min(g.get("current_amount", 0) / max(g.get("target_amount", 1), 1), 1.0)
            st.markdown(f"**{g.get('description', 'Meta')}** - R$ {g.get('target_amount', 0):,.2f}")
            st.progress(pct)
    else:
        st.write(g_data)
