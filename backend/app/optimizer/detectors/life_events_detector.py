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
from typing import TYPE_CHECKING

import polars as pl

from app.optimizer.detectors.evidence_scorer import (
    EvidenceScore,
    gather_evidence,
    compute_evidence_score,
    compute_false_positive_risk,
    missing_signals_from_evidence,
)
from app.core.formatacao import brl

if TYPE_CHECKING:
    from app.optimizer.detectors.personal_baseline import PersonalBaseline


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

# Subset altamente específico de keywords de casamento — podem detectar isoladas.
# Contrasta com soft keywords (BUFFET, FESTAS) que exigem corroboração obrigatória.
_WEDDING_ANCHOR_KEYWORDS = [
    "CERIMONIAL", "FOTOGRAFO CASAMENTO", "NOIVAS", "ALUGUEL VESTIDO",
]

_EDUCATION_KEYWORDS = [
    "FACULDADE", "UNIVERSIDADE", "MENSALIDADE EAD", "ESTACIO",
    "ANHANGUERA", "UNIP", "SENAC", "FIES", "PROUNI",
]

_SALARY_INCREASE_THRESHOLD = 0.20
_SALARY_DROP_THRESHOLD = -0.20

# Padrões pré-compilados — re.escape garante que keywords com caracteres especiais
# (ex: pontos, parênteses) não sejam interpretados como metacaracteres regex.
_P_BABY           = re.compile("|".join(re.escape(k) for k in _BABY_KEYWORDS),          re.IGNORECASE)
_P_MOVING         = re.compile("|".join(re.escape(k) for k in _MOVING_KEYWORDS),        re.IGNORECASE)
_P_WEDDING        = re.compile("|".join(re.escape(k) for k in _WEDDING_KEYWORDS),       re.IGNORECASE)
_P_WEDDING_ANCHOR = re.compile("|".join(re.escape(k) for k in _WEDDING_ANCHOR_KEYWORDS), re.IGNORECASE)
_P_EDUCATION      = re.compile("|".join(re.escape(k) for k in _EDUCATION_KEYWORDS),     re.IGNORECASE)

# Qualidade intrínseca das keywords por tipo de evento (0–1).
# Alta: keywords muito específicas (PAMPERS, CERIMONIAL, FACULDADE).
# Baixa: keywords ambíguas que sozinhas não identificam o evento (BUFFET, LEROY MERLIN).
_QUALITY_BABY             = 0.85  # FRALDA/PAMPERS → sinal específico, detecta isolado
_QUALITY_MOVING           = 0.65  # LEROY MERLIN é ambíguo; isolated_hard_gate obrigatório
_QUALITY_WEDDING_ANCHOR   = 0.90  # CERIMONIAL/NOIVAS/FOTOGRAFO: pode detectar isolado
_QUALITY_WEDDING_SOFT     = 0.55  # BUFFET/FESTAS: isolado sempre bloqueado (hard gate)
_QUALITY_EDUCATION        = 0.85  # FACULDADE/UNIVERSIDADE → sinal específico, detecta isolado


class LifeEventsDetector:

    def detect_all(
        self,
        txns_recent: pl.DataFrame,
        txns_history: pl.DataFrame,
        income_recent: float,
        income_historical: float,
        baseline: "PersonalBaseline | None" = None,
    ) -> list[LifeEvent]:
        """
        Args:
            txns_recent:        transações dos últimos 60 dias (janela de detecção).
            txns_history:       transações de 6–18 meses atrás (baseline de ausência).
            income_recent:      renda média mensal recente.
            income_historical:  renda média mensal histórica.
            baseline:           PersonalBaseline do usuário (90–540 dias). Quando fornecido,
                                os gates de gasto são escalados pelo nível de consumo pessoal,
                                tornando os limiares proporcionais à capacidade de gasto real.
        """
        events = []

        baby = self._detect_new_baby(txns_recent, txns_history, baseline)
        if baby:
            events.append(baby)

        moving = self._detect_moving(txns_recent, txns_history, baseline)
        if moving:
            events.append(moving)

        wedding = self._detect_wedding(txns_recent, txns_history, baseline)
        if wedding:
            events.append(wedding)

        education = self._detect_new_education(txns_recent, txns_history, baseline)
        if education:
            events.append(education)

        income_event = self._detect_income_change(income_recent, income_historical)
        if income_event:
            events.append(income_event)

        return events

    @staticmethod
    def _level_ratio(baseline: "PersonalBaseline | None") -> float:
        """
        Razão de escala baseada no nível de consumo mensal do usuário.

        Referência: R$3.000/mês → ratio = 1.0 (thresholds originais).
        Usuário com R$1.500/mês → ratio = 0.5 (gates menores: R$100 em fraldas é relevante).
        Usuário com R$6.000/mês → ratio = 2.0 (gates maiores: precisa mais volume para confirmar).
        Limitado a [0.33, 2.0] para evitar gates triviais ou inacessíveis.
        """
        if baseline is None or not baseline.has_data() or baseline.total_monthly_avg <= 0:
            return 1.0
        return min(max(baseline.total_monthly_avg / 3_000.0, 0.33), 2.0)

    def _detect_new_baby(
        self,
        recent: pl.DataFrame,
        history: pl.DataFrame,
        baseline: "PersonalBaseline | None" = None,
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_BABY
        )

        ratio = self._level_ratio(baseline)
        # Floor 100: 1 embalagem de fraldas já é sinal independente do nível de gasto
        spend_gate    = max(200.0 * ratio, 100.0)
        history_gate  = max(50.0  * ratio, 20.0)

        if recent_spend <= spend_gate or hist_spend >= history_gate:
            return None

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=spend_gate,
            history_baseline=history_gate,
            quality=_QUALITY_BABY,
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        signals = [
            f"baby_spend_recent={brl(recent_spend, 0)}",
            f"baby_spend_historical={brl(hist_spend, 0)}",
            f"txn_count={txn_count}",
            f"merchant_diversity={merchant_count}",
        ] + ev.as_signals()
        if baseline is not None and baseline.has_data():
            signals.append(f"spend_level_ratio={ratio:.2f}")

        return LifeEvent(
            event="new_baby",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_baby_financial_planning",
            supporting_signals=signals,
            missing_signals=missing_signals_from_evidence(ev),
            false_positive_risk=compute_false_positive_risk(ev.composite),
        )

    def _detect_moving(
        self,
        recent: pl.DataFrame,
        history: pl.DataFrame,
        baseline: "PersonalBaseline | None" = None,
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_MOVING
        )

        ratio = self._level_ratio(baseline)
        # Floor 250: mínimo razoável para um evento de mudança (caixas + frete básico)
        spend_gate    = max(500.0 * ratio, 250.0)
        history_gate  = max(100.0 * ratio, 50.0)

        if recent_spend <= spend_gate or hist_spend >= history_gate:
            return None

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=spend_gate,
            history_baseline=history_gate,
            quality=_QUALITY_MOVING,
            isolated_hard_gate=True,  # LEROY MERLIN/MADEIRAMADEIRA sozinhos são ambíguos
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        signals = [
            f"moving_spend={brl(recent_spend, 0)}",
            f"moving_historical={brl(hist_spend, 0)}",
            f"txn_count={txn_count}",
            f"merchant_diversity={merchant_count}",
        ] + ev.as_signals()
        if baseline is not None and baseline.has_data():
            signals.append(f"spend_level_ratio={ratio:.2f}")

        return LifeEvent(
            event="home_change",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_financing_vs_rent_analysis",
            supporting_signals=signals,
            missing_signals=missing_signals_from_evidence(ev),
            false_positive_risk=compute_false_positive_risk(ev.composite),
        )

    def _detect_wedding(
        self,
        recent: pl.DataFrame,
        history: pl.DataFrame,
        baseline: "PersonalBaseline | None" = None,
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_WEDDING
        )

        ratio = self._level_ratio(baseline)
        # Floor 500: sinal mínimo para evento de casamento (entrada de buffet ou cerimonial)
        spend_gate    = max(1_000.0 * ratio, 500.0)
        history_gate  = max(200.0   * ratio, 100.0)

        if recent_spend <= spend_gate or hist_spend >= history_gate:
            return None

        # Keywords âncora (CERIMONIAL, NOIVAS, FOTOGRAFO, ALUGUEL VESTIDO) são altamente
        # específicas e podem detectar isoladas. Keywords soft (BUFFET, FESTAS) exigem
        # corroboração obrigatória — isolated_hard_gate bloqueia sinais sem ao menos 1 ponto.
        anchor_spend, *_ = gather_evidence(recent, history, _P_WEDDING_ANCHOR)
        has_anchor = anchor_spend > 0
        quality = _QUALITY_WEDDING_ANCHOR if has_anchor else _QUALITY_WEDDING_SOFT
        isolated_hard_gate = not has_anchor

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=spend_gate,
            history_baseline=history_gate,
            quality=quality,
            isolated_hard_gate=isolated_hard_gate,
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        signals = [
            f"wedding_spend={brl(recent_spend, 0)}",
            f"wedding_historical={brl(hist_spend, 0)}",
            f"txn_count={txn_count}",
            f"merchant_diversity={merchant_count}",
            f"wedding_anchor={'sim' if has_anchor else 'nao'}",
        ] + ev.as_signals()
        if baseline is not None and baseline.has_data():
            signals.append(f"spend_level_ratio={ratio:.2f}")

        return LifeEvent(
            event="wedding",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_couple_financial_planning",
            supporting_signals=signals,
            missing_signals=missing_signals_from_evidence(ev),
            false_positive_risk=compute_false_positive_risk(ev.composite),
        )

    def _detect_new_education(
        self,
        recent: pl.DataFrame,
        history: pl.DataFrame,
        baseline: "PersonalBaseline | None" = None,
    ) -> LifeEvent | None:
        recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
            recent, history, _P_EDUCATION
        )

        ratio = self._level_ratio(baseline)
        # Floor 150: uma mensalidade básica de EAD ou curso livre
        spend_gate    = max(300.0 * ratio, 150.0)
        history_gate  = max(100.0 * ratio, 50.0)

        if recent_spend <= spend_gate or hist_spend >= history_gate:
            return None

        ev = compute_evidence_score(
            recent_spend, txn_count, merchant_count, months, hist_spend,
            spend_threshold=spend_gate,
            history_baseline=history_gate,
            quality=_QUALITY_EDUCATION,
        )
        if ev.composite < _MIN_EVENT_CONFIDENCE:
            return None

        signals = [
            f"edu_spend_recent={brl(recent_spend, 0)}",
            f"txn_count={txn_count}",
            f"merchant_diversity={merchant_count}",
        ] + ev.as_signals()
        if baseline is not None and baseline.has_data():
            signals.append(f"spend_level_ratio={ratio:.2f}")

        return LifeEvent(
            event="new_education",
            confidence=ev.composite,
            detected_at=date.today(),
            trigger_action="show_student_account_options",
            supporting_signals=signals,
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
