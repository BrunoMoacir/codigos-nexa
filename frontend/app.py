import streamlit as st
import time
from utils.ui import load_css, kpi_card, section_header
from utils.api import NexaAPIClient

st.set_page_config(
    page_title="Nexa · Central Financeira",
    page_icon="💜",
    layout="centered",
    initial_sidebar_state="collapsed",
)

load_css()

# ── Estado da Sessão ──────────────────────────────────────────────────────────
if "jwt_token" not in st.session_state:
    st.session_state.jwt_token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None

api = NexaAPIClient()


# ── Tela de Login ─────────────────────────────────────────────────────────────

def login_screen():
    # Logo + tagline centralizados
    st.markdown("""
    <div style="text-align:center; padding: 2.5rem 0 1rem 0;">
        <div style="font-size:3rem; margin-bottom:0.5rem;">💜</div>
        <h1 style="font-size:2.2rem; font-weight:800; background:linear-gradient(135deg,#6366f1,#a78bfa);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0;">
            Nexa
        </h1>
        <p style="color:#64748b; font-size:0.95rem; margin-top:0.4rem; letter-spacing:0.02em;">
            Seu cérebro financeiro com IA
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Card central de login
    st.markdown('<div class="glass-card" style="max-width:420px; margin:0 auto;">', unsafe_allow_html=True)

    st.markdown('<p style="font-size:0.8rem;color:#64748b;text-align:center;margin-bottom:1.2rem;">ACESSE OU CRIE SUA CONTA</p>', unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["Entrar", "Criar Conta"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Email/Usuário", placeholder="🪪  ex: golden_user_777 ou golden@nexa.com", label_visibility="collapsed")
            password = st.text_input("Senha", placeholder="🔑  Senha", type="password", label_visibility="collapsed")

            col_btn, _ = st.columns([3, 1])
            with col_btn:
                submit = st.form_submit_button("Entrar no Nexa →", use_container_width=True)

            if submit:
                if not username or not password:
                    st.error("Preencha usuário e senha.")
                else:
                    with st.spinner("Autenticando…"):
                        time.sleep(0.4)
                        resp = api.login(username, password)
                    if resp.get("success"):
                        st.session_state.username = username
                        st.session_state.user_id = resp.get("user_id")
                        st.success("✅ Bem-vindo! Abrindo seu painel…")
                        time.sleep(0.8)
                        st.rerun()
                    else:
                        st.error(f"❌ {resp.get('error', 'Credenciais inválidas')}")

    with tab_register:
        with st.form("register_form", clear_on_submit=True):
            reg_name = st.text_input("Nome Completo", placeholder="👤 Seu nome completo", label_visibility="collapsed")
            reg_email = st.text_input("E-mail", placeholder="📧 Seu e-mail (obrigatório)", label_visibility="collapsed")
            reg_pass = st.text_input("Senha", placeholder="🔑  Crie uma senha (mín. 6 chars)", type="password", label_visibility="collapsed")

            col_btn2, _ = st.columns([3, 1])
            with col_btn2:
                submit_reg = st.form_submit_button("Criar minha conta ✦", use_container_width=True)

            if submit_reg:
                if not reg_name or not reg_user or not reg_pass:
                    st.error("Preencha nome, usuário e senha.")
                elif len(reg_pass) < 6:
                    st.error("A senha deve ter pelo menos 6 caracteres.")
                else:
                    with st.spinner("Criando sua conta Nexa…"):
                        resp = api.register(reg_user, reg_pass, reg_name, reg_email)
                        
                    if resp.get("success"):
                        st.success("🎉 Conta criada com sucesso! Faça login abaixo ou aguarde o redirecionamento...")
                        # Auto-login após register
                        st.session_state.username = reg_user
                        st.session_state.user_id = resp.get("user_id")
                        st.session_state.jwt_token = resp.get("token")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(f"❌ Erro ao criar conta: {resp.get('error')}")

    st.markdown("</div>", unsafe_allow_html=True)

    # Badge de status da API
    st.markdown("""
    <div style="text-align:center; margin-top:1.5rem;">
        <span style="font-size:0.7rem; color:#475569; letter-spacing:0.08em;">
            🔒  Comunicação criptografada com JWT · Open Finance integrado
        </span>
    </div>
    """, unsafe_allow_html=True)


# ── Tela Home (pós-login) ─────────────────────────────────────────────────────

def home_screen():
    # Sidebar
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:1rem 0.5rem;">
            <div style="font-size:0.7rem;color:#475569;letter-spacing:0.1em;margin-bottom:0.3rem;">CONTA</div>
            <div style="font-weight:700;color:#e2e8f0;font-size:1rem;">@{st.session_state.username}</div>
            <div style="font-size:0.72rem;color:#64748b;margin-top:2px;">Nexa Premium ✦</div>
        </div>
        <hr style="border-color:rgba(99,102,241,0.15);margin:0.5rem 0;">
        """, unsafe_allow_html=True)

        if st.button("Sair →", use_container_width=True):
            st.session_state.jwt_token = None
            st.session_state.username = None
            st.rerun()

    # Cabeçalho
    hora = time.localtime().tm_hour
    saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    st.markdown(f"""
    <div style="margin-bottom:1.5rem;">
        <p style="color:#6366f1;font-size:0.85rem;font-weight:600;letter-spacing:0.06em;margin-bottom:4px;">
            NEXA CENTRAL
        </p>
        <h1 style="margin:0; font-size:2rem;">{saudacao}, {st.session_state.username.split('_')[0].title()} 👋</h1>
        <p style="color:#64748b;font-size:0.9rem;margin-top:6px;">
            Escolha uma seção abaixo para começar.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Cards de navegação
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <a href="/Chat_Inteligente" target="_self" style="text-decoration:none;">
          <div class="glass-card" style="cursor:pointer; background:linear-gradient(135deg,rgba(99,102,241,0.12),rgba(139,92,246,0.08));">
            <div style="font-size:2.2rem;margin-bottom:0.6rem;">💬</div>
            <div style="font-weight:700;font-size:1.05rem;color:#e2e8f0;">Chat Inteligente</div>
            <div style="color:#64748b;font-size:0.82rem;margin-top:6px;line-height:1.5;">
              Converse com seu agente financeiro. Ele conhece seu histórico completo e usa 8 ferramentas analíticas.
            </div>
            <div style="margin-top:12px;">
              <span class="badge badge-purple">LangGraph IA</span>
            </div>
          </div>
        </a>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <a href="/Meu_Dinheiro" target="_self" style="text-decoration:none;">
          <div class="glass-card" style="cursor:pointer; background:linear-gradient(135deg,rgba(16,185,129,0.1),rgba(5,150,105,0.06));">
            <div style="font-size:2.2rem;margin-bottom:0.6rem;">📊</div>
            <div style="font-weight:700;font-size:1.05rem;color:#e2e8f0;">Meu Dinheiro</div>
            <div style="color:#64748b;font-size:0.82rem;margin-top:6px;line-height:1.5;">
              Dashboard financeiro completo com KPIs, regra 50/30/20 e progresso das suas metas.
            </div>
            <div style="margin-top:12px;">
              <span class="badge badge-green">Dados Reais</span>
            </div>
          </div>
        </a>
        """, unsafe_allow_html=True)

    # Rodapé do card
    st.markdown("""
    <div class="glass-card" style="background:rgba(99,102,241,0.05); border-style:dashed; padding:16px 24px;">
        <p style="margin:0; font-size:0.8rem; color:#475569; text-align:center;">
            💡 <strong style="color:#6366f1">Dica</strong>: 
            Acesse o Chat e pergunte <em>"Como está minha saúde financeira?"</em> para uma análise completa.
        </p>
    </div>
    """, unsafe_allow_html=True)


# ── Roteamento ────────────────────────────────────────────────────────────────
if not st.session_state.jwt_token:
    login_screen()
else:
    home_screen()
