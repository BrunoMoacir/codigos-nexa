import streamlit as st
import base64

DESIGN_TOKENS = {
    "primary": "#6366f1",
    "secondary": "#8b5cf6",
    "success": "#10b981",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "text_main": "#e2e8f0",
    "text_muted": "#94a3b8",
    "surface": "rgba(15, 23, 42, 0.46)",
}


def load_css():
    """
    CSS Super Premium — Dark mode vibrante, Gradientes fluídos, Glassmorphism profundo, Glowing Animations.
    """
    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');

    /* ── Base & Fundo Animado ────────────────────────────────────────── */
    .stApp {
        background-color: #030712;
        background-image: 
            radial-gradient(at 0% 0%, rgba(79, 70, 229, 0.15) 0px, transparent 50%),
            radial-gradient(at 100% 0%, rgba(139, 92, 246, 0.15) 0px, transparent 50%),
            radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.08) 0px, transparent 50%),
            radial-gradient(at 0% 100%, rgba(56, 189, 248, 0.10) 0px, transparent 50%);
        background-attachment: fixed;
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }

    /* ── Sidebar ─────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: rgba(3, 7, 18, 0.65) !important;
        backdrop-filter: blur(24px) saturate(150%) !important;
        -webkit-backdrop-filter: blur(24px) saturate(150%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label {
        color: #94a3b8 !important;
    }

    /* ── Glassmorphism Cards ─────────────────────────────────────────── */
    .glass-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.4), rgba(15, 23, 42, 0.6));
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 24px;
        backdrop-filter: blur(20px);
        margin-bottom: 20px;
        box-shadow: 0 4px 24px -1px rgba(0, 0, 0, 0.2);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    .glass-card::before {
        content: '';
        position: absolute;
        top: 0; left: -100%;
        width: 100%; height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.03), transparent);
        transition: left 0.5s ease;
    }
    .glass-card:hover::before {
        left: 100%;
    }
    .glass-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 40px rgba(99, 102, 241, 0.15);
        border-color: rgba(99, 102, 241, 0.4);
    }

    /* ── Glowing KPI Cards ───────────────────────────────────────────── */
    .kpi-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9));
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.06);
        padding: 24px 28px;
        margin-bottom: 16px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }
    .kpi-card:hover {
        transform: translateY(-4px) scale(1.02);
    }
    .kpi-card::after {
        content: '';
        position: absolute;
        top: -50px; right: -50px;
        width: 120px; height: 120px;
        border-radius: 50%;
        filter: blur(40px);
        opacity: 0.15;
        z-index: 0;
        transition: opacity 0.3s ease;
    }
    .kpi-card:hover::after {
        opacity: 0.3;
    }
    
    .kpi-content {
        position: relative;
        z-index: 1;
    }
    .kpi-label { font-size: 0.75rem; color: #94a3b8; font-family: 'Inter', sans-serif; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 8px; }
    .kpi-value { font-size: 2.2rem; font-weight: 800; font-family: 'Outfit', sans-serif; color: #f8fafc; letter-spacing: -0.04em; line-height: 1.1; margin-bottom: 4px; }
    .kpi-sub   { font-size: 0.8rem; font-weight: 500; font-family: 'Inter', sans-serif; }

    /* Cores Específicas dos KPIs e Glows */
    .kpi-purple { border-left: 4px solid #8b5cf6; }
    .kpi-purple::after { background: #8b5cf6; }
    .kpi-purple .kpi-value { background: linear-gradient(135deg, #a78bfa, #c4b5fd); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .kpi-purple .kpi-sub { color: #a78bfa; }

    .kpi-green { border-left: 4px solid #10b981; }
    .kpi-green::after { background: #10b981; }
    .kpi-green .kpi-value { background: linear-gradient(135deg, #34d399, #6ee7b7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .kpi-green .kpi-sub { color: #34d399; }

    .kpi-yellow { border-left: 4px solid #f59e0b; }
    .kpi-yellow::after { background: #f59e0b; }
    .kpi-yellow .kpi-value { background: linear-gradient(135deg, #fbbf24, #fcd34d); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .kpi-yellow .kpi-sub { color: #fbbf24; }

    .kpi-red { border-left: 4px solid #ef4444; }
    .kpi-red::after { background: #ef4444; }
    .kpi-red .kpi-value { background: linear-gradient(135deg, #f87171, #fca5a5); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .kpi-red .kpi-sub { color: #f87171; }

    /* ── Tipografia ──────────────────────────────────────────────────── */
    h1 { font-family: 'Outfit', sans-serif !important; font-size: 2.75rem !important; font-weight: 800 !important; color: #ffffff !important; letter-spacing: -0.05em !important; margin-bottom: 0.5rem !important; }
    h2 { font-family: 'Outfit', sans-serif !important; font-size: 1.8rem !important; font-weight: 700 !important; color: #f8fafc !important; letter-spacing: -0.03em !important; }
    h3 { font-family: 'Outfit', sans-serif !important; font-size: 1.35rem !important; font-weight: 600 !important; color: #e2e8f0 !important; }

    /* ── Botões Vibrantes ────────────────────────────────────────────── */
    .stButton > button {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: #ffffff !important;
        border-radius: 12px;
        border: none !important;
        padding: 0.6rem 1.4rem;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        font-size: 0.95rem;
        letter-spacing: 0.02em;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4);
    }
    .stButton > button:hover {
        box-shadow: 0 8px 25px rgba(124, 58, 237, 0.6);
        transform: translateY(-2px);
    }
    .stButton > button:active { transform: translateY(0); box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4); }

    /* ── Inputs e Selects Modernos ──────────────────────────────────── */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    [data-baseweb="select"] > div {
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        background: rgba(15, 23, 42, 0.6) !important;
        color: #f8fafc !important;
        font-family: 'Inter', sans-serif !important;
        padding: 0.6rem 1rem !important;
        backdrop-filter: blur(10px);
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus,
    [data-baseweb="select"] > div:focus-within {
        border-color: #8b5cf6 !important;
        box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.25) !important;
    }

    /* ── Tabs Pílula (Pill Tabs) ─────────────────────────────────────── */
    [data-testid="stTabs"] button[role="tab"] {
        border-radius: 100px !important;
        border: 1px solid transparent !important;
        background: transparent !important;
        color: #94a3b8 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        padding: 0.5rem 1.25rem !important;
        margin-right: 8px !important;
        transition: all 0.3s ease;
    }
    [data-testid="stTabs"] button[role="tab"]:hover {
        background: rgba(255, 255, 255, 0.05) !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        background: rgba(139, 92, 246, 0.15) !important;
        color: #c4b5fd !important;
        border-color: rgba(139, 92, 246, 0.4) !important;
        box-shadow: 0 0 15px rgba(139, 92, 246, 0.1) !important;
    }

    /* ── Dataframes Transparentes ────────────────────────────────────── */
    [data-testid="stDataFrame"] { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; overflow: hidden; background: rgba(15, 23, 42, 0.5); }
    [data-testid="stTable"] { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; overflow: hidden; background: rgba(15, 23, 42, 0.5); }
    
    /* ── Expanders Minimalistas ──────────────────────────────────────── */
    [data-testid="stExpander"] {
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        background: rgba(15, 23, 42, 0.4) !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }
    [data-testid="stExpander"] summary { font-weight: 600 !important; color: #cbd5e1 !important; }

    /* ── Caixas de Info/Avisos Brilhantes ────────────────────────────── */
    .stInfo { background: rgba(56, 189, 248, 0.1) !important; border: 1px solid rgba(56, 189, 248, 0.3) !important; border-left: 4px solid #38bdf8 !important; border-radius: 12px !important; color: #bae6fd !important; backdrop-filter: blur(10px); }
    .stSuccess { background: rgba(16, 185, 129, 0.1) !important; border: 1px solid rgba(16, 185, 129, 0.3) !important; border-left: 4px solid #10b981 !important; border-radius: 12px !important; color: #a7f3d0 !important; backdrop-filter: blur(10px); }
    .stWarning { background: rgba(245, 158, 11, 0.1) !important; border: 1px solid rgba(245, 158, 11, 0.3) !important; border-left: 4px solid #f59e0b !important; border-radius: 12px !important; color: #fde68a !important; backdrop-filter: blur(10px); }
    .stError { background: rgba(239, 68, 68, 0.1) !important; border: 1px solid rgba(239, 68, 68, 0.3) !important; border-left: 4px solid #ef4444 !important; border-radius: 12px !important; color: #fecaca !important; backdrop-filter: blur(10px); }

    /* ── Badges Refinados (Pílulas) ──────────────────────────────────── */
    .badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 4px 10px;
        border-radius: 24px;
        font-size: 0.65rem;
        font-weight: 700;
        font-family: 'Inter', sans-serif;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .badge-green  { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(52,211,153,0.4); }
    .badge-yellow { background: rgba(245,158,11,0.15); color: #fcd34d; border: 1px solid rgba(251,191,36,0.4); }
    .badge-red    { background: rgba(239,68,68,0.15);  color: #fca5a5; border: 1px solid rgba(248,113,113,0.4); }
    .badge-purple { background: rgba(139,92,246,0.15); color: #c4b5fd; border: 1px solid rgba(165,180,252,0.4); }

    /* ── Section Headers Clean ───────────────────────────────────────── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 32px 0 16px 0;
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .section-header .icon { font-size: 1.5rem; }
    .section-header .title { font-size: 1.25rem; font-family: 'Outfit', sans-serif; font-weight: 700; color: #f8fafc; letter-spacing: -0.02em; }

    /* ── Esconder Footer do Streamlit ────────────────────────────────── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def kpi_card(label: str, value: str, sub: str = "", color: str = "purple") -> None:
    """Renderiza um KPI card premium com animação e garantias de fechamento de tags."""
    # Tratar sub em branco para garantir html limpo
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub and sub != "" else ""
    
    html = f"""
    <div class="kpi-card kpi-{color}">
        <div class="kpi-content">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {sub_html}
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def section_header(icon: str, title: str) -> None:
    st.markdown(
        f'<div class="section-header"><span class="icon">{icon}</span>'
        f'<span class="title">{title}</span></div>',
        unsafe_allow_html=True,
    )


def badge(text: str, color: str = "purple") -> str:
    return f'<span class="badge badge-{color}">{text}</span>'


def render_sidebar_nav(username: str, current: str):
    st.markdown(f"""
    <div style="padding:1rem 0.5rem 0.5rem 0.5rem;">
        <div style="font-size:0.7rem;color:#475569;letter-spacing:0.1em;margin-bottom:4px;">CONTA</div>
        <div style="font-weight:700;color:#e2e8f0;font-size:1rem;">@{username}</div>
    </div>
    <hr style="border-color:rgba(99,102,241,0.15);margin:0.4rem 0;">
    <div style="font-size:0.68rem;color:#64748b;letter-spacing:0.08em;margin-bottom:8px;">NAVEGAÇÃO</div>
    """, unsafe_allow_html=True)
    if current == "home":
        st.page_link("app.py", label="🏠 Início", disabled=True)
    else:
        st.page_link("app.py", label="🏠 Início")
    st.page_link("pages/2_📊_Meu_Dinheiro.py", label="📊 Meu Dinheiro", disabled=current == "money")
    st.page_link("pages/4_🧠_Estrategias_Nexa.py", label="🧠 Estratégias", disabled=current == "strategy")
    st.page_link("pages/3_🔗_Conexoes.py", label="🔗 Conexões", disabled=current == "connections")
    st.page_link("pages/1_💬_Chat_Inteligente.py", label="💬 Chat", disabled=current == "chat")


def render_skeleton(lines: int = 4):
    st.markdown('<div class="skeleton-card">', unsafe_allow_html=True)
    for i in range(lines):
        width = 95 - (i % 3) * 15
        st.markdown(f'<div class="skeleton-line" style="width:{width}%;"></div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
