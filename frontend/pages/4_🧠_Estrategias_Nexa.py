import streamlit as st
import pandas as pd

from utils.api import APIClient

st.set_page_config(page_title="Estratégias Nexa", page_icon="🧠", layout="wide")

api = APIClient()


def _auth_guard():
    if not st.session_state.get("token"):
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


def tab_optimizer(user_id: str):
    st.subheader("💳 Optimizer de Cartões")
    st.caption("Carteira ideal, promoções e custo de oportunidade com seus dados reais.")

    c1, c2 = st.columns([1, 1])
    with c1:
        monthly_income = st.number_input("Renda mensal (R$)", min_value=0.0, value=10000.0, step=500.0)
    with c2:
        max_cards = st.selectbox("Máx. de cartões na estratégia", [1, 2, 3, 4], index=2)

    portfolio_res = api.get_optimizer_portfolio(user_id=user_id, max_cards=max_cards, monthly_income=monthly_income)
    if portfolio_res.get("success"):
        data = portfolio_res["data"]
        _kpi_cards([
            ("Retorno anual", f"R$ {data.get('total_annual_return', 0):,.2f}", "Retorno bruto anual"),
            ("Custo anualidades", f"R$ {data.get('total_annuity_cost', 0):,.2f}", "Soma das anuidades efetivas"),
            ("Ganho líquido", f"R$ {data.get('net_annual_gain', 0):,.2f}", "Retorno - anuidades"),
        ])
        cards = data.get("cards") or []
        if cards:
            df_cards = pd.DataFrame(cards)
            st.dataframe(df_cards, use_container_width=True, hide_index=True)
        else:
            st.info("Sem composição de cartões para exibir.")
    else:
        st.error(f"Falha no portfólio: {portfolio_res.get('error', 'erro desconhecido')}")

    st.markdown("---")
    st.markdown("#### 🎯 Custo de Oportunidade")
    cards_res = api.get_optimizer_cards()
    if cards_res.get("success"):
        card_options = cards_res.get("data", {}).get("cards", []) or []
        if card_options:
            card_map = {f"{c.get('name', c.get('card_id'))} ({c.get('card_id')})": c.get("card_id") for c in card_options}
            selected_label = st.selectbox("Seu cartão atual", list(card_map.keys()))
            current_card_id = card_map[selected_label]
            months = st.slider("Janela de análise (meses)", min_value=1, max_value=12, value=3)
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
            st.markdown("#### 🔥 Promoções Ativas")
            st.dataframe(pd.DataFrame(promotions), use_container_width=True, hide_index=True)


def tab_architect(user_id: str):
    st.subheader("🏗️ Architect de Conquistas")
    st.caption("Simule financiamento, consórcio e poupar/investir com comparação estratégica.")

    c1, c2, c3 = st.columns(3)
    with c1:
        target_amount = st.number_input("Valor do objetivo (R$)", min_value=1000.0, value=120000.0, step=1000.0)
    with c2:
        down_payment = st.number_input("Entrada (R$)", min_value=0.0, value=20000.0, step=1000.0)
    with c3:
        financing_months = st.selectbox("Prazo financiamento (meses)", [24, 36, 48, 60, 72, 84], index=2)

    risk_profile = st.selectbox("Perfil de risco", ["conservador", "moderado", "agressivo"], index=1)
    asset_type = st.selectbox("Tipo de bem", ["IMOVEL", "VEICULO", "REFORMA", "VIAGEM", "OUTRO"], index=1)

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
            _kpi_cards([
                ("Estratégia recomendada", str(data.get("recommended_strategy", "-")), "Melhor estratégia pelo motor"),
                ("Confiança", f"{(data.get('confidence_score') or 0)*100:.1f}%", "Nível de confiança da recomendação"),
                ("Impacto de liquidez", f"{(data.get('liquidity_impact') or 0)*100:.1f}%", "Comprometimento da liquidez"),
            ])
            st.json(data)
        else:
            st.error(f"Erro na simulação: {sim.get('error', 'desconhecido')}")

    st.markdown("---")
    history = api.architect_list_simulations(user_id=user_id, limit=8)
    metrics = api.architect_metrics(user_id=user_id)

    c4, c5 = st.columns([2, 1])
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
    st.subheader("🧾 Fiscal Intelligence")
    st.caption("Resumo fiscal e uso misto PF/PJ com dados processados da sua base.")

    c1, c2 = st.columns(2)
    with c1:
        year = st.number_input("Ano", min_value=2020, max_value=2100, value=2026, step=1)
    with c2:
        month_opt = st.selectbox("Mês (opcional)", ["Todos"] + [str(i) for i in range(1, 13)], index=0)

    month = None if month_opt == "Todos" else int(month_opt)
    rep = api.get_fiscal_report(user_id=user_id, year=int(year), month=month)
    mix = api.get_fiscal_mixed_use(user_id=user_id, year=int(year), month=month)

    if rep.get("success"):
        st.markdown("#### Relatório Fiscal")
        st.json(rep["data"])
    else:
        st.warning(f"Relatório indisponível: {rep.get('error', 'erro')}")

    if mix.get("success"):
        st.markdown("#### Uso Misto PF/PJ")
        st.json(mix["data"])
    else:
        st.warning(f"Uso misto indisponível: {mix.get('error', 'erro')}")


def tab_peers_notifications(user_id: str):
    st.subheader("👥 Peers & Notificações")
    st.caption("Compare seu padrão com pares e receba ações priorizadas.")

    income = st.number_input("Renda mensal para benchmark (R$)", min_value=0.0, value=10000.0, step=500.0)
    history_months = st.slider("Histórico (meses)", min_value=1, max_value=12, value=3)

    col1, col2 = st.columns(2)
    with col1:
        cmp_res = api.get_peer_comparison(user_id=user_id, monthly_income=income, history_months=history_months)
        st.markdown("#### Benchmark com pares")
        if cmp_res.get("success"):
            st.json(cmp_res["data"])
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
                    st.markdown(f"**{i}. {alert.get('title', 'Alerta')}**")
                    if alert.get("message"):
                        st.caption(alert["message"])
            else:
                st.info("Sem alertas críticos no momento.")
        else:
            st.warning(f"Notificações indisponíveis: {notif.get('error', 'erro')}")


def main():
    _auth_guard()
    user_id = _get_user_ctx()

    st.title("🧠 Estratégias Nexa")
    st.markdown(
        "Painel premium com **Optimizer**, **Architect**, **Fiscal Intelligence**, "
        "**Peers** e **Notificações** usando sua API real."
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
