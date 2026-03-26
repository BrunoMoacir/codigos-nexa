"""
app/purchase/purchase_advisor.py — F7: Modo Compra Inteligente

Orquestra 4 fontes de dados para recomendar a melhor forma de pagamento:
  1. OptimizerService  → melhor cartão e reward estimado por categoria
  2. BacenConnector    → taxa de crédito pessoal (CDC) para opção financiamento
  3. SafeToSpendCalc   → margem disponível antes/após a compra
  4. DuckDB            → transações do usuário (histórico de gastos por categoria)

Lógica de ranqueamento:
  - Ordena opções por net_cost (menor custo líquido = melhor)
  - Recomenda a opção de menor net_cost que seja acessível (affordable)
  - Se nenhuma for acessível, recomenda a de menor impacto e avisa o usuário
"""

from __future__ import annotations

import logging
from typing import Optional

import polars as pl

from app.purchase.models import (
    LiquidityImpact,
    PaymentMethod,
    PaymentOption,
    PurchaseRecommendation,
    PurchaseRequest,
)

logger = logging.getLogger(__name__)

# Limiar a partir do qual oferecemos a opção de financiamento (CDC/empréstimo pessoal)
_FINANCING_MIN_AMOUNT = 1_000.0
# Taxa mensal de crédito pessoal usada como fallback se BACEN estiver indisponível
_FINANCING_FALLBACK_MONTHLY_RATE = 0.0399   # ~3.99% a.m. (média CDC março/2026)


class PurchaseAdvisor:
    """
    Analisa uma compra e retorna a recomendação de forma de pagamento.

    Usage:
        advisor = PurchaseAdvisor()
        result  = advisor.analyze(request)
    """

    def analyze(self, request: PurchaseRequest) -> PurchaseRecommendation:
        logger.info(
            "PurchaseAdvisor | user=%s amount=%.2f category=%s installments=%d",
            request.user_id, request.amount, request.category, request.installments,
        )

        warnings: list[str] = []
        data_sources: list[str] = []

        # ── 1. Buscar transações do usuário ──────────────────────────────
        transactions_df = self._fetch_transactions(request.user_id)
        if not transactions_df.is_empty():
            data_sources.append("transactions_db")
        else:
            warnings.append("Sem histórico de transações: recomendação baseada apenas no valor informado.")

        # ── 2. Buscar safe_to_spend atual ────────────────────────────────
        safe_to_spend = self._fetch_safe_to_spend(request.user_id, transactions_df)
        if safe_to_spend is not None:
            data_sources.append("f1_safe_to_spend")
        else:
            warnings.append("Safe-to-spend indisponível: impacto no orçamento não calculado.")
            safe_to_spend = 0.0

        # ── 3. Buscar melhor cartão para a categoria ─────────────────────
        best_card_name, reward_rate, card_warning = self._fetch_best_card(
            request=request,
            transactions_df=transactions_df,
        )
        if card_warning:
            warnings.append(card_warning)
        else:
            data_sources.append("optimizer_f2")

        # ── 4. Buscar taxa de financiamento (CDC / BACEN) ─────────────────
        monthly_rate, rate_warning = self._fetch_financing_rate()
        if rate_warning:
            warnings.append(rate_warning)
        else:
            data_sources.append("bacen_cdc")

        # ── 5. Montar opções de pagamento ────────────────────────────────
        options: list[PaymentOption] = []

        options.append(self._build_pix_option(request.amount))
        options.append(self._build_card_avista_option(request.amount, best_card_name, reward_rate))

        if request.installments > 1:
            options.append(
                self._build_card_parcelado_option(
                    amount=request.amount,
                    installments=request.installments,
                    best_card_name=best_card_name,
                    reward_rate=reward_rate,
                )
            )

        if request.amount >= _FINANCING_MIN_AMOUNT and request.installments > 6:
            options.append(
                self._build_financing_option(
                    amount=request.amount,
                    installments=request.installments,
                    monthly_rate=monthly_rate,
                )
            )

        # ── 6. Ranquear por net_cost (menor = melhor) ────────────────────
        options.sort(key=lambda o: o.net_cost)

        # ── 7. Escolher recomendação ──────────────────────────────────────
        recommended = self._pick_recommendation(options, safe_to_spend, warnings)

        # ── 8. Impacto de liquidez ───────────────────────────────────────
        liquidity = self._build_liquidity_impact(
            net_cost=recommended.net_cost,
            safe_to_spend=safe_to_spend,
        )

        # ── 9. Confidence score ──────────────────────────────────────────
        confidence = self._compute_confidence(
            has_transactions=not transactions_df.is_empty(),
            has_safe_to_spend="f1_safe_to_spend" in data_sources,
            has_income=request.monthly_income is not None,
            warning_count=len(warnings),
        )

        return PurchaseRecommendation(
            user_id=request.user_id,
            amount=request.amount,
            category=request.category,
            recommended_method=recommended.method,
            recommended_label=recommended.label,
            recommended_net_cost=recommended.net_cost,
            reasoning=self._build_reasoning(recommended, options, liquidity, request),
            options=options,
            liquidity_impact=liquidity,
            confidence_score=round(confidence, 2),
            data_sources=data_sources,
            warnings=warnings,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FETCH HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _fetch_transactions(self, user_id: str) -> pl.DataFrame:
        """Busca transações limpas do PostgreSQL. Retorna DataFrame vazio em caso de falha."""
        try:
            from app.core.db.queries import get_transactions_for_user
            return get_transactions_for_user(user_id)
        except Exception as exc:
            logger.warning("PurchaseAdvisor | erro ao buscar transações: %s", exc)
            return pl.DataFrame()

    def _fetch_safe_to_spend(
        self, user_id: str, transactions_df: pl.DataFrame
    ) -> Optional[float]:
        """
        Busca safe_to_spend via SafeToSpendCalculator.
        Retorna None se não houver dados suficientes.
        """
        if transactions_df.is_empty():
            return None

        try:
            from app.forecast.cashflow.projector import CashflowProjector
            from app.forecast.cashflow.safe_to_spend import SafeToSpendCalculator

            projection_df = CashflowProjector().project(
                transactions_df=transactions_df,
                shadow_invoices_df=pl.DataFrame(),
                horizon_days=30,
            )
            result = SafeToSpendCalculator().calculate(projection_df, horizon_days=30)
            return result.safe_to_spend_total
        except Exception as exc:
            logger.warning("PurchaseAdvisor | erro ao calcular safe_to_spend: %s", exc)
            return None

    def _fetch_best_card(
        self,
        request: PurchaseRequest,
        transactions_df: pl.DataFrame,
    ) -> tuple[str, float, Optional[str]]:
        """
        Retorna (nome_do_melhor_cartão, reward_rate, warning_ou_None).
        reward_rate = fração do valor que retorna em cashback/pontos (ex: 0.015 = 1.5%).
        """
        try:
            from app.optimizer.models import OptimizationRequest
            from app.optimizer.services.optimizer_service import OptimizerService

            opt_req = OptimizationRequest(
                user_id=request.user_id,
                monthly_income=request.monthly_income,
            )
            report = OptimizerService().analyze(
                request=opt_req,
                transactions_df=transactions_df,
            )

            if report.best_card:
                # net_gain_expected é anual; estimamos reward_rate sobre gasto médio mensal
                card = report.best_card
                monthly_spend = max(
                    request.amount,  # garante que ao menos o valor da compra é base
                    1.0,
                )
                # reward_rate = pontos/cashback gerados / valor da compra
                reward_rate = (
                    card.points_value_expected / (monthly_spend * 12)
                    if card.points_value_expected and monthly_spend > 0
                    else 0.0
                )
                reward_rate = min(reward_rate, 0.05)  # cap em 5% para evitar distorções
                return card.card_name, reward_rate, None

        except Exception as exc:
            logger.warning("PurchaseAdvisor | OptimizerService falhou: %s", exc)

        return "seu cartão atual", 0.0, "Não foi possível identificar o melhor cartão — usando sem reward."

    def _fetch_financing_rate(self) -> tuple[float, Optional[str]]:
        """
        Busca taxa mensal de crédito pessoal (CDC) no BACEN.
        Retorna (taxa_mensal, warning_ou_None).
        """
        try:
            from app.architect.connectors.bacen import BacenConnector
            selic_annual = BacenConnector().get_selic()
            # CDC ≈ SELIC + spread de ~2.5% a.m. (referência mercado 2026)
            monthly_rate = (selic_annual / 12) + 0.025
            return monthly_rate, None
        except Exception as exc:
            logger.warning("PurchaseAdvisor | BACEN indisponível: %s — usando fallback CDC", exc)
            return _FINANCING_FALLBACK_MONTHLY_RATE, "Taxa CDC baseada em referência de mercado (BACEN indisponível)."

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BUILDERS DE OPÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_pix_option(self, amount: float) -> PaymentOption:
        return PaymentOption(
            method=PaymentMethod.PIX_AVISTA,
            label="PIX à vista",
            total_cost=round(amount, 2),
            monthly_cost=None,
            installments=1,
            reward_value=0.0,
            notes="Sem juros, sem cashback. Melhor para negociar desconto à vista com o vendedor.",
        )

    def _build_card_avista_option(
        self, amount: float, card_name: str, reward_rate: float
    ) -> PaymentOption:
        reward = round(amount * reward_rate, 2)
        return PaymentOption(
            method=PaymentMethod.CARTAO_AVISTA,
            label=f"Cartão à vista ({card_name})",
            total_cost=round(amount, 2),
            monthly_cost=None,
            installments=1,
            reward_value=reward,
            notes=f"Gera ~R$ {reward:.2f} em cashback/pontos ({reward_rate:.1%} do valor).",
        )

    def _build_card_parcelado_option(
        self, amount: float, installments: int, card_name: str, reward_rate: float
    ) -> PaymentOption:
        """Parcelamento sem juros no cartão (padrão do mercado brasileiro)."""
        monthly = round(amount / installments, 2)
        reward = round(amount * reward_rate, 2)
        return PaymentOption(
            method=PaymentMethod.CARTAO_PARCELADO,
            label=f"Cartão parcelado {installments}x sem juros ({card_name})",
            total_cost=round(amount, 2),
            monthly_cost=monthly,
            installments=installments,
            reward_value=reward,
            notes=(
                f"{installments}x de R$ {monthly:.2f} sem juros. "
                f"Gera ~R$ {reward:.2f} em cashback/pontos."
            ),
        )

    def _build_financing_option(
        self, amount: float, installments: int, monthly_rate: float
    ) -> PaymentOption:
        """Crédito pessoal CDC com juros (price)."""
        # Fórmula PRICE: PMT = PV × r / (1 − (1+r)^−n)
        r = monthly_rate
        n = installments
        if r > 0:
            pmt = amount * r / (1 - (1 + r) ** -n)
        else:
            pmt = amount / n
        total = round(pmt * n, 2)
        pmt = round(pmt, 2)
        taxa_pct = monthly_rate * 100
        return PaymentOption(
            method=PaymentMethod.FINANCIAMENTO,
            label=f"Crédito pessoal {installments}x (CDC)",
            total_cost=total,
            monthly_cost=pmt,
            installments=installments,
            reward_value=0.0,
            notes=(
                f"Taxa {taxa_pct:.2f}% a.m. | {installments}x de R$ {pmt:.2f} | "
                f"Custo total: R$ {total:.2f} "
                f"(+R$ {total - amount:.2f} de juros)."
            ),
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LÓGICA DE RECOMENDAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _pick_recommendation(
        self,
        options: list[PaymentOption],
        safe_to_spend: float,
        warnings: list[str],
    ) -> PaymentOption:
        """
        Escolhe a melhor opção:
          1. Preferência por menor net_cost entre as acessíveis (net_cost <= safe_to_spend)
          2. Se nenhuma for acessível, escolhe a de menor net_cost e avisa o usuário
        """
        affordable = [o for o in options if o.net_cost <= safe_to_spend]

        if affordable:
            return affordable[0]  # já ordenado por net_cost

        # Nenhuma opção dentro do safe_to_spend
        warnings.append(
            f"Esta compra (R$ {options[0].net_cost:.2f}) excede sua margem atual "
            f"(R$ {safe_to_spend:.2f}). Considere adiar ou reduzir o valor."
        )
        return options[0]

    def _build_liquidity_impact(
        self, net_cost: float, safe_to_spend: float
    ) -> LiquidityImpact:
        after = max(0.0, safe_to_spend - net_cost)
        affordable = net_cost <= safe_to_spend

        if not affordable:
            risk = "CRITICAL"
        elif after < 300:
            risk = "HIGH"
        elif after < 1_000:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return LiquidityImpact(
            safe_to_spend_before=round(safe_to_spend, 2),
            safe_to_spend_after=round(after, 2),
            affordable=affordable,
            risk_level=risk,
        )

    def _build_reasoning(
        self,
        recommended: PaymentOption,
        all_options: list[PaymentOption],
        liquidity: LiquidityImpact,
        request: PurchaseRequest,
    ) -> str:
        lines = [
            f"Para uma compra de R$ {request.amount:,.2f} em {request.category}, "
            f"a opção com menor custo líquido é **{recommended.label}** "
            f"(custo efetivo: R$ {recommended.net_cost:,.2f})."
        ]

        if recommended.reward_value > 0:
            lines.append(
                f"Você gera R$ {recommended.reward_value:.2f} em cashback/pontos, "
                f"reduzindo o custo real da compra."
            )

        if not liquidity.affordable:
            lines.append(
                f"⚠️ Atenção: esta compra excede sua margem disponível "
                f"(R$ {liquidity.safe_to_spend_before:,.2f}). "
                "Considere parcelas menores ou adiar a compra."
            )
        else:
            lines.append(
                f"Após a compra, sua margem restante será de "
                f"R$ {liquidity.safe_to_spend_after:,.2f}."
            )

        worst = max(all_options, key=lambda o: o.net_cost)
        if worst.net_cost > recommended.net_cost:
            saved = round(worst.net_cost - recommended.net_cost, 2)
            lines.append(
                f"Comparado à pior opção ({worst.label}), "
                f"você economiza R$ {saved:.2f}."
            )

        return " ".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONFIDENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _compute_confidence(
        has_transactions: bool,
        has_safe_to_spend: bool,
        has_income: bool,
        warning_count: int,
    ) -> float:
        score = 0.0
        if has_transactions:
            score += 0.40
        if has_safe_to_spend:
            score += 0.30
        if has_income:
            score += 0.30
        score -= min(warning_count * 0.05, 0.20)
        return max(0.10, min(1.00, score))
