import streamlit as st
import time
from utils.ui import load_css
from utils.api import NexaAPIClient

st.set_page_config(
    page_title="Nexa Central",
    page_icon="💸",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Injetar CSS Premium
load_css()

# Estado da Sessão Global
if "jwt_token" not in st.session_state:
    st.session_state.jwt_token = None
if "username" not in st.session_state:
    st.session_state.username = None

api = NexaAPIClient()

def login_screen():
    st.markdown("<h1 style='text-align: center; color: white;'>Nexa Central</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #A0AEC0;'>Faça login para acessar seu cérebro financeiro</p>", unsafe_allow_html=True)
    
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Usuário (CPF ou ID)", placeholder="Ex: golden_user_777")
        password = st.text_input("Senha", type="password", placeholder="Sua senha secreta")
        
        submit = st.form_submit_button("Entrar no Nexa", use_container_width=True)
        
        if submit:
            with st.spinner("Autenticando..."):
                # Simular delay para feel premium
                time.sleep(0.5)
                # Chama login na API local
                # The auth token endpoint ignores "/api/v1", let's fix URL in python API client
                # Em nosso Mock, usamos a base da API e ajustamos a rota. Se funcionar ele injeta no session_state
                resp = api.login(username, password)
                if resp.get("success"):
                    st.session_state.username = username
                    st.success("Bem-vindo de volta! Redirecionando...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Erro: {resp.get('error', 'Credenciais inválidas')}")
    st.markdown("</div>", unsafe_allow_html=True)

def dashboard_home_screen():
    st.sidebar.title(f"Bem-vindo, {st.session_state.username}")
    if st.sidebar.button("Sair (Logout)"):
        st.session_state.jwt_token = None
        st.session_state.username = None
        st.rerun()
        
    st.title(f"Olá, {st.session_state.username} 👋")
    st.markdown("Use o menu lateral esquerdo para acessar:")
    
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    st.markdown("### 💬 Chat Inteligente")
    st.write("Fale com seu Agente Financeiro alimentado por IA. Ele se lembra de tudo e conhece todo seu histórico bancário.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    st.markdown("### 📊 Meu Dinheiro (Dashboard)")
    st.write("Acompanhe seus limites, o comportamento da regra 50/30/20 e suas faturas de maneira visual e rápida.")
    st.markdown("</div>", unsafe_allow_html=True)


if not st.session_state.jwt_token:
    login_screen()
else:
    dashboard_home_screen()
