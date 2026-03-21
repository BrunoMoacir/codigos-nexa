import streamlit as st
import pandas as pd

from utils.api import NexaAPIClient
from utils.ui import load_css, section_header

st.set_page_config(page_title="Estratégias Nexa", page_icon="🧠", layout="wide")
load_css()

api = NexaAPIClient()


def _auth_guard():
    if not st.session_state.get("jwt_token"):
        st.warning("Faça login para acessar as estratégias avançadas.")
        st.stop()


def _get_user_ctx():
    user_data = st.session_state.get("user_data") or {}
    user_id = (
        user_data.get("id")
        or user_data.get("user_id")
        or st.session_state.get("user_id")
        or ""
    )
    if not user_id:
        st.error("Não foi possível identificar o usuário logado.")
        st.stop()
    return user_id


def _kpi_cards(metrics: list[tuple[str, str, str]]):
    cols = st.columns(len(metrics))
    for idx, (label, value, help_text) in enumerate(metrics):
        cols[idx].metric(label, value, help=help_text)


def _pretty_alert(alert: dict, idx: int):
    level = str(alert.get("level", "INFO")).upper()
    color = "#ef4444" if level == "CRITICAL" else "#f59e0b" if level == "WARNING" else "#6366f1"
    icon = "🔴" if level == "CRITICAL" else "🟡" if level == "WARNING" else "🔵"
    title = alert.get("title", "Alerta")
    msg = alert.get("message", "")
    st.markdown(
        f"""
        <div class="glass-card" style="padding:14px 16px; margin-bottom:8px; border-left:4px solid {color};">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
            <div style="font-weight:700;color:#e2e8f0;">{icon} {idx}. {title}</div>
            <span class="badge" style="background:{color}22;color:{color};border:1px solid {color}55;">{level}</span>
          </div>
          <div style="color:#94a3b8;font-size:0.82rem;margin-top:6px;line-height:1.5;">{msg}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def tab_optimizer(user_id: str):
    section_header("💳", "Optimizer de Cartões")
    st.caption("Carteira ideal, promoções e custo de oportunidade com seus dados reais.")

    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        monthly_income = st.number_input("Renda mensal (R$)", min_value=0.0, value=10000.0, step=500.0)
    with c2:
        max_cards = st.selectbox("Máx. de cartões na estratégia", [1, 2, 3, 4], index=2)

    portfolio_res = api.get_optimizer_portfolio(user_id=user_id, max_cards=max_cards, monthly_income=monthly_income)
    if portfolio_res.get("success"):
        data = portfolio_res["data"]
        st.markdown(
            f"<div style='margin-bottom:8px;'>{data.get('explanation','')}</div>",
            unsafe_allow_html=True,
        )
        _kpi_cards([
            ("Retorno anual", f"R$ {data.get('total_annual_return', 0):,.2f}", "Retorno bruto anual"),
            ("Custo anualidades", f"R$ {data.get('total_annuity_cost', 0):,.2f}", "Soma das anuidades efetivas"),
            ("Ganho líquido", f"R$ {data.get('net_annual_gain', 0):,.2f}", "Retorno - anuidades"),
        ])
        cards = data.get("cards") or []
        if cards:
            df_cards = pd.DataFrame(cards)
            if "monthly_spend_directed" in df_cards.columns:
                df_cards["monthly_spend_directed"] = df_cards["monthly_spend_directed"].map(lambda x: f"R$ {float(x):,.2f}")
            if "annual_return_from_this_card" in df_cards.columns:
                df_cards["annual_return_from_this_card"] = df_cards["annual_return_from_this_card"].map(lambda x: f"R$ {float(x):,.2f}")
            if "net_annual" in df_cards.columns:
                df_cards["net_annual"] = df_cards["net_annual"].map(lambda x: f"R$ {float(x):,.2f}")
            st.dataframe(df_cards, use_container_width=True, hide_index=True)
        else:
            st.info("Sem composição de cartões para exibir.")
    else:
        st.error(f"Falha no portfólio: {portfolio_res.get('error', 'erro desconhecido')}")

    st.divider()
    st.markdown("### 🎯 Custo de Oportunidade")
    cards_res = api.get_optimizer_cards()
    if cards_res.get("success"):
        card_options = cards_res.get("data", {}).get("cards", []) or []
        if card_options:
            card_map = {f"{c.get('name', c.get('card_id'))} ({c.get('card_id')})": c.get("card_id") for c in card_options}
            selected_label = st.selectbox("Seu cartão atual", list(card_map.keys()), key="opt_current_card")
            current_card_id = card_map[selected_label]
            months = st.slider("Janela de análise (meses)", min_value=1, max_value=12, value=3, key="opt_months")
            opp = api.get_optimizer_opportunity_cost(user_id=user_id, current_card_id=current_card_id, months=months)
            if opp.get("success"):
                d = opp["data"]
                _kpi_cards([
                    ("Perda estimada", f"R$ {d.get('estimated_loss', 0):,.2f}", "Valor perdido mantendo o cartão atual"),
                    ("Ganho potencial", f"R$ {d.get('estimated_gain_if_switched', 0):,.2f}", "Valor potencial ao trocar"),
                    ("Melhor alternativa", str(d.get("suggested_best_card", "-")), "Cartão recomendado"),
                ])
                if d.get("recommendation_text"):
                    st.info(d["recommendation_text"])
            else:
                st.warning(f"Não foi possível calcular: {opp.get('error', 'erro')}")
        else:
            st.info("Sem cartões cadastrados no módulo optimizer.")
    else:
        st.warning(f"Falha ao carregar cartões: {cards_res.get('error', 'erro')}")

    promos = api.get_optimizer_promotions()
    if promos.get("success"):
        promotions = promos.get("data", {}).get("promotions", []) or []
        if promotions:
            st.markdown("### 🔥 Promoções Ativas")
            st.dataframe(pd.DataFrame(promotions), use_container_width=True, hide_index=True)


def tab_architect(user_id: str):
    section_header("🏗️", "Architect de Conquistas")
    st.caption("Simule financiamento, consórcio e poupar/investir com comparação estratégica.")

    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        target_amount = st.number_input("Valor do objetivo (R$)", min_value=1000.0, value=120000.0, step=1000.0)
    with c2:
        down_payment = st.number_input("Entrada (R$)", min_value=0.0, value=20000.0, step=1000.0)
    with c3:
        financing_months = st.selectbox("Prazo financiamento (meses)", [24, 36, 48, 60, 72, 84], index=2)

    risk_profile = st.selectbox("Perfil de risco", ["conservador", "moderado", "agressivo"], index=1, key="arch_risk")
    asset_type = st.selectbox("Tipo de bem", ["IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"], index=1, key="arch_asset")

    if st.button("Simular estratégia", type="primary"):
        payload = {
            "user_id": user_id,
            "target_amount": float(target_amount),
            "down_payment": float(down_payment),
            "risk_profile": risk_profile,
            "asset_type": asset_type,
            "financing_months": int(financing_months),
            "include_consortium": True,
            "prefers_consortium": False,
        }
        sim = api.architect_simulate(payload)
        if sim.get("success"):
            data = sim["data"]
            st.success("Simulação concluída.")
            with st.expander("Resumo estratégico", expanded=True):
                st.markdown(
                    f"""
                    **Recomendação:** `{data.get('recommended_strategy', '-')}`  
                    **Justificativa:** {data.get('justification', 'Sem justificativa detalhada no payload.')}
                    """,
                )
            _kpi_cards([
                ("Estratégia recomendada", str(data.get("recommended_strategy", "-")), "Melhor estratégia pelo motor"),
                ("Confiança", f"{(data.get('confidence_score') or 0)*100:.1f}%", "Nível de confiança da recomendação"),
                ("Impacto de liquidez", f"{(data.get('liquidity_impact') or 0)*100:.1f}%", "Comprometimento da liquidez"),
            ])
            st.json(data)
        else:
            st.error(f"Erro na simulação: {sim.get('error', 'desconhecido')}")

    st.divider()
    history = api.architect_list_simulations(user_id=user_id, limit=8)
    metrics = api.architect_metrics(user_id=user_id)

    c4, c5 = st.columns([2, 1], gap="large")
    with c4:
        st.markdown("#### Histórico recente")
        if history.get("success"):
            sims = history.get("data") or []
            if sims:
                st.dataframe(pd.DataFrame(sims), use_container_width=True, hide_index=True)
            else:
                st.info("Sem simulações no histórico.")
        else:
            st.warning(f"Falha no histórico: {history.get('error', 'erro')}")
    with c5:
        st.markdown("#### Métricas")
        if metrics.get("success"):
            m = metrics.get("data", {})
            _kpi_cards([
                ("Total simulações", str(m.get("total_simulations", 0)), "Quantidade de simulações salvas"),
                ("Estratégia favorita", str(m.get("favorite_strategy", "-")), "Mais recorrente no histórico"),
                ("Confiança média", f"{(m.get('avg_confidence_score') or 0)*100:.1f}%", "Média global"),
            ])
        else:
            st.info("Métricas ainda indisponíveis para este usuário.")


def tab_fiscal(user_id: str):
    section_header("🧾", "Fiscal Intelligence")
    st.caption("Resumo fiscal e uso misto PF/PJ com dados processados da sua base.")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        year = st.number_input("Ano", min_value=2020, max_value=2100, value=2026, step=1)
    with c2:
        month_opt = st.selectbox("Mês (opcional)", ["Todos"] + [str(i) for i in range(1, 13)], index=0)

    month = None if month_opt == "Todos" else int(month_opt)
    rep = api.get_fiscal_report(user_id=user_id, year=int(year), month=month)
    mix = api.get_fiscal_mixed_use(user_id=user_id, year=int(year), month=month)

    if rep.get("success"):
        st.markdown("#### Relatório Fiscal")
        report_data = rep["data"] or {}
        summary = report_data.get("summary", {}) if isinstance(report_data, dict) else {}
        if summary:
            c1, c2, c3 = st.columns(3)
            c1.metric("Receita", f"R$ {float(summary.get('total_income', 0) or 0):,.2f}")
            c2.metric("Despesa", f"R$ {float(summary.get('total_expenses', 0) or 0):,.2f}")
            c3.metric("Resultado", f"R$ {float(summary.get('net_result', 0) or 0):,.2f}")
        st.json(report_data)
    else:
        st.warning(f"Relatório indisponível: {rep.get('error', 'erro')}")

    if mix.get("success"):
        st.markdown("#### Uso Misto PF/PJ")
        st.json(mix["data"])
    else:
        st.warning(f"Uso misto indisponível: {mix.get('error', 'erro')}")


def tab_peers_notifications(user_id: str):
    section_header("👥", "Peers & Notificações")
    st.caption("Compare seu padrão com pares e receba ações priorizadas.")

    income = st.number_input("Renda mensal para benchmark (R$)", min_value=0.0, value=10000.0, step=500.0)
    history_months = st.slider("Histórico (meses)", min_value=1, max_value=12, value=3)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        cmp_res = api.get_peer_comparison(user_id=user_id, monthly_income=income, history_months=history_months)
        st.markdown("#### Benchmark com pares")
        if cmp_res.get("success"):
            d = cmp_res["data"] or {}
            if isinstance(d, dict):
                c1, c2, c3 = st.columns(3)
                c1.metric("Seu score", d.get("user_score", "—"))
                c2.metric("Média da faixa", d.get("peer_avg_score", "—"))
                c3.metric("Diferença", d.get("score_delta", "—"))
            st.json(d)
        else:
            st.warning(f"Benchmark indisponível: {cmp_res.get('error', 'erro')}")

    with col2:
        notif = api.get_notifications(user_id=user_id, monthly_income=income, include_info=True)
        st.markdown("#### Alertas inteligentes")
        if notif.get("success"):
            data = notif["data"]
            alerts = data.get("alerts", []) or []
            if alerts:
                for i, alert in enumerate(alerts[:10], 1):
                    _pretty_alert(alert, i)
            else:
                st.info("Sem alertas críticos no momento.")
        else:
            st.warning(f"Notificações indisponíveis: {notif.get('error', 'erro')}")


def main():
    _auth_guard()
    user_id = _get_user_ctx()

    st.markdown(
        """
        <div class="glass-card" style="background:linear-gradient(135deg,rgba(99,102,241,0.16),rgba(139,92,246,0.10));margin-bottom:1rem;">
          <p style="color:#a5b4fc;font-size:0.78rem;font-weight:700;letter-spacing:0.08em;margin-bottom:4px;">PAINEL PREMIUM</p>
          <h1 style="margin:0;">🧠 Estratégias Nexa</h1>
          <p style="color:#94a3b8;font-size:0.9rem;margin-top:6px;">
            Optimizer, Architect, Fiscal Intelligence, Peers e Notificações em tempo real com API real.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs([
        "💳 Optimizer",
        "🏗️ Architect",
        "🧾 Fiscal",
        "👥 Peers & Alertas",
    ])

    with tabs[0]:
        tab_optimizer(user_id)
    with tabs[1]:
        tab_architect(user_id)
    with tabs[2]:
        tab_fiscal(user_id)
    with tabs[3]:
        tab_peers_notifications(user_id)


if __name__ == "__main__":
    main()
