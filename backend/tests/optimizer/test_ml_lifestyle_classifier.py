# tests/optimizer/test_ml_lifestyle_classifier.py
# Fase 3 — classificador ML de clusters (destilado das regras) + fallback

from pathlib import Path

import pytest

from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier
from app.optimizer.detectors.lifestyle_features import (
    FEATURE_NAMES,
    extract_features,
)
from app.optimizer.detectors.ml_lifestyle_classifier import (
    MODEL_PATH,
    MLLifestyleClassifier,
)
from app.optimizer.profiler import UserProfile


def _profile(**overrides) -> UserProfile:
    base = dict(
        monthly_avg_spend=5000.0,
        spend_by_category={"alimentacao": 500.0, "supermercado": 800.0},
        travel_frequency_score=10.0,
        foodie_score=20.0,
        savings_rate=10.0,
        spending_stability=0.6,
        credit_spend_ratio=0.8,
        merchant_diversity_score=40.0,
        subscription_burn_monthly=50.0,
        committed_percentage=0.2,
    )
    base.update(overrides)
    return UserProfile(**base)


# ── artefatos do modelo ──────────────────────────────────────────────────────

def test_modelo_treinado_existe_e_carrega():
    assert MODEL_PATH.exists(), (
        "models/lifestyle_classifier.pkl ausente — rode "
        "scripts/train_lifestyle_classifier.py"
    )
    ml = MLLifestyleClassifier()
    assert ml.is_available


def test_metadata_registra_fidelidade():
    import json

    meta_path = MODEL_PATH.parent / "lifestyle_classifier_metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["fidelity_to_rules_holdout"] >= 0.95
    assert meta["features_version"] == "1.0"


def test_extract_features_ordem_e_tamanho():
    feats = extract_features(_profile())
    assert len(feats) == len(FEATURE_NAMES)
    assert all(isinstance(f, float) for f in feats)


# ── contrato e coerência com as regras ───────────────────────────────────────

def test_contrato_do_classify_ml():
    result = LifestyleClassifier().classify(_profile())
    assert set(result) >= {
        "lifestyle_cluster", "secondary_clusters", "cluster_scores",
        "classification_source",
    }
    assert result["classification_source"] in ("ml", "rules")
    assert len(result["secondary_clusters"]) <= 2


@pytest.mark.parametrize("overrides,expected", [
    # arquétipos inequívocos — ML deve concordar com as regras
    (dict(travel_frequency_score=95.0, international_spend_monthly=900.0,
          travel_profile="INTENSO"), "EXPLORADOR_GLOBAL"),
    (dict(foodie_score=90.0,
          spend_by_category={"alimentacao": 2200.0}), "URBANO_FOODIE"),
    (dict(investor_type="DIVERSIFICADO", savings_rate=40.0), "INVESTIDOR_CAUTELOSO"),
    (dict(savings_rate=-25.0, committed_percentage=0.8, spending_stability=0.1,
          fss_level="CRITICO"), "ESTRESSE_FINANCEIRO"),
    (dict(is_likely_mei=True), "MICROEMPREENDEDOR"),
])
def test_ml_concorda_com_regras_em_arquetipos_claros(overrides, expected):
    profile = _profile(**overrides)
    ml_result = MLLifestyleClassifier.shared().classify(profile)
    assert ml_result is not None
    assert ml_result["lifestyle_cluster"] == expected
    # e as regras (professor) concordam
    rules = LifestyleClassifier().classify_rules(profile)
    assert rules["lifestyle_cluster"] == expected


def test_perfil_neutro_nao_classificado():
    result = MLLifestyleClassifier.shared().classify(
        _profile(travel_frequency_score=0.0, foodie_score=0.0, savings_rate=2.0,
                 subscription_burn_monthly=0.0, credit_spend_ratio=1.0,
                 merchant_diversity_score=10.0,
                 spend_by_category={"supermercado": 300.0})
    )
    assert result["lifestyle_cluster"] == "NAO_CLASSIFICADO"


def test_ml_confidence_presente_e_valida():
    result = MLLifestyleClassifier.shared().classify(
        _profile(is_likely_mei=True)
    )
    assert 0.0 <= result["ml_confidence"] <= 1.0
    assert result["ml_confidence"] >= 0.35  # primário só existe acima do threshold


# ── fallback para regras ─────────────────────────────────────────────────────

def test_fallback_para_regras_quando_modelo_ausente(tmp_path, monkeypatch):
    import app.optimizer.detectors.lifestyle_classifier as lc_module
    from app.optimizer.detectors import ml_lifestyle_classifier as ml_module

    quebrado = MLLifestyleClassifier(model_path=tmp_path / "inexistente.pkl")
    assert quebrado.is_available is False

    monkeypatch.setattr(ml_module.MLLifestyleClassifier, "_shared_instance", quebrado)
    result = LifestyleClassifier().classify(_profile(is_likely_mei=True))
    assert result["classification_source"] == "rules"
    assert result["lifestyle_cluster"] == "MICROEMPREENDEDOR"


def test_modelo_com_versao_de_features_errada_e_ignorado(tmp_path):
    import pickle

    fake = tmp_path / "modelo_velho.pkl"
    fake.write_bytes(pickle.dumps({
        "model": object(), "classes": [], "features_version": "0.9",
        "feature_names": [],
    }))
    ml = MLLifestyleClassifier(model_path=fake)
    assert ml.is_available is False  # versão incompatível → regras assumem
