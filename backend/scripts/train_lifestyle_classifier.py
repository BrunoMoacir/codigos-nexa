#!/usr/bin/env python3
"""
scripts/train_lifestyle_classifier.py — Treina o classificador ML de clusters
de estilo de vida (Fase 3 da Inteligência Comportamental).

Estratégia (bootstrap sem dados reais de produção):
  DESTILAÇÃO — as regras calibradas do LifestyleClassifier são o "professor":
  1. Gera dezenas de milhares de UserProfiles sintéticos:
     - amostragem concentrada por arquétipo (garante cobertura das 8 classes);
     - amostragem uniforme ampla (cobre o espaço entre arquétipos);
     - misturas de 2 arquétipos (perfis híbridos, onde regras são frágeis);
  2. Rotula cada perfil com as REGRAS atuais (classify_rules);
  3. Treina RandomForest sobre o vetor de features (lifestyle_features.py);
  4. Avalia fidelidade às regras em holdout (meta ≥ 95%) + relatório por classe;
  5. Salva models/lifestyle_classifier.pkl + metadata JSON.

Quando houver dados reais rotulados (correções de usuários, validação manual),
o MESMO script re-treina trocando o gerador por dados reais — a inferência
não muda.

Uso:
    python3 scripts/train_lifestyle_classifier.py [--samples 60000] [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.forecast.etl.income_profiler import IncomeProfile  # noqa: E402
from app.optimizer.detectors.lifestyle_classifier import LifestyleClassifier  # noqa: E402
from app.optimizer.detectors.lifestyle_features import (  # noqa: E402
    FEATURE_NAMES,
    FEATURES_VERSION,
    extract_features,
)
from app.optimizer.profiler import UserProfile  # noqa: E402

MODEL_PATH = BACKEND / "models" / "lifestyle_classifier.pkl"
META_PATH = BACKEND / "models" / "lifestyle_classifier_metadata.json"


# ── Geração de perfis sintéticos ─────────────────────────────────────

def _income_profile(pattern: str) -> IncomeProfile | None:
    if not pattern:
        return None
    from app.forecast.etl.income_profiler import IncomePattern

    income = random.uniform(2000, 15000)
    return IncomeProfile(
        monthly_net_income=income,
        income_pattern=IncomePattern(pattern),
        income_stability=random.uniform(0.4, 0.9),
        confidence=0.8,
        salary_monthly=income if pattern == "CLT" else 0.0,
        freelance_monthly=income if pattern in ("PJ", "MIXED") else 0.0,
        raw_monthly_credits=income * 1.1,
        excluded_monthly=income * 0.1,
    )


def _base_profile() -> UserProfile:
    """Perfil neutro com ruído — base de todas as amostras."""
    spend = random.uniform(800, 20000)
    return UserProfile(
        monthly_avg_spend=spend,
        committed_percentage=random.uniform(0.05, 0.5),
        spend_by_category={
            "alimentacao": spend * random.uniform(0.05, 0.25),
            "supermercado": spend * random.uniform(0.05, 0.3),
            "saude": spend * random.uniform(0.0, 0.1),
            "educacao": spend * random.uniform(0.0, 0.08),
            "transporte": spend * random.uniform(0.02, 0.15),
            "lazer": spend * random.uniform(0.0, 0.15),
        },
        international_spend_monthly=random.uniform(0, 150),
        travel_spend_monthly=random.uniform(0, 300),
        estimated_monthly_income=spend * random.uniform(1.0, 1.8),
        data_coverage_months=3,
        spending_stability=random.uniform(0.2, 0.9),
        credit_spend_ratio=random.uniform(0.3, 1.0),
        travel_frequency_score=random.uniform(0, 35),
        travel_profile="OCASIONAL",
        foodie_score=random.uniform(0, 40),
        savings_rate=random.uniform(-10, 30),
        investor_type="NONE",
        is_likely_mei=False,
        merchant_diversity_score=random.uniform(10, 70),
        subscription_burn_monthly=random.uniform(0, 120),
        income_profile=_income_profile(random.choice(["CLT", "", ""])),
    )


def _apply_archetype(p: UserProfile, archetype: str, intensity: float) -> UserProfile:
    """Intensifica os sinais de um arquétipo (intensity 0.5–1.0)."""
    i = intensity
    if archetype == "EXPLORADOR_GLOBAL":
        p.travel_frequency_score = 40 + 60 * i * random.uniform(0.7, 1.0)
        p.international_spend_monthly = 200 + 800 * i
        p.travel_profile = random.choice(["FREQUENTE", "INTENSO"]) if i > 0.55 else "MODERADO"
        p.is_airbnb_user = random.random() < 0.4 * i
        p.is_digital_nomad = random.random() < 0.2 * i
    elif archetype == "URBANO_FOODIE":
        p.foodie_score = 45 + 55 * i * random.uniform(0.7, 1.0)
        p.spend_by_category["alimentacao"] = p.monthly_avg_spend * (0.2 + 0.3 * i)
    elif archetype == "INVESTIDOR_CAUTELOSO":
        p.investor_type = random.choice(["ATIVO", "DIVERSIFICADO"]) if i > 0.55 else "CASUAL"
        p.savings_rate = 15 + 35 * i
    elif archetype == "FAMILIA_ESTRUTURADA":
        p.is_family_with_kids = random.random() < 0.7 * i + 0.2
        p.family_score = 40 + 60 * i * random.uniform(0.6, 1.0)
        p.spend_by_category["saude"] = p.monthly_avg_spend * (0.06 + 0.10 * i)
        p.spend_by_category["educacao"] = p.monthly_avg_spend * (0.05 + 0.10 * i)
        p.income_profile = _income_profile("CLT")
        p.spending_stability = 0.6 + 0.35 * i
    elif archetype == "DIGITAL_NATIVO":
        p.subscription_burn_monthly = 80 + 200 * i
        p.credit_spend_ratio = max(0.0, 0.55 - 0.5 * i)
        p.merchant_diversity_score = 50 + 45 * i
    elif archetype == "ESTRESSE_FINANCEIRO":
        p.savings_rate = -30 * i - 2
        p.committed_percentage = 0.5 + 0.4 * i
        p.spending_stability = max(0.05, 0.35 - 0.3 * i)
        p.fss_level = "CRITICO" if i > 0.7 else ("ALERTA" if i > 0.4 else "ATENCAO")
    elif archetype == "MICROEMPREENDEDOR":
        p.is_likely_mei = random.random() < 0.75 * i + 0.2
        if not p.is_likely_mei:
            p.income_profile = _income_profile(random.choice(["PJ", "MIXED"]))
    return p


ARCHETYPES = [
    "EXPLORADOR_GLOBAL", "URBANO_FOODIE", "INVESTIDOR_CAUTELOSO",
    "FAMILIA_ESTRUTURADA", "DIGITAL_NATIVO", "ESTRESSE_FINANCEIRO",
    "MICROEMPREENDEDOR",
]


def generate_dataset(n_samples: int, seed: int):
    random.seed(seed)
    teacher = LifestyleClassifier()
    X, y = [], []

    n_arch = int(n_samples * 0.55)      # concentrado por arquétipo
    n_uniform = int(n_samples * 0.25)   # espaço amplo (incl. neutros)
    n_mixed = n_samples - n_arch - n_uniform  # híbridos de 2 arquétipos

    for k in range(n_arch):
        p = _apply_archetype(
            _base_profile(), ARCHETYPES[k % len(ARCHETYPES)], random.uniform(0.5, 1.0)
        )
        X.append(extract_features(p))
        y.append(teacher.classify_rules(p)["lifestyle_cluster"])

    for _ in range(n_uniform):
        p = _base_profile()
        X.append(extract_features(p))
        y.append(teacher.classify_rules(p)["lifestyle_cluster"])

    for _ in range(n_mixed):
        a, b = random.sample(ARCHETYPES, 2)
        p = _apply_archetype(_base_profile(), a, random.uniform(0.5, 1.0))
        p = _apply_archetype(p, b, random.uniform(0.3, 0.7))
        X.append(extract_features(p))
        y.append(teacher.classify_rules(p)["lifestyle_cluster"])

    return X, y


# ── Treino e avaliação ───────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=60000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import train_test_split

    print(f"Gerando {args.samples} perfis sintéticos (seed={args.seed})...")
    X, y = generate_dataset(args.samples, args.seed)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=args.seed, stratify=y
    )

    print("Treinando RandomForest...")
    # Hiperparâmetros escolhidos por sweep fidelidade × tamanho do artefato:
    # (80, 18, 4) → ~96% de fidelidade com ~6 MB gzip. Profundidade ilimitada
    # chegava a 97,4% mas gerava 189 MB — inviável para versionar.
    model = RandomForestClassifier(
        n_estimators=80,
        max_depth=18,
        min_samples_leaf=4,
        class_weight="balanced",
        random_state=args.seed,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    fidelity = accuracy_score(y_test, y_pred)
    print(f"\nFidelidade às regras (holdout): {fidelity:.4f}")
    print(classification_report(y_test, y_pred, digits=3))

    if fidelity < 0.95:
        print("⚠️ Fidelidade abaixo de 95% — modelo NÃO salvo. Ajuste o gerador/modelo.")
        sys.exit(1)

    top_features = sorted(
        zip(FEATURE_NAMES, model.feature_importances_), key=lambda t: -t[1]
    )[:8]

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    import gzip

    with gzip.open(MODEL_PATH, "wb", compresslevel=6) as f:
        pickle.dump(
            {
                "model": model,
                "feature_names": FEATURE_NAMES,
                "features_version": FEATURES_VERSION,
                "classes": list(model.classes_),
            },
            f,
        )

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "samples": args.samples,
        "seed": args.seed,
        "fidelity_to_rules_holdout": round(fidelity, 4),
        "features_version": FEATURES_VERSION,
        "classes": list(model.classes_),
        "top_features": [{"name": n, "importance": round(v, 4)} for n, v in top_features],
        "method": (
            "Destilação das regras do LifestyleClassifier em RandomForest sobre "
            "perfis sintéticos (55% arquétipos, 25% uniforme, 20% híbridos). "
            "Re-treinar com dados reais rotulados quando disponíveis."
        ),
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"\n✅ Modelo salvo em {MODEL_PATH}")
    print(f"   Metadata em {META_PATH}")
    print("   Top features:", ", ".join(f"{n}={v:.3f}" for n, v in top_features))


if __name__ == "__main__":
    main()
