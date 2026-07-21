"""
app/optimizer/detectors/ml_lifestyle_classifier.py — Inferência do modelo ML
de clusters de estilo de vida (Fase 3).

Carrega models/lifestyle_classifier.pkl (RandomForest destilado das regras —
ver scripts/train_lifestyle_classifier.py) e devolve o MESMO contrato do
classificador de regras, com probabilidades calibradas como cluster_scores:

    {
      "lifestyle_cluster": "URBANO_FOODIE",
      "secondary_clusters": ["DIGITAL_NATIVO"],
      "cluster_scores": {...},            # predict_proba por cluster
      "classification_source": "ml",
      "ml_confidence": 0.87,              # probabilidade do primário
    }

Decisão primário/secundários usa OS MESMOS thresholds das regras (0.35 /
0.30 / máx 2) — trocar o motor não muda a semântica do produto.

Segurança de versão: o pkl grava features_version; se divergir do
lifestyle_features.FEATURES_VERSION em runtime, o modelo é ignorado
(fallback regras) — nunca inferir com vetor incompatível.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

from app.optimizer.detectors.lifestyle_features import (
    FEATURES_VERSION,
    extract_features,
)
from app.optimizer.profiler import UserProfile

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "lifestyle_classifier.pkl"

_PRIMARY_THRESHOLD = 0.35
_SECONDARY_THRESHOLD = 0.30
_MAX_SECONDARY = 2
_UNCLASSIFIED = "NAO_CLASSIFICADO"


class MLLifestyleClassifier:
    """Carrega o modelo uma única vez por processo (singleton via shared())."""

    _shared_instance: "MLLifestyleClassifier | None" = None

    def __init__(self, model_path: Path | None = None):
        self._path = model_path or MODEL_PATH
        self._model = None
        self._classes: list[str] = []
        self._load()

    @classmethod
    def shared(cls) -> "MLLifestyleClassifier":
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    def _load(self) -> None:
        try:
            if not self._path.exists():
                logger.info("[MLLifestyle] modelo ausente (%s) — usando regras", self._path)
                return
            import gzip

            with open(self._path, "rb") as raw:
                magic = raw.read(2)
            opener = gzip.open if magic == b"\x1f\x8b" else open
            with opener(self._path, "rb") as f:
                bundle = pickle.load(f)
            if bundle.get("features_version") != FEATURES_VERSION:
                logger.warning(
                    "[MLLifestyle] versão de features do modelo (%s) difere do runtime (%s) "
                    "— modelo ignorado; re-treine com scripts/train_lifestyle_classifier.py",
                    bundle.get("features_version"), FEATURES_VERSION,
                )
                return
            self._model = bundle["model"]
            self._classes = list(bundle["classes"])
            logger.info(
                "[MLLifestyle] modelo carregado (%d classes, features v%s)",
                len(self._classes), FEATURES_VERSION,
            )
        except Exception as exc:
            logger.error("[MLLifestyle] falha ao carregar modelo: %s — usando regras", exc)
            self._model = None

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def classify(self, profile: UserProfile) -> dict | None:
        """
        Classificação HÍBRIDA. None em qualquer falha (caller usa regras).

        - PRIMÁRIO: argmax das probabilidades do modelo (fronteiras suaves,
          confiança calibrada);
        - SECUNDÁRIOS e cluster_scores: afinidades independentes das REGRAS —
          probabilidades somam 1 entre 8 classes, então o threshold de
          secundários (0.30, definido para scores independentes) quase nunca
          dispararia sobre probas; as afinidades preservam a semântica que os
          consumidores (notificações, agente, optimizer) já conhecem.
        """
        if self._model is None:
            return None
        try:
            probas = self._model.predict_proba([extract_features(profile)])[0]
        except Exception as exc:
            logger.warning("[MLLifestyle] inferência falhou: %s", exc)
            return None

        ml_probs = {cls: float(p) for cls, p in zip(self._classes, probas)}
        candidates = {c: s for c, s in ml_probs.items() if c != _UNCLASSIFIED}
        primary = max(candidates, key=candidates.get) if candidates else _UNCLASSIFIED
        confidence = candidates.get(primary, 0.0)
        if confidence < _PRIMARY_THRESHOLD:
            primary = _UNCLASSIFIED

        # Afinidades independentes das regras (mesma escala 0–1 de sempre)
        from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier

        rule_scores = LifestyleClassifier().classify_rules(profile)["cluster_scores"]
        secondary = sorted(
            [
                c for c, s in rule_scores.items()
                if c != primary and c != _UNCLASSIFIED and s >= _SECONDARY_THRESHOLD
            ],
            key=lambda c: rule_scores[c],
            reverse=True,
        )[:_MAX_SECONDARY]

        return {
            "lifestyle_cluster": primary,
            "secondary_clusters": secondary,
            "cluster_scores": rule_scores,
            "ml_probabilities": {k: round(v, 3) for k, v in ml_probs.items()},
            "classification_source": "ml",
            "ml_confidence": round(confidence, 3),
        }


__all__ = ["MLLifestyleClassifier", "MODEL_PATH"]
