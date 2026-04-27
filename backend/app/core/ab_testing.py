# app/core/ab_testing.py
# Framework de A/B Testing determinístico — T3.5

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ABVariant(str, Enum):
    CONTROL = "control"
    TREATMENT = "treatment"


@dataclass(frozen=True)
class Experiment:
    name: str
    description: str
    traffic_pct: float = 0.50  # fração de usuários no TREATMENT


# Registro central de experimentos ativos.
# Adicionar novos experimentos aqui antes de ativá-los no código.
EXPERIMENTS: dict[str, Experiment] = {
    "ranker_v2_hyperpersonalized": Experiment(
        name="ranker_v2_hyperpersonalized",
        description=(
            "CONTROL: ranker clássico (net_gain + eligibility). "
            "TREATMENT: ranker hiperpersonalizado 4 pesos W1-W4 (T2.4)."
        ),
        traffic_pct=0.50,
    ),
    "cluster_tone_personalization": Experiment(
        name="cluster_tone_personalization",
        description=(
            "CONTROL: texto de insight genérico. "
            "TREATMENT: texto personalizado por cluster de estilo de vida (T2.6)."
        ),
        traffic_pct=0.50,
    ),
    "life_events_nudge": Experiment(
        name="life_events_nudge",
        description=(
            "Experimento graduado: 100% TREATMENT (feature ativa para todos os usuários). "
            "Notificações e forecast já integram LifeEvents independentemente do optimizer. "
            "Gate mantido para retrocompatibilidade — pode ser removido no próximo cleanup."
        ),
        traffic_pct=1.0,
    ),
}


def get_variant(user_id: str, experiment_name: str) -> ABVariant:
    """
    Retorna a variante A/B para um usuário num experimento.

    Determinístico: mesmo user_id + experiment_name → sempre a mesma variante.
    Usa MD5 apenas como função de hash (não criptográfico) para bucketing uniforme.

    Raises:
        ValueError: se experiment_name não está em EXPERIMENTS.
    """
    exp = EXPERIMENTS.get(experiment_name)
    if exp is None:
        raise ValueError(
            f"Experimento '{experiment_name}' não registrado. "
            f"Experimentos disponíveis: {list(EXPERIMENTS)}"
        )

    hash_input = f"{user_id}:{experiment_name}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    normalized = (hash_value % 10_000) / 10_000.0
    return ABVariant.TREATMENT if normalized < exp.traffic_pct else ABVariant.CONTROL


def log_exposure(user_id: str, experiment_name: str, variant: ABVariant) -> None:
    """
    Registra a exposição do usuário a um experimento.

    Formato estruturado para facilitar parsing por ferramentas de analytics
    (ex: grep "AB_EXPOSURE" nos logs → pivot por experiment + variant).
    """
    logger.info(
        "AB_EXPOSURE user_id=%s experiment=%s variant=%s",
        user_id,
        experiment_name,
        variant.value,
    )
