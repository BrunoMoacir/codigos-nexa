# app/optimizer/detectors/lifestyle_classifier.py

from __future__ import annotations
from app.optimizer.profiler import UserProfile


CLUSTER_EXPLORER_GLOBAL    = "EXPLORADOR_GLOBAL"
CLUSTER_URBAN_FOODIE       = "URBANO_FOODIE"
CLUSTER_INVESTOR           = "INVESTIDOR_CAUTELOSO"
CLUSTER_FAMILY             = "FAMILIA_ESTRUTURADA"
CLUSTER_DIGITAL_NATIVE     = "DIGITAL_NATIVO"
CLUSTER_FINANCIAL_STRESS   = "ESTRESSE_FINANCEIRO"
CLUSTER_MICROEMPREENDEDOR  = "MICROEMPREENDEDOR"
CLUSTER_UNCLASSIFIED       = "NAO_CLASSIFICADO"

# Score mínimo para o cluster primário (deve "ganhar" claramente)
_PRIMARY_THRESHOLD = 0.35
# Score mínimo para clusters secundários (basta "estar presente" de forma relevante)
_SECONDARY_THRESHOLD = 0.30
# Máximo de clusters secundários retornados
_MAX_SECONDARY = 2


class LifestyleClassifier:
    """
    Classifica o UserProfile em um ou mais clusters de estilo de vida.

    Fase 3 (ATUAL): modelo ML (RandomForest destilado das regras — ver
    scripts/train_lifestyle_classifier.py) com FALLBACK nas regras
    determinísticas — padrão multi-layer do projeto (ML → regras → default).
    O modelo devolve probabilidades calibradas por cluster; sem modelo
    disponível (arquivo ausente/corrompido), as regras respondem sozinhas.

    Retorna:
        lifestyle_cluster:      cluster primário (score/probabilidade ≥ 0.35)
        secondary_clusters:     score ≥ 0.30, distintos do primário (máx 2)
        cluster_scores:         afinidade 0.0–1.0 por cluster
        classification_source:  "ml" | "rules"
    """

    def classify(self, profile: UserProfile) -> dict:
        """ML primeiro; regras como fallback. Contrato idêntico nos dois.

        INVARIANTE DE SEGURANÇA (determinístico, fora do ML): FSS CRITICO
        sempre passa pelas regras — o tratamento de estresse financeiro
        (empatia, zero sugestão de gasto) não pode depender de fronteira
        aprendida.
        """
        fss_critical = getattr(profile, "fss_level", None) == "CRITICO"
        if not fss_critical:
            try:
                from app.optimizer.detectors.ml_lifestyle_classifier import (
                    MLLifestyleClassifier,
                )

                ml = MLLifestyleClassifier.shared()
                if ml.is_available:
                    result = ml.classify(profile)
                    if result is not None:
                        return self._apply_rules_floor(profile, result)
            except Exception:  # nunca deixa o ML derrubar a classificação
                pass

        result = self.classify_rules(profile)
        result["classification_source"] = "rules"
        return result

    # Piso de regras: quando o ML ABSTÉM (primário = NAO_CLASSIFICADO por
    # ficar abaixo do limiar de probabilidade) mas as REGRAS — que são o
    # professor do modelo — têm um veredito CONFIANTE, confia nas regras.
    # Sem isso, o híbrido perde classificações claras em perfis realistas
    # onde o ML espalha probabilidade entre classes correlacionadas (ex.:
    # foodie que também parece esticado pelo aluguel). Descoberto pelo
    # teste ponta a ponta do demo.
    _RULES_FLOOR_CONFIDENCE = 0.60

    # Corroboração: dois sinais fracos que APONTAM PARA O MESMO LUGAR valem
    # mais que um sinal fraco sozinho. É exatamente o princípio que o
    # EvidenceScorer já aplica nos eventos de vida — BUFFET isolado é
    # bloqueado, BUFFET+NOIVAS+FOTÓGRAFO passa com folga — aplicado aqui, no
    # ponto em que o híbrido é mais fraco.
    #
    # Medição que motivou isto: em 4.000 perfis, o ML abstinha e o piso de
    # 0,60 salvava 18,5%. O resto virava NAO_CLASSIFICADO, que no produto
    # significa tom neutro no chat, nenhum ajuste de orçamento e nenhum
    # bônus de ranking — ou seja, a feature inteira desligada para aquele
    # usuário. Boa parte desses casos tinha ML e regras concordando, cada um
    # logo abaixo do seu próprio limiar.
    _CORROBORATION_ML = 0.25      # vs 0.35 exigido do ML sozinho
    _CORROBORATION_RULES = 0.40   # vs 0.60 exigido das regras sozinhas

    def _apply_rules_floor(self, profile: UserProfile, ml_result: dict) -> dict:
        if ml_result.get("lifestyle_cluster") != CLUSTER_UNCLASSIFIED:
            return ml_result

        # `ml.classify()` já devolve as afinidades das regras em
        # `cluster_scores` — recalcular aqui daria o mesmo resultado por um
        # segundo passe do classificador de regras.
        rule_scores = ml_result.get("cluster_scores") or {}
        rules = self.classify_rules(profile) if not rule_scores else None
        if rules is not None:
            rule_scores = rules["cluster_scores"]

        candidatos = {c: s for c, s in rule_scores.items() if c != CLUSTER_UNCLASSIFIED}
        if not candidatos:
            return ml_result
        rule_primary = max(candidatos, key=candidatos.get)
        rule_score = candidatos[rule_primary]

        fonte = None
        if rule_score >= self._RULES_FLOOR_CONFIDENCE:
            fonte = "ml+rules_floor"
        elif rule_score >= self._CORROBORATION_RULES:
            # O ML absteve por não cruzar 0,35, mas ainda tem um favorito.
            # Se o favorito dele é o mesmo das regras, os dois concordam.
            probas = ml_result.get("ml_probabilities") or {}
            ml_cands = {c: p for c, p in probas.items() if c != CLUSTER_UNCLASSIFIED}
            if ml_cands:
                ml_top = max(ml_cands, key=ml_cands.get)
                if ml_top == rule_primary and ml_cands[ml_top] >= self._CORROBORATION_ML:
                    fonte = "ml+rules_agreement"

        if fonte is None:
            return ml_result

        secundarios = sorted(
            [c for c, s in candidatos.items()
             if c != rule_primary and s >= _SECONDARY_THRESHOLD],
            key=lambda c: candidatos[c],
            reverse=True,
        )[:_MAX_SECONDARY]

        return {
            "lifestyle_cluster": rule_primary,
            "secondary_clusters": secundarios,
            "cluster_scores": rule_scores,
            "ml_probabilities": ml_result.get("ml_probabilities"),
            "classification_source": fonte,
            "ml_confidence": ml_result.get("ml_confidence"),
        }

    def classify_rules(self, profile: UserProfile) -> dict:
        scores = {
            CLUSTER_EXPLORER_GLOBAL:   self._score_explorer(profile),
            CLUSTER_URBAN_FOODIE:      self._score_foodie(profile),
            CLUSTER_INVESTOR:          self._score_investor(profile),
            CLUSTER_FAMILY:            self._score_family(profile),
            CLUSTER_DIGITAL_NATIVE:    self._score_digital_native(profile),
            CLUSTER_FINANCIAL_STRESS:  self._score_financial_stress(profile),
            CLUSTER_MICROEMPREENDEDOR: self._score_mei(profile),
        }

        primary = max(scores, key=lambda k: scores[k])

        # Threshold mínimo para primário — se nenhum cluster tem afinidade > 0.35, não classificar
        if scores[primary] < _PRIMARY_THRESHOLD:
            primary = CLUSTER_UNCLASSIFIED

        # Clusters secundários: score ≥ 0.30, distintos do primário
        secondary = sorted(
            [c for c, s in scores.items() if c != primary and s >= _SECONDARY_THRESHOLD],
            key=lambda c: scores[c],
            reverse=True,
        )[:_MAX_SECONDARY]

        return {
            "lifestyle_cluster": primary,
            "secondary_clusters": secondary,
            "cluster_scores": {k: round(v, 3) for k, v in scores.items()},
        }

    def _score_explorer(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.travel_frequency_score / 100, 1.0) * 0.45
        score += min(p.international_spend_monthly / 500, 1.0) * 0.30
        score += (1.0 if p.travel_profile in ("FREQUENTE", "INTENSO") else 0.0) * 0.15
        # T2.5: Airbnb / nômade digital reforça cluster de explorador
        if getattr(p, "is_digital_nomad", False):
            score += 0.10
        elif getattr(p, "is_airbnb_user", False):
            score += 0.05
        return score

    def _score_foodie(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.foodie_score / 100, 1.0) * 0.60
        # category_canonical usa "alimentacao" (lowercase, sem acento) — elimina dual-lookup
        food_spend = p.spend_by_category.get("alimentacao", 0)
        pct_food = food_spend / p.monthly_avg_spend if p.monthly_avg_spend > 0 else 0
        score += min(pct_food * 2, 1.0) * 0.40
        return score

    def _score_investor(self, p: UserProfile) -> float:
        score = 0.0
        score += (1.0 if p.investor_type in ("ATIVO", "DIVERSIFICADO") else
                  0.5 if p.investor_type == "CASUAL" else 0.0) * 0.50
        # savings_rate é porcentagem (ex: 22.5 = 22.5%). Normalizar para 0-1 dividindo por 50
        # para que 25% → 0.5, 50% → 1.0 (full score).
        score += min(p.savings_rate / 50, 1.0) * 0.50
        return score

    def _score_family(self, p: UserProfile) -> float:
        # Sinal direto do FamilyDetector (T2.3) — tem prioridade sobre heurísticas
        if getattr(p, "is_family_with_kids", False):
            family_s = getattr(p, "family_score", 0.0)
            # family_score 0-100 → 0.4-1.0 (threshold de detecção já é 40)
            return 0.4 + min(family_s / 100, 1.0) * 0.6

        # Fallback heurístico para perfis sem FamilyDetector
        edu_health = (
            p.spend_by_category.get("saude", 0)
            + p.spend_by_category.get("educacao", 0)
        )
        edu_health_pct = edu_health / p.monthly_avg_spend if p.monthly_avg_spend > 0 else 0
        score = min(edu_health_pct * 3, 0.6)

        if p.income_profile and p.income_profile.income_pattern == "CLT":
            score += 0.2
        if p.spending_stability > 0.7:
            score += 0.2
        return score

    def _score_digital_native(self, p: UserProfile) -> float:
        score = 0.0
        score += min(p.subscription_burn_monthly / 200, 1.0) * 0.40
        pix_proxy = 1.0 - p.credit_spend_ratio
        score += min(pix_proxy * 1.5, 1.0) * 0.30
        score += min(p.merchant_diversity_score / 80, 1.0) * 0.30
        return score

    def _score_financial_stress(self, p: UserProfile) -> float:
        score = 0.0
        # savings_rate é porcentagem: -5 = -5%. Threshold alinhado com FSSCalculator.
        if p.savings_rate < -5:
            score += 0.4
        elif p.savings_rate < 0:
            score += 0.15
        if p.committed_percentage > 0.6:
            score += 0.3
        if p.spending_stability < 0.3:
            score += 0.3
        # FSS já calculado (T2.2): se disponível, usa como sinal direto de estresse.
        fss_level = getattr(p, "fss_level", None)
        if fss_level == "CRITICO":
            score = max(score, 0.75)
        elif fss_level == "ALERTA":
            score = max(score, 0.50)
        return score

    def _score_mei(self, p: UserProfile) -> float:
        if p.is_likely_mei:
            return 0.8
        if p.income_profile and p.income_profile.income_pattern in ("PJ", "MIXED"):
            return 0.5
        return 0.0
