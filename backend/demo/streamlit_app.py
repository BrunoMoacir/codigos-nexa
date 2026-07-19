"""
demo/streamlit_app.py — Nexa em "produção" para teste ponta a ponta.

Três superfícies do produto real, alimentadas pelos serviços reais sobre os
dados das personas (semeados via ETL):

  📊 Dashboard  — forecast, safe-to-spend, health score, perfil comportamental
                  (cluster ML), gastos por categoria e separação PF/PJ
  🔔 Feed       — cards proativos reais (ProactiveNotifier + filtro de relevância)
  💬 Chat       — o agente LangGraph real (31 ferramentas)

Rodar:
    cd backend
    python3 -m demo.seed                       # popula as personas (uma vez)
    streamlit run demo/streamlit_app.py
"""

import os
import sys
from pathlib import Path

import streamlit as st

# Garante que `app` e `demo` sejam importáveis quando o Streamlit roda o arquivo
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from demo.personas import PERSONAS  # noqa: E402
from demo.services import build_feed, dashboard_data  # noqa: E402

st.set_page_config(page_title="Nexa — Demo em Produção", page_icon="💸", layout="wide")

_PRIORITY_STYLE = {
    "CRITICAL": ("🔴", "#3d1a1a"),
    "WARNING": ("🟠", "#3d331a"),
    "INFO": ("🔵", "#1a2a3d"),
}
_CLUSTER_LABEL = {
    "EXPLORADOR_GLOBAL": "✈️ Explorador Global",
    "URBANO_FOODIE": "🍽️ Urbano Foodie",
    "INVESTIDOR_CAUTELOSO": "📈 Investidor Cauteloso",
    "FAMILIA_ESTRUTURADA": "👨‍👩‍👧 Família Estruturada",
    "DIGITAL_NATIVO": "📱 Digital Nativo",
    "ESTRESSE_FINANCEIRO": "🆘 Estresse Financeiro",
    "MICROEMPREENDEDOR": "🧾 Microempreendedor",
    "NAO_CLASSIFICADO": "⚪ Não classificado",
}


def _brl(v) -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(show_spinner="Rodando o pipeline financeiro real...", ttl=300)
def _load_dashboard(user_id: str) -> dict:
    return dashboard_data(user_id)


@st.cache_data(show_spinner="Gerando o feed proativo...", ttl=300)
def _load_feed(user_id: str, income: float) -> list:
    return build_feed(user_id, income)


# ── Sidebar: seleção de persona ──────────────────────────────────────────

st.sidebar.title("💸 Nexa — Demo")
st.sidebar.caption("Produto real sobre dados que passaram pelo ETL")

persona_key = st.sidebar.selectbox(
    "Persona (conta conectada)",
    options=list(PERSONAS.keys()),
    format_func=lambda k: PERSONAS[k].full_name,
)
persona = PERSONAS[persona_key]
st.sidebar.markdown(
    f"**Plano:** `{persona.plan.upper()}`  \n"
    f"**Banco:** {persona.institution.title()}  \n"
    f"**Renda alvo:** {_brl(persona.monthly_income)}  \n"
    f"**Perfil esperado:** {_CLUSTER_LABEL.get(persona.expected_cluster, persona.expected_cluster)}"
)
if st.sidebar.button("🔄 Recarregar dados (limpar cache)"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
st.sidebar.caption(
    "Dados semeados via `python3 -m demo.seed`. Cada persona passou pelo "
    "pipeline real: Pluggy-style → validação → ETL → classificação → PF/PJ → banco."
)

page = st.sidebar.radio("Superfície", ["📊 Dashboard", "🔔 Feed", "💬 Chat"], index=0)

data = _load_dashboard(persona.user_id)
if not data.get("ok"):
    st.error(data.get("error", "Sem dados. Rode `python3 -m demo.seed` no diretório backend."))
    st.stop()


# ══════════════════════════════════════════════════════════════════════
# 📊 DASHBOARD
# ══════════════════════════════════════════════════════════════════════

if page == "📊 Dashboard":
    st.title(f"📊 {persona.full_name}")
    prof = data.get("profile", {})
    hs = data.get("health_score", {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Margem segura/dia", _brl(data.get("safe_to_spend_daily")))
    c2.metric("Renda detectada", _brl(data.get("monthly_income")),
              help=f"Padrão: {data.get('income_pattern')}")
    c3.metric("Health Score", f"{hs.get('score', '—')}/100", hs.get("level"))
    c4.metric("Transações", data.get("n_transactions"))

    st.divider()
    left, right = st.columns([1, 1])

    with left:
        st.subheader("🧠 Perfil comportamental")
        cluster = prof.get("cluster", "NAO_CLASSIFICADO")
        st.markdown(f"### {_CLUSTER_LABEL.get(cluster, cluster)}")
        badges = []
        if prof.get("source"):
            conf = prof.get("ml_confidence")
            badges.append(f"classificado por **{prof['source']}**"
                          + (f" (confiança {conf:.0%})" if conf else ""))
        if prof.get("secondary"):
            badges.append("secundários: " + ", ".join(prof["secondary"]))
        if prof.get("fss_level"):
            badges.append(f"FSS: **{prof['fss_level']}**")
        if prof.get("is_mei"):
            badges.append("🧾 sinal de MEI detectado")
        st.caption(" · ".join(badges))
        if prof.get("savings_rate") is not None:
            st.caption(f"Taxa de poupança estimada: {prof['savings_rate']:.1f}%")

        st.subheader("💰 Separação PF / PJ (F4)")
        pf_pj = data.get("pf_pj", {})
        if pf_pj:
            st.bar_chart(pf_pj)
        else:
            st.caption("Sem dados de contexto PF/PJ.")

    with right:
        st.subheader("📉 Projeção de caixa (30 dias)")
        cf = data.get("cashflow_forecast")
        if cf is not None:
            try:
                import polars as pl

                pdf = cf.select(
                    [c for c in cf.columns if c in ("date", "day", "projected_balance")]
                ).to_pandas()
                ycol = "projected_balance"
                xcol = "date" if "date" in pdf.columns else pdf.columns[0]
                st.line_chart(pdf.set_index(xcol)[ycol])
            except Exception as exc:
                st.caption(f"(projeção indisponível: {exc})")
        st.caption(
            f"Saldo atual estimado: {_brl(data.get('current_balance'))} · "
            f"mínimo projetado: {_brl(data.get('min_projected_balance'))}"
        )

    st.divider()
    st.subheader("🏷️ Gastos por categoria")
    cats = data.get("by_category", [])
    if cats:
        chart = {c["category"]: c["total"] for c in cats}
        st.bar_chart(chart)

    st.subheader("🧾 Transações recentes")
    recent = data.get("recent", [])
    if recent:
        import pandas as pd

        df = pd.DataFrame(recent)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════
# 🔔 FEED
# ══════════════════════════════════════════════════════════════════════

elif page == "🔔 Feed":
    st.title("🔔 Feed de Oportunidades")
    st.caption(
        "Cards gerados pelo `ProactiveNotifier` real e ordenados pelo filtro de "
        "relevância (mesma inteligência do produto), a partir dos dados desta persona."
    )
    feed = _load_feed(persona.user_id, data.get("monthly_income") or 0.0)
    if not feed:
        st.info("Nenhum card relevante no momento para esta persona.")
    else:
        counts = {}
        for c in feed:
            counts[c["priority"]] = counts.get(c["priority"], 0) + 1
        cols = st.columns(3)
        cols[0].metric("🔴 Críticos", counts.get("CRITICAL", 0))
        cols[1].metric("🟠 Avisos", counts.get("WARNING", 0))
        cols[2].metric("🔵 Informativos", counts.get("INFO", 0))
        st.divider()

        for card in feed:
            icon, bg = _PRIORITY_STYLE.get(card["priority"], ("•", "#222"))
            with st.container():
                st.markdown(
                    f"<div style='background:{bg};padding:14px 18px;border-radius:10px;"
                    f"margin-bottom:10px'>"
                    f"<b>{icon} {card['title']}</b><br>"
                    f"<span style='opacity:.85'>{card['message']}</span>"
                    + (f"<br><i style='opacity:.7'>💡 {card['action_hint']}</i>"
                       if card.get("action_hint") else "")
                    + f"<br><code style='opacity:.5;font-size:11px'>{card['type']}</code>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════
# 💬 CHAT
# ══════════════════════════════════════════════════════════════════════

elif page == "💬 Chat":
    st.title("💬 Chat com o Consultor Nexa")
    st.caption("Agente LangGraph real (31 ferramentas). Usa os dados desta persona.")

    from app.core.config import settings

    has_llm = bool(
        (settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY
         and settings.ANTHROPIC_API_KEY != "mock")
        or (settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY
            and settings.OPENAI_API_KEY != "mock")
    )
    if not has_llm:
        st.warning(
            "⚠️ Nenhuma chave de LLM configurada. Para ativar o chat, defina "
            "`ANTHROPIC_API_KEY` (ou `OPENAI_API_KEY`) no `backend/.env` e recarregue. "
            "O Dashboard e o Feed funcionam sem chave."
        )
        st.info(
            "Perguntas que o agente responderia usando as ferramentas reais:\n\n"
            "- *Como estão minhas finanças este mês?*\n"
            "- *Qual o melhor cartão para o meu perfil?*\n"
            "- *Tenho dinheiro parado rendendo pouco?*\n"
            "- *Meu banco está cobrando juros abusivos?*  (persona Carla)\n"
            "- *Quanto vou pagar de DAS este ano?*  (persona Bruno)\n"
            "- *Qual o meu plano e quantas mensagens ainda tenho?*"
        )
        st.stop()

    session_key = f"chat_{persona.user_id}"
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    for role, content in st.session_state[session_key]:
        with st.chat_message(role):
            st.markdown(content)

    prompt = st.chat_input("Pergunte sobre suas finanças...")
    if prompt:
        st.session_state[session_key].append(("user", prompt))
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"), st.spinner("O agente está pensando..."):
            try:
                from langchain_core.messages import HumanMessage

                from app.agent.singleton import get_agent

                agent = get_agent()
                inputs = {"messages": [HumanMessage(
                    content=f"[user_id={persona.user_id}] {prompt}"
                )]}
                config = {"configurable": {"thread_id": persona.user_id}}
                result = agent.invoke(inputs, config=config)
                answer = result["messages"][-1].content
            except Exception as exc:
                answer = f"❌ Erro ao consultar o agente: {exc}"
            st.markdown(answer)
            st.session_state[session_key].append(("assistant", answer))
