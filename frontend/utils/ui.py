import streamlit as st
import base64


def load_css():
    """
    CSS premium — dark mode, gradientes, animações, glassmorphism.
    """
    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Base ──────────────────────────────────────────────── */
    .stApp {
        background: linear-gradient(135deg, #0a0e1a 0%, #0f172a 60%, #1a0a2e 100%);
        color: #e2e8f0;
        font-family: 'Inter', sans-serif;
    }

    /* ── Sidebar ────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1117 0%, #161b27 100%);
        border-right: 1px solid rgba(99, 102, 241, 0.2);
    }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label {
        color: #94a3b8 !important;
    }

    /* ── Glassmorphism Cards ────────────────────────────────── */
    .glass-card {
        background: rgba(255, 255, 255, 0.04);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 24px;
        backdrop-filter: blur(20px);
        margin-bottom: 16px;
        transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    }
    .glass-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 40px rgba(99, 102, 241, 0.15);
        border-color: rgba(99, 102, 241, 0.3);
    }

    /* ── KPI Cards ──────────────────────────────────────────── */
    .kpi-card {
        background: linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(139,92,246,0.08) 100%);
        border-radius: 16px;
        border: 1px solid rgba(99, 102, 241, 0.25);
        padding: 20px 24px;
        margin-bottom: 12px;
        transition: all 0.25s ease;
        position: relative;
        overflow: hidden;
    }
    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0;
        width: 4px; height: 100%;
        background: linear-gradient(180deg, #6366f1, #8b5cf6);
        border-radius: 4px 0 0 4px;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(99, 102, 241, 0.2);
    }
    .kpi-label { font-size: 0.75rem; color: #94a3b8; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 4px; }
    .kpi-value { font-size: 1.75rem; font-weight: 700; color: #f1f5f9; letter-spacing: -0.03em; }
    .kpi-sub   { font-size: 0.75rem; color: #64748b; margin-top: 4px; }

    /* Health Score cores */
    .kpi-green::before { background: linear-gradient(180deg, #10b981, #34d399); }
    .kpi-yellow::before { background: linear-gradient(180deg, #f59e0b, #fbbf24); }
    .kpi-red::before { background: linear-gradient(180deg, #ef4444, #f87171); }
    .kpi-green .kpi-value { color: #34d399; }
    .kpi-yellow .kpi-value { color: #fbbf24; }
    .kpi-red .kpi-value { color: #f87171; }

    /* ── Tipografia ─────────────────────────────────────────── */
    h1 { font-size: 2rem !important; font-weight: 700 !important; color: #f1f5f9 !important;
         letter-spacing: -0.04em !important; }
    h2 { font-size: 1.4rem !important; color: #e2e8f0 !important; font-weight: 600 !important; }
    h3 { font-size: 1.1rem !important; color: #cbd5e1 !important; font-weight: 500 !important; }

    /* ── Botões ─────────────────────────────────────────────── */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white !important;
        border-radius: 10px;
        border: none !important;
        padding: 0.55rem 1.2rem;
        font-weight: 600;
        font-size: 0.9rem;
        letter-spacing: 0.01em;
        transition: all 0.2s ease;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3);
    }
    .stButton > button:hover {
        box-shadow: 0 6px 25px rgba(99, 102, 241, 0.5);
        transform: translateY(-1px);
    }
    .stButton > button:active { transform: translateY(0); }

    /* Botão danger (logout) */
    .btn-danger > button {
        background: linear-gradient(135deg, #dc2626, #ef4444) !important;
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.3) !important;
    }

    /* ── Inputs ─────────────────────────────────────────────── */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    [data-baseweb="select"] > div {
        border-radius: 10px !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
        background: rgba(15, 23, 42, 0.8) !important;
        color: #e2e8f0 !important;
        font-family: 'Inter', sans-serif !important;
        padding: 0.5rem 0.75rem !important;
    }
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25) !important;
    }

    /* ── Tabs ───────────────────────────────────────────────── */
    [data-testid="stTabs"] button[role="tab"] {
        border-radius: 10px !important;
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
        background: rgba(15, 23, 42, 0.45) !important;
        color: #cbd5e1 !important;
        margin-right: 6px !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.35), rgba(139, 92, 246, 0.25)) !important;
        color: #f8fafc !important;
        border-color: rgba(129, 140, 248, 0.6) !important;
    }

    /* ── Dataframe / Table ─────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 12px;
        overflow: hidden;
    }
    [data-testid="stTable"] {
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 12px;
        overflow: hidden;
    }

    /* ── Expander ───────────────────────────────────────────── */
    [data-testid="stExpander"] {
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
        border-radius: 12px !important;
        background: rgba(15, 23, 42, 0.35) !important;
    }

    /* ── JSON viewer card ───────────────────────────────────── */
    [data-testid="stJson"] {
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 12px;
        padding: 6px;
        background: rgba(2, 6, 23, 0.55);
    }

    /* ── Progress bars ──────────────────────────────────────── */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #6366f1, #8b5cf6, #a78bfa) !important;
        border-radius: 4px !important;
    }
    .stProgress > div > div > div {
        background: rgba(255,255,255,0.06) !important;
        border-radius: 4px !important;
    }

    /* ── Info / Warning / Success boxes ────────────────────── */
    .stInfo {
        background: rgba(99, 102, 241, 0.1) !important;
        border-left: 4px solid #6366f1 !important;
        border-radius: 8px !important;
        color: #c7d2fe !important;
    }
    .stSuccess {
        background: rgba(16, 185, 129, 0.1) !important;
        border-left: 4px solid #10b981 !important;
        border-radius: 8px !important;
    }
    .stWarning {
        background: rgba(245, 158, 11, 0.1) !important;
        border-left: 4px solid #f59e0b !important;
        border-radius: 8px !important;
    }
    .stError {
        background: rgba(239, 68, 68, 0.1) !important;
        border-left: 4px solid #ef4444 !important;
        border-radius: 8px !important;
    }

    /* ── Chat ───────────────────────────────────────────────── */
    .stChatMessage {
        border-radius: 14px !important;
        margin-bottom: 0.75rem !important;
        padding: 1rem !important;
    }
    [data-testid="chatAvatarIcon-user"] {
        background: linear-gradient(135deg, #4f46e5, #6366f1) !important;
    }
    [data-testid="chatAvatarIcon-assistant"] {
        background: linear-gradient(135deg, #059669, #10b981) !important;
    }
    [data-testid="stChatMessageContent"] p { color: #e2e8f0 !important; line-height: 1.65; }
    .stChatInputContainer > div {
        border: 1px solid rgba(99, 102, 241, 0.3) !important;
        border-radius: 14px !important;
        background: rgba(15, 23, 42, 0.8) !important;
    }

    /* ── Divider ────────────────────────────────────────────── */
    hr { border-color: rgba(99, 102, 241, 0.15) !important; }

    /* ── Metric ─────────────────────────────────────────────── */
    [data-testid="stMetricValue"] { color: #f1f5f9 !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #94a3b8 !important; font-size: 0.8rem !important; }
    [data-testid="stMetricDelta"] { font-size: 0.8rem !important; }

    /* ── Hide Streamlit footer ──────────────────────────────── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stToolbar"] { visibility: hidden; }

    /* ── Spinner ────────────────────────────────────────────── */
    .stSpinner > div > div { border-top-color: #6366f1 !important; }

    /* ── Tooltip badge ──────────────────────────────────────── */
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 20px;
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .badge-green  { background: rgba(16,185,129,0.2);  color: #34d399; border: 1px solid rgba(52,211,153,0.3); }
    .badge-yellow { background: rgba(245,158,11,0.2);  color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
    .badge-red    { background: rgba(239,68,68,0.2);   color: #f87171; border: 1px solid rgba(248,113,113,0.3); }
    .badge-purple { background: rgba(99,102,241,0.2);  color: #a5b4fc; border: 1px solid rgba(165,180,252,0.3); }

    /* ── Section header strip ───────────────────────────────── */
    .section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 24px 0 12px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(99, 102, 241, 0.2);
    }
    .section-header .icon { font-size: 1.4rem; }
    .section-header .title { font-size: 1.1rem; font-weight: 600; color: #e2e8f0; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def kpi_card(label: str, value: str, sub: str = "", color: str = "purple") -> None:
    """Renderiza um KPI card colorido com borda lateral."""
    st.markdown(
        f"""<div class="kpi-card kpi-{color}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {f'<div class="kpi-sub">{sub}</div>' if sub else ''}
        </div>""",
        unsafe_allow_html=True,
    )


def section_header(icon: str, title: str) -> None:
    st.markdown(
        f'<div class="section-header"><span class="icon">{icon}</span>'
        f'<span class="title">{title}</span></div>',
        unsafe_allow_html=True,
    )


def badge(text: str, color: str = "purple") -> str:
    return f'<span class="badge badge-{color}">{text}</span>'
