"""
app/architect/services/calibration_pipeline.py — Calibração contínua dos modelos da F3

Responsabilidade:
    Recalibrar três eixos do Nexa Architect com base nos feedbacks coletados
    ~6 meses após cada simulação:

    1. Limiares de discretização do RiskScorer (_calibrate_score_thresholds)
       Isotonic Regression em (risk_score, feedback_followed) → encontra os
       thresholds empíricos onde P(seguiu recomendação) cruza 0.5 e 0.75.

    2. Parâmetros do Monte Carlo de consórcio (_calibrate_bid_params)
       Compara P50 real de contemplação com P50 simulado → ajusta bid_mean_initial.

    3. Teto do confidence_score (_calibrate_confidence_threshold)
       Analisa precisão por decil de confidence → rebaixa o teto quando o modelo
       estava superconfiante (recomendações com conf > 0.90 que falharam muito).

Quando rodar:
    Disparado sincronamente em feedback_queries.save_feedback_and_check_trigger()
    quando total ≥ MIN_FEEDBACKS_FOR_TRIGGER AND ≥ MIN_DAYS_BETWEEN dias desde
    a última calibração.  O SELECT FOR UPDATE no CalibrationState garante que
    apenas uma thread por janela dispara a pipeline (sem race condition).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from statistics import mean, median
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.isotonic import IsotonicRegression

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.architect.models_orm import SimulationFeedback

from app.architect.models import CalibrationResult

logger = logging.getLogger(__name__)

# ── Mínimos por sub-sistema ───────────────────────────────────────────────────
MIN_FEEDBACKS_PER_ASSET = 15   # para calibrar limiares por asset_type
MIN_CONSORTIUM_FEEDBACKS = 10  # para calibrar bid_params
MIN_FEEDBACKS_CONFIDENCE = 20  # para calibrar confidence threshold

# ── Limites de segurança ──────────────────────────────────────────────────────
CONSERVATIVE_MIN, CONSERVATIVE_MAX = 0.20, 0.45
AGGRESSIVE_MIN,   AGGRESSIVE_MAX   = 0.55, 0.80
BID_MEAN_MIN,     BID_MEAN_MAX     = 0.15, 0.55
BID_STD_MIN,      BID_STD_MAX      = 0.05, 0.25
CONFIDENCE_MIN = 0.60

# Precisão alvo para o limiar de confidence (rebaixa teto se precision < alvo)
PRECISION_TARGET = 0.75
MIN_BUCKET_SIZE = 5   # guarda decis com poucos dados


class CalibrationPipeline:
    """
    Pipeline de calibração contínua dos modelos da F3.

    Stateless — recebe a Session do banco e trabalha com os dados disponíveis.
    Persiste o novo estado via feedback_queries.save_calibration_state().
    """

    def run(self, db: "Session") -> CalibrationResult:
        """
        Executa os três sub-sistemas de calibração e persiste o novo estado.

        Cada sub-sistema verifica independentemente se há dados suficientes.
        Retorna CalibrationResult descrevendo honestamente o que foi ou não
        calibrado, incluindo motivos quando os dados são insuficientes.
        """
        from app.architect.feedback_queries import (
            get_feedbacks_for_calibration,
            get_consortium_feedbacks_with_p50,
            load_calibration_state,
            save_calibration_state,
        )

        feedbacks: List["SimulationFeedback"] = get_feedbacks_for_calibration(db)
        current_state = load_calibration_state() or {}

        changes: List[str] = []
        updates: Dict[str, Any] = {}
        thresholds_updated = bid_params_updated = confidence_updated = False

        # ── 1. Limiares do RiskScorer ─────────────────────────────────────────
        per_asset = _group_by_asset(feedbacks)
        threshold_update, threshold_changes = self._calibrate_score_thresholds(
            per_asset, current_state
        )
        changes.extend(threshold_changes)
        if threshold_update:
            updates.update(threshold_update)
            thresholds_updated = True

        # ── 2. Parâmetros do Monte Carlo de consórcio ─────────────────────────
        consortium_rows = get_consortium_feedbacks_with_p50(db)
        bid_update, bid_changes = self._calibrate_bid_params(
            consortium_rows, current_state
        )
        changes.extend(bid_changes)
        if bid_update:
            updates["bid_params"] = bid_update
            bid_params_updated = True

        # ── 3. Teto do confidence_score ───────────────────────────────────────
        conf_update, conf_changes = self._calibrate_confidence_threshold(
            feedbacks, current_state
        )
        changes.extend(conf_changes)
        if conf_update is not None:
            updates["confidence_threshold_upper"] = conf_update
            confidence_updated = True

        # ── Persiste se houve alguma mudança ──────────────────────────────────
        if updates:
            updates["n_feedbacks_used"] = len(feedbacks)
            save_calibration_state(updates)
            logger.info(
                "CalibrationPipeline | calibração concluída com %d feedbacks — %s",
                len(feedbacks),
                changes,
            )

        return CalibrationResult(
            thresholds_updated=thresholds_updated,
            bid_params_updated=bid_params_updated,
            confidence_threshold_updated=confidence_updated,
            n_feedbacks_used=len(feedbacks),
            changes=changes,
        )

    # ─── Sub-sistema 1: limiares de discretização ─────────────────────────────

    def _calibrate_score_thresholds(
        self,
        per_asset: Dict[str, List["SimulationFeedback"]],
        current_state: Dict[str, Any],
    ) -> Tuple[Optional[Dict], List[str]]:
        """
        Usa IsotonicRegression para encontrar empiricamente os limiares onde
        P(seguiu recomendação | risk_score) = 0.5 (conservador) e 0.75 (agressivo).

        Retorna (updates_dict_or_None, lista_de_mudanças).
        """
        updates: Dict[str, float] = {}
        changes: List[str] = []

        current_cons = current_state.get("threshold_conservative", 0.35)
        current_agg  = current_state.get("threshold_aggressive", 0.65)

        # Agrega feedbacks de todos os asset_types com dados suficientes
        # para estimar os limiares globais (mais robusto que por asset_type)
        eligible = [
            fb for asset_fbs in per_asset.values()
            if len(asset_fbs) >= MIN_FEEDBACKS_PER_ASSET
            for fb in asset_fbs
            if fb.risk_score_at_simulation is not None
        ]

        if len(eligible) < MIN_FEEDBACKS_PER_ASSET:
            max_per_asset = max((len(v) for v in per_asset.values()), default=0)
            changes.append(
                f"Dados insuficientes para calibrar limiares "
                f"(mínimo {MIN_FEEDBACKS_PER_ASSET} por tipo, maior atual: {max_per_asset})"
            )
            return None, changes

        X = np.array([fb.risk_score_at_simulation for fb in eligible])
        y = np.array([1.0 if fb.feedback_followed else 0.0 for fb in eligible])

        iso = IsotonicRegression(out_of_bounds="clip").fit(X, y)

        candidates = np.linspace(0.05, 0.95, 500)
        p_follow = iso.predict(candidates)

        # threshold_conservative: menor score onde P(follow) ≥ 0.5
        mask_cons = p_follow >= 0.50
        new_cons = float(np.clip(
            candidates[mask_cons][0] if mask_cons.any() else current_cons,
            CONSERVATIVE_MIN, CONSERVATIVE_MAX,
        ))

        # threshold_aggressive: menor score onde P(follow) ≥ 0.75
        mask_agg = p_follow >= 0.75
        new_agg = float(np.clip(
            candidates[mask_agg][0] if mask_agg.any() else current_agg,
            AGGRESSIVE_MIN, AGGRESSIVE_MAX,
        ))

        # Garante que conservative < aggressive com margem mínima de 0.10
        if new_agg <= new_cons + 0.10:
            new_agg = min(new_cons + 0.15, AGGRESSIVE_MAX)

        delta_cons = abs(new_cons - current_cons)
        delta_agg  = abs(new_agg  - current_agg)

        if delta_cons > 0.005:
            updates["threshold_conservative"] = round(new_cons, 4)
            changes.append(
                f"threshold_conservative: {current_cons:.3f} → {new_cons:.3f} "
                f"(Δ={new_cons - current_cons:+.3f}, n={len(eligible)})"
            )
        if delta_agg > 0.005:
            updates["threshold_aggressive"] = round(new_agg, 4)
            changes.append(
                f"threshold_aggressive: {current_agg:.3f} → {new_agg:.3f} "
                f"(Δ={new_agg - current_agg:+.3f}, n={len(eligible)})"
            )

        if not updates:
            changes.append(
                f"Limiares estáveis (Δ < 0.005, n={len(eligible)})"
            )
            return None, changes

        return updates, changes

    # ─── Sub-sistema 2: parâmetros do MC de consórcio ─────────────────────────

    def _calibrate_bid_params(
        self,
        consortium_rows: List[Dict[str, Any]],
        current_state: Dict[str, Any],
    ) -> Tuple[Optional[Dict], List[str]]:
        """
        Ajusta bid_mean_initial comparando P50 real vs P50 simulado.

        Se contemplações reais demoram mais que o simulado, os bids projetados
        estão otimistas → reduz bid_mean_initial.
        Se contemplações reais são mais rápidas → aumenta bid_mean_initial.
        """
        changes: List[str] = []

        valid = [
            r for r in consortium_rows
            if r.get("simulated_p50") is not None
            and r["feedback"].actual_contemplation_month is not None
        ]

        if len(valid) < MIN_CONSORTIUM_FEEDBACKS:
            changes.append(
                f"Dados insuficientes para calibrar MC de consórcio "
                f"(mínimo {MIN_CONSORTIUM_FEEDBACKS}, atual: {len(valid)})"
            )
            return None, changes

        real_p50 = median(r["feedback"].actual_contemplation_month for r in valid)
        sim_p50  = median(r["simulated_p50"] for r in valid)

        if sim_p50 <= 0:
            changes.append("sim_p50 inválido — calibração de consórcio ignorada")
            return None, changes

        erro_relativo = (real_p50 - sim_p50) / sim_p50
        # Clamp conservador: ajusta no máximo ±5% do valor atual por rodada
        delta = float(np.clip(erro_relativo * 0.05, -0.05, 0.05))

        current_bid_params = current_state.get("bid_params", {})
        # Aplica ajuste global (sem distinção por asset_type — dados insuficientes)
        current_bid_mean = current_bid_params.get("global", {}).get("bid_mean_initial", 0.35)
        current_bid_std  = current_bid_params.get("global", {}).get("bid_std",          0.12)

        new_bid_mean = float(np.clip(current_bid_mean - delta, BID_MEAN_MIN, BID_MEAN_MAX))
        new_bid_std  = float(np.clip(current_bid_std,          BID_STD_MIN,  BID_STD_MAX))

        if abs(new_bid_mean - current_bid_mean) < 0.001:
            changes.append(
                f"bid_mean_initial estável (real_p50={real_p50:.0f}m, "
                f"sim_p50={sim_p50:.0f}m, Δ<0.001)"
            )
            return None, changes

        new_params = dict(current_bid_params)
        new_params["global"] = {
            "bid_mean_initial": round(new_bid_mean, 4),
            "bid_std":          round(new_bid_std,  4),
        }

        changes.append(
            f"bid_mean_initial: {current_bid_mean:.4f} → {new_bid_mean:.4f} "
            f"(real_p50={real_p50:.0f}m, sim_p50={sim_p50:.0f}m, "
            f"erro_rel={erro_relativo:+.1%}, n={len(valid)})"
        )
        return new_params, changes

    # ─── Sub-sistema 3: teto do confidence_score ──────────────────────────────

    def _calibrate_confidence_threshold(
        self,
        feedbacks: List["SimulationFeedback"],
        current_state: Dict[str, Any],
    ) -> Tuple[Optional[float], List[str]]:
        """
        Analisa a precisão real por decil de confidence_score.

        Se recomendações com confidence > teto_atual erraram frequentemente,
        rebaixa o teto para o limite superior do último decil com
        precision ≥ PRECISION_TARGET (ponto acima do qual o modelo se torna
        superconfiante). O teto nunca sobe acima de 1.0 nem cai abaixo de
        CONFIDENCE_MIN.
        """
        changes: List[str] = []
        current_teto = current_state.get("confidence_threshold_upper", 1.0)

        eligible = [
            fb for fb in feedbacks
            if fb.confidence_score_at_simulation is not None
        ]

        if len(eligible) < MIN_FEEDBACKS_CONFIDENCE:
            changes.append(
                f"Dados insuficientes para calibrar confidence threshold "
                f"(mínimo {MIN_FEEDBACKS_CONFIDENCE}, atual: {len(eligible)})"
            )
            return None, changes

        bins = np.linspace(0, 1, 11)  # 10 decis
        bucket_stats: List[Tuple[float, float, int]] = []  # (low, precision, n)

        for lo, hi in zip(bins, bins[1:]):
            bucket = [
                fb for fb in eligible
                if lo <= fb.confidence_score_at_simulation < hi
            ]
            if len(bucket) < MIN_BUCKET_SIZE:
                continue
            prec = mean(1.0 if fb.feedback_followed else 0.0 for fb in bucket)
            bucket_stats.append((lo, prec, len(bucket)))

        if not bucket_stats:
            changes.append("Nenhum decil com amostras suficientes para calibrar confidence")
            return None, changes

        # Limite superior do último bucket com precision ≥ PRECISION_TARGET.
        # Iterando em ordem decrescente encontramos o ponto acima do qual
        # a precisão cai — é aí que o modelo se torna superconfiante.
        c_star: Optional[float] = None
        for lo, prec, _ in reversed(bucket_stats):
            if prec >= PRECISION_TARGET:
                c_star = round(lo + 0.1, 2)
                break

        if c_star is None:
            changes.append(
                f"Nenhum decil atinge precision ≥ {PRECISION_TARGET:.0%} "
                f"— confidence threshold mantido em {current_teto:.2f}"
            )
            return None, changes

        new_teto = float(np.clip(c_star, CONFIDENCE_MIN, 1.0))

        if abs(new_teto - current_teto) < 0.01:
            changes.append(
                f"confidence threshold estável ({current_teto:.2f}, Δ<0.01)"
            )
            return None, changes

        changes.append(
            f"confidence_threshold_upper: {current_teto:.2f} → {new_teto:.2f} "
            f"(c*={c_star:.2f}, n={len(eligible)})"
        )
        return new_teto, changes


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _group_by_asset(
    feedbacks: List["SimulationFeedback"],
) -> Dict[str, List["SimulationFeedback"]]:
    groups: Dict[str, List] = defaultdict(list)
    for fb in feedbacks:
        groups[fb.asset_type].append(fb)
    return dict(groups)
