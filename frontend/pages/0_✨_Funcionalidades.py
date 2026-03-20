import streamlit as st
import json
from utils.ui import load_css, section_header
from utils.api import NexaAPIClient

if "jwt_token" not in st.session_state or not st.session_state.jwt_token:
    st.warning("🔒 Faça login na tela inicial primeiro.")
    st.page_link("app.py", label="Ir para o Login", icon="🏠")
    st.stop()

st.set_page_config(page_title="Funcionalidades · Nexa", page_icon="✨", layout="wide")
load_css()

api = NexaAPIClient()
user_id = st.session_state.get("user_id") or st.session_state.get("username", "")

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="padding:1rem 0.5rem 0.5rem 0.5rem;">
        <div style="font-size:0.7rem;color:#475569;letter-spacing:0.1em;margin-bottom:4px;">CONTA</div>
        <div style="font-weight:700;color:#e2e8f0;font-size:1rem;">@{user_id}</div>
    </div>
    <hr style="border-color:rgba(99,102,241,0.15);margin:0.4rem 0;">
    """, unsafe_allow_html=True)

    if st.button("← Voltar ao Início", use_container_width=True):
        st.switch_page("app.py")

# ── Header ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:1.5rem;">
  <p style="color:#6366f1;font-size:0.78rem;font-weight:600;letter-spacing:0.08em;margin-bottom:4px;">TESTE DE ENDPOINTS</p>
  <h1 style="margin:0;">✨ Funcionalidades & API</h1>
  <p style="color:#64748b;font-size:0.88rem;margin-top:6px;">Teste todos os endpoints da Nexa em tempo real</p>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════════

tabs = st.tabs([
    "📊 Transações",
    "💰 Forecast",
    "🎯 Metas",
    "💳 Orçamento",
    "🏦 Conexões",
    "🔗 Context Override",
    "❤️ Health Score",
])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: Transações
# ═══════════════════════════════════════════════════════════════════════════

with tabs[0]:
    st.markdown("### 📊 GET /api/v1/transactions/{user_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.text_input("Data início (YYYY-MM-DD)", value="", placeholder="2025-01-01")
        category_filter = st.text_input("Categoria (opcional)", value="")
    with col2:
        end_date = st.text_input("Data fim (YYYY-MM-DD)", value="", placeholder="2026-03-20")
        tx_type = st.selectbox("Tipo", ["todos", "debit", "credit"])

    if st.button("🔍 Buscar Transações", key="btn_txns", use_container_width=True):
        with st.spinner("Buscando transações…"):
            try:
                import requests
                params = {"user_id": user_id, "limit": 50}
                if start_date:
                    params["start_date"] = start_date
                if end_date:
                    params["end_date"] = end_date
                if category_filter:
                    params["category"] = category_filter
                if tx_type != "todos":
                    params["transaction_type"] = tx_type

                url = f"{api.base_url}/transactions/{user_id}"
                resp = requests.get(url, headers=api._headers(), params=params, timeout=10)
                data = resp.json()
                
                if resp.status_code == 200:
                    st.success(f"✅ {data.get('total', 0)} transações encontradas")
                    st.json(data)
                else:
                    st.error(f"Erro {resp.status_code}: {data.get('detail', 'Desconhecido')}")
            except Exception as e:
                st.error(f"Erro: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: Forecast
# ═══════════════════════════════════════════════════════════════════════════

with tabs[1]:
    st.markdown("### 💰 GET /api/v1/forecast/{user_id}")
    
    if st.button("🔍 Buscar Forecast", key="btn_forecast", use_container_width=True):
        with st.spinner("Calculando forecast…"):
            resp = api.get_forecast_summary(user_id)
            if resp.get("success"):
                st.success("✅ Forecast carregado")
                st.json(resp["data"])
            else:
                st.error(f"Erro: {resp.get('error')}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: Metas
# ═══════════════════════════════════════════════════════════════════════════

with tabs[2]:
    st.markdown("### 🎯 GET /api/v1/goals/{user_id}")
    
    if st.button("🔍 Buscar Metas", key="btn_goals", use_container_width=True):
        with st.spinner("Carregando metas…"):
            resp = api.get_goals_summary(user_id)
            if resp.get("success"):
                st.success("✅ Metas carregadas")
                st.json(resp["data"])
            else:
                st.error(f"Erro: {resp.get('error')}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: Orçamento
# ═══════════════════════════════════════════════════════════════════════════

with tabs[3]:
    st.markdown("### 💳 GET /api/v1/budget/{user_id}")
    
    monthly_income = st.number_input("Renda mensal (R$)", value=10000.0, min_value=1000.0)
    
    if st.button("🔍 Buscar Orçamento", key="btn_budget", use_container_width=True):
        with st.spinner("Calculando orçamento…"):
            resp = api.get_budget_advice(user_id, monthly_income=monthly_income)
            if resp.get("success"):
                st.success("✅ Orçamento calculado")
                st.json(resp["data"])
            else:
                st.error(f"Erro: {resp.get('error')}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 5: Conexões Pluggy
# ═══════════════════════════════════════════════════════════════════════════

with tabs[4]:
    st.markdown("### 🏦 Pluggy Items")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📋 Listar Contas", key="btn_items", use_container_width=True):
            with st.spinner("Buscando contas…"):
                resp = api.get_pluggy_items()
                if resp.get("success"):
                    st.success("✅ Contas encontradas")
                    st.json(resp["data"])
                else:
                    st.error(f"Erro: {resp.get('error')}")
    
    with col2:
        if st.button("🧪 Criar Sandbox", key="btn_sandbox", use_container_width=True):
            with st.spinner("Criando conta test…"):
                resp = api.create_sandbox_item()
                if resp.get("success"):
                    st.success("✅ Sandbox criado")
                    st.json(resp["data"])
                else:
                    st.error(f"Erro: {resp.get('error')}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 6: Context Override
# ═══════════════════════════════════════════════════════════════════════════

with tabs[5]:
    st.markdown("### 🔗 Context Override (PF/PJ)")
    
    col1, col2 = st.columns(2)
    with col1:
        tx_id = st.text_input("Transaction ID", placeholder="ex: txn_12345")
        context = st.selectbox("Classificação", ["PF", "PJ"])
        reason = st.text_input("Motivo (opcional)", placeholder="Por quê?")
    
    with col2:
        if st.button("💾 Salvar Override", key="btn_override", use_container_width=True):
            if not tx_id:
                st.error("Informe Transaction ID")
            else:
                with st.spinner("Salvando…"):
                    try:
                        import requests
                        payload = {
                            "transaction_id": tx_id,
                            "corrected_context": context,
                            "reason": reason or None
                        }
                        url = f"{api.base_url}/context/override?user_id={user_id}"
                        resp = requests.post(url, json=payload, headers=api._headers(), timeout=10)
                        if resp.status_code == 200:
                            st.success("✅ Override salvo")
                            st.json(resp.json())
                        else:
                            st.error(f"Erro {resp.status_code}: {resp.json().get('detail', 'Desconhecido')}")
                    except Exception as e:
                        st.error(f"Erro: {str(e)}")
        
        if st.button("📊 Listar Overrides", key="btn_list_overrides", use_container_width=True):
            with st.spinner("Carregando…"):
                try:
                    import requests
                    url = f"{api.base_url}/context/overrides?user_id={user_id}"
                    resp = requests.get(url, headers=api._headers(), timeout=10)
                    if resp.status_code == 200:
                        st.success("✅ Overrides carregados")
                        st.json(resp.json())
                    else:
                        st.error(f"Erro {resp.status_code}")
                except Exception as e:
                    st.error(f"Erro: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 7: Health Score
# ═══════════════════════════════════════════════════════════════════════════

with tabs[6]:
    st.markdown("### ❤️ GET /api/v1/health-score/history/{user_id}")
    
    months = st.slider("Meses de histórico", min_value=1, max_value=24, value=6)
    
    if st.button("📈 Buscar Health Score", key="btn_health", use_container_width=True):
        with st.spinner("Calculando health score…"):
            try:
                import requests
                url = f"{api.base_url}/health-score/history/{user_id}?months={months}"
                resp = requests.get(url, headers=api._headers(), timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"✅ Score atual: {data.get('current_score', '—')}/100 ({data.get('trend', '—')})")
                    st.json(data)
                else:
                    st.error(f"Erro {resp.status_code}: {resp.json().get('detail', 'Desconhecido')}")
            except Exception as e:
                st.error(f"Erro: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════
# RODAPÉ
# ═══════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown("""
<div style="text-align:center; color:#64748b; font-size:0.8rem; margin-top:2rem;">
    💡 **Dica**: Se um endpoint falhar, verifique:
    1. Backend rodando: `cd backend && uvicorn app.main:app --reload`
    2. Token válido (login necessário)
    3. User ID correto (deve estar em `session_state`)
    4. Postgres ou DuckDB disponível
</div>
""", unsafe_allow_html=True)
