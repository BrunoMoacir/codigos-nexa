import streamlit as st
import time
from utils.ui import load_css, section_header, badge
from utils.api import NexaAPIClient

# ── Auth guard ────────────────────────────────────────────────────────────────
if "jwt_token" not in st.session_state or not st.session_state.jwt_token:
    st.warning("🔒 Faça login na tela inicial primeiro.")
    st.page_link("app.py", label="Ir para o Login", icon="🏠")
    st.stop()

st.set_page_config(
    page_title="Chat Inteligente · Nexa",
    page_icon="💬",
    layout="wide",
)
load_css()

api = NexaAPIClient()
user_id = st.session_state.username

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="padding:1rem 0.5rem 0.5rem 0.5rem;">
        <div style="font-size:0.7rem;color:#475569;letter-spacing:0.1em;margin-bottom:4px;">CONTA</div>
        <div style="font-weight:700;color:#e2e8f0;font-size:1rem;">@{user_id}</div>
    </div>
    <hr style="border-color:rgba(99,102,241,0.15);margin:0.4rem 0 0.8rem 0;">
    """, unsafe_allow_html=True)

    if st.button("← Voltar ao Início", use_container_width=True):
        st.switch_page("app.py")

    st.markdown("---")

    # Sugestões de perguntas
    st.markdown("""
    <div style="font-size:0.72rem;color:#475569;letter-spacing:0.08em;margin-bottom:0.6rem;">
        💡 PERGUNTAS SUGERIDAS
    </div>
    """, unsafe_allow_html=True)

    sugestoes = [
        "Como está minha saúde financeira?",
        "Qual meu safe to spend hoje?",
        "Qual cartão devo usar?",
        "Me fala sobre minhas metas",
        "Como posso economizar mais?",
    ]

    for s in sugestoes:
        if st.button(s, use_container_width=True, key=f"sug_{s[:20]}"):
            st.session_state["_quick_prompt"] = s
            st.rerun()

    st.markdown("---")
    if st.button("🗑️ Limpar conversa", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    # Contador de mensagens
    n = len(st.session_state.get("messages", []))
    st.markdown(f"""
    <div style="text-align:center;margin-top:1rem;">
        <span style="font-size:0.72rem;color:#334155;">{n} mensagens nesta sessão</span>
    </div>
    """, unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:1rem;">
  <p style="color:#6366f1;font-size:0.78rem;font-weight:600;letter-spacing:0.08em;margin-bottom:4px;">
    AGENTE FINANCEIRO
  </p>
  <h1 style="margin:0;">💬 Chat Inteligente</h1>
  <p style="color:#64748b;font-size:0.85rem;margin-top:6px;">
    Baseado em LangGraph · Acesso a 8 ferramentas analíticas · Memória de sessão
  </p>
</div>
""", unsafe_allow_html=True)

# ── Estado do chat ────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mensagem de boas-vindas (primeira vez)
if not st.session_state.messages:
    st.markdown("""
    <div class="glass-card" style="background:linear-gradient(135deg,rgba(99,102,241,0.1),rgba(139,92,246,0.06));
         text-align:center; padding:2rem;">
        <div style="font-size:2.5rem;margin-bottom:0.6rem;">🤖</div>
        <div style="font-weight:700;font-size:1.05rem;color:#e2e8f0;margin-bottom:0.4rem;">
            Nexa Agent está pronto
        </div>
        <p style="color:#64748b;font-size:0.85rem;line-height:1.6;max-width:460px;margin:0 auto;">
            Sou seu assistente financeiro pessoal. Tenho acesso ao seu histórico bancário completo,
            metas, cartões e projeções. Pergunte qualquer coisa!
        </p>
        <div style="margin-top:1rem;display:flex;gap:8px;justify-content:center;flex-wrap:wrap;">
            <span class="badge badge-purple">Forecast</span>
            <span class="badge badge-green">Metas</span>
            <span class="badge badge-purple">Orçamento</span>
            <span class="badge badge-yellow">Cartões</span>
            <span class="badge badge-purple">Safe to Spend</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Histórico de mensagens ────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("meta"):
            # Linha de metadados estilizada
            meta_parts = msg["meta"].split(" | ")
            meta_html = " &nbsp;·&nbsp; ".join(
                f'<span style="color:#475569">{p}</span>' for p in meta_parts
            )
            st.markdown(
                f'<div style="margin-top:6px;font-size:0.72rem;">{meta_html}</div>',
                unsafe_allow_html=True,
            )

# ── Quick prompt via sidebar ──────────────────────────────────────────────────
quick = st.session_state.pop("_quick_prompt", None)

# ── Input do chat ─────────────────────────────────────────────────────────────
prompt = st.chat_input("Pergunte sobre limites, cartões, metas, gastos…") or quick

if prompt:
    # Exibe mensagem do usuário
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Chama a API e exibe resposta
    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        status_placeholder.markdown(
            '<div style="color:#64748b;font-size:0.85rem;">💭 O Nexa Agent está analisando…</div>',
            unsafe_allow_html=True,
        )
        t0 = time.time()
        resp = api.post_chat_message(user_id, prompt)
        latency_ms = (time.time() - t0) * 1000
        status_placeholder.empty()

        if resp.get("success"):
            answer     = resp["data"].get("response", "")
            cost_usd   = resp["data"].get("cost_usd")
            tools_used = resp["data"].get("tools_used", [])

            st.markdown(answer)

            # Linha de metadados
            meta_parts = [f"⏱ {latency_ms:.0f}ms"]
            if cost_usd:
                meta_parts.append(f"💰 USD {cost_usd:.5f}")
            if tools_used:
                tools_str = " · ".join([f"`{t}`" for t in tools_used])
                meta_parts.append(f"🛠 {tools_str}")
            meta_str = " | ".join(meta_parts)

            meta_html = " &nbsp;·&nbsp; ".join(
                f'<span style="color:#475569">{p}</span>' for p in meta_parts
            )
            st.markdown(
                f'<div style="margin-top:8px;font-size:0.72rem;">{meta_html}</div>',
                unsafe_allow_html=True,
            )
            st.session_state.messages.append({
                "role": "assistant", "content": answer, "meta": meta_str
            })
        else:
            err = f"⚠️ Falha de comunicação com a API: {resp.get('error', 'Erro desconhecido')}"
            st.error(err)
            st.session_state.messages.append({"role": "assistant", "content": err})
