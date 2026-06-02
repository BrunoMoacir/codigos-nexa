"""
app/etl/subscription_detector.py - Detecção de Assinaturas Esquecidas (M1.5)

RESPONSABILIDADE:
    Identifica assinaturas recorrentes no histórico de transações do usuário
    (streaming, apps, academias, etc.) e sinaliza aquelas que podem estar
    sendo pagas sem uso ou com custo desnecessariamente alto.

LÓGICA DE DETECÇÃO:
    1. RECURRING DETECTION: mesma descrição (normalizada), mesmo valor (±5%),
       ocorrendo em datas do mês similares (±5 dias) — recorrência mensal.
    2. HEURÍSTICAS DE "POSSIVELMENTE ESQUECIDA":
       DUPLICATE_CATEGORY  — múltiplos serviços na mesma sub-categoria de streaming
                             (ex: Netflix + Disney+ + Globoplay → 3 serviços)
       LOW_VALUE           — assinatura < R$ 15/mês — fácil de esquecer
       PRICE_INCREASE      — valor atual > primeira cobrança × 1.10 (+10%)

SAÍDA:
    SubscriptionReport com lista de Subscription e AlertedSubscription.
    Cada alertada traz reason legível para o usuário / LLM.

INTEGRAÇÃO:
    - Chamado via GET /api/v1/subscriptions/{user_id}
    - Agente usa na strategy_text: "Você tem 3 streamings somando R$ 104/mês..."
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

import polars as pl

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Tolerância de valor para considerar a mesma assinatura mesmo com reajuste pequeno
_VALUE_TOLERANCE_PCT: float = 0.05          # ±5%

# Janela de dias do mês para considerar "mesma data mensal"
_DAY_OF_MONTH_WINDOW: int = 5

# Mínimo de recorrências para considerar como assinatura confirmada
_MIN_OCCURRENCES: int = 2

# Valor máximo para "low value" flag (R$ — fácil de esquecer)
_LOW_VALUE_THRESHOLD: float = 15.0

# Aumento de preço mínimo para flag de "price increase"
_PRICE_INCREASE_FACTOR: float = 1.10       # +10%

# Mínimo de serviços na mesma categoria para flag "duplicate category"
_MAX_SAME_CATEGORY: int = 2                # alerta quando > 2 = 3+

# Keywords que mapeiam descrições para categorias de assinatura
_STREAMING_VIDEO_KEYWORDS = {
    "netflix", "disney", "hbo", "max", "amazon prime", "primevideo",
    "globoplay", "telecine", "paramount", "apple tv", "mubi", "lionsgate",
    "star+", "star plus", "discovery+", "discovery plus", "now",
}
_STREAMING_MUSIC_KEYWORDS = {
    "spotify", "deezer", "apple music", "tidal", "youtube music", "youtube premium",
    "amazon music",
}
_STREAMING_GAMING_KEYWORDS = {
    "xbox game pass", "playstation plus", "psn", "nintendo switch online",
    "ea play", "geforce now",
}
_FITNESS_KEYWORDS = {
    "academia", "smartfit", "bluefit", "treino livre", "bodytech",
    "crossfit", "total pass",
}
_PRODUCTIVITY_KEYWORDS = {
    "adobe", "microsoft 365", "office365", "canva", "notion", "dropbox",
    "google one", "icloud", "slack", "zoom", "github",
}
_NEWS_KEYWORDS = {
    "folha", "estadao", "globo.com", "uol", "the economist", "nyt", "new york times",
    "financial times", "bbc",
}
_CATEGORY_MAP: dict[str, frozenset[str]] = {
    "streaming_video":  frozenset(_STREAMING_VIDEO_KEYWORDS),
    "streaming_music":  frozenset(_STREAMING_MUSIC_KEYWORDS),
    "streaming_gaming": frozenset(_STREAMING_GAMING_KEYWORDS),
    "fitness":          frozenset(_FITNESS_KEYWORDS),
    "productivity":     frozenset(_PRODUCTIVITY_KEYWORDS),
    "news":             frozenset(_NEWS_KEYWORDS),
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIPOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AlertReason(str, Enum):
    DUPLICATE_CATEGORY = "DUPLICATE_CATEGORY"   # 3+ serviços na mesma categoria
    LOW_VALUE          = "LOW_VALUE"             # < R$15 — fácil de esquecer
    PRICE_INCREASE     = "PRICE_INCREASE"        # aumento de preço > 10%


@dataclass
class Subscription:
    """Uma assinatura recorrente detectada."""
    merchant: str               # nome normalizado
    monthly_amount: float       # último valor cobrado
    first_seen: date
    last_seen: date
    occurrences: int            # quantas vezes apareceu no histórico
    subscription_category: Optional[str]  # "streaming_video", "fitness", etc. (None = desconhecida)
    first_amount: float         # valor na primeira cobrança (para detectar reajuste)

    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant,
            "monthly_amount": round(self.monthly_amount, 2),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "occurrences": self.occurrences,
            "subscription_category": self.subscription_category,
            "first_amount": round(self.first_amount, 2),
        }


@dataclass
class AlertedSubscription:
    """Assinatura com uma ou mais flags de atenção."""
    subscription: Subscription
    alerts: list[AlertReason]
    alert_messages: list[str]   # textos legíveis para o usuário

    def to_dict(self) -> dict:
        return {
            **self.subscription.to_dict(),
            "alerts": [a.value for a in self.alerts],
            "alert_messages": self.alert_messages,
        }


@dataclass
class SubscriptionReport:
    """Relatório completo de assinaturas do usuário."""
    user_id: str
    total_subscriptions: int
    total_monthly_cost: float       # soma de todas as mensalidades detectadas
    alerted_count: int
    subscriptions: list[Subscription] = field(default_factory=list)
    alerted: list[AlertedSubscription] = field(default_factory=list)
    summary_text: str = ""

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "total_subscriptions": self.total_subscriptions,
            "total_monthly_cost": round(self.total_monthly_cost, 2),
            "alerted_count": self.alerted_count,
            "summary_text": self.summary_text,
            "subscriptions": [s.to_dict() for s in self.subscriptions],
            "alerted": [a.to_dict() for a in self.alerted],
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DETECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SubscriptionDetector:
    """
    Detecta e analisa assinaturas recorrentes nas transações do usuário.

    Example:
        >>> detector = SubscriptionDetector()
        >>> report = detector.detect(transactions_df=df, user_id="user_123")
        >>> print(report.summary_text)
        "Encontrei 6 assinaturas ativas totalizando R$ 213/mês. ..."
    """

    def detect(
        self,
        transactions_df: pl.DataFrame,
        user_id: str = "",
    ) -> SubscriptionReport:
        """
        Detecta assinaturas recorrentes e gera alertas.

        Args:
            transactions_df: DataFrame com colunas: date, amount, description
                             (e opcionalmente category). amount deve ser negativo
                             para despesas (como no schema da F1).
            user_id: ID do usuário (usado no relatório).

        Returns:
            SubscriptionReport com todas as assinaturas e alertas.
        """
        if transactions_df.is_empty():
            return SubscriptionReport(
                user_id=user_id, total_subscriptions=0,
                total_monthly_cost=0.0, alerted_count=0,
                summary_text="Nenhuma transação disponível.",
            )

        expenses = self._prepare_expenses(transactions_df)
        if expenses.is_empty():
            return SubscriptionReport(
                user_id=user_id, total_subscriptions=0,
                total_monthly_cost=0.0, alerted_count=0,
                summary_text="Nenhuma despesa encontrada.",
            )

        # 1. Detectar candidatos recorrentes
        subscriptions = self._detect_recurring(expenses)

        if not subscriptions:
            return SubscriptionReport(
                user_id=user_id, total_subscriptions=0,
                total_monthly_cost=0.0, alerted_count=0,
                summary_text="Nenhuma assinatura recorrente detectada.",
            )

        # 2. Aplicar heurísticas
        alerted = self._apply_heuristics(subscriptions)

        total_cost = sum(s.monthly_amount for s in subscriptions)
        summary = self._build_summary(subscriptions, alerted, total_cost)

        logger.info(
            f"SubscriptionDetector [{user_id}]: {len(subscriptions)} assinaturas "
            f"(R$ {total_cost:.0f}/mês), {len(alerted)} alertadas"
        )

        return SubscriptionReport(
            user_id=user_id,
            total_subscriptions=len(subscriptions),
            total_monthly_cost=total_cost,
            alerted_count=len(alerted),
            subscriptions=subscriptions,
            alerted=alerted,
            summary_text=summary,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DETECÇÃO DE RECORRÊNCIA
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_expenses(self, df: pl.DataFrame) -> pl.DataFrame:
        """Filtra despesas, normaliza descrição e extrai dia do mês."""
        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return expenses

        # merchant_id colapsa aliases ("PG*NETFLIX", "NETFLIX.COM" → "netflix")
        # antes de detectar recorrência — sem isso cada variante gera assinatura separada.
        # Underscores → espaços para que keyword classification e .title() funcionem:
        # "amazon_prime" → "amazon prime" → "Amazon Prime".
        if "merchant_id" in expenses.columns:
            desc_expr: pl.Expr = pl.col("merchant_id").str.replace_all("_", " ")
            if "description" in expenses.columns:
                desc_expr = desc_expr.fill_null(
                    pl.col("description").str.to_lowercase().str.strip_chars()
                )
        else:
            desc_expr = (
                pl.col("description")
                .str.to_lowercase()
                .str.strip_chars()
                .str.replace_all(r"\s+", " ", literal=False)
            )

        return (
            expenses
            .with_columns([
                pl.col("amount").abs().alias("amount"),
                desc_expr.alias("desc_norm"),
                pl.col("date").cast(pl.Date).alias("date"),
            ])
            .with_columns(
                pl.col("date").dt.day().alias("day_of_month")
            )
            .drop_nulls(subset=["desc_norm", "amount"])
            .filter(pl.col("amount") > 0)
        )

    def _detect_recurring(self, df: pl.DataFrame) -> list[Subscription]:
        """
        Agrupa transações por descrição normalizada e identifica recorrência mensal.

        Critérios de recorrência:
        - ≥ _MIN_OCCURRENCES transações com a mesma descrição normalizada
        - Valor estável (coeficiente de variação ≤ 10%)
        - Distribuição por meses distintos (não apenas muitas compras no mesmo dia)
        """
        rows = df.to_dicts()
        # Agrupa por descrição normalizada
        groups: dict[str, list[dict]] = {}
        for row in rows:
            key = row["desc_norm"]
            groups.setdefault(key, []).append(row)

        subscriptions: list[Subscription] = []
        for desc, group in groups.items():
            if len(group) < _MIN_OCCURRENCES:
                continue

            amounts = [r["amount"] for r in group]
            avg_amount = sum(amounts) / len(amounts)
            # Coeficiente de variação — muito variado não é assinatura
            if avg_amount > 0:
                cv = (max(amounts) - min(amounts)) / avg_amount
                if cv > 0.40:  # tolerância de 40%: permite reajustes de até ~40% sem descartar
                    continue

            # Deve ter ocorrido em pelo menos 2 meses distintos
            dates = [r["date"] for r in group]
            months = {(d.year, d.month) for d in dates}
            if len(months) < _MIN_OCCURRENCES:
                continue

            sorted_group = sorted(group, key=lambda r: r["date"])
            category = self._classify_category(desc)

            subscriptions.append(Subscription(
                merchant=desc,
                monthly_amount=sorted_group[-1]["amount"],   # valor mais recente
                first_seen=sorted_group[0]["date"],
                last_seen=sorted_group[-1]["date"],
                occurrences=len(group),
                subscription_category=category,
                first_amount=sorted_group[0]["amount"],
            ))

        # Ordenar por custo mensal decrescente
        subscriptions.sort(key=lambda s: s.monthly_amount, reverse=True)
        return subscriptions

    # ─────────────────────────────────────────────────────────────────────────
    # CLASSIFICAÇÃO DE CATEGORIA
    # ─────────────────────────────────────────────────────────────────────────

    def _classify_category(self, desc_norm: str) -> Optional[str]:
        """Classifica a descrição em uma categoria de assinatura usando keyword matching."""
        for category, keywords in _CATEGORY_MAP.items():
            for kw in keywords:
                if kw in desc_norm:
                    return category
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # HEURÍSTICAS DE ALERTA
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_heuristics(
        self,
        subscriptions: list[Subscription],
    ) -> list[AlertedSubscription]:
        """Aplica as 3 heurísticas do spec M1.5 e retorna assinaturas alertadas."""
        # Agrupar por categoria para heurística DUPLICATE_CATEGORY
        by_category: dict[str, list[Subscription]] = {}
        for sub in subscriptions:
            if sub.subscription_category:
                by_category.setdefault(sub.subscription_category, []).append(sub)

        alerted: list[AlertedSubscription] = []

        for sub in subscriptions:
            alerts: list[AlertReason] = []
            messages: list[str] = []

            # Heurística 1: DUPLICATE_CATEGORY — 3+ serviços na mesma categoria
            if (
                sub.subscription_category
                and len(by_category.get(sub.subscription_category, [])) > _MAX_SAME_CATEGORY
            ):
                count = len(by_category[sub.subscription_category])
                cat_label = sub.subscription_category.replace("_", " ")
                total_cat = sum(s.monthly_amount for s in by_category[sub.subscription_category])
                alerts.append(AlertReason.DUPLICATE_CATEGORY)
                messages.append(
                    f"Você tem {count} serviços de {cat_label} — "
                    f"R$ {total_cat:.0f}/mês no total. Vale revisar quais usa."
                )

            # Heurística 2: LOW_VALUE — < R$15, fácil de esquecer
            if sub.monthly_amount < _LOW_VALUE_THRESHOLD:
                alerts.append(AlertReason.LOW_VALUE)
                messages.append(
                    f"{sub.merchant.title()}: R$ {sub.monthly_amount:.2f}/mês "
                    f"— valor pequeno, fácil de esquecer. Ainda usa?"
                )

            # Heurística 3: PRICE_INCREASE — reajuste > 10%
            if (
                sub.first_amount > 0
                and sub.monthly_amount > sub.first_amount * _PRICE_INCREASE_FACTOR
            ):
                pct = (sub.monthly_amount / sub.first_amount - 1) * 100
                alerts.append(AlertReason.PRICE_INCREASE)
                messages.append(
                    f"{sub.merchant.title()} aumentou de R$ {sub.first_amount:.2f} "
                    f"para R$ {sub.monthly_amount:.2f} (+{pct:.0f}%). "
                    f"Ainda vale a pena manter?"
                )

            if alerts:
                alerted.append(AlertedSubscription(
                    subscription=sub,
                    alerts=alerts,
                    alert_messages=messages,
                ))

        return alerted

    # ─────────────────────────────────────────────────────────────────────────
    # TEXTO DE RESUMO
    # ─────────────────────────────────────────────────────────────────────────

    def _build_summary(
        self,
        subscriptions: list[Subscription],
        alerted: list[AlertedSubscription],
        total_cost: float,
    ) -> str:
        """Gera texto de resumo em português natural para exibição ao usuário / LLM."""
        parts: list[str] = []

        parts.append(
            f"Encontrei {len(subscriptions)} assinaturas ativas "
            f"totalizando R$ {total_cost:.0f}/mês."
        )

        if alerted:
            parts.append(f"{len(alerted)} merecem sua atenção:")
            for a in alerted[:3]:  # máx 3 no resumo
                parts.append(f"• {a.alert_messages[0]}")

        # Destaques de categoria
        from collections import Counter
        cat_counts = Counter(
            s.subscription_category for s in subscriptions if s.subscription_category
        )
        top_cats = [(cat, cnt) for cat, cnt in cat_counts.most_common(3) if cnt >= 2]
        if top_cats:
            cat_text = "; ".join(
                f"{cnt} de {cat.replace('_', ' ')}"
                for cat, cnt in top_cats
            )
            parts.append(f"Destaques por categoria: {cat_text}.")

        return " ".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÃO DE CONVENIÊNCIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_subscriptions(
    transactions_df: pl.DataFrame,
    user_id: str = "",
) -> SubscriptionReport:
    """Wrapper de conveniência para SubscriptionDetector.detect()."""
    return SubscriptionDetector().detect(transactions_df=transactions_df, user_id=user_id)


__all__ = [
    "SubscriptionDetector",
    "SubscriptionReport",
    "Subscription",
    "AlertedSubscription",
    "AlertReason",
    "detect_subscriptions",
]
