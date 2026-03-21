import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utils.ui import (
    load_css,
    kpi_card,
    section_header,
    badge,
    render_sidebar_nav,
    render_skeleton,
)
from utils.api import NexaAPIClient

# ── Auth guard ────────────────────────────────────────────────────────────────
if "jwt_token" not in st.session_state or not st.session_state.jwt_token:
    st.warning("🔒 Faça login na tela inicial primeiro.")
    st.page_link("app.py", label="Ir para o Login", icon="🏠")
    st.stop()

st.set_page_config(page_title="Meu Dinheiro · Nexa", page_icon="📊", layout="wide")
load_css()

api     = NexaAPIClient()
user_id = st.session_state.get("user_id") or st.session_state.get("username", "")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    render_sidebar_nav(username=user_id, current="money")
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
  <p class="hero-kicker">DASHBOARD FINANCEIRO</p>
  <h1 style="margin:0;">📊 Meu Dinheiro</h1>
  <p class="hero-sub">Seus dados financeiros reais, via Open Finance</p>
</div>
""", unsafe_allow_html=True)

# ── Carregar dados da API ─────────────────────────────────────────────────────
loading_ph = st.empty()
with st.spinner("⚡ Sincronizando dados via Open Finance…"):
    with loading_ph.container():
        render_skeleton(5)
    forecast     = api.get_forecast_summary(user_id)
    income_val   = 10_000.0
    if forecast.get("success"):
        raw_income = forecast["data"].get("financial_health", {}).get("total_income", 10_000.0)
        # O endpoint /budget exige monthly_income > 0
        income_val = float(raw_income) if raw_income and float(raw_income) > 0 else 10_000.0
    budget       = api.get_budget_advice(user_id, monthly_income=income_val)
    goals        = api.get_goals_summary(user_id)
    transactions = api.get_transactions(user_id, limit=300)
    alerts       = api.get_alerts(user_id)
    subs         = api.get_subscriptions(user_id)
    health_hist  = api.get_health_score_history(user_id, months=6)
loading_ph.empty()

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
#  SEÇÃO 1: KPIs de visão geral
# ══════════════════════════════════════════════════════════════════════════════
section_header("💎", "Visão Geral")

if forecast.get("success"):
    f_data  = forecast["data"]
    health  = f_data.get("financial_health", {})
    sts     = f_data.get("safe_to_spend", {})
    cf      = f_data.get("cashflow", {})
    si      = f_data.get("shadow_invoices", {})

    score        = health.get("health_score", 0) or health.get("score", 0)
    total_income = health.get("total_income", 0)
    total_exp    = health.get("total_expenses", 0)
    safe         = sts.get("safe_to_spend_total", 0)
    safe_daily   = sts.get("safe_to_spend_daily", 0)
    risk         = sts.get("risk_level", "LOW")
    burn_alert   = health.get("burn_rate_alert", "NORMAL")
    savings_rate = health.get("savings_rate", 0)
    profile_type = health.get("profile_type", "EQUILIBRADO")

    score_color = "green" if score >= 70 else "yellow" if score >= 40 else "red"
    risk_color  = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red"}.get(risk, "green")
    burn_color  = {"NORMAL": "green", "ATTENTION": "yellow", "WARNING": "yellow",
                   "CRITICAL": "red"}.get(burn_alert, "green")

    # ── 4 KPIs principais ─────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Renda Mensal Líquida", f"R$ {total_income:,.2f}",
                 sub=f"Perfil: {profile_type}", color="purple")
    with c2:
        kpi_card("Safe to Spend", f"R$ {safe:,.2f}",
                 sub=f"R$ {safe_daily:,.2f}/dia · Risco: {risk}", color=risk_color)
    with c3:
        kpi_card("Health Score", f"{score:.0f} / 100",
                 sub=f"Poupança: {savings_rate*100:.1f}%", color=score_color)
    with c4:
        kpi_card("Gastos Mensais", f"R$ {total_exp:,.2f}",
                 sub=f"Burn Alert: {burn_alert}", color=burn_color)

    # ── Score Progress Bar ──────────────────────────────────────────────
    bar_color = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    st.markdown(f"""
    <div style="margin:0 0 1.5rem 0;">
      <div style="display:flex; justify-content:space-between; font-size:0.72rem; color:#64748b; margin-bottom:4px;">
        <span>Saúde Financeira</span><span>{score:.0f}/100</span>
      </div>
      <div style="background:rgba(255,255,255,0.05); border-radius:6px; height:10px; overflow:hidden;">
        <div style="width:{score}%; height:100%;
             background:linear-gradient(90deg, {bar_color}88, {bar_color});
             border-radius:6px; transition:width 0.5s ease;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Cashflow mini metrics ───────────────────────────────────────────
    ending_bal  = cf.get("ending_balance", 0)
    worst_bal   = cf.get("worst_balance", 0)
    days_risk   = cf.get("days_at_risk", 0)
    shadow_cnt  = si.get("total_count", 0)
    shadow_imp  = si.get("total_monthly_impact", 0)

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Saldo Projetado (30d)", f"R$ {ending_bal:,.2f}",
              delta=f"{ending_bal - total_income:+,.2f}")
    c6.metric("Pior Saldo Projetado", f"R$ {worst_bal:,.2f}",
              delta=f"{'⚠️ ' if worst_bal < 0 else ''}{days_risk}d em risco")
    c7.metric("Obrigações Futuras", f"{shadow_cnt} itens",
              delta=f"Impacto: R$ {abs(shadow_imp):,.2f}/mês")
    c8.metric("Nível de Risco", risk,
              delta=f"Burn: {burn_alert}")

    # Executivo: waterfall receita vs gastos
    section_header("🧮", "Fluxo Executivo")
    wf = go.Figure(go.Waterfall(
        name="Fluxo",
        orientation="v",
        measure=["relative", "relative", "total"],
        x=["Renda", "Gastos", "Saldo"],
        y=[total_income, -abs(total_exp), total_income - abs(total_exp)],
        connector={"line": {"color": "rgba(148,163,184,0.4)"}},
        increasing={"marker": {"color": "#10b981"}},
        decreasing={"marker": {"color": "#ef4444"}},
        totals={"marker": {"color": "#6366f1"}},
    ))
    wf.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, l=0, r=0, b=0),
        font=dict(color="#94a3b8"),
        height=280,
    )
    st.plotly_chart(wf, use_container_width=True)

else:
    st.error("⚠️ Não foi possível carregar o Forecast. Veja instruções abaixo ↓")

# ══════════════════════════════════════════════════════════════════════════════
#  SEÇÃO 2: Orçamento 50/30/20
# ══════════════════════════════════════════════════════════════════════════════
section_header("💰", "Regra 50/30/20")

if budget.get("success"):
    b_data = budget["data"]
    try:
        text_advice = b_data.get("summary_text", "")
        groups      = b_data.get("group_summary", [])
        cuts        = b_data.get("actionable_cuts", [])

        col_chart, col_info = st.columns([1.2, 1])

        with col_chart:
            if groups:
                g_map   = {g["group"]: g for g in groups}
                labels  = ["Essenciais", "Desejos", "Poupança"]
                keys    = ["essenciais", "desejos", "poupanca"]
                actuals = [g_map.get(k, {}).get("current_pct", 0) for k in keys]
                targets = [50, 30, 20]
                colors  = ["#6366f1", "#a78bfa", "#10b981"]

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name="Atual (%)", x=labels, y=actuals,
                    marker_color=colors, marker_line_width=0, width=0.38,
                ))
                fig.add_trace(go.Bar(
                    name="Meta (%)", x=labels, y=targets,
                    marker_color=["rgba(99,102,241,0.18)", "rgba(167,139,250,0.18)", "rgba(16,185,129,0.18)"],
                    marker_line_color=colors, marker_line_width=1.5, width=0.38,
                ))
                fig.update_layout(
                    barmode="group",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#94a3b8", family="Inter"),
                    legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.04)", zeroline=False),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.04)", zeroline=False,
                               ticksuffix="%", range=[0, 60]),
                    margin=dict(t=10, b=10, l=0, r=0), height=260,
                )
                st.plotly_chart(fig, use_container_width=True)

            # Status de cada grupo
            for g in groups:
                key    = g["group"]
                cur    = g.get("current_pct", 0)
                target = g.get("target_pct", {"essenciais": 50, "desejos": 30, "poupanca": 20}.get(key, 0))
                status = g.get("status", "OK")
                icon   = "✅" if status == "OK" else "⚠️"
                label  = {"essenciais": "Essenciais", "desejos": "Desejos", "poupanca": "Poupança"}.get(key, key)
                color  = "#10b981" if status == "OK" else "#f59e0b"
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                     padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
                  <span style="color:#94a3b8;font-size:0.82rem;">{icon} {label}</span>
                  <span style="color:{color};font-weight:600;font-size:0.82rem;">{cur:.1f}% <span style="color:#475569;">/ {target:.0f}%</span></span>
                </div>
                """, unsafe_allow_html=True)

        with col_info:
            if text_advice:
                st.info("💡 **Análise da IA**\n\n" + text_advice)

            if cuts:
                st.markdown("**✂️ Cortes Sugeridos**")
                for cut in cuts[:3]:
                    saving = cut.get("saving", 0)
                    cat    = cut.get("category", "").title()
                    reason = cut.get("reasoning", "")
                    st.markdown(f"""
                    <div class="glass-card" style="padding:14px 18px; margin-bottom:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="font-weight:600;font-size:0.88rem;color:#e2e8f0;">✂️ {cat}</span>
                            <span class="badge badge-red">-R$ {saving:,.0f}/mês</span>
                        </div>
                        <p style="color:#64748b;font-size:0.78rem;margin:0;line-height:1.5;">{reason[:180]}</p>
                    </div>
                    """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Erro ao processar orçamento: {e}")
else:
    st.warning("Não foi possível carregar dados de orçamento.")

# ══════════════════════════════════════════════════════════════════════════════
#  SEÇÃO 3: Shadow Invoices (Obrigações Futuras)
# ══════════════════════════════════════════════════════════════════════════════
section_header("👻", "Obrigações Futuras (Shadow Invoices)")

if forecast.get("success"):
    si_data   = forecast["data"].get("shadow_invoices", {})
    invoices  = si_data.get("invoices", [])
    si_total  = si_data.get("total_monthly_impact", 0)
    sub_count = si_data.get("subscriptions_count", 0)
    inst_count = si_data.get("installments_count", 0)

    ca, cb, cc = st.columns(3)
    ca.metric("Impacto Mensal Total", f"R$ {abs(si_total):,.2f}", delta="obrigações detectadas")
    cb.metric("Assinaturas",          f"{sub_count} ativas",      delta="recorrentes")
    cc.metric("Parcelas",             f"{inst_count} em aberto",  delta="parcelamentos")

    if invoices:
        st.markdown("""
        <div style="margin-top:12px;">
        <table style="width:100%;border-collapse:collapse;font-size:0.82rem;">
          <thead>
            <tr style="color:#64748b;border-bottom:1px solid rgba(255,255,255,0.06);">
              <th style="padding:8px;text-align:left;">Tipo</th>
              <th style="padding:8px;text-align:left;">Descrição</th>
              <th style="padding:8px;text-align:right;">Valor</th>
              <th style="padding:8px;text-align:right;">Próximo</th>
              <th style="padding:8px;text-align:right;">Confiança</th>
            </tr>
          </thead>
          <tbody>
        """, unsafe_allow_html=True)
        for inv in invoices[:8]:
            tipo = inv.get("type", "").upper()
            tipo_color = "#a78bfa" if tipo == "SUBSCRIPTION" else "#6366f1"
            tipo_label = "📋 Assinatura" if tipo == "SUBSCRIPTION" else "💳 Parcela"
            desc  = inv.get("description", "—")[:40]
            amt   = inv.get("amount", 0)
            due   = inv.get("next_due_date", "—")
            conf  = inv.get("confidence", 0) * 100
            st.markdown(f"""
            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
              <td style="padding:8px;"><span class="badge" style="background:rgba(99,102,241,0.15);color:{tipo_color};border:1px solid {tipo_color}44;">{tipo_label}</span></td>
              <td style="padding:8px;color:#e2e8f0;">{desc}</td>
              <td style="padding:8px;text-align:right;color:#f87171;font-weight:600;">-R$ {abs(amt):,.2f}</td>
              <td style="padding:8px;text-align:right;color:#94a3b8;">{due}</td>
              <td style="padding:8px;text-align:right;">
                <div style="background:rgba(255,255,255,0.06);border-radius:4px;height:6px;width:60px;display:inline-block;vertical-align:middle;">
                  <div style="width:{conf:.0f}%;height:100%;background:#6366f1;border-radius:4px;"></div>
                </div>
                <span style="color:#64748b;font-size:0.72rem;margin-left:6px;">{conf:.0f}%</span>
              </td>
            </tr>
            """, unsafe_allow_html=True)
        st.markdown("</tbody></table></div>", unsafe_allow_html=True)
    else:
        st.info("✅ Nenhuma obrigação futura detectada no período. Excelente!")
else:
    st.warning("Aguardando dados do Forecast para exibir Shadow Invoices.")

# ══════════════════════════════════════════════════════════════════════════════
#  SEÇÃO 4: Metas Financeiras
# ══════════════════════════════════════════════════════════════════════════════
section_header("🎯", "Suas Metas")

if goals.get("success"):
    goal_list = goals["data"].get("goals", [])
    if goal_list:
        cols = st.columns(min(len(goal_list), 3))
        for idx, g in enumerate(goal_list):
            pct        = g.get("progress_pct", 0)
            name       = g.get("name", "Meta")
            current    = g.get("current_amount", 0)
            target     = g.get("target_amount", 0)
            status     = g.get("status", "ACTIVE")
            proj       = g.get("projection", {}) or {}
            suggestion = proj.get("suggestion", "")
            remaining  = target - current

            bar_color  = "#10b981" if pct >= 80 else "#6366f1" if pct >= 40 else "#f59e0b"
            bdg_color  = "green"   if pct >= 80 else "purple"   if pct >= 40 else "yellow"

            with cols[idx % 3]:
                st.markdown(f"""
                <div class="glass-card" style="padding:20px 22px;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
                        <span style="font-weight:700;font-size:0.95rem;color:#e2e8f0;">{name}</span>
                        {badge(f"{pct:.0f}%", bdg_color)}
                    </div>
                    <div style="font-size:1.5rem;font-weight:700;color:{bar_color};margin-bottom:2px;">
                        R$ {current:,.2f}
                    </div>
                    <div style="font-size:0.72rem;color:#64748b;margin-bottom:12px;">
                        de R$ {target:,.2f} · faltam R$ {remaining:,.2f}
                    </div>
                    <div style="background:rgba(255,255,255,0.06);border-radius:6px;height:8px;overflow:hidden;margin-bottom:10px;">
                        <div style="width:{min(pct,100):.1f}%;height:100%;
                                    background:linear-gradient(90deg,{bar_color}88,{bar_color});
                                    border-radius:6px;"></div>
                    </div>
                    {f'<p style="color:#94a3b8;font-size:0.76rem;margin:0;line-height:1.5;">💡 {suggestion}</p>' if suggestion else ''}
                </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="glass-card" style="text-align:center; padding:2rem; border-style:dashed;">
            <div style="font-size:2rem;margin-bottom:0.5rem;">🎯</div>
            <p style="color:#64748b;margin:0;">Você ainda não tem metas cadastradas.</p>
            <p style="color:#475569;font-size:0.8rem;margin-top:4px;">
                Converse com o agente e diga: <i>"Quero criar uma meta de poupança"</i>
            </p>
        </div>
        """, unsafe_allow_html=True)
else:
    st.error("⚠️ Erro ao carregar metas financeiras.")

# ══════════════════════════════════════════════════════════════════════════════
#  SEÇÃO 5: Detalhes do Perfil Financeiro
# ══════════════════════════════════════════════════════════════════════════════
if forecast.get("success"):
    section_header("📈", "Perfil & Tendências")

    f_data  = forecast["data"]
    health  = f_data.get("financial_health", {})
    top_cats = health.get("top_categories", []) or []
    if not top_cats and transactions.get("success"):
        tx_rows = (transactions.get("data", {}) or {}).get("transactions", []) or []
        if tx_rows:
            df_tx = pd.DataFrame(tx_rows)
            if "category" in df_tx.columns:
                top_cats = (
                    df_tx["category"]
                    .fillna("Sem categoria")
                    .astype(str)
                    .value_counts()
                    .head(5)
                    .index
                    .tolist()
                )
    trend    = health.get("trend", "ESTÁVEL")
    burn_r   = health.get("burn_rate_ratio", 0)
    profile  = health.get("profile_type", "EQUILIBRADO")

    trend_icon  = "📈" if trend == "CRESCENTE" else "📉" if trend == "DECRESCENTE" else "➡️"
    trend_color = "#10b981" if trend == "ESTÁVEL" else "#f59e0b" if trend == "CRESCENTE" else "#ef4444"

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(f"""
        <div class="glass-card">
          <div style="font-size:0.72rem;color:#64748b;margin-bottom:8px;">PERFIL FINANCEIRO</div>
          <div style="font-size:2rem;font-weight:700;color:#a5b4fc;margin-bottom:4px;">{profile}</div>
          <div style="font-size:0.82rem;color:{trend_color};">{trend_icon} Tendência: {trend}</div>
          <div style="margin-top:12px;">
            <div style="font-size:0.72rem;color:#64748b;margin-bottom:4px;">Taxa de consumo de renda</div>
            <div style="background:rgba(255,255,255,0.06);border-radius:6px;height:8px;overflow:hidden;">
              <div style="width:{min(burn_r*100,100):.1f}%;height:100%;
                   background:{'#ef4444' if burn_r > 0.8 else '#f59e0b' if burn_r > 0.6 else '#10b981'};
                   border-radius:6px;"></div>
            </div>
            <div style="font-size:0.72rem;color:#64748b;margin-top:4px;">{burn_r*100:.1f}% da renda comprometida com gastos</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        if top_cats:
            st.markdown("""
            <div class="glass-card">
              <div style="font-size:0.72rem;color:#64748b;margin-bottom:10px;">TOP CATEGORIAS DE GASTO</div>
            """, unsafe_allow_html=True)
            colors_list = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"]
            for i, cat in enumerate(top_cats[:5]):
                color = colors_list[i % len(colors_list)]
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:8px;padding:5px 0;
                     border-bottom:1px solid rgba(255,255,255,0.04);">
                  <div style="width:10px;height:10px;border-radius:50%;background:{color};flex-shrink:0;"></div>
                  <span style="color:#e2e8f0;font-size:0.85rem;">{cat.title()}</span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Ainda não há categorias suficientes para exibir ranking.")

# ══════════════════════════════════════════════════════════════════════════════
#  SEÇÃO 6: Abas Operacionais (sem chat)
# ══════════════════════════════════════════════════════════════════════════════
section_header("🧩", "Operações Nexa (API real)")

with st.expander("⚡ Centro de Ações", expanded=False):
    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("🔄 Sincronizar Pluggy agora", use_container_width=True):
            sync = api.sync_pluggy_transactions()
            if sync.get("success"):
                st.success("Sync concluído com sucesso.")
            else:
                st.warning(f"Falha no sync: {sync.get('error')}")
    with a2:
        if st.button("🧾 Recalcular orçamento", use_container_width=True):
            _ = api.get_budget_advice(user_id, monthly_income=income_val)
            st.success("Orçamento recalculado.")
    with a3:
        if st.button("📥 Atualizar transações", use_container_width=True):
            _ = api.get_transactions(user_id, limit=300)
            st.success("Transações atualizadas.")

tab_tx, tab_alerts, tab_subs, tab_score = st.tabs([
    "📜 Transações",
    "🚨 Alertas",
    "🔁 Assinaturas",
    "❤️ Health Score",
])

with tab_tx:
    if transactions.get("success"):
        tx_data = (transactions.get("data", {}) or {})
        tx_rows = tx_data.get("transactions", []) or []
        st.caption(f"Total: {tx_data.get('total', 0)} · Débito: {tx_data.get('debit_count', 0)} · Crédito: {tx_data.get('credit_count', 0)}")
        if tx_rows:
            df = pd.DataFrame(tx_rows)
            cols = [c for c in ["date", "description", "amount", "category", "transaction_type", "context_type"] if c in df.columns]
            st.dataframe(df[cols] if cols else df, use_container_width=True, hide_index=True)
        else:
            st.info("Sem transações para mostrar.")
    else:
        st.warning(f"Falha ao carregar transações: {transactions.get('error')}")

with tab_alerts:
    if alerts.get("success"):
        data = alerts.get("data", {}) or {}
        rows = data.get("alerts", []) or []
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", data.get("total_count", 0))
        c2.metric("Críticos", data.get("critical_count", 0))
        c3.metric("Warnings", data.get("warning_count", 0))
        if rows:
            for a in rows[:8]:
                lvl = (a.get("level") or "INFO").upper()
                emoji = "🔴" if lvl == "CRITICAL" else "🟡" if lvl == "WARNING" else "🔵"
                st.markdown(f"**{emoji} {a.get('title','Alerta')}**  \n{a.get('message','')}")
        else:
            st.success("Sem alertas ativos no momento.")
    else:
        st.warning(f"Falha ao carregar alertas: {alerts.get('error')}")

with tab_subs:
    if subs.get("success"):
        data = subs.get("data", {}) or {}
        c1, c2, c3 = st.columns(3)
        c1.metric("Assinaturas", data.get("total_subscriptions", 0))
        c2.metric("Custo Mensal", f"R$ {float(data.get('total_monthly_cost', 0) or 0):,.2f}")
        c3.metric("Com alerta", data.get("alerted_count", 0))
        st.caption(data.get("summary_text", ""))
        rows = data.get("subscriptions", []) or []
        if rows:
            df = pd.DataFrame(rows)
            cols = [c for c in ["description", "amount", "next_due_date", "confidence"] if c in df.columns]
            st.dataframe(df[cols] if cols else df, use_container_width=True, hide_index=True)
    else:
        st.warning(f"Falha ao carregar assinaturas: {subs.get('error')}")

with tab_score:
    if health_hist.get("success"):
        data = health_hist.get("data", {}) or {}
        c1, c2, c3 = st.columns(3)
        c1.metric("Score atual", data.get("current_score", "—"))
        c2.metric("Tendência", data.get("trend", "—"))
        c3.metric("Qualidade", data.get("data_quality", "—"))
        hist = data.get("history", []) or []
        if hist:
            dfh = pd.DataFrame(hist)
            x_col = "date"
            y_col = "score" if "score" in dfh.columns else "health_score"
            if y_col in dfh.columns:
                fig_hs = px.line(dfh, x=x_col, y=y_col, markers=True, title="Evolução do Health Score")
                fig_hs.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=40, l=0, r=0, b=0),
                    font=dict(color="#94a3b8"),
                )
                st.plotly_chart(fig_hs, use_container_width=True)
    else:
        st.warning(f"Falha ao carregar histórico de score: {health_hist.get('error')}")

# ── Rodapé ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:2rem; padding:1rem; text-align:center;
     border-top:1px solid rgba(99,102,241,0.1);">
    <span style="font-size:0.72rem;color:#334155;">
        Nexa · Dados via Open Finance · Atualizado em tempo real
    </span>
</div>
""", unsafe_allow_html=True)
