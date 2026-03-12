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
    
    income = 10000.0
    if forecast.get("success"):
        income = forecast.get("data", {}).get("financial_health", {}).get("total_income", 10000.0)
        
    budget = api.get_budget_advice(user_id, monthly_income=income)
    goals = api.get_goals_summary(user_id)

st.divider()

# Colunas de KPIs
col1, col2, col3 = st.columns(3)

if forecast.get("success"):
    f_data = forecast["data"]
    health = f_data.get("financial_health", {})
    sts = f_data.get("safe_to_spend", {})
    
    burn_rate_alert = health.get("burn_rate_alert", "NORMAL")
    score = health.get("health_score", 0)
    
    with col1:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.metric("Renda Mensal (Líquida)", f"R$ {health.get('total_income', 0):,.2f}")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col2:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.metric("Safe to Spend (Mês)", f"R$ {sts.get('safe_to_spend_total', 0):,.2f}")
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
    try:
        if isinstance(b_data, dict) and "summary_text" in b_data:
            text_advice = b_data["summary_text"]
            st.info("💡 **Insights 50/30/20:**\n\n" + text_advice)
            
            # Gráfico de Rosca baseado nos grupos do Budget
            groups = b_data.get("group_summary", [])
            if groups:
                # Converter lista para dicionário para facilitar acesso
                g_map = {g['group']: g.get('current_pct', 0) for g in groups}
                
                fig = go.Figure(data=[go.Pie(
                    labels=['Essenciais', 'Desejos', 'Poupança'],
                    values=[
                        g_map.get('essenciais', 0),
                        g_map.get('desejos', 0),
                        g_map.get('poupanca', 0)
                    ],
                    hole=.5,
                    marker_colors=['#F56565', '#ECC94B', '#48BB78']
                )])
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', 
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#FAFAFA'),
                    margin=dict(t=0, b=0, l=0, r=0)
                )
                st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao processar budget: {e}")

# Progresso das Metas
st.subheader("🎯 Suas Metas")
if goals.get("success"):
    g_data = goals["data"]
    goal_list = g_data.get("goals", [])
    
    if goal_list:
        for g in goal_list:
            pct = g.get("progress_pct", 0) / 100.0
            st.markdown(f"**{g.get('name', 'Meta')}** — R$ {g.get('current_amount', 0):,.2f} de R$ {g.get('target_amount', 0):,.2f}")
            st.progress(pct)
            
            proj = g.get("projection", {})
            if proj.get("suggestion"):
                st.caption(f"💡 {proj['suggestion']}")
    else:
        st.write("Você ainda não tem metas cadastradas.")
else:
    st.error("Não foi possível carregar suas metas.")
