import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.ui import load_css, kpi_card, section_header, badge
from utils.api import NexaAPIClient

# ── Auth guard ────────────────────────────────────────────────────────────────
if "jwt_token" not in st.session_state or not st.session_state.jwt_token:
    st.warning("🔒 Faça login na tela inicial primeiro.")
    st.page_link("app.py", label="Ir para o Login", icon="🏠")
    st.stop()

st.set_page_config(page_title="Meu Dinheiro · Nexa", page_icon="📊", layout="wide")
load_css()

api = NexaAPIClient()
user_id = st.session_state.user_id or st.session_state.username

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="padding:1rem 0.5rem 0.5rem 0.5rem;">
        <div style="font-size:0.7rem;color:#475569;letter-spacing:0.1em;margin-bottom:4px;">CONTA</div>
        <div style="font-weight:700;color:#e2e8f0;font-size:1rem;">@{user_id}</div>
    </div>
    <hr style="border-color:rgba(99,102,241,0.15);margin:0.4rem 0;">
    """, unsafe_allow_html=True)
    if st.button("← Voltar ao Início", use_container_width=True):
        st.switch_page("app.py")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:1.5rem;">
  <p style="color:#6366f1;font-size:0.78rem;font-weight:600;letter-spacing:0.08em;margin-bottom:4px;">DASHBOARD FINANCEIRO</p>
  <h1 style="margin:0;">📊 Meu Dinheiro</h1>
  <p style="color:#64748b;font-size:0.88rem;margin-top:6px;">Seus dados financeiros reais, via Open Finance</p>
</div>
""", unsafe_allow_html=True)

# ── Carregar dados da API ─────────────────────────────────────────────────────
with st.spinner("⚡ Sincronizando dados via Open Finance…"):
    forecast = api.get_forecast_summary(user_id)
    income = 10_000.0
    if forecast.get("success"):
        income = forecast["data"].get("financial_health", {}).get("total_income", 10_000.0)
    budget = api.get_budget_advice(user_id, monthly_income=income)
    goals = api.get_goals_summary(user_id)

st.divider()

# ── KPIs ──────────────────────────────────────────────────────────────────────
section_header("💎", "Visão Geral")
col1, col2, col3 = st.columns(3)

if forecast.get("success"):
    f_data = forecast["data"]
    health = f_data.get("financial_health", {})
    sts    = f_data.get("safe_to_spend", {})
    score  = health.get("health_score", 0) or health.get("score", 0)
    total_income = health.get("total_income", 0)
    safe   = sts.get("safe_to_spend_total", 0)
    risk   = sts.get("risk_level", "LOW")

    score_color = "green" if score >= 70 else "yellow" if score >= 40 else "red"
    risk_badge  = badge(risk, "green" if risk == "LOW" else "yellow" if risk == "MEDIUM" else "red")

    with col1:
        kpi_card("Renda Mensal (Líquida)", f"R$ {total_income:,.2f}", sub="Baseado no seu histórico", color="purple")
    with col2:
        kpi_card("Safe to Spend", f"R$ {safe:,.2f}", sub=f"Nível de risco: {risk}", color=score_color)
    with col3:
        kpi_card("Health Score", f"{score:.0f} / 100", sub="Saúde financeira geral", color=score_color)

    # Score Progress Bar visual
    score_bar_color = "#10b981" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    st.markdown(f"""
    <div style="margin:0 0 1.5rem 0;">
      <div style="display:flex; justify-content:space-between; font-size:0.72rem; color:#64748b; margin-bottom:4px;">
        <span>Saúde Financeira</span><span>{score:.0f}%</span>
      </div>
      <div style="background:rgba(255,255,255,0.05); border-radius:6px; height:8px; overflow:hidden;">
        <div style="width:{score}%; height:100%;
             background:linear-gradient(90deg, {score_bar_color}88, {score_bar_color});
             border-radius:6px; transition:width 0.5s ease;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.error("⚠️ Não foi possível carregar os dados de Forecast. Verifique se o backend está rodando.")

# ── Orçamento 50/30/20 ────────────────────────────────────────────────────────
section_header("💰", "Regra 50/30/20")

if budget.get("success"):
    b_data = budget["data"]
    try:
        text_advice = b_data.get("summary_text", "")
        groups      = b_data.get("group_summary", [])
        cuts        = b_data.get("actionable_cuts", [])

        col_chart, col_info = st.columns([1, 1])

        with col_chart:
            if groups:
                g_map = {g["group"]: g for g in groups}
                labels  = ["Essenciais", "Desejos", "Poupança"]
                keys    = ["essenciais", "desejos", "poupanca"]
                actuals = [g_map.get(k, {}).get("current_pct", 0) for k in keys]
                targets = [50, 30, 20]
                colors  = ["#6366f1", "#a78bfa", "#10b981"]

                fig = go.Figure()

                fig.add_trace(go.Bar(
                    name="Atual (%)",
                    x=labels,
                    y=actuals,
                    marker_color=colors,
                    marker_line_width=0,
                    width=0.4,
                ))
                fig.add_trace(go.Bar(
                    name="Meta (%)",
                    x=labels,
                    y=targets,
                    marker_color=["rgba(99,102,241,0.2)", "rgba(167,139,250,0.2)", "rgba(16,185,129,0.2)"],
                    marker_line_color=colors,
                    marker_line_width=1.5,
                    width=0.4,
                ))
                fig.update_layout(
                    barmode="group",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#94a3b8", family="Inter"),
                    legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.04)", zeroline=False),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.04)", zeroline=False, ticksuffix="%", range=[0, 60]),
                    margin=dict(t=10, b=10, l=0, r=0),
                    height=260,
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_info:
            if text_advice:
                st.info("💡 **Análise da IA**\n\n" + text_advice)

            if cuts:
                st.markdown("""<div style="margin-top:8px;">""", unsafe_allow_html=True)
                for cut in cuts[:2]:
                    saving = cut.get("saving", 0)
                    cat    = cut.get("category", "").title()
                    reason = cut.get("reasoning", "")
                    st.markdown(f"""
                    <div class="glass-card" style="padding:14px 18px; margin-bottom:8px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="font-weight:600;font-size:0.88rem;color:#e2e8f0;">✂️ {cat}</span>
                            <span class="badge badge-red">Economia: R$ {saving:,.0f}/mês</span>
                        </div>
                        <p style="color:#64748b;font-size:0.78rem;margin:0;line-height:1.5;">{reason[:160]}…</p>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Erro ao processar orçamento: {e}")
else:
    st.warning("Não foi possível carregar dados de orçamento.")

# ── Metas Financeiras ─────────────────────────────────────────────────────────
section_header("🎯", "Suas Metas")

if goals.get("success"):
    goal_list = goals["data"].get("goals", [])
    if goal_list:
        cols = st.columns(min(len(goal_list), 2))
        for idx, g in enumerate(goal_list):
            pct        = g.get("progress_pct", 0)
            name       = g.get("name", "Meta")
            current    = g.get("current_amount", 0)
            target     = g.get("target_amount", 0)
            status     = g.get("status", "ACTIVE")
            proj       = g.get("projection", {})
            suggestion = proj.get("suggestion", "")

            bar_color  = "#10b981" if pct >= 80 else "#6366f1" if pct >= 40 else "#f59e0b"
            badge_color = "green" if pct >= 80 else "purple" if pct >= 40 else "yellow"

            with cols[idx % 2]:
                st.markdown(f"""
                <div class="glass-card" style="padding:20px 22px;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
                        <span style="font-weight:700;font-size:0.95rem;color:#e2e8f0;">{name}</span>
                        {badge(f"{pct:.0f}%", badge_color)}
                    </div>
                    <div style="font-size:1.4rem;font-weight:700;color:{bar_color};margin-bottom:4px;">
                        R$ {current:,.2f}
                    </div>
                    <div style="font-size:0.72rem;color:#64748b;margin-bottom:10px;">
                        de R$ {target:,.2f} · {status}
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
                Converse com o agente e peça para criar uma meta financeira.
            </p>
        </div>
        """, unsafe_allow_html=True)
else:
    st.error("⚠️ Erro ao carregar metas financeiras.")

# ── Rodapé ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:2rem; padding:1rem; text-align:center;
     border-top:1px solid rgba(99,102,241,0.1);">
    <span style="font-size:0.72rem;color:#334155;">
        Nexa · Dados via Open Finance · Atualizado em tempo real
    </span>
</div>
""", unsafe_allow_html=True)
