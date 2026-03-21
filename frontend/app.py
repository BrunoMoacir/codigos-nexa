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
            username = st.text_input("Email", placeholder="📧  ex: seuemail@dominio.com", label_visibility="collapsed")
            password = st.text_input("Senha", placeholder="🔑  Senha", type="password", label_visibility="collapsed")

            col_btn, _ = st.columns([3, 1])
            with col_btn:
                submit = st.form_submit_button("Entrar no Nexa →", use_container_width=True)

            if submit:
                if not username or not password:
                    st.error("Preencha e-mail e senha.")
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
                if not reg_name or not reg_email or not reg_pass:
                    st.error("Preencha nome, e-mail e senha.")
                elif len(reg_pass) < 6:
                    st.error("A senha deve ter pelo menos 6 caracteres.")
                else:
                    with st.spinner("Criando sua conta Nexa…"):
                        resp = api.register(reg_email, reg_pass, reg_name)

                    if resp.get("success"):
                        # Auto-login após register
                        with st.spinner("Entrando…"):
                            login = api.login(reg_email, reg_pass)
                        if login.get("success"):
                            st.session_state.username = reg_email
                            st.session_state.user_id = login.get("user_id")
                            st.success("🎉 Conta criada e login feito! Abrindo seu painel…")
                            time.sleep(0.8)
                            st.rerun()
                        else:
                            st.success("🎉 Conta criada com sucesso! Faça login na aba Entrar.")
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
            st.session_state.user_id = None
            st.rerun()

    # Cabeçalho
    hora = time.localtime().tm_hour
    saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    display_name = (st.session_state.username or "").split("@")[0].split("_")[0]
    display_name = display_name.title() if display_name else ""

    st.markdown(f"""
    <div class="hero-banner">
      <div class="hero-kicker">NEXA CENTRAL</div>
      <h1 style="margin:0;">{saudacao}{', ' + display_name if display_name else ''} 👋</h1>
      <p class="hero-sub">Seu cockpit financeiro completo: visão diária, conexões bancárias e estratégia avançada.</p>
    </div>
    """, unsafe_allow_html=True)

    section_header("🧭", "Módulos principais")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("""
          <div class="nav-tile">
            <div style="font-size:1.8rem;">📊</div>
            <div class="nav-tile-title">Meu Dinheiro</div>
            <div class="nav-tile-desc">KPIs, cashflow, regra 50/30/20, metas e operações em tempo real.</div>
            <div style="margin-top:10px;"><span class="badge badge-green">Dados Reais</span></div>
          </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/2_📊_Meu_Dinheiro.py", label="→ Acessar Meu Dinheiro")
    with c2:
        st.markdown("""
          <div class="nav-tile">
            <div style="font-size:1.8rem;">🧠</div>
            <div class="nav-tile-title">Estratégias Nexa</div>
            <div class="nav-tile-desc">Optimizer, Architect, Fiscal Intelligence, peers e alertas de ação.</div>
            <div style="margin-top:10px;"><span class="badge badge-purple">Premium</span></div>
          </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/4_🧠_Estrategias_Nexa.py", label="→ Acessar Estratégias")

    c3, c4 = st.columns(2, gap="large")
    with c3:
        st.markdown("""
          <div class="nav-tile">
            <div style="font-size:1.8rem;">🔗</div>
            <div class="nav-tile-title">Conexões Open Finance</div>
            <div class="nav-tile-desc">Conecte bancos reais via Pluggy e sincronize transações com 1 clique.</div>
            <div style="margin-top:10px;"><span class="badge badge-yellow">Pluggy</span></div>
          </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/3_🔗_Conexoes.py", label="→ Acessar Conexões")
    with c4:
        st.markdown("""
          <div class="nav-tile">
            <div style="font-size:1.8rem;">💬</div>
            <div class="nav-tile-title">Chat Inteligente</div>
            <div class="nav-tile-desc">Assistente financeiro com ferramentas analíticas e contexto da sua conta.</div>
            <div style="margin-top:10px;"><span class="badge badge-purple">LangGraph IA</span></div>
          </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/1_💬_Chat_Inteligente.py", label="→ Acessar Chat")

    section_header("⚡", "Acesso rápido")
    q1, q2, q3 = st.columns(3)
    q1.metric("Modo", "Teste Real", delta="sem mock")
    q2.metric("Fonte", "Open Finance", delta="Pluggy integrado")
    q3.metric("Cobertura", "Módulos ativos", delta="Dashboard + Estratégias")

    st.markdown("""
    <div class="glass-card" style="background:rgba(99,102,241,0.05); border-style:dashed; padding:16px 24px;">
      <p style="margin:0; font-size:0.82rem; color:#94a3b8; text-align:center;">
        💡 Dica: abra <strong style="color:#c7d2fe;">Meu Dinheiro</strong> para validar consistência dos dados e depois use
        <strong style="color:#c7d2fe;">Estratégias Nexa</strong> para recomendações acionáveis.
      </p>
    </div>
    """, unsafe_allow_html=True)


# ── Roteamento ────────────────────────────────────────────────────────────────
if not st.session_state.jwt_token:
    login_screen()
else:
    home_screen()
