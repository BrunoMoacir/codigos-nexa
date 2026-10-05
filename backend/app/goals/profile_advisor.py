# app/goals/profile_advisor.py
"""
GoalProfileAdvisor — personaliza o sistema de metas com dados do ConsumptionProfiler.

Responsabilidade única: dado um UserProfile (optimizer) e uma lista de metas ativas,
retorna:
  - profile_alerts:   avisos gerais por FSS / cluster
  - suggested_goals:  sugestões de novos tipos de meta que o cluster indica
  - goal_warnings:    aviso por meta específica (incompatibilidade com estresse atual)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from app.core.formatacao import brl

if TYPE_CHECKING:
    from app.optimizer.profiler import UserProfile
    from app.goals.tracker import Goal

logger = logging.getLogger(__name__)

# Threshold: se contribuição necessária > X × poupança estimada → alerta de inviabilidade
_INFEASIBILITY_RATIO = 1.5

# Meses de reserva de emergência sugeridos por cluster/FSS
_EMERGENCY_MONTHS_BY_FSS = {
    "CRITICO": 3,
    "ALERTA":  3,
    "ATENCAO": 6,
    "SAUDAVEL": 6,
}


@dataclass
class GoalProfileContext:
    """Resultado da análise de compatibilidade perfil × metas."""
    lifestyle_cluster: str = "NAO_CLASSIFICADO"
    fss_level: str = "SAUDAVEL"
    fss: float = 0.0
    investor_type: str = "NONE"
    savings_rate: float = 0.0
    monthly_avg_spend: float = 0.0
    profile_alerts: list[str] = field(default_factory=list)
    suggested_goals: list[dict] = field(default_factory=list)
    goal_warnings: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "lifestyle_cluster":  self.lifestyle_cluster,
            "fss_level":          self.fss_level,
            "fss_score":          round(self.fss, 1),
            "investor_type":      self.investor_type,
            "savings_rate":       round(self.savings_rate, 1),
            "profile_alerts":     self.profile_alerts,
            "suggested_goals":    self.suggested_goals,
            "goal_warnings":      self.goal_warnings,
        }


class GoalProfileAdvisor:
    """
    Cruza o UserProfile comportamental com as metas ativas do usuário e produz
    alertas, sugestões e avisos de incompatibilidade.
    """

    def analyze(
        self,
        profile: "UserProfile",
        active_goals: list["Goal"],
    ) -> GoalProfileContext:
        cluster      = profile.lifestyle_cluster
        fss_level    = profile.fss_level
        fss          = profile.fss
        investor     = profile.investor_type
        savings_rate = getattr(profile, "savings_rate", 0.0)
        avg_spend    = profile.monthly_avg_spend

        ctx = GoalProfileContext(
            lifestyle_cluster = cluster,
            fss_level         = fss_level,
            fss               = fss,
            investor_type     = investor,
            savings_rate      = savings_rate,
            monthly_avg_spend = avg_spend,
        )

        existing_types = {g.goal_type.lower() for g in active_goals}

        self._add_fss_alerts(ctx, fss_level, fss)
        self._add_cluster_suggestions(ctx, cluster, investor, fss_level, existing_types, avg_spend)
        self._add_goal_warnings(ctx, profile, active_goals, savings_rate, avg_spend)

        return ctx

    # ─────────────────────────────────────────────────────────────────
    # FSS alerts
    # ─────────────────────────────────────────────────────────────────

    def _add_fss_alerts(
        self,
        ctx: GoalProfileContext,
        fss_level: str,
        fss: float,
    ) -> None:
        if fss_level == "CRITICO":
            ctx.profile_alerts.append(
                f"🆘 FSS Crítico ({fss:.0f}/100): estresse financeiro severo detectado. "
                "Pause metas de acumulação e priorize eliminar dívidas e cheque especial primeiro."
            )
        elif fss_level == "ALERTA":
            ctx.profile_alerts.append(
                f"🔴 FSS em Alerta ({fss:.0f}/100): pressão financeira acima do normal. "
                "Construa uma reserva de emergência antes de avançar em outras metas."
            )
        elif fss_level == "ATENCAO":
            ctx.profile_alerts.append(
                f"⚠️ FSS em Atenção ({fss:.0f}/100): finanças estáveis, mas com pontos de melhora. "
                "Revise metas com prazo curto para garantir que são alcançáveis."
            )

    # ─────────────────────────────────────────────────────────────────
    # Cluster suggestions
    # ─────────────────────────────────────────────────────────────────

    def _add_cluster_suggestions(
        self,
        ctx: GoalProfileContext,
        cluster: str,
        investor: str,
        fss_level: str,
        existing_types: set[str],
        avg_spend: float,
    ) -> None:
        # Reserva de emergência sempre sugerida quando não existe e FSS não é saudável,
        # ou quando investidor ativo não tem reserva (pré-requisito para investir)
        needs_emergency = (
            "emergencia" not in existing_types
            and (
                fss_level in ("CRITICO", "ALERTA", "ATENCAO")
                or investor in ("ATIVO", "DIVERSIFICADO")
            )
        )
        if needs_emergency:
            months = _EMERGENCY_MONTHS_BY_FSS.get(fss_level, 6)
            target = round(avg_spend * months, -2) if avg_spend > 0 else 15000.0
            urgency = "🆘 Urgente" if fss_level == "CRITICO" else (
                "🔴 Alta prioridade" if fss_level == "ALERTA" else "ℹ️ Recomendado"
            )
            reason = (
                "Pré-requisito para investir com segurança: reserva protege aportes de resgates de emergência."
                if investor in ("ATIVO", "DIVERSIFICADO") else
                "Reserva de emergência é a base de qualquer planejamento financeiro sólido."
            )
            ctx.suggested_goals.append({
                "goal_type":    "emergencia",
                "name":         f"Reserva de Emergência ({months} meses)",
                "target_amount": target,
                "priority":     urgency,
                "reason":       reason,
            })

        # Cluster-specific suggestions
        if cluster == "EXPLORADOR_GLOBAL" and "viagem" not in existing_types:
            ctx.suggested_goals.append({
                "goal_type":    "viagem",
                "name":         "Fundo de Viagens",
                "target_amount": 8000.0,
                "priority":     "ℹ️ Alinhado ao seu perfil",
                "reason":       "Você é um viajante frequente. Ter um fundo dedicado evita "
                                "comprometer o orçamento quando a próxima viagem aparecer.",
            })

        if cluster == "FAMILIA_ESTRUTURADA" and "educacao" not in existing_types:
            ctx.suggested_goals.append({
                "goal_type":    "educacao",
                "name":         "Fundo de Educação",
                "target_amount": 30000.0,
                "priority":     "ℹ️ Alinhado ao seu perfil",
                "reason":       "Família com filhos: começar cedo um fundo de educação "
                                "reduz o impacto das mensalidades futuras.",
            })

        if cluster == "MICROEMPREENDEDOR" and "outros" not in existing_types:
            ctx.suggested_goals.append({
                "goal_type":    "outros",
                "name":         "Capital de Giro (PJ)",
                "target_amount": avg_spend * 3 if avg_spend > 0 else 10000.0,
                "priority":     "ℹ️ Alinhado ao seu perfil",
                "reason":       "Autônomo/MEI: manter 3 meses de custos operacionais como "
                                "capital de giro protege o negócio em meses de baixa receita.",
            })

        if cluster == "INVESTIDOR_CAUTELOSO" and investor in ("ATIVO", "DIVERSIFICADO"):
            if "emergencia" not in existing_types:
                pass  # já sugerida acima
            # Sugerir meta de previdência se não tiver nenhuma meta de longo prazo
            long_term_types = {"imovel", "previdencia", "aposentadoria"}
            if not existing_types & long_term_types:
                ctx.suggested_goals.append({
                    "goal_type":    "outros",
                    "name":         "Previdência / Aposentadoria",
                    "target_amount": 500000.0,
                    "priority":     "ℹ️ Longo prazo",
                    "reason":       "Investidor ativo: consolidar um objetivo de longo prazo "
                                    "direciona os aportes e otimiza a estratégia de carteira.",
                })

    # ─────────────────────────────────────────────────────────────────
    # Per-goal warnings
    # ─────────────────────────────────────────────────────────────────

    def _add_goal_warnings(
        self,
        ctx: GoalProfileContext,
        profile: "UserProfile",
        active_goals: list["Goal"],
        savings_rate: float,
        avg_spend: float,
    ) -> None:
        fss_level    = profile.fss_level
        # Poupança mensal estimada (pode ser negativa se déficit)
        estimated_monthly_savings = avg_spend * savings_rate / 100 if avg_spend > 0 else 0.0

        for goal in active_goals:
            needed = goal.monthly_contribution_needed
            if needed is None or needed <= 0:
                continue

            warnings = []

            # FSS CRÍTICO: qualquer meta de acumulação é arriscada
            if fss_level == "CRITICO" and goal.goal_type not in ("emergencia",):
                warnings.append(
                    f"🆘 FSS Crítico: recomendamos pausar esta meta e focar em "
                    "liquidar dívidas primeiro. Retome quando FSS baixar de ALERTA."
                )

            # Inviabilidade de ritmo: precisa mais do que X× a poupança atual
            elif (
                estimated_monthly_savings > 0
                and needed > estimated_monthly_savings * _INFEASIBILITY_RATIO
            ):
                warnings.append(
                    f"⚠️ Esta meta exige {brl(needed, 0)}/mês mas sua poupança estimada "
                    f"é {brl(estimated_monthly_savings, 0)}/mês — ritmo atual não suficiente. "
                    "Considere estender o prazo ou reduzir o valor alvo."
                )
            # Sem poupança detectada e meta tem prazo
            elif estimated_monthly_savings <= 0 and goal.target_date and needed > 0:
                warnings.append(
                    f"⚠️ Nenhuma poupança regular detectada. Para atingir esta meta "
                    f"no prazo você precisaria guardar {brl(needed, 0)}/mês."
                )

            if warnings:
                ctx.goal_warnings[goal.goal_id] = " ".join(warnings)
