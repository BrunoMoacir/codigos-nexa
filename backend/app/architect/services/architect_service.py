"""
app/architect/services/architect_service.py - Orquestrador da F3

Feature: F3 - Nexa Architect
Version: 1.0.0

Responsabilidade:
    Ponto único de entrada da lógica de negócio da F3.
    Orquestra, em ordem:
        1. Validação de inputs (InputValidator)
        2. Busca de taxas de mercado (BacenConnector, AnbimaConnector, MarketRatesConnector)
        3. Simulação das 3 estratégias (StrategyEngine)
        4. Cálculo de liquidez real (LiquidityValidator)
        5. Consolidação da resposta final (warnings + confidence_score)

Integração com F1 (Core Engine):
    O safe_to_spend da F1 requer o pipeline ETL completo (Pluggy → ETL → Cashflow).
    Por isso, o service NÃO chama a F1 diretamente — ele recebe `safe_to_spend`
    como parâmetro opcional. A rota (architect.py) é responsável por buscar
    esse dado da F1 e passá-lo aqui.

    Se safe_to_spend=None, o LiquidityValidator usa max_monthly_budget como fallback
    e registra um aviso na resposta.

Usage:
    from app.architect.services.architect_service import ArchitectService

    service = ArchitectService()
    response = service.simulate(request, safe_to_spend=8500.0)
"""

import logging
from typing import Optional

from app.architect.connectors.abac import AbacConnector
from app.architect.connectors.anbima import AnbimaConnector
from app.architect.connectors.bacen import BacenConnector
from app.architect.connectors.consortium_rate_provider import ConsortiumRateProvider
from app.architect.connectors.ipca import IPCAConnector
from app.architect.connectors.market_rates import MarketRatesConnector
from app.architect.models import (
    CardOptimizationBonus,
    SimulationRequest,
    SimulationResponse,
    StrategyType,
)
from app.architect.simulators.strategy_engine import StrategyEngine
from app.architect.validators.input_validator import InputValidator
from app.architect.validators.liquidity_validator import LiquidityValidator, RiskLevel

logger = logging.getLogger(__name__)


class ArchitectService:
    """
    Orquestrador central da F3 — Nexa Architect.

    Instância única por processo (stateless exceto pelos conectores,
    que mantêm cache em memória com TTL).

    Args:
        bacen:         Conector BACEN (SELIC). Injetável para testes.
        anbima:        Conector ANBIMA (CDI). Injetável para testes.
        market_rates:  Conector de CETs. Injetável para testes.
        abac:          Conector ABAC (estatísticas de consórcio). Injetável para testes.
        engine:        StrategyEngine. Injetável para testes.

    Example:
        >>> service = ArchitectService()
        >>> response = service.simulate(request, safe_to_spend=9000.0)
        >>> print(response.recommended_strategy)
    """

    def __init__(
        self,
        bacen: Optional[BacenConnector] = None,
        anbima: Optional[AnbimaConnector] = None,
        market_rates: Optional[MarketRatesConnector] = None,
        abac: Optional[AbacConnector] = None,
        ipca: Optional[IPCAConnector] = None,
        consortium_provider: Optional[ConsortiumRateProvider] = None,
        engine: Optional[StrategyEngine] = None,
    ) -> None:
        self._bacen        = bacen        or BacenConnector()
        self._anbima       = anbima       or AnbimaConnector()
        self._market_rates = market_rates or MarketRatesConnector()
        self._abac         = abac         or AbacConnector()
        self._ipca         = ipca         or IPCAConnector()
        # ConsortiumRateProvider recebe as mesmas instâncias de abac e ipca
        # para compartilhar o cache — sem duplo fetch
        self._consortium_provider = consortium_provider or ConsortiumRateProvider(
            abac=self._abac,
            ipca=self._ipca,
        )
        self._engine       = engine       or StrategyEngine()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PONTO DE ENTRADA PRINCIPAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def simulate(
        self,
        request: SimulationRequest,
        safe_to_spend: Optional[float] = None,
        transactions_df=None,
    ) -> SimulationResponse:
        """
        Executa a simulação completa e retorna a recomendação.

        Args:
            request:       Parâmetros de entrada (já validados pelo Pydantic).
            safe_to_spend: Valor mensal disponível calculado pela F1 (R$).
                           None se F1 não estiver disponível.

        Returns:
            SimulationResponse com estratégia recomendada, custos, NPV,
            impacto de liquidez, plano de ação e score de confiança.

        Raises:
            ValueError: Se o request falhar nas validações de negócio.
        """
        logger.info(
            "simulate | user=%s target=%.2f safe_to_spend=%s",
            request.user_id,
            request.target_amount,
            safe_to_spend,
        )

        # ── 1. Validar inputs ────────────────────────────────────────
        accumulated_warnings: list[str] = []
        self._validate_or_raise(request, accumulated_warnings)

        # ── 1.5 Inferir risk_profile do histórico se não informado ───
        request = self._infer_risk_profile(request, transactions_df, accumulated_warnings)

        # ── 2. Buscar taxas de mercado ───────────────────────────────
        market_rates, rate_warnings = self._fetch_market_rates(request)
        accumulated_warnings.extend(rate_warnings)

        # ── 3. Simular estratégias ───────────────────────────────────
        base_response = self._engine.simulate(request, market_rates)
        # Preserva warnings gerados pelo engine (perfil de risco, depreciação, etc.)
        accumulated_warnings.extend(base_response.warnings)

        # ── 4. Recalcular liquidez com safe_to_spend real ────────────
        monthly_payment = self._estimate_monthly_payment(base_response, request)
        liquidity = LiquidityValidator.calculate(
            monthly_payment=monthly_payment,
            safe_to_spend=safe_to_spend,
            max_monthly_budget=request.max_monthly_budget,
        )
        accumulated_warnings.extend(liquidity.warnings)

        # ── 5. Calcular confidence_score ─────────────────────────────
        confidence = self._compute_confidence(
            base_confidence=base_response.confidence_score,
            has_f1_data=(safe_to_spend is not None),
            used_fallback_rates=bool(rate_warnings),
            warning_count=len(accumulated_warnings),
        )

        # ── 6. Consolidar data_sources ───────────────────────────────
        data_sources = list(base_response.data_sources)
        if safe_to_spend is not None:
            data_sources.append("f1_safe_to_spend")
        # ABAC sempre consultado para simulações de consórcio (Fase 2)
        if request.include_consortium and "abac" not in data_sources:
            data_sources.append("abac")
        # IPCA — M3.1
        if "ipca" not in data_sources:
            data_sources.append("ipca")

        # ── 7. M3.3 — Custo de oportunidade cruzado F3↔F2 ───────────
        card_bonus: Optional[CardOptimizationBonus] = None
        if base_response.recommended_strategy in (StrategyType.FINANCING, StrategyType.FINANCING_RENTAL):
            card_bonus = self._compute_card_optimization_bonus(
                monthly_payment=monthly_payment,
                financing_months=request.financing_months,
                user_id=request.user_id,
                monthly_income=request.monthly_income,
                transactions_df=transactions_df,
            )
            source = "optimizer_f2" if card_bonus and card_bonus.best_card_name != "melhor cartão premium de mercado" else "market_reference_estimate"
            data_sources.append(source)

            # Penalizar confidence quando o melhor cartão tem risco de liquidez alto.
            if card_bonus and card_bonus.liquidity_risk in ("HIGH", "CRITICAL"):
                confidence = max(0.30, confidence - 0.05)
                accumulated_warnings.append(
                    f"O cartão recomendado ({card_bonus.best_card_name}) apresenta risco de liquidez "
                    f"{card_bonus.liquidity_risk} para sua margem atual — avalie se a anuidade é sustentável."
                )

        # ── 7b. Validar parcela contra orçamento ideal (BudgetAdvisor) ──
        confidence = self._adjust_confidence_budget(
            confidence=confidence,
            monthly_payment=monthly_payment,
            monthly_income=request.monthly_income,
            transactions_df=transactions_df,
            strategy=base_response.recommended_strategy,
            warnings=accumulated_warnings,
            data_sources=data_sources,
        )

        # ── 7c. Validar aportes contra metas ativas (GoalTracker) ──────
        confidence = self._adjust_confidence_goals(
            confidence=confidence,
            monthly_payment=monthly_payment,
            user_id=request.user_id,
            strategy=base_response.recommended_strategy,
            warnings=accumulated_warnings,
            data_sources=data_sources,
        )

        # ── 8. Montar resposta final ─────────────────────────────────
        return base_response.model_copy(
            update={
                "liquidity_impact": liquidity.impact,
                "warnings": accumulated_warnings,
                "confidence_score": round(confidence, 2),
                "data_sources": data_sources,
                "card_optimization_bonus": card_bonus,
            }
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _validate_or_raise(
        self,
        request: SimulationRequest,
        warnings: list[str],
    ) -> None:
        """
        Valida o request com regras de negócio.
        Erros bloqueantes lançam ValueError.
        Avisos são adicionados à lista `warnings`.
        """
        result = InputValidator.validate(request)
        warnings.extend(result.warnings)

        if not result.is_valid:
            logger.warning(
                "simulate | user=%s | validação falhou: %s",
                request.user_id,
                result.errors,
            )
            raise ValueError(f"Request inválido: {'; '.join(result.errors)}")

    def fetch_market_rates(
        self, request: SimulationRequest
    ) -> dict[str, float]:
        """
        Versão pública de _fetch_market_rates — retorna apenas as taxas (sem warnings).

        Útil para endpoints que precisam das taxas sem executar a simulação completa
        (ex: GET /architect/simulations/{id}/sensitivity).

        Args:
            request: SimulationRequest com asset_type para selecionar o CET correto.

        Returns:
            Dict com selic_annual, cdi_annual, best_cet_annual e estatísticas de consórcio.
        """
        rates, _ = self._fetch_market_rates(request)
        return rates

    def _fetch_market_rates(
        self, request: SimulationRequest
    ) -> tuple[dict[str, float], list[str]]:
        """
        Busca SELIC, CDI e CET do mercado.

        Retorna (rates_dict, warnings). Se algum conector falhar,
        o fallback hardcoded é usado silenciosamente, mas um aviso
        é registrado no response.

        Returns:
            (market_rates, warnings)
        """
        warnings: list[str] = []

        # SELIC
        try:
            selic = self._bacen.get_selic()
        except Exception as exc:
            logger.warning("BACEN indisponível: %s — usando fallback", exc)
            selic = self._bacen.get_fallback_rates()["selic_annual"]
            warnings.append("Taxa SELIC obtida de dados de referência (BACEN indisponível).")

        # CDI
        try:
            cdi = self._anbima.get_cdi()
        except Exception as exc:
            logger.warning("ANBIMA indisponível: %s — usando fallback", exc)
            cdi = self._anbima.get_fallback_rates()["cdi_annual"]
            warnings.append("Taxa CDI obtida de dados de referência (ANBIMA indisponível).")

        # CET para o tipo de bem
        asset_type = request.asset_type.value
        try:
            best_cet = self._market_rates.get_best_cet(asset_type)
        except Exception as exc:
            logger.warning("MarketRates indisponível: %s — usando fallback", exc)
            fb = self._market_rates.get_fallback_rates()
            best_cet = fb.get(f"cet_{asset_type}_min", 0.15)
            warnings.append("CET de mercado obtido de dados de referência.")

        # IPCA — M3.1: ajuste por inflação (também usado pelo ConsortiumRateProvider)
        try:
            ipca_annual = self._ipca.get_ipca()
        except Exception as exc:
            logger.warning("IPCA indisponível: %s — usando fallback", exc)
            ipca_annual = self._ipca.get_fallback_rates()["ipca_annual"]
            warnings.append("IPCA obtido de dados de referência (BCB indisponível).")

        # Parâmetros de consórcio — ConsortiumRateProvider (ABAC + IPCA)
        # O provider usa as mesmas instâncias de _abac e _ipca (cache compartilhado).
        try:
            cons_params = self._consortium_provider.get_params(asset_type)
            if cons_params.using_incc_approximation:
                logger.info(
                    "ConsortiumRateProvider: reajuste IMOVEL via INCC≈IPCA×1.5 (%.2f%%)",
                    cons_params.annual_adjustment_rate * 100,
                )
        except Exception as exc:
            logger.warning(
                "ConsortiumRateProvider falhou: %s — usando fallback hardcoded", exc
            )
            cons_params = self._consortium_provider.get_fallback_params(asset_type)
            warnings.append(
                "Parâmetros de consórcio obtidos de dados de referência "
                "(ABAC/IPCA indisponíveis)."
            )

        return {
            "selic_annual":    selic,
            "cdi_annual":      cdi,
            "best_cet_annual": best_cet,
            "ipca_annual":     ipca_annual,
            **cons_params.to_rates_dict(),
        }, warnings

    @staticmethod
    def _estimate_monthly_payment(
        response: SimulationResponse,
        request: SimulationRequest,
    ) -> float:
        """
        Estima a parcela mensal efetiva da estratégia recomendada.

        Usado como entrada do LiquidityValidator. Cada estratégia tem
        uma lógica diferente para chegar ao compromisso mensal de caixa.

        - FINANCING:   custo total / prazo do financiamento (parcela fixa PRICE)
        - SAVE_INVEST: custo total / meses de acumulação (aporte mensal)
        - CONSORTIUM:  custo total / meses de acumulação (parcela mensal)

        Limitação (MVP): para SAC, retorna a parcela média (custo_total / n_meses),
        não a parcela inicial (a mais alta). O LiquidityValidator pode subestimar
        o impacto real no mês 1 quando amortization_method=SAC. Aceitável enquanto
        PRICE for o default, pois para PRICE custo_total / n_meses == parcela fixa.
        """
        # Estratégias compostas: usar custo líquido (após aluguel/SELIC)
        if response.recommended_strategy in (
            StrategyType.FINANCING_RENTAL,
            StrategyType.CONSORTIUM_SELIC_RENTAL,
        ):
            if response.compound_strategies:
                for leg in response.compound_strategies:
                    if leg.strategy_type == response.recommended_strategy:
                        return leg.monthly_net_cost
            # Fallback improvável: usa custo bruto do contrato
            return round(response.costs.expected_cost / max(request.financing_months, 1), 2)

        expected_cost = response.costs.expected_cost
        months_to_achieve = max(response.months_to_achieve, 1)

        if response.recommended_strategy == StrategyType.FINANCING:
            # months_to_achieve = 1 (aquisição imediata) — usar prazo real do contrato
            denominator = max(request.financing_months, 1)
        else:
            # SAVE_INVEST e CONSORTIUM: meses até ter o bem
            denominator = months_to_achieve

        return round(expected_cost / denominator, 2)

    @staticmethod
    def _infer_risk_profile(
        request: "SimulationRequest",
        transactions_df,
        warnings: list[str],
    ) -> "SimulationRequest":
        """
        Infere risk_profile e risk_score do histórico de transações via RiskScorer.

        Usa scoring multidimensional (4 componentes) em vez do mapeamento binário
        savings_rate → {CONSERVADOR, EQUILIBRADO, GASTADOR} → {CONSERVADOR, MODERADO}.

        Se risk_profile foi declarado explicitamente pelo usuário, ainda computa
        risk_score para alimentar os thresholds interpolados do engine — mas não
        sobrescreve o risk_profile declarado.
        """
        from app.architect.validators.risk_scorer import RiskScorer

        if transactions_df is None:
            return request

        try:
            from app.forecast.etl.income_profiler import IncomeProfiler
            from app.forecast.etl.profiles import UserProfileAnalyzer

            income_profile = IncomeProfiler().build(transactions_df)
            fin_profile = UserProfileAnalyzer().analyze(transactions_df, income_profile)

            risk_result = RiskScorer.score(
                request=request,
                income_profile=income_profile,
                user_profile=fin_profile,
                transactions_df=transactions_df,
            )

            tier = getattr(fin_profile, "behavior_tier", fin_profile.profile_type)
            resilience = getattr(fin_profile, "resilience_score", fin_profile.financial_health_score)

            updates: dict = {"risk_score": risk_result.score}

            if request.risk_profile is None:
                updates["risk_profile"] = risk_result.profile
                warnings.append(
                    f"Perfil de risco inferido: {risk_result.profile.value} "
                    f"(score={risk_result.score:.2f}, tier={tier}, "
                    f"savings={fin_profile.savings_rate:.0f}%, "
                    f"resilience={resilience})."
                )
            else:
                warnings.append(
                    f"Risk score calculado: {risk_result.score:.2f} "
                    f"(perfil declarado: {request.risk_profile.value})."
                )

            return request.model_copy(update=updates)

        except Exception as exc:
            logger.warning("ArchitectService | inferência de risk_profile falhou: %s", exc)
            return request

    @staticmethod
    def _compute_card_optimization_bonus(
        monthly_payment: float,
        financing_months: int,
        pts_per_brl: float = 2.0,
        point_value_brl: float = 0.016,
        best_card_name: str = "melhor cartão premium de mercado",
        user_id: Optional[str] = None,
        monthly_income: Optional[float] = None,
        transactions_df=None,
    ) -> CardOptimizationBonus:
        """
        M3.3 — Calcula o retorno de pontos/cashback ao pagar parcelas no melhor cartão.

        Usa valores de referência de mercado (2 pts/R$ × R$ 0,016/ponto ≈ 3,2% de retorno),
        representativo de cartões como Itaucard Ultravioleta, C6 Carbon e similares.

        Args:
            monthly_payment:  Parcela mensal do financiamento (R$).
            financing_months: Prazo do financiamento em meses.
            pts_per_brl:      Pontos por R$ do melhor cartão simulado.
            point_value_brl:  Valor de cada ponto em R$ (milhas Smiles, Livelo, etc.).
            best_card_name:   Nome descritivo do cartão usado na narrativa.

        Returns:
            CardOptimizationBonus com retorno mensal, anual, total e % de redução.
        """
        card_liquidity_risk = "SAFE"
        # Tenta obter dados reais do cartão via OptimizerService (F2)
        if user_id and transactions_df is not None:
            try:
                from app.optimizer.models import OptimizationRequest
                from app.optimizer.services.optimizer_service import OptimizerService

                opt_req = OptimizationRequest(
                    user_id=user_id,
                    monthly_income=monthly_income,
                )
                report = OptimizerService().analyze(
                    request=opt_req, transactions_df=transactions_df
                )
                if report.best_card and report.best_card.points_per_brl_actual:
                    pts_per_brl         = report.best_card.points_per_brl_actual
                    point_value_brl     = report.best_card.point_value_brl or point_value_brl
                    best_card_name      = report.best_card.card_name
                    card_liquidity_risk = str(report.best_card.liquidity_risk)
            except Exception as exc:
                logger.warning("ArchitectService | OptimizerService falhou no CardBonus: %s", exc)
                # mantém fallback de mercado

        monthly_bonus = round(monthly_payment * pts_per_brl * point_value_brl, 2)
        annual_bonus  = round(monthly_bonus * 12, 2)
        total_bonus   = round(monthly_bonus * financing_months, 2)
        total_cost    = monthly_payment * financing_months
        reduction_pct = round((total_bonus / total_cost * 100) if total_cost > 0 else 0.0, 2)

        narrative = (
            f"Se você pagar as parcelas de R$ {monthly_payment:,.2f}/mês no "
            f"{best_card_name} ({pts_per_brl:.1f} pts/R$), gera aproximadamente "
            f"R$ {annual_bonus:,.0f}/ano em pontos — reduzindo o custo efetivo "
            f"do financiamento em {reduction_pct:.1f}% ao longo de {financing_months} meses."
        )

        return CardOptimizationBonus(
            best_card_name=best_card_name,
            pts_per_brl=pts_per_brl,
            point_value_brl=point_value_brl,
            monthly_bonus_brl=monthly_bonus,
            annual_bonus_brl=annual_bonus,
            total_bonus_brl=total_bonus,
            effective_cost_reduction_pct=reduction_pct,
            narrative=narrative,
            liquidity_risk=card_liquidity_risk,
        )

    @staticmethod
    def _adjust_confidence_budget(
        confidence: float,
        monthly_payment: float,
        monthly_income: Optional[float],
        transactions_df,
        strategy,
        warnings: list[str],
        data_sources: list[str],
    ) -> float:
        """
        Ajusta confidence_score com base no orçamento 50/30/20 (BudgetAdvisor).

        Se a parcela do financiamento cabe dentro da margem de Desejos disponível
        no orçamento ideal → +0.05 confidence (validação positiva).
        Se os Essenciais estão OVER → -0.05 (sinal de aperto orçamentário).
        """
        if transactions_df is None or monthly_income is None or monthly_income <= 0:
            return confidence
        try:
            from app.budget.budget_advisor import BudgetAdvisor
            budget = BudgetAdvisor().suggest(transactions_df, monthly_income)
            data_sources.append("budget_advisor")

            wants_group = next((g for g in budget.group_summary if g.group == "desejos"), None)
            essentials_group = next((g for g in budget.group_summary if g.group == "essenciais"), None)

            if wants_group:
                wants_remaining = wants_group.suggested_amount - wants_group.current_amount
                if monthly_payment <= wants_remaining:
                    confidence = min(1.0, confidence + 0.05)
                else:
                    warnings.append(
                        f"A parcela mensal (R$ {monthly_payment:,.0f}) excede a margem "
                        f"disponível no grupo Desejos (R$ {max(0, wants_remaining):,.0f}/mês)."
                    )

            if essentials_group and essentials_group.status == "OVER":
                confidence = max(0.30, confidence - 0.05)
                warnings.append(
                    f"Essenciais representam {essentials_group.current_pct * 100:.0f}% da renda "
                    f"(ideal: 50%) — orçamento sob pressão antes desta aquisição."
                )
        except Exception as exc:
            logger.warning("ArchitectService | BudgetAdvisor falhou: %s", exc)
        return confidence

    @staticmethod
    def _adjust_confidence_goals(
        confidence: float,
        monthly_payment: float,
        user_id: Optional[str],
        strategy,
        warnings: list[str],
        data_sources: list[str],
    ) -> float:
        """
        Ajusta confidence_score com base nas metas financeiras ativas (GoalTracker).

        Se SAVE_INVEST e metas cobrem o aporte necessário → +0.05 confidence.
        Se metas têm gap e strategy é SAVE_INVEST → aviso sobre competição de aportes.
        """
        if not user_id:
            return confidence
        try:
            from app.goals.tracker import GoalTracker
            from app.core.db.session import get_db_session
            from app.architect.models import StrategyType

            with get_db_session() as db:
                goals = GoalTracker(db).list_goals(user_id, status="ACTIVE")

            if not goals:
                return confidence

            data_sources.append("goal_tracker")
            total_gap = sum(
                max(0.0, (g.monthly_contribution_needed or 0) - (g.monthly_contribution_actual or 0))
                for g in goals
            )

            if strategy == StrategyType.SAVE_INVEST:
                if total_gap == 0:
                    # Metas no ritmo — SAVE_INVEST ainda mais viável
                    confidence = min(1.0, confidence + 0.05)
                elif total_gap > monthly_payment * 0.5:
                    warnings.append(
                        f"Você tem R$ {total_gap:,.0f}/mês de gap nas metas ativas — "
                        f"somado à parcela mensal (R$ {monthly_payment:,.0f}), "
                        "avalie a viabilidade de aportes simultâneos."
                    )
                    confidence = max(0.30, confidence - 0.05)
        except Exception as exc:
            logger.warning("ArchitectService | GoalTracker falhou: %s", exc)
        return confidence

    @staticmethod
    def _compute_confidence(
        base_confidence: float,
        has_f1_data: bool,
        used_fallback_rates: bool,
        warning_count: int,
    ) -> float:
        """
        Ajusta o score de confiança baseado na qualidade dos dados disponíveis.

        Base (do engine):       0.85
        + dados reais da F1:   +0.10
        - taxas de fallback:   -0.05
        - por aviso gerado:    -0.02 (máx: -0.10)

        Clamped em [0.30, 1.00].
        """
        score = base_confidence

        if has_f1_data:
            score += 0.10

        if used_fallback_rates:
            score -= 0.05

        score -= min(warning_count * 0.02, 0.10)

        return max(0.30, min(1.00, score))


__all__ = ["ArchitectService"]
