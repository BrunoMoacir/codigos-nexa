"""
EvidenceScore — confiança multi-sinal para detectores de eventos de vida.

Em vez de valores fixos (0.70, 0.85), cada detector coleta evidências brutas
das transações e computa um score composto a partir de cinco dimensões:

    volume      × 0.30  — volume de gasto relativo ao threshold de disparo
    recurrence  × 0.25  — número de transações / meses distintos com sinal
    absence     × 0.20  — ausência do padrão no histórico (novo = mais forte)
    diversity   × 0.15  — merchants distintos corroborando o sinal
    quality     × 0.10  — especificidade intrínseca das keywords do evento

Um único gasto isolado no threshold gera composite ≈ 0.40–0.55.
Três sinais corroborantes (merchants, meses, volume alto) empurram para 0.80+.

Exemplo wedding:
    "BUFFET" isolado (R$1.100):          composite ≈ 0.44
    BUFFET + DECORAÇÃO + FOTÓGRAFO:      composite ≈ 0.80

Uso:
    recent_spend, txn_count, merchant_count, months, hist_spend = gather_evidence(
        recent_df, history_df, _P_WEDDING
    )
    ev = compute_evidence_score(
        recent_spend, txn_count, merchant_count, months, hist_spend,
        spend_threshold=1_000, history_baseline=200, quality=0.72,
    )
    # ev.composite → confiança 0.0–1.0
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class EvidenceScore:
    """Score de confiança multi-sinal para um evento de vida detectado."""

    volume: float       # gasto vs threshold normalizado (0–1)
    recurrence: float   # recorrência de transações / meses (0–1)
    absence: float      # ausência do padrão no histórico (0–1)
    diversity: float    # merchants distintos corroborando (0–1)
    quality: float      # especificidade intrínseca das keywords (0–1, caller-set)
    composite: float    # soma ponderada — usar como confidence (0–1)

    def as_signals(self) -> list[str]:
        """Retorna lista de strings para incluir em supporting_signals."""
        return [
            f"ev_volume={self.volume:.2f}",
            f"ev_recurrence={self.recurrence:.2f}",
            f"ev_absence={self.absence:.2f}",
            f"ev_diversity={self.diversity:.2f}",
        ]


def gather_evidence(
    recent: pl.DataFrame,
    history: pl.DataFrame,
    pattern: re.Pattern,
) -> tuple[float, int, int, int, float]:
    """
    Extrai sinais brutos de um padrão de keyword nos DataFrames de transações.

    Returns:
        (recent_spend, txn_count, merchant_count, months_with_signal, historical_spend)
    """
    recent_spend = 0.0
    txn_count = 0
    merchant_count = 0
    months_with_signal = 0
    historical_spend = 0.0

    if not recent.is_empty() and "description" in recent.columns:
        matched = recent.filter(
            (pl.col("amount") < 0)
            & pl.col("description").str.to_uppercase().str.contains(pattern.pattern)
        )
        if not matched.is_empty():
            recent_spend = float(matched["amount"].sum()) * -1
            txn_count = len(matched)
            # merchant_normalized remove ruído de pagamento (PG*, .COM, TED...) antes
            # de contar merchants distintos — evita contar "PG*SPOTIFY" e "SPOTIFY"
            # como dois merchants. Fallback para description quando ausente.
            merch_col = "merchant_normalized" if "merchant_normalized" in matched.columns else "description"
            merchant_count = matched[merch_col].n_unique()
            if "date" in matched.columns:
                months_with_signal = (
                    matched
                    .with_columns(
                        (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
                    )
                    .select("ym")
                    .unique()
                    .height
                )

    if not history.is_empty() and "description" in history.columns:
        hist_matched = history.filter(
            (pl.col("amount") < 0)
            & pl.col("description").str.to_uppercase().str.contains(pattern.pattern)
        )
        if not hist_matched.is_empty():
            historical_spend = float(hist_matched["amount"].sum()) * -1

    return recent_spend, txn_count, merchant_count, months_with_signal, historical_spend


def compute_evidence_score(
    recent_spend: float,
    txn_count: int,
    merchant_count: int,
    months_with_signal: int,
    historical_spend: float,
    spend_threshold: float,
    history_baseline: float,
    quality: float = 0.75,
) -> EvidenceScore:
    """
    Computa confiança multi-sinal para um evento de vida detectado.

    Args:
        recent_spend:        gasto total matching na janela recente
        txn_count:           número de transações que fizeram match
        merchant_count:      descriptions únicas que fizeram match
        months_with_signal:  meses distintos com pelo menos 1 match
        historical_spend:    gasto total matching na janela histórica
        spend_threshold:     mínimo de gasto para disparar detecção (gate do caller)
        history_baseline:    máximo de histórico considerado "ausente"
        quality:             força intrínseca do conjunto de keywords do evento (0–1)

    Returns:
        EvidenceScore com composite em [0.0, 1.0].
    """
    # Volume: 0.5 no threshold, 1.0 em 2× threshold (motivação: "quase lá" é incerto)
    volume = min(recent_spend / (spend_threshold * 2), 1.0) if spend_threshold > 0 else 0.0

    # Recorrência: múltiplas transações ou meses distintos = padrão intencional
    # 1 txn = 0, 5+ txns = 1.0 | 1 mês = 0, 2+ meses = 1.0
    txn_signal = min((txn_count - 1) / 4, 1.0) if txn_count > 1 else 0.0
    month_signal = min((months_with_signal - 1) / 2, 1.0) if months_with_signal > 1 else 0.0
    recurrence = max(txn_signal, month_signal)

    # Ausência histórica: histórico limpo = evento novo, não comportamento contínuo
    if history_baseline <= 0:
        absence = 1.0
    else:
        absence = max(0.0, 1.0 - historical_spend / history_baseline)

    # Diversidade: merchants distintos corroborando o sinal
    # 1 merchant = 0, 2 = 0.33, 3 = 0.67, 4+ = 1.0
    diversity = min((merchant_count - 1) / 3, 1.0) if merchant_count > 1 else 0.0

    composite = (
        0.30 * volume
        + 0.25 * recurrence
        + 0.20 * absence
        + 0.15 * diversity
        + 0.10 * quality
    )

    return EvidenceScore(
        volume=round(volume, 4),
        recurrence=round(recurrence, 4),
        absence=round(absence, 4),
        diversity=round(diversity, 4),
        quality=round(quality, 4),
        composite=round(min(composite, 1.0), 4),
    )
