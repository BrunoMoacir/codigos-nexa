# app/agent/tools/get_financial_forecast.py
"""
Tool: get_financial_forecast
Retorna o diagnóstico financeiro completo do usuário:
  - Cashflow, safe-to-spend, saúde financeira (via UserProfileAnalyzer)
  - Cluster de estilo de vida, FSS e eventos de vida (via ConsumptionProfiler)
"""
from langchain_core.tools import tool
from typing import Optional
import logging
from datetime import date, timedelta

import polars as pl

logger = logging.getLogger(__name__)


@tool
def get_financial_forecast(
    user_id: str,
    monthly_income: Optional[float] = None,
    horizon_days: int = 30,
) -> str:
    """
    Busca o diagnóstico financeiro completo do usuário: cashflow, safe-to-spend,
    health score, projeção de saldo, renda estimada, cluster comportamental,
    nível de estresse financeiro (FSS) e eventos de vida recentes.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Resumo da situação financeira
    - Quanto pode gastar / margem disponível
    - Como estão as finanças este mês
    - Saúde financeira (health score)

    Args:
        user_id: ID do usuário (obrigatório).
        monthly_income: Renda mensal declarada (opcional — melhora a análise).
        horizon_days: Horizonte de projeção em dias (padrão: 30).
    """
    logger.info("[Tool] get_financial_forecast para %s", user_id)
    try:
        from app.runner import get_runner

        result = get_runner().run_from_db(user_id=user_id, horizon_days=horizon_days)

        if result is None:
            return (
                "Ainda não há transações conectadas para este usuário. "
                "Para ver o diagnóstico financeiro real, conecte uma conta bancária via Open Finance "
                "na seção 'Conectar conta' do aplicativo."
            )

        if not result or result.get("status") != "success":
            return (
                "Não consegui carregar dados financeiros para este usuário no momento. "
                "Verifique se há transações conectadas via Open Finance."
            )

        proj           = result.get("projections", {})
        safe           = proj.get("safe_to_spend")
        analysis       = result.get("analysis", {})
        income_profile = analysis.get("income_profile")

        # Extrai transactions_df do resultado — já está em memória, sem I/O extra
        txns_data      = result.get("transactions", {})
        transactions_df: pl.DataFrame = (
            txns_data.get("pf_pj_classified_df")
            or txns_data.get("clean_df")
            or pl.DataFrame()
        )

        lines = ["📊 **Diagnóstico Financeiro Nexa**", ""]

        # ── Safe-to-spend ──────────────────────────────────────────────────
        if safe:
            lines.append("💰 **Margem disponível para gastar:**")
            lines.append(f"   • Este mês: R$ {safe.safe_to_spend_total:,.2f}")
            lines.append(f"   • Por dia com segurança: R$ {safe.safe_to_spend_daily:,.2f}")
            lines.append(f"   • Nível de risco: {safe.risk_level}")
            lines.append("")

        # ── Renda ─────────────────────────────────────────────────────────
        if monthly_income:
            lines.append(f"💵 Renda declarada: R$ {monthly_income:,.0f}/mês")
        elif income_profile and income_profile.confidence >= 0.5:
            lines.append(
                f"💵 Renda estimada: R$ {income_profile.monthly_net_income:,.0f}/mês "
                f"(padrão {income_profile.income_pattern.value}, "
                f"confiança {income_profile.confidence:.0%})"
            )

        # ── Health Score + Perfil financeiro (UserProfileAnalyzer) ────────
        fin_profile = None
        if not transactions_df.is_empty():
            try:
                from app.forecast.etl.profiles import UserProfileAnalyzer
                fin_profile = UserProfileAnalyzer().analyze(
                    transactions_df,
                    income_profile=income_profile,
                )
                score        = fin_profile.financial_health_score
                trend        = fin_profile.trend
                profile_type = getattr(fin_profile, "profile_type", "EQUILIBRADO")
                behavior_tier = getattr(fin_profile, "behavior_tier", None)
                lines.append(f"🏥 Health Score: {score}/100 (tendência: {trend})")
                tier_txt = f" — tier: {behavior_tier}" if behavior_tier else ""
                lines.append(f"   Perfil: {profile_type}{tier_txt}")
                lines.append("")
            except Exception as exc:
                logger.debug("[Tool] UserProfileAnalyzer indisponível: %s", exc)

        # ── Cashflow forecast ──────────────────────────────────────────────
        cf = proj.get("cashflow_forecast")
        cf_has_data = (
            cf is not None
            and not (isinstance(cf, pl.DataFrame) and cf.is_empty())
        )
        if cf_has_data:
            lines.append("📈 **Projeção de Cashflow (30 dias):**")
            if hasattr(cf, "ending_balance"):
                lines.append(f"   • Saldo esperado ao fim: R$ {cf.ending_balance:,.2f}")
            elif hasattr(cf, "expected_balance"):
                lines.append(f"   • Saldo esperado ao fim: R$ {cf.expected_balance:,.2f}")
            if hasattr(cf, "monthly_income"):
                lines.append(f"   • Receita estimada: R$ {cf.monthly_income:,.2f}")
            if hasattr(cf, "monthly_expense"):
                lines.append(f"   • Despesas estimadas: R$ {cf.monthly_expense:,.2f}")
            if hasattr(cf, "worst_balance"):
                lines.append(f"   • Pior saldo projetado: R$ {cf.worst_balance:,.2f}")
            lines.append("")

        # ── Shadow invoices ────────────────────────────────────────────────
        shadow = result.get("shadow_invoices", {})
        if shadow:
            total_impact = shadow.get("total_monthly_impact", 0)
            count        = shadow.get("total_count", 0)
            if count > 0:
                lines.append(f"👻 **Obrigações futuras:** {count} itens detectados")
                lines.append(f"   • Impacto mensal: R$ {abs(total_impact):,.2f}")
                lines.append("")

        # ── Cluster + FSS (ConsumptionProfiler) ───────────────────────────
        if not transactions_df.is_empty():
            try:
                from app.optimizer.profiler import ConsumptionProfiler
                beh_profile = ConsumptionProfiler().build(transactions_df)

                cluster = beh_profile.lifestyle_cluster
                fss     = beh_profile.fss
                fss_lvl = beh_profile.fss_level

                fss_emoji = {
                    "SAUDAVEL": "✅", "ATENCAO": "⚠️",
                    "ALERTA": "🔴", "CRITICO": "🆘",
                }.get(fss_lvl, "⚠️")

                lines.append("🧠 **Perfil Comportamental:**")
                lines.append(f"   • Cluster: {cluster}")
                lines.append(f"   • Estresse Financeiro: {fss_emoji} {fss_lvl} (FSS {fss:.0f}/100)")

                savings_rate = getattr(beh_profile, "savings_rate", None)
                if savings_rate is not None:
                    lines.append(f"   • Taxa de poupança: {savings_rate:.1f}%")

                lines.append("")

                # ── Eventos de vida (LifeEventsDetector) ──────────────────
                try:
                    from app.optimizer.detectors.life_events_detector import LifeEventsDetector
                    from app.optimizer.feature_store import TransactionFeatureEnricher

                    today      = date.today()
                    cutoff_60d = today - timedelta(days=60)
                    cutoff_6m  = today - timedelta(days=180)

                    date_col = "date" if "date" in transactions_df.columns else "transaction_date"

                    # Enriquecer antes de slicear para que merchant_normalized esteja
                    # disponível em txns_recent e txns_history. Idempotente.
                    txns_enriched = TransactionFeatureEnricher().enrich(transactions_df)

                    txns_recent = txns_enriched.filter(
                        pl.col(date_col).cast(pl.Date) >= cutoff_60d
                    )
                    txns_history = txns_enriched.filter(
                        pl.col(date_col).cast(pl.Date) < cutoff_6m
                    )

                    income_recent     = income_profile.monthly_net_income if income_profile else 0.0
                    income_historical = income_recent  # fallback quando não há histórico separado

                    life_events = LifeEventsDetector().detect_all(
                        txns_recent=txns_recent,
                        txns_history=txns_history,
                        income_recent=income_recent,
                        income_historical=income_historical,
                    )

                    if life_events:
                        lines.append("🔔 **Eventos de Vida Detectados:**")
                        for evt in life_events:
                            confidence_pct = int(evt.confidence * 100)
                            lines.append(
                                f"   • {evt.event} (confiança {confidence_pct}%) "
                                f"→ {evt.trigger_action}"
                            )
                        lines.append("")
                except Exception as le_exc:
                    logger.debug("[Tool] LifeEventsDetector indisponível: %s", le_exc)

            except Exception as beh_exc:
                logger.debug("[Tool] ConsumptionProfiler indisponível: %s", beh_exc)

        if len(lines) <= 2:
            return (
                "Diagnóstico calculado, mas sem dados históricos suficientes para montar o relatório completo. "
                "Conecte mais contas bancárias via Open Finance para uma análise mais precisa."
            )

        return "\n".join(lines)

    except Exception as e:
        logger.error("[Tool] get_financial_forecast erro: %s", e, exc_info=True)
        return (
            "Não consegui acessar os dados financeiros agora. "
            "Tente novamente ou informe sua renda e gastos mensais para uma análise manual."
        )
