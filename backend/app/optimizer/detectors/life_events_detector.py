"""
LifeEventsDetector — detecta eventos de vida de alta relevância financeira.

Cada detector retorna:
    {
        "event": str,          # identificador do evento
        "confidence": float,   # 0.0–1.0
        "detected_at": date,   # data aproximada do evento
        "trigger_action": str, # ação a ser tomada pelo produto
    }

O detector opera sobre dois DataFrames:
    - txns_recent: transações dos últimos 60 dias (janela de detecção)
    - txns_history: transações de 6–18 meses atrás (baseline para comparação)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date
import polars as pl


@dataclass
class LifeEvent:
    event: str
    confidence: float
    detected_at: date
    trigger_action: str
    supporting_signals: list[str] = field(default_factory=list)


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
_P_BABY     = re.compile("|".join(re.escape(k) for k in _BABY_KEYWORDS),     re.IGNORECASE)
_P_MOVING   = re.compile("|".join(re.escape(k) for k in _MOVING_KEYWORDS),   re.IGNORECASE)
_P_WEDDING  = re.compile("|".join(re.escape(k) for k in _WEDDING_KEYWORDS),  re.IGNORECASE)
_P_EDUCATION = re.compile("|".join(re.escape(k) for k in _EDUCATION_KEYWORDS), re.IGNORECASE)


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

    def _keyword_spend(self, df: pl.DataFrame, pattern: re.Pattern) -> float:
        if df.is_empty() or "description" not in df.columns:
            return 0.0
        filtered = df.filter(
            (pl.col("amount") < 0) &
            pl.col("description").str.to_uppercase().str.contains(pattern.pattern)
        )
        return float(filtered["amount"].sum()) * -1 if not filtered.is_empty() else 0.0

    def _detect_new_baby(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _P_BABY)
        historical_spend = self._keyword_spend(history, _P_BABY)

        if recent_spend > 200 and historical_spend < 50:
            signals = [
                f"baby_spend_recent=R${recent_spend:.0f}",
                f"baby_spend_historical=R${historical_spend:.0f}",
            ]
            confidence = 0.85 if recent_spend > 500 else 0.65
            return LifeEvent(
                event="new_baby",
                confidence=confidence,
                detected_at=date.today(),
                trigger_action="show_baby_financial_planning",
                supporting_signals=signals,
            )
        return None

    def _detect_moving(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _P_MOVING)
        historical_spend = self._keyword_spend(history, _P_MOVING)

        # Requer gasto alto E sem histórico prévio similar.
        # Guard explícito: historical_spend < 100 previne falso positivo quando
        # historical_spend == 0 (sem histórico) — nesse caso "any spend > 0" passaria.
        if recent_spend > 500 and historical_spend < 100:
            return LifeEvent(
                event="home_change",
                confidence=0.70,
                detected_at=date.today(),
                trigger_action="show_financing_vs_rent_analysis",
                supporting_signals=[
                    f"moving_spend=R${recent_spend:.0f}",
                    f"moving_historical=R${historical_spend:.0f}",
                ],
            )
        return None

    def _detect_wedding(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _P_WEDDING)
        historical_spend = self._keyword_spend(history, _P_WEDDING)

        # Exige gasto recente alto E ausência de padrão histórico similar,
        # para distinguir eventos pontuais (um casamento) de gastos regulares em eventos.
        if recent_spend > 1000 and historical_spend < 200:
            confidence = 0.85 if recent_spend > 3000 else 0.75
            return LifeEvent(
                event="wedding",
                confidence=confidence,
                detected_at=date.today(),
                trigger_action="show_couple_financial_planning",
                supporting_signals=[
                    f"wedding_spend=R${recent_spend:.0f}",
                    f"wedding_historical=R${historical_spend:.0f}",
                ],
            )
        return None

    def _detect_new_education(
        self, recent: pl.DataFrame, history: pl.DataFrame
    ) -> LifeEvent | None:
        recent_spend = self._keyword_spend(recent, _P_EDUCATION)
        historical_spend = self._keyword_spend(history, _P_EDUCATION)

        if recent_spend > 300 and historical_spend < 100:
            return LifeEvent(
                event="new_education",
                confidence=0.80,
                detected_at=date.today(),
                trigger_action="show_student_account_options",
                supporting_signals=[f"edu_spend_recent=R${recent_spend:.0f}"],
            )
        return None

    def _detect_income_change(
        self, income_recent: float, income_historical: float
    ) -> LifeEvent | None:
        if income_historical <= 0:
            return None

        change_ratio = (income_recent - income_historical) / income_historical

        if change_ratio > _SALARY_INCREASE_THRESHOLD:
            return LifeEvent(
                event="income_increase",
                confidence=0.80,
                detected_at=date.today(),
                trigger_action="suggest_investment_of_raise",
                supporting_signals=[f"income_change={change_ratio:.1%}"],
            )

        if change_ratio < _SALARY_DROP_THRESHOLD:
            return LifeEvent(
                event="income_drop",
                confidence=0.85,
                detected_at=date.today(),
                trigger_action="activate_defense_mode",
                supporting_signals=[f"income_change={change_ratio:.1%}"],
            )

        return None
