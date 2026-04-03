"""
app/purchase/purchase_advisor.py — F7: Modo Compra Inteligente (v2)

Orquestra 7 fontes de dados para recomendar a melhor forma de pagamento:
  1. OptimizerService          → melhor cartão e reward por categoria
  2. BacenConnector            → taxa CDI/CDC atual
  3. SafeToSpendCalculator     → margem disponível (com limiares relativos)
  4. InvoiceHorizon            → pressão da fatura atual
  5. UserProfileAnalyzer       → perfil financeiro (CONSERVADOR/EQUILIBRADO/GASTADOR)
  6. IncomeProfiler            → renda mensal líquida real
  7. SpendingAnomalyDetector   → anomalias recentes na categoria da compra

Lógica de ranqueamento (v2):
  - Ordena por net_cost_real (inclui custo/ganho de oportunidade CDI)
  - Aplica profile_fit por opção (IDEAL/OK/CAUTELA/EVITAR)
  - Penaliza cartão se invoice_pressure for CRITICAL/HEAVY
  - Reasoning contextualizado em 3 blocos: recomendação, situação, histórico
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
from app.purchase.opportunity_cost import apply_opportunity_cost
from app.purchase.profile_context import build_profile_context, apply_profile_fit

logger = logging.getLogger(__name__)

_FINANCING_MIN_AMOUNT = 1_000.0
_FINANCING_FALLBACK_MONTHLY_RATE = 0.0415
_CDI_FALLBACK = 0.1475


class PurchaseAdvisor:
    """
    Analisa uma compra e retorna a recomendação de forma de pagamento.

    Usage:
        advisor = PurchaseAdvisor()
        result  = advisor.analyze(request)
    """

    def analyze(self, request: PurchaseRequest) -> PurchaseRecommendation:
        logger.info(
            "PurchaseAdvisor v2 | user=%s amount=%.2f category=%s installments=%d",
            request.user_id, request.amount, request.category, request.installments,
        )

        warnings: list[str] = []
        data_sources: list[str] = []

        # ── 1. Transações ────────────────────────────────────────────
        transactions_df = self._fetch_transactions(request.user_id)
        if not transactions_df.is_empty():
            data_sources.append("transactions_db")
        else:
            warnings.append("Sem histórico de transações: recomendação baseada apenas no valor informado.")

        # ── 2. Renda mensal ──────────────────────────────────────────
        income_profile = self._fetch_income_profile(transactions_df)
        monthly_income: float = (
            request.monthly_income
            or (income_profile.monthly_net_income if income_profile else None)
            or 0.0
        )
        if income_profile and income_profile.confidence >= 0.5:
            data_sources.append("income_profiler")

        # ── 3. Perfil financeiro ─────────────────────────────────────
        fin_profile = self._fetch_financial_profile(transactions_df, income_profile)
        if fin_profile:
            data_sources.append("user_profile_analyzer")

        # ── 4. Perfil de consumo (committed_percentage) ──────────────
        consumption_profile = self._fetch_consumption_profile(transactions_df)
        committed_pct: float = (
            consumption_profile.committed_percentage if consumption_profile else 0.0
        )

        # ── 5. Safe-to-spend (com renda para limiares relativos) ─────
        safe_to_spend_result = self._fetch_safe_to_spend_result(
            request.user_id, transactions_df, monthly_income or None
        )
        safe_to_spend: float = (
            safe_to_spend_result.safe_to_spend_total if safe_to_spend_result else 0.0
        )
        if safe_to_spend_result is not None:
            data_sources.append("f1_safe_to_spend")
        else:
            warnings.append("Safe-to-spend indisponível: impacto no orçamento não calculado.")

        # ── 6. Pressão de fatura ─────────────────────────────────────
        invoice_horizon = self._fetch_invoice_horizon(
            transactions_df=transactions_df,
            user_id=request.user_id,
            monthly_income=monthly_income,
        )
        if invoice_horizon:
            data_sources.append("invoice_horizon")

        # ── 7. Melhor cartão ─────────────────────────────────────────
        best_card_name, reward_rate, card_warning = self._fetch_best_card(
            request=request, transactions_df=transactions_df
        )
        if card_warning:
            warnings.append(card_warning)
        else:
            data_sources.append("optimizer_f2")

        # ── 8. Taxa CDI / CDC ────────────────────────────────────────
        cdi_annual, monthly_rate, rate_warning = self._fetch_rates()
        if rate_warning:
            warnings.append(rate_warning)
        else:
            data_sources.append("bacen_cdc")

        # ── 9. Anomalias na categoria ────────────────────────────────
        anomaly_pressure, anomaly_notes = self._fetch_anomaly_context(
            transactions_df=transactions_df,
            category=request.category,
        )

        # ── 10. Contexto de perfil e pressure_score ─────────────────
        profile_ctx = None
        pressure_score: float = 0.0
        profile_summary: Optional[str] = None

        if fin_profile and monthly_income > 0:
            profile_ctx = build_profile_context(
                profile_type=fin_profile.profile_type,
                savings_rate=fin_profile.savings_rate,
                trend=fin_profile.trend,
                health_score=fin_profile.financial_health_score,
                committed_pct=committed_pct,
                monthly_income=monthly_income,
                safe_to_spend=safe_to_spend,
            )
            pressure_score = min(1.0, profile_ctx.pressure_score + anomaly_pressure)
            profile_summary = profile_ctx.summary

        # ── 11. Montar opções de pagamento ───────────────────────────
        options: list[PaymentOption] = []
        options.append(self._build_pix_option(request.amount))
        options.append(self._build_card_avista_option(request.amount, best_card_name, reward_rate))

        if request.installments > 1:
            options.append(
                self._build_card_parcelado_option(
                    amount=request.amount,
                    installments=request.installments,
                    card_name=best_card_name,
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

        # ── 12. Custo de oportunidade CDI ────────────────────────────
        if request.apply_opportunity_cost:
            options = [apply_opportunity_cost(opt, cdi_annual) for opt in options]

        # ── 13. Profile fit por opção ────────────────────────────────
        if fin_profile:
            safe_ratio = safe_to_spend / monthly_income if monthly_income > 0 else 0.0
            options = apply_profile_fit(
                options=options,
                pressure_score=pressure_score,
                profile_type=fin_profile.profile_type,
                category=request.category,
                installments=request.installments,
                safe_to_spend_ratio=safe_ratio,
                committed_pct=committed_pct,
            )

        # ── 14. Penalidade de fatura no cartão ───────────────────────
        if invoice_horizon and invoice_horizon.invoice_pressure in ("CRITICAL", "HEAVY"):
            options = self._apply_invoice_penalty(options, invoice_horizon.invoice_pressure)

        # ── 15. Ranquear por net_cost_real ───────────────────────────
        options.sort(key=lambda o: o.net_cost_real if o.net_cost_real is not None else o.net_cost)

        # ── 16. Escolher recomendação ────────────────────────────────
        recommended = self._pick_recommendation(options, safe_to_spend, warnings)

        # ── 17. Impacto de liquidez ──────────────────────────────────
        liquidity = self._build_liquidity_impact(
            option=recommended,
            safe_to_spend=safe_to_spend,
        )

        # ── 18. Confidence score ─────────────────────────────────────
        confidence = self._compute_confidence(
            has_transactions=not transactions_df.is_empty(),
            has_safe_to_spend=safe_to_spend_result is not None,
            has_income=monthly_income > 0,
            has_profile=fin_profile is not None,
            warning_count=len(warnings),
        )

        # ── 19. Reasoning contextualizado ───────────────────────────
        reasoning = self._build_reasoning(
            recommended=recommended,
            all_options=options,
            liquidity=liquidity,
            request=request,
            invoice_horizon=invoice_horizon,
            profile_ctx=profile_ctx,
            fin_profile=fin_profile,
            monthly_income=monthly_income,
            anomaly_notes=anomaly_notes,
            cdi_annual=cdi_annual,
        )

        return PurchaseRecommendation(
            user_id=request.user_id,
            amount=request.amount,
            category=request.category,
            recommended_method=recommended.method,
            recommended_label=recommended.label,
            recommended_net_cost=recommended.net_cost,
            reasoning=reasoning,
            options=options,
            liquidity_impact=liquidity,
            confidence_score=round(confidence, 2),
            data_sources=data_sources,
            warnings=warnings,
            invoice_horizon=invoice_horizon.to_dict() if invoice_horizon else None,
            pressure_score=round(pressure_score, 2) if pressure_score else None,
            profile_summary=profile_summary,
            cdi_rate_used=round(cdi_annual, 4),
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FETCH HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _fetch_transactions(self, user_id: str) -> pl.DataFrame:
        try:
            from app.core.db.queries import get_transactions_for_user
            return get_transactions_for_user(user_id)
        except Exception as exc:
            logger.warning("PurchaseAdvisor | erro ao buscar transações: %s", exc)
            return pl.DataFrame()

    def _fetch_income_profile(self, transactions_df: pl.DataFrame):
        if transactions_df.is_empty():
            return None
        try:
            from app.forecast.etl.income_profiler import IncomeProfiler
            return IncomeProfiler().analyze(transactions_df)
        except Exception as exc:
            logger.warning("PurchaseAdvisor | IncomeProfiler falhou: %s", exc)
            return None

    def _fetch_financial_profile(self, transactions_df: pl.DataFrame, income_profile):
        if transactions_df.is_empty():
            return None
        try:
            from app.forecast.etl.profiles import UserProfileAnalyzer
            return UserProfileAnalyzer().analyze(transactions_df, income_profile)
        except Exception as exc:
            logger.warning("PurchaseAdvisor | UserProfileAnalyzer falhou: %s", exc)
            return None

    def _fetch_consumption_profile(self, transactions_df: pl.DataFrame):
        if transactions_df.is_empty():
            return None
        try:
            from app.optimizer.profiler import ConsumptionProfiler
            return ConsumptionProfiler().build(transactions_df)
        except Exception as exc:
            logger.warning("PurchaseAdvisor | ConsumptionProfiler falhou: %s", exc)
            return None

    def _fetch_safe_to_spend_result(
        self,
        user_id: str,
        transactions_df: pl.DataFrame,
        income_monthly: Optional[float],
    ):
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
            return SafeToSpendCalculator().calculate(
                projection_df, horizon_days=30, income_monthly=income_monthly
            )
        except Exception as exc:
            logger.warning("PurchaseAdvisor | safe_to_spend falhou: %s", exc)
            return None

    def _fetch_invoice_horizon(
        self,
        transactions_df: pl.DataFrame,
        user_id: str,
        monthly_income: float,
    ):
        if monthly_income <= 0:
            return None
        try:
            from app.forecast.cashflow.invoice_horizon import build_invoice_horizon
            from app.core.db.queries import get_shadow_invoices_for_user

            shadow_invoices = []
            try:
                shadow_invoices = get_shadow_invoices_for_user(user_id)
            except Exception:
                pass  # sem shadow invoices — ainda útil calcular ciclo atual

            return build_invoice_horizon(
                transactions_df=transactions_df,
                shadow_invoices=shadow_invoices,
                monthly_income=monthly_income,
            )
        except Exception as exc:
            logger.warning("PurchaseAdvisor | InvoiceHorizon falhou: %s", exc)
            return None

    def _fetch_best_card(
        self, request: PurchaseRequest, transactions_df: pl.DataFrame
    ) -> tuple[str, float, Optional[str]]:
        try:
            from app.optimizer.models import OptimizationRequest
            from app.optimizer.services.optimizer_service import OptimizerService

            opt_req = OptimizationRequest(
                user_id=request.user_id,
                monthly_income=request.monthly_income,
            )
            report = OptimizerService().analyze(
                request=opt_req, transactions_df=transactions_df
            )
            if report.best_card:
                card = report.best_card
                monthly_spend = max(request.amount, 1.0)
                reward_rate = (
                    card.points_value_expected / (monthly_spend * 12)
                    if card.points_value_expected and monthly_spend > 0
                    else 0.0
                )
                reward_rate = min(reward_rate, 0.05)
                return card.card_name, reward_rate, None
        except Exception as exc:
            logger.warning("PurchaseAdvisor | OptimizerService falhou: %s", exc)

        return "seu cartão atual", 0.0, "Não foi possível identificar o melhor cartão — usando sem reward."

    def _fetch_rates(self) -> tuple[float, float, Optional[str]]:
        """Retorna (cdi_annual, monthly_cdc_rate, warning_ou_None)."""
        try:
            from app.architect.connectors.bacen import BacenConnector
            selic_annual = BacenConnector().get_selic()
            monthly_rate = (selic_annual / 12) + 0.025
            return selic_annual, monthly_rate, None
        except Exception as exc:
            logger.warning("PurchaseAdvisor | BACEN indisponível: %s", exc)
            return (
                _CDI_FALLBACK,
                _FINANCING_FALLBACK_MONTHLY_RATE,
                "Taxa CDI/CDC baseada em referência de mercado (BACEN indisponível).",
            )

    def _fetch_anomaly_context(
        self, transactions_df: pl.DataFrame, category: str
    ) -> tuple[float, list[str]]:
        """
        Retorna (pressure_bonus, notas de anomalia).
        pressure_bonus: +0.10 por anomalia ativa na categoria (máx 0.20).
        """
        if transactions_df.is_empty():
            return 0.0, []
        try:
            from app.forecast.etl.spending_anomaly_detector import SpendingAnomalyDetector

            anomalies = SpendingAnomalyDetector().detect(
                transactions_df=transactions_df,
                history_df=transactions_df,
            )
            category_lower = category.lower()
            notes: list[str] = []
            bonus = 0.0

            for a in anomalies:
                desc_lower = a.description.lower()
                if category_lower not in desc_lower:
                    continue
                if a.anomaly_type.value == "UNUSUAL_AMOUNT":
                    notes.append(f"Você teve um gasto incomum em {category} recentemente.")
                    bonus = min(0.20, bonus + 0.10)
                elif a.anomaly_type.value == "FREQUENCY_SPIKE":
                    notes.append(
                        f"Você está comprando em {category} com frequência acima do seu padrão."
                    )
                    bonus = min(0.20, bonus + 0.10)

            return bonus, notes
        except Exception as exc:
            logger.warning("PurchaseAdvisor | SpendingAnomalyDetector falhou: %s", exc)
            return 0.0, []

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
            notes="Sem juros, sem cashback. Melhor para negociar desconto à vista.",
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
        monthly = round(amount / installments, 2)
        reward = round(amount * reward_rate, 2)
        return PaymentOption(
            method=PaymentMethod.CARTAO_PARCELADO,
            label=f"Cartão {installments}x sem juros ({card_name})",
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
        r, n = monthly_rate, installments
        pmt = amount * r / (1 - (1 + r) ** -n) if r > 0 else amount / n
        total = round(pmt * n, 2)
        pmt = round(pmt, 2)
        return PaymentOption(
            method=PaymentMethod.FINANCIAMENTO,
            label=f"Crédito pessoal {installments}x (CDC)",
            total_cost=total,
            monthly_cost=pmt,
            installments=installments,
            reward_value=0.0,
            notes=(
                f"Taxa {monthly_rate * 100:.2f}% a.m. | {installments}x de R$ {pmt:.2f} | "
                f"Custo total: R$ {total:.2f} (+R$ {total - amount:.2f} de juros)."
            ),
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LÓGICA DE RECOMENDAÇÃO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _apply_invoice_penalty(
        self, options: list[PaymentOption], pressure: str
    ) -> list[PaymentOption]:
        """
        Quando a fatura está CRITICAL ou HEAVY, move opções de cartão para o fim
        da lista trocando o net_cost_real por um valor penalizado (não bloqueia).
        """
        penalized = []
        for opt in options:
            if opt.method in (PaymentMethod.CARTAO_AVISTA, PaymentMethod.CARTAO_PARCELADO):
                penalty = opt.net_cost_real * 1.20 if pressure == "CRITICAL" else opt.net_cost_real * 1.10
                penalized.append(opt.model_copy(update={"net_cost_real": round(penalty, 2)}))
            else:
                penalized.append(opt)
        return penalized

    def _pick_recommendation(
        self,
        options: list[PaymentOption],
        safe_to_spend: float,
        warnings: list[str],
    ) -> PaymentOption:
        # Critério: se não temos safe_to_spend (> 0), evite avisar e devolva a opção de menor custo real
        def _best_by_cost(opts: list[PaymentOption]) -> PaymentOption:
            not_avoid = [o for o in opts if o.profile_fit != "EVITAR"]
            return not_avoid[0] if not_avoid else opts[0]

        if safe_to_spend is None or safe_to_spend <= 0:
            return _best_by_cost(options)

        # Definir critério de impacto mensal: se parcelado use monthly_cost, senão total_cost
        def monthly_outflow(o: PaymentOption) -> float:
            return o.monthly_cost if (o.monthly_cost is not None and o.installments and o.installments > 1) else o.total_cost

        # Filtra opções que cabem na margem mensal
        affordable = [o for o in options if monthly_outflow(o) <= safe_to_spend]
        if affordable:
            return _best_by_cost(affordable)

        # Nenhuma opção acessível mensalmente: avisar e retornar a de menor custo real
        warnings.append(
            f"Esta compra (R$ {options[0].net_cost_real or options[0].net_cost:.2f}) excede sua margem atual "
            f"(R$ {safe_to_spend:.2f}). Considere adiar ou reduzir o valor."
        )
        return _best_by_cost(options)

    def _build_liquidity_impact(
        self, option: PaymentOption, safe_to_spend: float
    ) -> LiquidityImpact:
        """
        Calcula impacto de liquidez comparando a saída mensal esperada com o safe_to_spend.
        Para parcelado sem juros usa `monthly_cost`; para à vista/PIX considera o total no mês corrente.
        """
        monthly = option.monthly_cost if (option.monthly_cost is not None and option.installments and option.installments > 1) else option.total_cost
        after = max(0.0, safe_to_spend - monthly)
        affordable = monthly <= safe_to_spend

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
        invoice_horizon,
        profile_ctx,
        fin_profile,
        monthly_income: float,
        anomaly_notes: list[str],
        cdi_annual: float,
    ) -> str:
        lines: list[str] = []

        # ── Bloco 1: O que recomendo e por quê ──────────────────────
        cost_real = recommended.net_cost_real if recommended.net_cost_real is not None else recommended.net_cost
        lines.append(
            f"Para R$ {request.amount:,.2f} em {request.category}, "
            f"a recomendação é **{recommended.label}** "
            f"(custo efetivo: R$ {cost_real:,.2f})."
        )

        if recommended.opportunity_cost_gain > 0 and recommended.method == PaymentMethod.CARTAO_PARCELADO:
            lines.append(
                f"O capital parcelado rende ~R$ {recommended.opportunity_cost_gain:.2f} no CDI "
                f"({cdi_annual:.1%} a.a.) durante as {recommended.installments} parcelas — "
                f"tornando o parcelamento R$ {recommended.opportunity_cost_gain:.2f} mais barato que à vista."
            )
        elif recommended.reward_value > 0:
            lines.append(
                f"Você gera R$ {recommended.reward_value:.2f} em cashback/pontos, reduzindo o custo real."
            )
        # Comparação com a pior opção (considerando net_cost_real quando disponível)
        worst = max(all_options, key=lambda o: (o.net_cost_real if getattr(o, 'net_cost_real', None) is not None else o.net_cost))
        worst_cost = worst.net_cost_real if getattr(worst, 'net_cost_real', None) is not None else worst.net_cost
        if worst_cost > cost_real:
            saved = round(worst_cost - cost_real, 2)
            lines.append(
                f"Comparado à pior opção ({worst.label}), você economiza R$ {saved:.2f}."
            )

        # ── Bloco 2: Como isso afeta sua situação atual ─────────────
        if not liquidity.affordable:
            lines.append(
                f"⚠️ Esta compra excede sua margem disponível "
                f"(R$ {liquidity.safe_to_spend_before:,.2f}). "
                "Considere parcelas menores ou adiar a compra."
            )
        elif monthly_income > 0:
            ratio_pct = liquidity.safe_to_spend_before / monthly_income * 100
            lines.append(
                f"Seu safe-to-spend é R$ {liquidity.safe_to_spend_before:,.2f} "
                f"({ratio_pct:.0f}% da renda). "
                f"Após a compra: R$ {liquidity.safe_to_spend_after:,.2f}."
            )
        else:
            lines.append(
                f"Após a compra, sua margem restante será de R$ {liquidity.safe_to_spend_after:,.2f}."
            )

        if invoice_horizon:
            pressure = invoice_horizon.invoice_pressure
            if pressure == "CRITICAL":
                lines.append(
                    f"⚠️ Fatura fecha em {invoice_horizon.days_to_close} dia(s) com "
                    f"R$ {invoice_horizon.current_cycle_committed:,.2f} já comprometidos "
                    f"({invoice_horizon.total_committed / invoice_horizon.monthly_income:.0%} da renda) — "
                    "prefira PIX para evitar rotativo."
                )
            elif pressure == "HEAVY":
                lines.append(
                    f"Fatura fecha em {invoice_horizon.days_to_close} dias com "
                    f"R$ {invoice_horizon.total_committed:,.2f} comprometidos — "
                    "atenção ao impacto no ciclo atual."
                )

        # ── Bloco 3: Histórico e alertas de perfil ──────────────────
        if profile_ctx:
            lines.append(profile_ctx.summary)

        if fin_profile and fin_profile.trend == "CRESCENTE":
            lines.append("Seus gastos gerais estão em tendência crescente — monitore o orçamento.")

        for note in anomaly_notes:
            lines.append(note)

        if recommended.profile_fit == "CAUTELA":
            lines.append("Atenção: esta opção merece cuidado dado seu perfil financeiro atual.")
        elif recommended.profile_fit == "EVITAR":
            lines.append("⚠️ Esta opção não é recomendada para seu perfil — considere as alternativas.")

        return " ".join(lines)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CONFIDENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _compute_confidence(
        has_transactions: bool,
        has_safe_to_spend: bool,
        has_income: bool,
        has_profile: bool,
        warning_count: int,
    ) -> float:
        score = 0.0
        if has_transactions:
            score += 0.35
        if has_safe_to_spend:
            score += 0.25
        if has_income:
            score += 0.25
        if has_profile:
            score += 0.15
        score -= min(warning_count * 0.05, 0.20)
        return max(0.10, min(1.00, score))
