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

api     = NexaAPIClient()
user_id = st.session_state.get("user_id") or st.session_state.get("username", "")

# ── Estado do chat ────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "total_cost" not in st.session_state:
    st.session_state.total_cost = 0.0
if "total_tools" not in st.session_state:
    st.session_state.total_tools = 0

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

    # Status do backend (usa o mesmo host do api.base_url)
    api_root = api.base_url.rsplit("/api/v1", 1)[0] if "/api/v1" in api.base_url else api.base_url
    try:
        import requests as req
        r_health = req.get(f"{api_root}/health", timeout=2)
        backend_ok = r_health.status_code == 200
    except Exception:
        backend_ok = False

    status_color = "#10b981" if backend_ok else "#ef4444"
    status_text  = "Online" if backend_ok else "Offline"
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;
         background:rgba(0,0,0,0.2);border-radius:8px;margin-bottom:10px;">
      <div style="width:8px;height:8px;border-radius:50%;background:{status_color};
                  box-shadow:0 0 6px {status_color};flex-shrink:0;"></div>
      <span style="font-size:0.75rem;color:#94a3b8;">Backend: <b style="color:{status_color};">{status_text}</b></span>
    </div>
    """, unsafe_allow_html=True)

    if not backend_ok:
        st.error(
            "Backend offline! Se estiver em Docker, verifique o container. "
            "Se estiver local, rode:\n```\ncd backend\nuvicorn app.main:app --reload\n```"
        )

    # Sugestões
    st.markdown("""
    <div style="font-size:0.72rem;color:#475569;letter-spacing:0.08em;margin-bottom:0.6rem;">
        💡 PERGUNTAS SUGERIDAS
    </div>
    """, unsafe_allow_html=True)

    sugestoes = [
        "Como está minha saúde financeira?",
        "Qual meu safe to spend hoje?",
        "Qual cartão devo usar para alimentação?",
        "Me fala sobre minhas metas",
        "Posso comprar um carro de R$ 60.000?",
        "Compare meus gastos com a média",
        "Me dê dicas para economizar mais",
    ]

    for s in sugestoes:
        if st.button(s, use_container_width=True, key=f"sug_{s[:25]}"):
            st.session_state["_quick_prompt"] = s
            st.rerun()

    st.markdown("---")

    # Stats da sessão
    n_msgs  = len(st.session_state.get("messages", []))
    tot_cost = st.session_state.get("total_cost", 0.0)
    tot_tools = st.session_state.get("total_tools", 0)

    st.markdown(f"""
    <div style="padding:10px;background:rgba(0,0,0,0.2);border-radius:8px;margin-bottom:8px;">
      <div style="font-size:0.68rem;color:#475569;margin-bottom:6px;letter-spacing:0.05em;">SESSÃO ATUAL</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
        <div>
          <div style="color:#6366f1;font-size:1rem;font-weight:700;">{n_msgs}</div>
          <div style="color:#64748b;font-size:0.68rem;">mensagens</div>
        </div>
        <div>
          <div style="color:#10b981;font-size:1rem;font-weight:700;">{tot_tools}</div>
          <div style="color:#64748b;font-size:0.68rem;">ferramentas</div>
        </div>
      </div>
      {f'<div style="color:#f59e0b;font-size:0.72rem;margin-top:6px;">💰 USD {tot_cost:.4f} usado</div>' if tot_cost > 0 else ''}
    </div>
    """, unsafe_allow_html=True)

    if st.button("🗑️ Limpar conversa", use_container_width=True):
        st.session_state.messages = []
        st.session_state.total_cost  = 0.0
        st.session_state.total_tools = 0
        st.rerun()

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

# ── Mensagem de boas-vindas (somente se vazio) ────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div class="glass-card" style="background:linear-gradient(135deg,rgba(99,102,241,0.1),rgba(139,92,246,0.06));
         text-align:center; padding:2rem;">
        <div style="font-size:2.5rem;margin-bottom:0.6rem;">🤖</div>
        <div style="font-weight:700;font-size:1.05rem;color:#e2e8f0;margin-bottom:0.4rem;">
            Nexa Agent está pronto
        </div>
        <p style="color:#64748b;font-size:0.85rem;line-height:1.6;max-width:520px;margin:0 auto;">
            Sou seu assistente financeiro pessoal com acesso ao seu histórico bancário completo,
            metas, cartões, projeções de cashflow, e comparação com pares. Pergunte qualquer coisa!
        </p>
        <div style="margin-top:1.2rem;display:flex;gap:8px;justify-content:center;flex-wrap:wrap;">
            <span class="badge badge-purple">💰 Forecast</span>
            <span class="badge badge-green">🎯 Metas</span>
            <span class="badge badge-purple">📊 Orçamento</span>
            <span class="badge badge-yellow">💳 Cartões</span>
            <span class="badge badge-green">💡 Safe to Spend</span>
            <span class="badge badge-purple">📈 Peer Compare</span>
            <span class="badge badge-yellow">🏠 Financiamento</span>
            <span class="badge badge-green">🧾 Fiscal MEI/PJ</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Histórico de mensagens ────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("meta"):
            meta_parts = msg["meta"].split(" | ")
            meta_html  = " &nbsp;·&nbsp; ".join(
                f'<span style="color:#475569">{p}</span>' for p in meta_parts
            )
            st.markdown(
                f'<div style="margin-top:6px;font-size:0.72rem;">{meta_html}</div>',
                unsafe_allow_html=True,
            )

# ── Quick prompt via sidebar ──────────────────────────────────────────────────
quick = st.session_state.pop("_quick_prompt", None)

# ── Input do chat ─────────────────────────────────────────────────────────────
prompt = st.chat_input("Pergunte sobre limites, cartões, metas, gastos, financiamentos…") or quick

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        status_ph = st.empty()
        status_ph.markdown(
            '<div style="color:#64748b;font-size:0.85rem;">💭 O Nexa Agent está analisando…</div>',
            unsafe_allow_html=True,
        )
        t0   = time.time()
        resp = api.post_chat_message(user_id, prompt)
        lat  = (time.time() - t0) * 1000
        status_ph.empty()

        if resp.get("success"):
            answer     = resp["data"].get("response", "")
            cost_usd   = resp["data"].get("cost_usd") or 0.0
            tools_used = resp["data"].get("tools_used", []) or []

            # Acumular stats da sessão
            st.session_state.total_cost  += cost_usd
            st.session_state.total_tools += len(tools_used)

            st.markdown(answer)

            # Metadata footer
            meta_parts = [f"⏱ {lat:.0f}ms"]
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
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "meta": meta_str}
            )
        else:
            err_raw = resp.get("error", "Erro desconhecido")
            if "403" in err_raw:
                err = "🔒 **Erro 403:** Token não autorizado para este usuário. Faça logout e login novamente."
            elif "Connection" in err_raw or "refused" in err_raw.lower():
                err = "🔌 **Backend offline.** Certifique-se de que o servidor está rodando em `localhost:8000`."
            else:
                err = f"⚠️ Falha de comunicação com a API: {err_raw}"
            st.error(err)
            st.session_state.messages.append({"role": "assistant", "content": err})
