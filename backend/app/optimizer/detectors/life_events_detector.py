"""
LifeEventsDetector — detecta eventos de vida de alta relevância financeira.

Cada detector retorna:
    {
        "event": str,          # identificador do evento
        "confidence": float,   # 0.0–1.0, calculado pelo EvidenceScore
        "detected_at": date,   # data aproximada do evento
        "trigger_action": str, # ação a ser tomada pelo produto
    }

O detector opera sobre dois DataFrames:
    - txns_recent: transações dos últimos 60 dias (janela de detecção)
    - txns_history: transações de 6–18 meses atrás (baseline para comparação)

Confiança por evidência (não por regra fixa):
    confidence = volume × 0.30 + recurrence × 0.25 + absence × 0.20
               + diversity × 0.15 + quality × 0.10

Um único gasto isolado em "BUFFET" gera ~0.44.
BUFFET + DECORAÇÃO + FOTÓGRAFO em meses próximos gera ~0.80.
Eventos abaixo de _MIN_EVENT_CONFIDENCE não são retornados.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date

import polars as pl

from app.optimizer.detectors.evidence_scorer import (
    EvidenceScore,
    gather_evidence,
    compute_evidence_score,
    compute_false_positive_risk,
    missing_signals_from_evidence,
)


# Confiança mínima para surfaçar um evento — filtra sinais isolados e fracos.
# O relevance_filter.py usa >= 0.75 para notificações; este gate remove o ruído
# antes mesmo de chegar ao relatório.
_MIN_EVENT_CONFIDENCE = 0.40


@dataclass
class LifeEvent:
    event: str
    confidence: float
    detected_at: date
    trigger_action: str
    supporting_signals: list[str] = field(default_factory=list)
    missing_signals: list[str] = field(default_factory=list)
    false_positive_risk: str = "high"


_BABY_KEYWORDS = [
    "FRALDA", "PAMPERS", "HUGGIES", "JOHNSON BABY", "MATERNIDADE",
    "ENXOVAL", "BEBE", "INFANTIL", "KINDER", "NUTRILON", "NAN NESTLE",
    "NENUCO", "CHICCO", "BRINQUEDO BEBE",
]

_MOVING_KEYWORDS = [
    # Sinais de reforma/móveis/mudança — excluem qualquer keyword de aluguel recorrente.
    # "ALUGUEL" e "DEPOSITO ALUGUEL" são pagamentos mensais, não eventos de mudança.
    "MUDANCA", "LEROY MERLIN", "TOKSTOK", "ETNA",
    "MADEIRAMADEIRA", "CASA SHOW", "TELHANORTE",
    "CONSTRUTORA", "IMOVEL",
]

_WEDDING_KEYWORDS = [
    "BUFFET", "CERIMONIAL", "FOTOGRAFO CASAMENTO", "NOIVAS", "FESTAS",
    "MUITO PELO RISO", "ALUGUEL VESTIDO", "DECORACAO FESTA",
]

_EDUCATION_KEYWORDS = [
    "FACULDADE", "UNIVERSIDADE", "MENSALIDADE EAD", "ESTACIO",
    "ANHANGUERA", "UNIP", "SENAC", "FIES", "PROUNI",
]

_SALARY_INCREASE_THRESHOLD = 0.20
_SALARY_DROP_THRESHOLD = -0.20

# Padrões pré-compilados — re.escape garante que keywords com caracteres especiais
# (ex: pontos, parênteses) não sejam interpretados como metacaracteres regex.
_P_BABY      = re.compile("|".join(re.escape(k) for k in _BABY_KEYWORDS),      re.IGNORECASE)
_P_MOVING    = re.compile("|".join(re.escape(k) for k in _MOVING_KEYWORDS),    re.IGNORECASE)
_P_WEDDING   = re.compile("|".join(re.escape(k) for k in _WEDDING_KEYWORDS),   re.IGNORECASE)
_P_EDUCATION = re.compile("|".join(re.escape(k) for k in _EDUCATION_KEYWORDS), re.IGNORECASE)

# Qualidade intrínseca das keywords por tipo de evento (0–1).
# Alta: keywords muito específicas (PAMPERS, CERIMONIAL, FACULDADE).
# Baixa: keywords ambíguas que sozinhas não identificam o evento (BUFFET, LEROY MERLIN).
_QUALITY_BABY      = 0.85  # FRALDA/PAMPERS → fortíssimo sinal
_QUALITY_MOVING    = 0.65  # LEROY MERLIN pode ser reforma pontual; IMOVEL é mais forte
_QUALITY_WEDDING   = 0.72  # CERIMONIAL/NOIVAS forte; BUFFET ambíguo sozinho
_QUALITY_EDUCATION = 0.85  # FACULDADE/UNIVERSIDADE → muito específico


class LifeEventsDetector:

    def detect_all(
        self,
        txns_recent: pl.DataFrame,
        txns_history: pl.DataFrame,
        income_recent: float,
        income_historical: float,
    ) -> list[LifeEvent]:
        events = []

        baby = self._detect_new_baby(txns_recent, txns_history)
        if baby:
            events.append(baby)

        moving = self._detect_moving(txns_recent, txns_history)
        if moving:
            events.append(moving)

        wedding = self._detect_wedding(txns_recent, txns_history)
        if wedding:
            events.append(wedding)

        education = self._detect_new_education(txns_recent, txns_history)
        if education:
            events.append(education)

        income_event = self._detect_income_change(income_recent, income_historical)
        if income_event:
            events.append(income_event)

        return events

    def _detect_new_baby(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_BABY
        )

        # Gate primário: gasto mínimo e ausência de padrão histórico similar
        if recent_spend <= 200 or hist_spend >= 50:
            return None

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=200, history_baseline=50, quality=_QUALITY_BABY,
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        return LifeEvent(
            event="new_baby",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_baby_financial_planning",
            supporting_signals=[
                f"baby_spend_recent=R${recent_spend:.0f}",
                f"baby_spend_historical=R${hist_spend:.0f}",
                f"txn_count={txn_count}",
                f"merchant_diversity={merchant_count}",
            ] + ev.as_signals(),
            missing_signals=missing_signals_from_evidence(ev),
            false_positive_risk=compute_false_positive_risk(ev.composite),
        )

    def _detect_moving(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_MOVING
        )

        # Requer gasto alto E sem histórico prévio similar.
        # Guard explícito: historical_spend < 100 previne falso positivo quando
        # historical_spend == 0 (sem histórico) — nesse caso "any spend > 0" passaria.
        if recent_spend <= 500 or hist_spend >= 100:
            return None

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=500, history_baseline=100, quality=_QUALITY_MOVING,
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        return LifeEvent(
            event="home_change",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_financing_vs_rent_analysis",
            supporting_signals=[
                f"moving_spend=R${recent_spend:.0f}",
                f"moving_historical=R${hist_spend:.0f}",
                f"txn_count={txn_count}",
                f"merchant_diversity={merchant_count}",
            ] + ev.as_signals(),
            missing_signals=missing_signals_from_evidence(ev),
            false_positive_risk=compute_false_positive_risk(ev.composite),
        )

    def _detect_wedding(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_WEDDING
        )

        # Exige gasto recente alto E ausência de padrão histórico similar,
        # para distinguir eventos pontuais (um casamento) de gastos regulares em eventos.
        if recent_spend <= 1000 or hist_spend >= 200:
            return None

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=1_000, history_baseline=200, quality=_QUALITY_WEDDING,
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        return LifeEvent(
            event="wedding",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_couple_financial_planning",
            supporting_signals=[
                f"wedding_spend=R${recent_spend:.0f}",
                f"wedding_historical=R${hist_spend:.0f}",
                f"txn_count={txn_count}",
                f"merchant_diversity={merchant_count}",
            ] + ev.as_signals(),
            missing_signals=missing_signals_from_evidence(ev),
            false_positive_risk=compute_false_positive_risk(ev.composite),
        )

    def _detect_new_education(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_EDUCATION
        )

        if recent_spend <= 300 or hist_spend >= 100:
            return None

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=300, history_baseline=100, quality=_QUALITY_EDUCATION,
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        return LifeEvent(
            event="new_education",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_student_account_options",
            supporting_signals=[
                f"edu_spend_recent=R${recent_spend:.0f}",
                f"txn_count={txn_count}",
                f"merchant_diversity={merchant_count}",
            ] + ev.as_signals(),
            missing_signals=missing_signals_from_evidence(ev),
            false_positive_risk=compute_false_positive_risk(ev.composite),
        )

    def _detect_income_change(
        self, income_recent: float, income_historical: float
    ) -> LifeEvent | None:
        if income_historical <= 0:
            return None

        change_ratio = (income_recent - income_historical) / income_historical

        if change_ratio > _SALARY_INCREASE_THRESHOLD:
            # Confiança cresce com a magnitude da mudança:
            #   +20% (threshold) → 0.55 | +50% → 0.80 | +100% → 0.95 (cap)
            confidence = round(min(0.55 + (change_ratio - 0.20) * 0.83, 0.95), 4)
            return LifeEvent(
                event="income_increase",
                confidence=confidence,
                detected_at=date.today(),
                trigger_action="suggest_investment_of_raise",
                supporting_signals=[f"income_change={change_ratio:.1%}"],
                missing_signals=[],
                false_positive_risk=compute_false_positive_risk(confidence),
            )

        if change_ratio < _SALARY_DROP_THRESHOLD:
            # Queda de renda: confiança cresce com a magnitude (invertida)
            magnitude = abs(change_ratio)
            confidence = round(min(0.55 + (magnitude - 0.20) * 0.83, 0.95), 4)
            return LifeEvent(
                event="income_drop",
                confidence=confidence,
                detected_at=date.today(),
                trigger_action="activate_defense_mode",
                supporting_signals=[f"income_change={change_ratio:.1%}"],
                missing_signals=[],
                false_positive_risk=compute_false_positive_risk(confidence),
            )

        return None
