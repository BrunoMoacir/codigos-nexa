"""
streamlit_opp_test.py — Teste completo do OPP (Radar de Oportunidades)

Como usar:
    cd backend
    streamlit run streamlit_opp_test.py

- Sem backend rodando (chamadas diretas aos serviços Python)
- Dados sintéticos configuráveis na sidebar (renda, gastos, saldos reais,
  tarifas, perfil FSS/investidor, banco conectado)
- Taxas REAIS (CDI/SELIC/TR via ANBIMA/BACEN, com fallback dos conectores)
- Cobre: OPP.1 (dinheiro parado com saldo real), OPP.2 (ranking líquido),
  OPP.3 (Tesouro vs CDB vs Poupança), OPP.4 (poupança vs CDI genérico e
  personalizado), OPP.5 (passos práticos), Bank Match, Feed/notificações,
  tools do agente e catálogo/Open Finance.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_BACKEND = Path(__file__).parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import polars as pl
import streamlit as st

st.set_page_config(page_title="Nexa — OPP Radar de Oportunidades", page_icon="🎯", layout="wide")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INFRA — tabela de saldos + usuário de teste por sessão
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.cache_resource
def _ensure_tables() -> bool:
    from app.core.database import Base, engine
    from app.core.models.account_balance import AccountBalance
    Base.metadata.create_all(bind=engine, tables=[AccountBalance.__table__])
    return True


_ensure_tables()

if "opp_user_id" not in st.session_state:
    st.session_state.opp_user_id = f"opp_demo_{uuid.uuid4().hex[:8]}"
USER_ID = st.session_state.opp_user_id


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIDEBAR — perfil financeiro sintético
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with st.sidebar:
    st.title("🎯 OPP — Config do usuário")
    st.caption(f"user_id da sessão: `{USER_ID}`")

    st.subheader("Fluxo de caixa (histórico sintético)")
    monthly_income = st.slider("Renda mensal (R$)", 1_000, 30_000, 8_000, step=500)
    monthly_expenses = st.slider("Gastos mensais (R$)", 500, 25_000, 4_500, step=500)
    months_history = st.slider("Meses de histórico", 1, 12, 6)
    monthly_fee = st.slider("Tarifa bancária mensal (R$)", 0, 120, 30, step=5)

    st.subheader("Saldos reais (Pluggy simulado)")
    use_real_balance = st.toggle("Persistir saldo real (account_balances)", value=True,
                                 help="Desligado = radar usa o proxy de fluxo de caixa (CASHFLOW_PROXY)")
    checking_balance = st.slider("Saldo em conta corrente (R$)", 0, 200_000, 42_000, step=1_000)
    savings_balance = st.slider("Saldo na poupança (R$)", 0, 200_000, 15_000, step=1_000)
    user_bank = st.selectbox("Banco conectado", ["Nubank", "Banco Inter", "C6 Bank", "Itaú", "Santander", "Bradesco"])

    st.subheader("Perfil comportamental (override)")
    fss_level = st.selectbox("FSS (estresse financeiro)", ["SAUDAVEL", "ATENCAO", "ALERTA", "CRITICO"])
    investor_type = st.selectbox("Tipo de investidor", ["NONE", "CASUAL", "ATIVO", "DIVERSIFICADO"])
    lifestyle = st.selectbox("Cluster", ["NAO_CLASSIFICADO", "EXPLORADOR_GLOBAL", "URBANO_FOODIE"])

    st.divider()
    seed = st.button("💾 Preparar dados do usuário", type="primary", use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DADOS SINTÉTICOS — transações + saldos persistidos
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_transactions_df() -> pl.DataFrame:
    """Histórico mensal: salário, gastos em 3 categorias e tarifa bancária."""
    rows = []
    first_of_month = date.today().replace(day=1)
    for m in range(1, months_history + 1):
        base = (first_of_month - timedelta(days=30 * m)).replace(day=5)
        rows.append({"date": base, "amount": float(monthly_income),
                     "description": "SALARIO EMPRESA XYZ", "account_id": "acc_cc"})
        split = [0.5, 0.3, 0.2]
        descs = ["SUPERMERCADO PAO DE ACUCAR", "ALUGUEL APTO", "RESTAURANTE OUTBACK"]
        for frac, desc in zip(split, descs):
            rows.append({"date": base + timedelta(days=3), "amount": -round(monthly_expenses * frac, 2),
                         "description": desc, "account_id": "acc_cc"})
        if monthly_fee > 0:
            rows.append({"date": base + timedelta(days=1), "amount": -float(monthly_fee),
                         "description": "TARIFA PACOTE DE SERVICOS", "account_id": "acc_cc"})
    return pl.DataFrame(rows)


def seed_balances() -> int:
    """Persiste saldos reais como o sync Pluggy faria (mesmo caminho de produção)."""
    from app.core.db.balances import save_account_balances
    accounts = []
    if checking_balance > 0:
        accounts.append({"id": "acc_cc", "type": "BANK", "subtype": "CHECKING_ACCOUNT",
                         "balance": float(checking_balance), "currencyCode": "BRL",
                         "connector": {"name": user_bank}})
    if savings_balance > 0:
        accounts.append({"id": "acc_pp", "type": "BANK", "subtype": "SAVINGS_ACCOUNT",
                         "balance": float(savings_balance), "currencyCode": "BRL",
                         "connector": {"name": user_bank}})
    return save_account_balances(USER_ID, "item_demo", accounts)


def clear_balances() -> None:
    from sqlalchemy import text
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        db.execute(text("DELETE FROM account_balances WHERE user_id = :uid"), {"uid": USER_ID})
        db.commit()


if seed:
    clear_balances()
    n = seed_balances() if use_real_balance else 0
    st.session_state.opp_seeded = True
    st.sidebar.success(
        f"Dados prontos: {len(build_transactions_df())} transações sintéticas"
        + (f" + {n} saldos reais persistidos" if n else " (modo proxy, sem saldo real)")
    )

TX_DF = build_transactions_df()
PROFILE = SimpleNamespace(fss_level=fss_level, investor_type=investor_type, lifestyle_cluster=lifestyle)


def _patched_engine():
    """OpportunityEngine lendo as transações sintéticas e o perfil da sidebar."""
    from app.opportunities.services.opportunity_engine import OpportunityEngine
    return patch.multiple(
        OpportunityEngine,
        _fetch_transactions=staticmethod(lambda user_id: TX_DF),
        _build_user_profile=staticmethod(lambda df: PROFILE),
    )


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEADER + TAXAS DO DIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.title("🎯 OPP — Radar de Oportunidades (teste completo)")

if not st.session_state.get("opp_seeded"):
    st.info("👈 Configure o perfil na sidebar e clique em **Preparar dados do usuário** para começar.")


@st.cache_data(ttl=600)
def get_market_rates() -> dict:
    from app.opportunities.services.opportunity_engine import OpportunityEngine
    from app.opportunities.services.savings_rate import calculate_savings_rate
    from app.architect.connectors.bacen import BacenConnector
    cdi = OpportunityEngine._get_cdi_annual()
    selic = OpportunityEngine._get_selic_annual() or 0.15
    try:
        tr = BacenConnector().get_tr_monthly()
    except Exception:
        tr = 0.0
    poup = calculate_savings_rate(selic, tr)
    return {"cdi": cdi, "selic": selic, "tr": tr, "poupanca": poup.savings_annual}


rates = get_market_rates()
c1, c2, c3, c4 = st.columns(4)
c1.metric("CDI (ANBIMA/BCB)", f"{rates['cdi']*100:.2f}% a.a.")
c2.metric("SELIC (BCB)", f"{rates['selic']*100:.2f}% a.a.")
c3.metric("TR (BCB)", f"{rates['tr']*100:.4f}% a.m.")
c4.metric("Poupança (fórmula oficial)", f"{rates['poupanca']*100:.2f}% a.a.")

tab_radar, tab_compare, tab_tesouro, tab_poupanca, tab_match, tab_feed, tab_agent, tab_catalog = st.tabs([
    "🎯 Radar (OPP.1)", "💰 Simulador (OPP.2)", "🏛️ Tesouro (OPP.3)", "🐷 Poupança (OPP.4)",
    "🏆 Bank Match", "📣 Feed", "🤖 Agente", "📦 Catálogo",
])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 — RADAR (OPP.1 + OPP.5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_radar:
    st.subheader("Dinheiro parado + melhor destino (líquido pós-IR)")
    if st.button("🔍 Analisar", key="run_radar", type="primary"):
        from app.opportunities.services.opportunity_engine import OpportunityEngine
        with _patched_engine():
            result = OpportunityEngine().analyze(USER_ID, persist_snapshot=False)

        source_badge = ("🔗 SALDO REAL (contas conectadas)" if result.idle_source == "REAL_BALANCE"
                        else "📊 estimativa por fluxo de caixa")
        a, b, c, d = st.columns(4)
        a.metric("Dinheiro parado", brl(result.idle_amount), source_badge)
        b.metric("Saldo bruto", brl(result.gross_idle_amount))
        c.metric("Reserva protegida", brl(result.emergency_reserve),
                 f"{result.reserve_months_applied} meses de gastos")
        d.metric("Perda mensal na conta", f"−{brl(result.monthly_loss_in_checking)}")

        st.markdown(f"**Status da detecção:** `{result.idle_detection_status}` — {result.idle_detection_reason}")
        st.success(result.recommendation)

        if result.opportunities:
            st.markdown("#### Ranking (líquido após IR — OPP.2)")
            st.dataframe(pl.DataFrame([{
                "#": o.rank, "Banco": o.bank_name, "Produto": o.product_type,
                "% CDI": o.cdi_pct, "Bruto a.a.": f"{o.annual_rate_gross_pct:.2f}%",
                "Líquido a.a.": f"{o.annual_rate_net_pct:.2f}%",
                "IR": "isento" if o.is_exempt else f"{o.ir_rate*100:.1f}%",
                "Liquidez": o.liquidity, "Ganho/ano": brl(o.annual_gain_brl),
                "FGC": "✅" if o.fgc_covered else "Tesouro", "Elegível": "✅" if o.eligible else "—",
            } for o in result.opportunities]).to_pandas(), use_container_width=True, hide_index=True)

            top = result.top_opportunity
            if top and top.steps:
                with st.expander(f"👣 OPP.5 — Passo a passo: {top.bank_name} {top.product_type}"):
                    for i, s in enumerate(top.steps, 1):
                        st.markdown(f"{i}. {s}")
        st.caption(result.disclaimer + " | Fontes: " + "; ".join(result.data_sources))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 — SIMULADOR AD HOC (OPP.2)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_compare:
    st.subheader("Simule um aporte: valor + prazo → ranking completo")
    col1, col2 = st.columns(2)
    amount_sim = col1.number_input("Valor (R$)", 100.0, 5_000_000.0, 20_000.0, step=1_000.0)
    months_sim = col2.slider("Prazo (meses)", 1, 60, 12, key="sim_months")
    if st.button("📈 Simular", key="run_compare"):
        from app.opportunities.services.bank_comparator import BankComparator
        ranked = BankComparator().rank(
            amount=amount_sim, holding_months=months_sim,
            cdi_annual=rates["cdi"], selic_annual=rates["selic"],
        )
        st.dataframe(pl.DataFrame([{
            "#": o.rank, "Banco": o.bank_name, "Produto": o.product_type,
            "Líquido a.a.": o.annual_rate_net_pct, "Ganho no prazo": brl(o.annual_gain_brl),
            "IR": "isento" if o.is_exempt else f"{o.ir_rate*100:.1f}%",
            "Liquidez (dias)": o.liquidity_days, "Mínimo": brl(o.min_amount),
            "Elegível": "✅" if o.eligible else "—",
        } for o in ranked]).to_pandas(), use_container_width=True, hide_index=True)
        st.caption("A LCI isenta pode vencer CDB de taxa bruta maior — esse é o teste central do OPP.2.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 — TESOURO vs CDB vs POUPANÇA (OPP.3)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_tesouro:
    st.subheader("As três clássicas, em rendimento líquido real")
    col1, col2 = st.columns(2)
    amount_t = col1.number_input("Valor (R$)", 100.0, 5_000_000.0, 10_000.0, step=1_000.0, key="t_amount")
    months_t = col2.slider("Prazo (meses)", 1, 60, 12, key="t_months")
    if st.button("🏛️ Comparar", key="run_tesouro"):
        from app.opportunities.services.treasury_comparator import TreasuryComparatorService
        r = TreasuryComparatorService().compare(amount=amount_t, holding_months=months_t)
        cols = st.columns(len(r.entries))
        for col, e in zip(cols, r.entries):
            medal = "🥇" if e.label == r.winner else ""
            col.metric(f"{medal} {e.label}", brl(e.net_yield_brl), f"{e.annual_rate_net_pct:.2f}% a.a. líquido")
            col.caption(("isento de IR" if e.is_exempt else f"IR {e.ir_rate*100:.1f}%")
                        + (f" · custódia {brl(e.fees_brl)}" if e.fees_brl else "")
                        + (" · FGC" if e.fgc_covered else " · Tesouro Nacional"))
        st.success(r.recommendation)
        st.caption(f"Vencedor rende {brl(r.winner_vs_savings_brl)} a mais que a poupança no período.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4 — POUPANÇA vs CDI (OPP.4, genérico e personalizado)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_poupanca:
    st.subheader("Genérico (referência) vs Personalizado (saldo real)")
    from app.opportunities.services.savings_vs_cdi import get_savings_vs_cdi_service
    svc = get_savings_vs_cdi_service()
    left, right = st.columns(2)
    with left:
        st.markdown("##### 📋 Genérico (R$ 10 mil de referência)")
        if st.button("Calcular", key="run_poup_gen"):
            g = svc.analyze()
            st.metric("Status", f"{g.status} / {g.severity}")
            st.metric("Perda estimada/ano", brl(g.estimated_loss_annual_brl))
            st.info(g.reason)
    with right:
        st.markdown("##### 👤 Personalizado (OPP4-E — saldo real)")
        if st.button("Calcular", key="run_poup_pers"):
            p = svc.analyze_for_user(USER_ID)
            if p.is_personalized:
                st.metric("Seu saldo na poupança", brl(p.savings_balance_brl or 0),
                          f"capturado em {p.balance_captured_at:%d/%m %H:%M}" if p.balance_captured_at else "")
                st.metric("SUA perda estimada/ano", brl(p.estimated_loss_annual_brl))
                st.warning(p.reason)
            else:
                st.info("Sem saldo real de poupança persistido — caiu no genérico (correto: nunca "
                        "afirmar saldo). Ligue o toggle na sidebar e clique em Preparar dados.")
                st.metric("Perda estimada/ano (referência)", brl(p.estimated_loss_annual_brl))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 5 — BANK MATCH (melhor banco pelo perfil)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_match:
    st.subheader("Qual é o melhor banco PARA este perfil?")
    amount_m = st.number_input("Valor de referência (R$)", 1_000.0, 5_000_000.0, 10_000.0,
                               step=1_000.0, key="m_amount")
    if st.button("🏆 Calcular Bank Match", key="run_match", type="primary"):
        from app.opportunities.services.bank_match import BankMatchService
        from app.opportunities.services.bank_scorecard import BankScorecardService
        with patch.object(BankScorecardService, "_get_user_banks", return_value={user_bank}):
            r = BankMatchService().build(
                user_id=USER_ID, amount=amount_m, holding_months=12,
                cdi_annual=rates["cdi"], selic_annual=rates["selic"],
                user_profile=PROFILE, transactions_df=TX_DF,
            )
        w = r.profile_used["weights"]
        st.caption(f"Pesos p/ FSS **{fss_level}** + investidor **{investor_type}**: "
                   f"rendimento {w['yield']:.0%} · tarifas {w['fees']:.0%} · "
                   f"cartões {w['card']:.0%} · perfil {w['fit']:.0%}")
        if r.user_current_bank:
            st.markdown(f"📍 Banco atual: **{r.user_current_bank}** "
                        f"({r.user_current_bank_rank}º de {len(r.ranking)})")
        st.dataframe(pl.DataFrame([{
            "#": i + 1, "Banco": e.bank_name + (" 📍" if e.is_user_current_bank else ""),
            "Match": e.match_score, "Rendimento": e.components.yield_score,
            "Tarifas": e.components.fees_score, "Cartões": e.components.card_score,
            "Perfil": e.components.fit_score, "Tier": e.risk_tier,
            "Ganho/ano": brl(e.projected_annual_gain_brl),
            "Tarifa/mês": brl(e.projected_monthly_fee_brl),
            "Cartão destaque": e.top_card_name or "—",
        } for i, e in enumerate(r.ranking)]).to_pandas(), use_container_width=True, hide_index=True)
        st.success(r.switch_recommendation)
        with st.expander("🔍 Razões por banco (transparência do score)"):
            for e in r.ranking[:5]:
                st.markdown(f"**{e.bank_name}** ({e.match_score:.0f}/100)")
                for reason in e.reasons:
                    st.markdown(f"- {reason}")
        st.caption("Com tarifa mensal > 0 na sidebar, o pilar Tarifas do banco conectado usa o valor "
                   "REAL detectado no extrato ('Você paga R$ X/mês...').")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 6 — FEED / NOTIFICAÇÕES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_feed:
    st.subheader("Cards proativos (com filtro de relevância)")
    if st.button("📣 Gerar cards", key="run_feed"):
        from app.notifications.engine import NotificationEngine
        from app.notifications.notifier import NotificationContext, ProactiveNotifier
        from app.notifications.relevance_filter import NotificationRelevanceFilter
        from app.opportunities.services.opportunity_engine import OpportunityEngine

        ctx = NotificationContext()
        ctx.savings_below_cdi = NotificationEngine._detect_savings_below_cdi(USER_ID)
        with _patched_engine(), patch.object(
            NotificationEngine, "_has_recent_idle_snapshot", staticmethod(lambda uid: True)
        ):
            idle_result = OpportunityEngine().analyze(USER_ID, persist_snapshot=False)
            if idle_result.idle_amount > 0 and idle_result.top_opportunity:
                from app.notifications.notifier import IdleMoneyInput
                top = idle_result.top_opportunity
                ctx.idle_money = IdleMoneyInput(
                    idle_amount=idle_result.idle_amount,
                    monthly_loss=idle_result.monthly_loss_in_checking,
                    top_opportunity=f"{top.bank_name} {top.product_type} {top.cdi_pct:.0f}% CDI",
                    top_gain_monthly_brl=top.monthly_gain_brl,
                )

        notes = ProactiveNotifier().generate(ctx)
        relevant = NotificationRelevanceFilter().filter(notes, monthly_income=float(monthly_income))
        if not relevant:
            st.info("Nenhum card relevante para este perfil (filtro de relevância barrou ou não há "
                    "ociosidade/poupança).")
        for n in relevant:
            with st.container(border=True):
                st.markdown(f"**{n.title}**  \n{n.message}")
                if n.action_hint:
                    st.caption(f"💡 {n.action_hint}")
                st.caption(f"tipo `{n.type}` · prioridade `{n.priority}` · "
                           f"personalizado: {n.metadata.get('is_personalized', '—')}")
        dropped = len(notes) - len(relevant)
        if dropped:
            st.caption(f"{dropped} card(s) barrados pelo filtro de relevância (ganho irrisório p/ a renda).")
        st.caption("Obs.: em produção há ainda dedup por TTL (não reaparece por 14–30 dias) — "
                   "não aplicado aqui para facilitar o teste repetido.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 7 — TOOLS DO AGENTE (texto que o chat entrega)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_agent:
    st.subheader("Saída real das 3 tools do agente ReAct")
    tool = st.radio("Tool", ["get_opportunities (radar no chat)",
                             "simulate_investment (simulação)",
                             "get_best_bank (melhor banco)"], horizontal=True)
    if tool.startswith("simulate"):
        ca, cb = st.columns(2)
        a_amt = ca.number_input("Valor (R$)", 100.0, 5_000_000.0, 20_000.0, step=1_000.0, key="ag_amt")
        a_m = cb.slider("Prazo (meses)", 1, 60, 24, key="ag_months")
    if st.button("🤖 Executar tool", key="run_agent"):
        with _patched_engine():
            if tool.startswith("get_opportunities"):
                from app.agent.tools.get_opportunities import get_opportunities
                out = get_opportunities.invoke({"user_id": USER_ID})
            elif tool.startswith("simulate"):
                from app.agent.tools.simulate_investment import simulate_investment
                out = simulate_investment.invoke({"amount": a_amt, "holding_months": a_m})
            else:
                from app.agent.tools.get_best_bank import get_best_bank
                from app.opportunities.services.bank_scorecard import BankScorecardService
                with patch.object(BankScorecardService, "_get_user_banks", return_value={user_bank}):
                    out = get_best_bank.invoke({"user_id": USER_ID})
        st.code(out, language=None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 8 — CATÁLOGO + OPEN FINANCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab_catalog:
    st.subheader("Catálogo em uso (transparência) e conector Open Finance")
    from app.opportunities.services.bank_comparator import BankComparator
    meta = BankComparator.catalog_metadata()
    a, b, c = st.columns(3)
    a.metric("Origem", meta["source"])
    b.metric("Produtos", len(meta["products"]))
    c.metric("Atualizado em", meta["updated_at"])
    st.dataframe(pl.DataFrame(meta["products"]).to_pandas(), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("##### 🌐 Diretório real do Open Finance Brasil (rede)")
    if st.button("Descobrir endpoints de bank-fixed-incomes", key="run_of"):
        from app.opportunities.connectors.open_finance_products import OpenFinanceProductsConnector
        conn = OpenFinanceProductsConnector(timeout_seconds=10)
        with st.spinner("Consultando diretório de participantes..."):
            try:
                eps = conn._discover_endpoints()
                st.success(f"{len(eps)} endpoints descobertos no diretório oficial.")
                st.dataframe(pl.DataFrame(
                    [{"Instituição": i, "Endpoint": u} for i, u in eps[:30]]
                ).to_pandas(), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.warning(f"Diretório indisponível ({type(exc).__name__}) — em produção o job cai "
                           "no catálogo curado (fallback), sem quebrar o radar.")
