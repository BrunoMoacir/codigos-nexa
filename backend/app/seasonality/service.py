"""
app/seasonality/service.py — SeasonalityService (R2.c)

Combina o calendário fiscal puro (fiscal_calendar.py) com os sinais de
perfil do usuário (profile_probe.py) e devolve eventos personalizados:

  - Eventos "mei" só aparecem para quem tem sinal de MEI/PJ.
  - Eventos "clt" só aparecem para quem tem salário recorrente.
  - Valores estimados (13º ≈ salário, DAS ≈ último DAS pago, IPVA/IPTU ≈
    pago no ano anterior) entram quando há dado real — nunca inventados.

Usado por: router REST, NotificationEngine (feed) e tool de chat.
"""

from __future__ import annotations

import logging
from datetime import date

from app.seasonality.fiscal_calendar import CalendarEvent, active_events
from app.seasonality.models import SeasonalEventOut, SeasonalityResponse
from app.seasonality.profile_probe import SeasonalProfile, build_profile
from app.core.formatacao import brl

logger = logging.getLogger(__name__)

# Teto de renda anual isenta da declaração do IR (ano-base 2025 → IR 2026).
# Abaixo disso o card de IR vira lembrete de restituição, não de obrigação.
_IR_EXEMPTION_ANNUAL_BRL = 33_888.0


class SeasonalityService:
    """Eventos fiscais sazonais personalizados por usuário."""

    def get_events(
        self,
        user_id: str,
        today: date | None = None,
        profile: SeasonalProfile | None = None,
    ) -> SeasonalityResponse:
        today = today or date.today()
        profile = profile or build_profile(user_id, today)

        events: list[SeasonalEventOut] = []
        for raw in active_events(today):
            if raw.audience == "mei" and not profile.is_mei:
                continue
            if raw.audience == "clt" and not profile.has_salary:
                continue
            events.append(self._personalize(raw, profile, today))

        return SeasonalityResponse(
            user_id=user_id,
            reference_date=today,
            total=len(events),
            events=events,
            profile_signals={
                "is_mei": profile.is_mei,
                "has_salary": profile.has_salary,
            },
        )

    # ── Personalização por evento ─────────────────────────────────────

    @staticmethod
    def _personalize(
        raw: CalendarEvent,
        profile: SeasonalProfile,
        today: date,
    ) -> SeasonalEventOut:
        estimated: float | None = None
        personalized = False
        description = raw.description
        action_hint = raw.action_hint

        if raw.event_code in ("DECIMO_PRIMEIRA", "DECIMO_SEGUNDA") and profile.monthly_salary_brl:
            # 1ª parcela = ~50% do bruto sem descontos; 2ª = restante com
            # IR/INSS. Aproximação conservadora sobre o líquido detectado.
            estimated = round(profile.monthly_salary_brl / 2, 2)
            personalized = True
            description += (
                f" Pela sua renda recorrente, esta parcela deve ficar perto de "
                f"{brl(estimated, 0)}."
            )

        elif raw.event_code == "DAS_MEI" and profile.last_das_amount_brl:
            estimated = profile.last_das_amount_brl
            personalized = True
            description += (
                f" Seu último DAS foi de {brl(estimated)}."
            )

        elif raw.event_code == "IPVA_IPTU" and profile.ipva_iptu_last_year_brl:
            estimated = profile.ipva_iptu_last_year_brl
            personalized = True
            description += (
                f" No ano passado você pagou {brl(estimated, 0)} em IPVA/IPTU — "
                f"use esse valor como referência para a reserva."
            )

        elif raw.event_code == "IR_DECLARACAO" and profile.annual_income_brl:
            estimated = profile.annual_income_brl
            personalized = True
            if profile.annual_income_brl < _IR_EXEMPTION_ANNUAL_BRL:
                description += (
                    " Pela renda detectada nas suas contas conectadas, você pode "
                    "estar abaixo do teto de obrigatoriedade — mas declarar mesmo "
                    "assim pode recuperar IR retido na fonte."
                )
            else:
                description += (
                    f" Renda anual detectada nas contas conectadas: "
                    f"{brl(profile.annual_income_brl, 0)} — declaração obrigatória."
                )

        return SeasonalEventOut(
            event_code=raw.event_code,
            name=raw.name,
            description=description,
            action_hint=action_hint,
            deadline=raw.deadline,
            days_until_deadline=raw.days_until_deadline(today),
            is_obligation=raw.is_obligation,
            estimated_amount_brl=estimated,
            is_personalized=personalized,
            metadata=raw.metadata,
        )


_service: SeasonalityService | None = None


def get_seasonality_service() -> SeasonalityService:
    global _service
    if _service is None:
        _service = SeasonalityService()
    return _service


__all__ = ["SeasonalityService", "get_seasonality_service"]
