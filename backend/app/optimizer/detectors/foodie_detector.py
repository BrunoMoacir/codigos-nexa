# app/optimizer/detectors/foodie_detector.py
# FoodieDetector — score de perfil gastronômico

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import polars as pl

from app.optimizer.detectors.evidence_scorer import compute_false_positive_risk
from app.core.formatacao import brl

if TYPE_CHECKING:
    from app.optimizer.detectors.personal_baseline import PersonalBaseline

logger = logging.getLogger(__name__)

# Categoria L1 canônica (category_canonical, lowercase sem acento)
_FOOD_CATEGORY_CANONICAL = "alimentacao"
# Categorias L2 (T1.1) que mapeiam para alimentação
_FOOD_CATEGORIES_L2 = {"DELIVERY", "RESTAURANTE", "SUPERMERCADO"}
# Fallback: raw category names de bancos que não passam por category_canonical
_FOOD_CATEGORIES_RAW = {"Alimentação", "alimentacao"}

# Ticket médio acima deste valor em restaurante = sinal de fine dining
_FINE_DINING_TICKET = 150.0


class FoodieDetector:
    """
    Detecta intensidade do perfil gastronômico.

    foodie_score (0–100):
        pct_food_spend    (peso 40): % dos gastos totais em alimentação
        restaurant_diversity (peso 30): merchants únicos em restaurante/delivery
        avg_restaurant_ticket (peso 20): ticket médio em restaurante (normalizado)
        fine_dining_bonus    (peso 10): ticket médio > R$150 → fine dining

    Depende de T1.1: merchant_category_l2.
    Usa também category (L1) como fallback quando L2 não está disponível.
    """

    def calc_foodie_score(
        self,
        df: pl.DataFrame,
        monthly_avg_spend: float,
        baseline: "PersonalBaseline | None" = None,
    ) -> dict:
        """
        Args:
            df:                transactions_clean já enriquecido (T1.1).
            monthly_avg_spend: gasto médio mensal total (R$), do ConsumptionProfiler.
            baseline:          PersonalBaseline do usuário (90–540 dias). Quando fornecido:
                               - threshold de fine dining é ajustado pelo nível de gasto histórico
                               - spike de alimentação vs baseline gera bonus de até +10 pts
                               - deviation_ratio é exposto em supporting_signals

        Returns:
            dict com foodie_score, foodie_profile e métricas auxiliares.
        """
        if monthly_avg_spend <= 0 or df.is_empty():
            return self._zero_result()

        expenses = df.filter(pl.col("amount") < 0)
        if expenses.is_empty():
            return self._zero_result()

        coverage_months = max(
            df.with_columns(
                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
            ).select("ym").unique().height,
            1,
        )
        total_spend_period = monthly_avg_spend * coverage_months

        # ── Gasto em alimentação — hierarquia de campos ───────────────────────
        # 1. merchant_category_l1 (canônico, derivado do L2): mais preciso
        # 2. merchant_category_l2 (subcategoria): fallback quando L1 ausente
        # 3. category_canonical (normalizado do banco): inclui transações sem L2
        # 4. category (raw): compatibilidade com bancos que não passam por enrich
        food_filter = pl.lit(False)
        if "merchant_category_l1" in df.columns:
            food_filter = food_filter | (
                pl.col("merchant_category_l1") == _FOOD_CATEGORY_CANONICAL
            )
        if "merchant_category_l2" in df.columns:
            food_filter = food_filter | pl.col("merchant_category_l2").is_in(
                list(_FOOD_CATEGORIES_L2)
            )
        if "category_canonical" in df.columns:
            food_filter = food_filter | (
                pl.col("category_canonical") == _FOOD_CATEGORY_CANONICAL
            )
        elif "category" in df.columns:
            food_filter = food_filter | pl.col("category").is_in(
                list(_FOOD_CATEGORIES_RAW)
            )

        food_df = expenses.filter(food_filter)
        food_spend = float(food_df["amount"].sum()) * -1 if not food_df.is_empty() else 0.0
        pct_food = food_spend / total_spend_period if total_spend_period > 0 else 0.0

        # ── Diversidade de restaurantes (merchants únicos) ────────────────────
        restaurant_diversity = 0
        avg_ticket = 0.0
        fine_dining = False

        if "merchant_category_l2" in df.columns and "description" in df.columns:
            rest_df = expenses.filter(
                pl.col("merchant_category_l2").is_in({"RESTAURANTE", "DELIVERY"})
            )
            if not rest_df.is_empty():
                # merchant_id colapsa aliases do mesmo merchant antes de contar
                # diversidade: "PG*IFOOD", "IFOOD*PADARIA", "IFOOD.COM" → todos "ifood".
                if "merchant_id" in rest_df.columns:
                    merch_col = "merchant_id"
                elif "merchant_normalized" in rest_df.columns:
                    merch_col = "merchant_normalized"
                else:
                    merch_col = "description"
                restaurant_diversity = rest_df[merch_col].n_unique()
                avg_ticket = float(rest_df["amount"].sum()) * -1 / len(rest_df)

                # Fine dining threshold adaptado ao nível histórico de gasto do usuário.
                # Referência: R$3.000/mês = perfil mediano (ratio=1.0 → threshold=R$150).
                # Gasto menor → threshold menor (R$80 já é fine dining para renda baixa).
                # Gasto maior → threshold maior (R$150 é normal para quem gasta R$6k/mês).
                if baseline is not None and baseline.has_data() and baseline.total_monthly_avg > 0:
                    spend_ratio = baseline.total_monthly_avg / 3_000.0
                    fine_dining_threshold = max(_FINE_DINING_TICKET * spend_ratio, 60.0)
                else:
                    fine_dining_threshold = _FINE_DINING_TICKET

                fine_dining = avg_ticket > fine_dining_threshold

        # ── Score composto ────────────────────────────────────────────────────
        pct_score       = min(pct_food * 160, 40)              # 25% em food → 40 pts
        diversity_score = min(restaurant_diversity * 1.5, 30)  # 20 merchants → 30 pts
        ticket_score    = min((avg_ticket / 200) * 20, 20)     # R$200 ticket → 20 pts
        fine_bonus      = 10 if fine_dining else 0

        # ── Bonus de comportamento: spike de alimentação vs baseline pessoal ──
        # Detecta que o usuário está gastando notavelmente mais em alimentação do
        # que seu próprio histórico — sinal de mudança real de comportamento.
        baseline_bonus = 0.0
        baseline_signals: list[str] = []
        if baseline is not None and baseline.has_data():
            food_monthly = food_spend / coverage_months
            food_ratio = baseline.deviation_ratio("alimentacao", food_monthly)
            if food_ratio == float("inf") and food_spend > 0:
                # Categoria nova para o usuário — qualquer gasto é comportamento emergente
                baseline_bonus = 5.0
                baseline_signals.append("alimentacao_categoria_nova")
            elif food_ratio >= 2.0:
                # Dobrou ou mais vs histórico — mudança expressiva de comportamento
                baseline_bonus = min((food_ratio - 1.0) * 3.0, 10.0)
                baseline_signals.append(f"food_vs_baseline={food_ratio:.1f}x")
            elif food_ratio >= 1.5:
                # 50–100% acima — elevação moderada
                baseline_bonus = 3.0
                baseline_signals.append(f"food_vs_baseline={food_ratio:.1f}x")

        foodie_score = round(min(pct_score + diversity_score + ticket_score + fine_bonus + baseline_bonus, 100.0), 1)
        profile = self._classify(foodie_score)

        confidence = round(foodie_score / 100, 4)

        supporting_signals: list[str] = []
        if pct_score > 0:
            supporting_signals.append(f"pct_alimentacao={pct_food:.1%}")
        if diversity_score > 0:
            supporting_signals.append(f"merchants_distintos={restaurant_diversity}")
        if ticket_score > 0:
            supporting_signals.append(f"ticket_medio={brl(avg_ticket, 0)}")
        if fine_dining:
            supporting_signals.append("fine_dining=True")
        supporting_signals.extend(baseline_signals)

        missing_signals: list[str] = []
        if pct_score < 20:
            missing_signals.append("proporcao_alimentacao_baixa")
        if diversity_score < 15:
            missing_signals.append("diversidade_restaurantes_baixa")
        if ticket_score < 10:
            missing_signals.append("ticket_medio_baixo")
        if not fine_dining:
            missing_signals.append("sem_fine_dining")

        return {
            "foodie_score": foodie_score,
            "foodie_profile": profile,
            "pct_food_spend": round(pct_food, 3),
            "food_spend_monthly": round(food_spend / coverage_months, 2),
            "restaurant_diversity": restaurant_diversity,
            "avg_restaurant_ticket": round(avg_ticket, 2),
            "is_fine_dining": fine_dining,
            "confidence": confidence,
            "supporting_signals": supporting_signals,
            "missing_signals": missing_signals,
            "false_positive_risk": compute_false_positive_risk(confidence),
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _classify(score: float) -> str:
        if score <= 25:
            return "BASICO"
        if score <= 55:
            return "APRECIADOR"
        if score <= 75:
            return "GOURMET"
        return "ENTUSIASTA"

    @staticmethod
    def _zero_result() -> dict:
        return {
            "foodie_score": 0.0,
            "foodie_profile": "BASICO",
            "pct_food_spend": 0.0,
            "food_spend_monthly": 0.0,
            "restaurant_diversity": 0,
            "avg_restaurant_ticket": 0.0,
            "is_fine_dining": False,
            "confidence": 0.0,
            "supporting_signals": [],
            "missing_signals": ["proporcao_alimentacao_baixa", "diversidade_restaurantes_baixa", "ticket_medio_baixo", "sem_fine_dining"],
            "false_positive_risk": "high",
        }
