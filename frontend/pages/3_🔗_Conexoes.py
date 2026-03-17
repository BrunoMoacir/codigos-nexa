import streamlit as st
import time
from utils.ui import load_css
from utils.api import NexaAPIClient
import streamlit.components.v1 as components

# ── Auth guard ────────────────────────────────────────────────────────────────
if "jwt_token" not in st.session_state or not st.session_state.jwt_token:
    st.warning("🔒 Faça login na tela inicial primeiro.")
    st.page_link("app.py", label="Ir para o Login", icon="🏠")
    st.stop()

st.set_page_config(
    page_title="Conexões · Nexa",
    page_icon="🔗",
    layout="centered",
)
load_css()

api = NexaAPIClient()
user_id = st.session_state.get("user_id")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="padding:1rem 0.5rem 0.5rem 0.5rem;">
        <div style="font-size:0.7rem;color:#475569;letter-spacing:0.1em;margin-bottom:4px;">CONTA</div>
        <div style="font-weight:700;color:#e2e8f0;font-size:1rem;">@{st.session_state.username}</div>
    </div>
    <hr style="border-color:rgba(99,102,241,0.15);margin:0.4rem 0 0.8rem 0;">
    """, unsafe_allow_html=True)

    if st.button("← Voltar ao Início", use_container_width=True):
        st.switch_page("app.py")

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:2rem; text-align: center;">
  <p style="color:#10b981;font-size:0.78rem;font-weight:600;letter-spacing:0.08em;margin-bottom:4px;">
    OPEN FINANCE
  </p>
  <h1 style="margin:0; font-size:2.5rem;">🔗 Suas Conexões</h1>
  <p style="color:#64748b;font-size:0.95rem;margin-top:6px; max-width: 500px; margin-left: auto; margin-right: auto;">
    Conecte suas contas bancárias de forma segura para alimentar a inteligência financeira do Nexa.
  </p>
</div>
""", unsafe_allow_html=True)

if "pluggy_token" not in st.session_state:
    st.session_state.pluggy_token = None

st.markdown('<div class="glass-card" style="padding: 2rem; max-width: 600px; margin: 0 auto;">', unsafe_allow_html=True)

st.markdown("""
<div style="display: flex; align-items: center; gap: 15px; margin-bottom: 1.5rem;">
    <div style="width: 48px; height: 48px; background: rgba(99,102,241,0.1); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem;">
        🏦
    </div>
    <div>
        <h3 style="margin: 0; font-size: 1.2rem; color: #e2e8f0;">Adicionar nova conta</h3>
        <p style="margin: 0; font-size: 0.85rem; color: #94a3b8;">Via Pluggy Open Finance</p>
    </div>
</div>
""", unsafe_allow_html=True)

if not st.session_state.pluggy_token:
    st.info("💡 A conexão é segura, em formato de leitura e gerida pelas regras do Open Finance Brasil.")
    if st.button("🔌 Conectar Instituição (Gerar Token)", use_container_width=True, type="primary"):
        with st.spinner("Solicitando token seguro..."):
            resp = api.create_pluggy_token()
            if resp.get("success"):
                st.session_state.pluggy_token = resp.get("token")
                st.rerun()
            else:
                st.error(f"Erro ao gerar token: {resp.get('error')}")
else:
    st.success("✅ Conexão estabelecida com a provedora. Carregando widget...")
    
    # HTML do Widget Oficial da Pluggy
    pluggy_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.pluggy.ai/pluggy-connect/v1.0.0/pluggy-connect.js"></script>
        <style>
            body {{ margin: 0; padding: 0; background: transparent; display: flex; justify-content: center; align-items: center; height: 100vh; }}
            #pluggy-container {{ width: 100%; max-width: 400px; height: 600px; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        </style>
    </head>
    <body>
        <div id="pluggy-container"></div>
        <script>
            const connectToken = "{st.session_state.pluggy_token}";
            
            const pluggyConnect = new PluggyConnect({{
                connectToken: connectToken,
                container: document.getElementById('pluggy-container'),
                onSuccess: function(itemData) {{
                    console.log('Success:', itemData);
                    window.parent.postMessage({{type: 'pluggy-success', item: itemData}}, '*');
                }},
                onError: function(error) {{
                    console.error('Error:', error);
                    window.parent.postMessage({{type: 'pluggy-error', error: error}}, '*');
                }},
                onClose: function() {{
                    window.parent.postMessage({{type: 'pluggy-close'}}, '*');
                }}
            }});
            
            pluggyConnect.init();
        </script>
    </body>
    </html>
    """
    
    # Embed do HTML no Streamlit
    components.html(pluggy_html, height=650)
    
    if st.button("⬅️ Cancelar / Fechar Widget", use_container_width=True):
        st.session_state.pluggy_token = None
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# ── Rodapé ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align: center; margin-top: 3rem; color: #64748b; font-size: 0.8rem;">
    Segurança de nível bancário testada e validada pelo Banco Central do Brasil.<br>
    Suas credenciais nunca são armazenadas pelo Nexa.
</div>
""", unsafe_allow_html=True)
