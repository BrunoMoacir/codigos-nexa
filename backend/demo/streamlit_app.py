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

from demo import data_readers as R  # noqa: E402
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
_banks_str = ", ".join(b.name for b in persona.banks)
st.sidebar.markdown(
    f"**Plano:** `{persona.plan.upper()}`  \n"
    f"**Bancos conectados:** {_banks_str}  \n"
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

page = st.sidebar.radio(
    "Superfície",
    ["📊 Dashboard", "🔔 Feed", "💬 Chat", "🗄️ Meus Dados", "🧬 Aprendizado"],
    index=0,
)

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


# ══════════════════════════════════════════════════════════════════════
# 🗄️ MEUS DADOS — o footprint completo que a Nexa armazena
# ══════════════════════════════════════════════════════════════════════

elif page == "🗄️ Meus Dados":
    st.title("🗄️ Tudo que a Nexa guarda sobre você")
    st.caption(
        "Este é o footprint real de uma conta usada há meses — as mesmas tabelas "
        "de produção (contas, histórico de score, tarifas, negociações, desafios, chat)."
    )

    # ── Contas e saldos (agrupados por banco conectado) ──
    accs = R.accounts(persona.user_id)
    if accs:
        _label = {"CHECKING": "Conta corrente", "SAVINGS": "Poupança",
                  "INVESTMENT": "Investimentos", "CREDIT": "Cartão de crédito"}
        # agrupa por banco
        by_bank: dict[str, list] = {}
        for a in accs:
            by_bank.setdefault(a["bank_name"], []).append(a)

        st.subheader(f"🏦 {len(by_bank)} bancos conectados · {len(accs)} contas (Open Finance)")
        for bank_name, bank_accs in by_bank.items():
            st.markdown(f"**🏛️ {bank_name}**")
            cols = st.columns(len(bank_accs))
            for col, a in zip(cols, bank_accs):
                col.metric(_label.get(a["account_type"], a["account_type"]),
                           _brl(a["balance"]))
        patrimonio = sum(a["balance"] for a in accs)
        st.success(f"**Patrimônio líquido consolidado:** {_brl(patrimonio)} "
                   f"— a Nexa soma tudo que está espalhado em {len(by_bank)} bancos.")
    else:
        st.caption("Sem contas — rode `python3 -m demo.seed`.")

    # ── Evolução do health score ──
    st.subheader("📈 Evolução do Health Score (6 meses)")
    hist = R.score_history(persona.user_id)
    if hist:
        import pandas as pd
        df = pd.DataFrame(hist)
        st.line_chart(df.set_index("date")["health_score"])
        delta = hist[-1]["health_score"] - hist[0]["health_score"]
        st.caption(f"Variação no período: {'📈 +' if delta >= 0 else '📉 '}{delta} pontos "
                   f"· perfil atual: {hist[-1]['profile_type']}")

    # ── Metas ──
    gs = R.goals(persona.user_id)
    if gs:
        st.subheader("🎯 Metas")
        for g in gs:
            st.markdown(f"**{g['name']}** — {_brl(g['current'])} de {_brl(g['target'])}")
            st.progress(min(g["pct"] / 100, 1.0), text=f"{g['pct']:.0f}%")

    c1, c2 = st.columns(2)

    # ── Tarifas pagas ──
    with c1:
        st.subheader("💸 Tarifas pagas (histórico)")
        fees = R.fee_history(persona.user_id)
        if fees:
            import pandas as pd
            fdf = pd.DataFrame(fees)
            total = fdf["amount"].sum()
            st.dataframe(fdf, use_container_width=True, hide_index=True, height=200)
            st.caption(f"Total no período: **{_brl(float(total))}** — matéria-prima do "
                       f"Raio-X (F5) e da Defesa (D2/D4).")
        else:
            st.caption("Sem tarifas registradas.")

    # ── Desafios e badges ──
    with c2:
        st.subheader("🏆 Desafios do mês")
        chs = R.challenges(persona.user_id)
        for ch in chs:
            icon = "✅" if ch["status"] == "COMPLETED" else "🔵"
            st.markdown(f"{icon} **{ch['title']}** — {ch.get('target_label', '')}")
            st.progress(min(float(ch["pct_progress"]) / 100, 1.0))
        bs = R.badges(persona.user_id)
        if bs:
            st.caption("Badges: " + " · ".join(f"🏅 {b['badge_type']}" for b in bs))

    # ── Negociações com desfecho ──
    st.subheader("🤝 Negociações (com desfecho reportado)")
    negs = R.negotiations(persona.user_id)
    if negs:
        import pandas as pd
        ndf = pd.DataFrame(negs)
        st.dataframe(ndf, use_container_width=True, hide_index=True, height=180)
        st.caption("Os desfechos reais alimentam a **calibração** do Negociador "
                   "(ver aba Aprendizado).")
    else:
        st.caption("Sem negociações.")

    # ── Correções manuais (PF/PJ) ──
    ovr = R.context_overrides(persona.user_id)
    if ovr:
        st.subheader("✏️ Correções manuais do usuário (PF/PJ)")
        for o in ovr:
            st.markdown(f"- {o['original_context']} → **{o['corrected_context']}** "
                        f"· _{o['reason']}_")

    # ── Histórico de chat ──
    st.subheader("💬 Histórico de conversas")
    chat = R.chat_history(persona.user_id)
    if chat:
        for m in chat:
            with st.chat_message("user" if m["role"] == "human" else "assistant"):
                st.markdown(m["content"])
    else:
        st.caption("Sem histórico de chat.")


# ══════════════════════════════════════════════════════════════════════
# 🧬 APRENDIZADO — a inteligência sobre a inteligência (loops fechados)
# ══════════════════════════════════════════════════════════════════════

elif page == "🧬 Aprendizado":
    st.title("🧬 Loops de Aprendizado (dados agregados)")
    st.caption(
        "O que a Nexa APRENDE com o comportamento real dos usuários — dados "
        "globais (não de uma persona só). É a inteligência que se recalibra sozinha."
    )
    loops = R.learning_loops()

    st.subheader("🤝 Calibração do Negociador (F13)")
    st.caption("Desfechos reais reportados → fator de realização por gatilho. "
               "O ganho apresentado ao usuário passa a ser `estimado × fator`.")
    cal = loops["calibration"]
    if cal:
        import pandas as pd
        rows = [{"gatilho": k, "fator de realização": v["factor"],
                 "taxa de sucesso": f"{v['success_rate']:.0%}",
                 "amostras": v["samples"]} for k, v in cal.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Ainda sem gatilhos com amostras suficientes (mín. 5 desfechos).")

    st.subheader("👍 Peso das recomendações (feedback)")
    st.caption("Recomendação que os usuários rejeitam perde peso no ranking: "
               "`peso = 0,5 + taxa_de_aceitação` (range 0,5–1,5).")
    fb = loops["feedback"]
    if fb:
        import pandas as pd
        rows = [{"tipo de insight": f["insight_type"],
                 "aceitação": f"{f['acceptance_rate']:.0%}",
                 "peso resultante": round(0.5 + f["acceptance_rate"], 2),
                 "total": f["total"]} for f in fb]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Ainda sem feedback registrado.")

    st.subheader("📊 Métricas de inteligência (série temporal)")
    st.caption("Persistidas pelo job `intelligence_metrics` (05h30) — a régua de "
               "acurácia e cobertura em produção.")
    metrics = loops["metrics"]
    if metrics:
        import pandas as pd
        st.dataframe(pd.DataFrame(metrics), use_container_width=True, hide_index=True)
    else:
        st.info("Rode o job de métricas para popular a série.")

    st.divider()
    st.caption(
        "💡 Estes loops estavam vazios até o banco ter dados de desfecho reais. "
        "Com o footprint completo semeado, eles passam a computar — é a diferença "
        "entre ter a inteligência instrumentada e ter ela aprendendo."
    )
