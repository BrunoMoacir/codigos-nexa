# app/optimizer/detectors/foodie_detector.py
# FoodieDetector — score de perfil gastronômico

from __future__ import annotations

import logging

import polars as pl

logger = logging.getLogger(__name__)

# Categorias L1 do optimizer que compõem "alimentação"
_FOOD_CATEGORIES_L1 = {"Alimentação", "alimentacao"}
# Categorias L2 (T1.1) que compõem "alimentação"
_FOOD_CATEGORIES_L2 = {"DELIVERY", "RESTAURANTE", "SUPERMERCADO"}

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
    ) -> dict:
        """
        Args:
            df: transactions_clean já enriquecido (T1.1).
            monthly_avg_spend: gasto médio mensal total (R$), do ConsumptionProfiler.

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

        # ── Gasto em alimentação (L2 prioritário, L1 como fallback) ──────────
        food_filter = pl.lit(False)
        if "merchant_category_l2" in df.columns:
            food_filter = food_filter | pl.col("merchant_category_l2").is_in(
                list(_FOOD_CATEGORIES_L2)
            )
        if "category" in df.columns:
            food_filter = food_filter | pl.col("category").is_in(
                list(_FOOD_CATEGORIES_L1)
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
                restaurant_diversity = rest_df["description"].n_unique()
                avg_ticket = float(rest_df["amount"].sum()) * -1 / len(rest_df)
                fine_dining = avg_ticket > _FINE_DINING_TICKET

        # ── Score composto ────────────────────────────────────────────────────
        pct_score      = min(pct_food * 160, 40)              # 25% em food → 40 pts
        diversity_score = min(restaurant_diversity * 1.5, 30)  # 20 merchants → 30 pts
        ticket_score   = min((avg_ticket / 200) * 20, 20)     # R$200 ticket → 20 pts
        fine_bonus     = 10 if fine_dining else 0

        foodie_score = round(min(pct_score + diversity_score + ticket_score + fine_bonus, 100.0), 1)
        profile = self._classify(foodie_score)

        return {
            "foodie_score": foodie_score,
            "foodie_profile": profile,
            "pct_food_spend": round(pct_food, 3),
            "food_spend_monthly": round(food_spend / coverage_months, 2),
            "restaurant_diversity": restaurant_diversity,
            "avg_restaurant_ticket": round(avg_ticket, 2),
            "is_fine_dining": fine_dining,
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
        }
