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
import time
from typing import Optional

from app.architect.connectors.abac import AbacConnector
from app.architect.connectors.anbima import AnbimaConnector
from app.architect.connectors.bacen import BacenConnector
from app.architect.connectors.consortium_rate_provider import ConsortiumRateProvider
from app.architect.connectors.ipca import IPCAConnector
from app.architect.connectors.market_rates import MarketRatesConnector
from app.architect.models import (
    AmortizationMethod,
    CardOptimizationBonus,
    OpenFinanceFeatures,
    SimulationRequest,
    SimulationResponse,
    StrategyType,
)
from app.architect.services.llm_reasoner import LLMReasoner
from app.architect.simulators.strategy_engine import StrategyEngine
from app.architect.utils.cache import make_simulation_key, simulation_cache
from app.architect.validators.input_validator import InputValidator
from app.architect.validators.liquidity_validator import LiquidityValidator, RiskLevel

logger = logging.getLogger(__name__)

_CALIBRATION_CACHE_TTL = 300  # 5 minutos


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
        llm_reasoner: Optional[LLMReasoner] = None,
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
        self._engine        = engine       or StrategyEngine()
        self._llm_reasoner  = llm_reasoner or LLMReasoner()
        self._calibration_state: Optional[dict] = None
        self._cache_loaded_at: float = 0.0

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CALIBRAÇÃO — TTL CACHE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_calibration_state(self) -> dict:
        """
        Retorna o estado de calibração com cache de 5 minutos.

        Evita hit ao banco em cada simulação; invalida automaticamente
        após _CALIBRATION_CACHE_TTL segundos (nova calibração é detectada
        na próxima janela mesmo sem reiniciar o processo).
        """
        if time.time() - self._cache_loaded_at > _CALIBRATION_CACHE_TTL:
            from app.architect.feedback_queries import load_calibration_state
            loaded = load_calibration_state()
            self._calibration_state = loaded or {}
            self._cache_loaded_at = time.time()
        return self._calibration_state or {}

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
        cal = self._get_calibration_state()
        request = self._infer_risk_profile(
            request,
            transactions_df,
            accumulated_warnings,
            threshold_conservative=cal.get("threshold_conservative", 0.35),
            threshold_aggressive=cal.get("threshold_aggressive", 0.65),
        )

        # ── 2. Buscar taxas de mercado ───────────────────────────────
        market_rates, rate_warnings = self._fetch_market_rates(request)
        accumulated_warnings.extend(rate_warnings)

        # Injeta parâmetros de lance calibrados para o MC de consórcio
        cal_bid = cal.get("bid_params", {}).get("global", {})
        if cal_bid.get("bid_mean_initial") is not None:
            market_rates["bid_mean_initial"] = cal_bid["bid_mean_initial"]
        if cal_bid.get("bid_std") is not None:
            market_rates["bid_std"] = cal_bid["bid_std"]

        # ── 2.5. Open Finance: personalizar taxas com dados reais ────
        has_open_finance_data = False
        if request.open_finance_features is not None:
            market_rates, of_warnings = self._apply_open_finance_overrides(
                market_rates, request.open_finance_features, request
            )
            accumulated_warnings.extend(of_warnings)
            has_open_finance_data = True

        # ── 3. Simular estratégias ───────────────────────────────────
        # Cache bypassa quando: (a) Open Finance presente — resultado personalizado
        # por usuário; (b) LLM habilitado — resposta não-determinística.
        # Flags determinísticas (include_macro, include_breakeven_distribution)
        # entram na chave, então fast_mode e full_mode têm entradas separadas.
        _bypass_cache = (
            request.open_finance_features is not None
            or request.include_llm_reasoning
        )
        _cache_key: Optional[str] = None
        if not _bypass_cache:
            _cache_key = make_simulation_key(
                request.model_dump(mode="json"),
                market_rates,
                calibration_version=cal.get("calibration_version", 0),
            )
            _cached = simulation_cache.get(_cache_key)
            if _cached is not None:
                logger.debug("simulate | cache HIT key=%.16s…", _cache_key)
                base_response = SimulationResponse.model_validate(_cached)
            else:
                base_response = self._engine.simulate(request, market_rates)
                simulation_cache.set(
                    _cache_key,
                    base_response.model_dump(mode="json"),
                    l1_ttl=900,    # 15 min L1
                    l2_ttl=1800,   # 30 min L2
                )
        else:
            base_response = self._engine.simulate(request, market_rates)
        # Preserva warnings gerados pelo engine (perfil de risco, depreciação, etc.)
        accumulated_warnings.extend(base_response.warnings)

        # ── 3.5. LLM co-raciocínio (consistência + rerun + narrativa) ──
        # LLMReasoner age como analista sênior: verifica inconsistências entre
        # perfil e recomendação, sugere ajuste de parâmetros (override_params)
        # e gera narrativa contextualizada em 3 parágrafos.
        # Retorna (None, base_response) quando LLM não está configurado, falha
        # ou include_llm_reasoning=False.
        if request.include_llm_reasoning:
            llm_result, base_response = self._llm_reasoner.reason(
                request=request,
                base_response=base_response,
                market_rates=market_rates,
                rerun_fn=lambda req: self._engine.simulate(req, market_rates),
            )
        else:
            llm_result = None
        _MAX_FLAG_LEN = 200
        if llm_result is not None and llm_result.consistency.flags:
            accumulated_warnings.extend(
                f"[LLM] {str(flag)[:_MAX_FLAG_LEN]}"
                for flag in llm_result.consistency.flags
                if flag
            )

        return self._finalize_simulation_response(
            request=request,
            base_response=base_response,
            transactions_df=transactions_df,
            accumulated_warnings=accumulated_warnings,
            safe_to_spend=safe_to_spend,
            market_rates=market_rates,
            has_open_finance_data=has_open_finance_data,
            rate_warnings=rate_warnings,
            llm_result=llm_result,
            confidence_cap=cal.get("confidence_threshold_upper", 1.0),
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _finalize_simulation_response(
        self,
        request: SimulationRequest,
        base_response: SimulationResponse,
        transactions_df,
        accumulated_warnings: list[str],
        safe_to_spend: Optional[float],
        market_rates: dict[str, float],
        has_open_finance_data: bool,
        rate_warnings: list[str],
        llm_result,
        confidence_cap: float,
    ) -> SimulationResponse:
        """
        Consolida a resposta final depois do cálculo principal.

        Esta etapa fica isolada para manter `simulate()` como coordenador.
        """
        urgency_analysis = None
        follow_up_questions = None
        _strat = base_response.recommended_strategy
        _liq = base_response.liquidity_impact

        if _strat == StrategyType.SAVE_INVEST:
            urgency_analysis, follow_up_questions = self._build_save_invest_analysis(
                request, base_response
            )
            if urgency_analysis is not None and urgency_analysis.urgency_level in ("TIGHT", "CRITICAL"):
                accumulated_warnings.append(
                    f"[URGÊNCIA {urgency_analysis.urgency_level}] {urgency_analysis.narrative}"
                )
        elif _strat in (StrategyType.FINANCING, StrategyType.FINANCING_RENTAL):
            if _liq is not None and _liq < -0.40:
                follow_up_questions = self._build_financing_followups(request, base_response)
        elif _strat in (StrategyType.CONSORTIUM, StrategyType.CONSORTIUM_SELIC_RENTAL):
            if _liq is not None and _liq < -0.40:
                follow_up_questions = self._build_consortium_followups(request, base_response)

        (
            monthly_payment,
            liquidity,
            confidence,
            data_sources,
            card_bonus,
        ) = self._build_response_context(
            request=request,
            base_response=base_response,
            transactions_df=transactions_df,
            accumulated_warnings=accumulated_warnings,
            safe_to_spend=safe_to_spend,
            market_rates=market_rates,
            has_open_finance_data=has_open_finance_data,
            rate_warnings=rate_warnings,
        )

        confidence = min(confidence, confidence_cap)

        return base_response.model_copy(
            update={
                "liquidity_impact": liquidity.impact,
                "warnings": accumulated_warnings,
                "confidence_score": round(confidence, 2),
                "data_sources": data_sources,
                "card_optimization_bonus": card_bonus,
                "llm_reasoning": llm_result,
                "urgency_analysis": urgency_analysis,
                "follow_up_questions": follow_up_questions,
            }
        )

    def _build_response_context(
        self,
        request: SimulationRequest,
        base_response: SimulationResponse,
        transactions_df,
        accumulated_warnings: list[str],
        safe_to_spend: Optional[float],
        market_rates: dict[str, float],
        has_open_finance_data: bool,
        rate_warnings: list[str],
    ) -> tuple[float, object, float, list[str], Optional[CardOptimizationBonus]]:
        """Calcula liquidez, confiança, fontes e bônus antes da montagem final."""
        monthly_payment = self._estimate_monthly_payment(base_response, request, market_rates)
        liquidity = LiquidityValidator.calculate(
            monthly_payment=monthly_payment,
            safe_to_spend=safe_to_spend,
            max_monthly_budget=request.max_monthly_budget,
        )
        accumulated_warnings.extend(liquidity.warnings)

        has_f1_transactions = transactions_df is not None and not transactions_df.is_empty()
        confidence = self._compute_confidence(
            base_confidence=base_response.confidence_score,
            has_f1_data=(safe_to_spend is not None or has_f1_transactions),
            used_fallback_rates=bool(rate_warnings),
            warning_count=len(accumulated_warnings),
            has_open_finance_data=has_open_finance_data,
        )

        data_sources = list(base_response.data_sources)
        if safe_to_spend is not None:
            data_sources.append("f1_safe_to_spend")
        if has_f1_transactions:
            data_sources.append("f1_transactions")
        if has_open_finance_data:
            data_sources.append("open_finance")
        if request.include_consortium and "abac" not in data_sources:
            data_sources.append("abac")
        if "ipca" not in data_sources:
            data_sources.append("ipca")

        card_bonus: Optional[CardOptimizationBonus] = None
        if base_response.recommended_strategy in (StrategyType.FINANCING, StrategyType.FINANCING_RENTAL):
            card_bonus = self._compute_card_optimization_bonus(
                monthly_payment=monthly_payment,
                financing_months=request.financing_months,
                user_id=request.user_id,
                monthly_income=request.monthly_income,
                transactions_df=transactions_df,
            )
            source = (
                "optimizer_f2"
                if card_bonus and card_bonus.best_card_name != "melhor cartão premium de mercado"
                else "market_reference_estimate"
            )
            data_sources.append(source)

            if card_bonus and card_bonus.liquidity_risk in ("HIGH", "CRITICAL"):
                confidence = max(0.30, confidence - 0.05)
                accumulated_warnings.append(
                    f"O cartão recomendado ({card_bonus.best_card_name}) apresenta risco de liquidez "
                    f"{card_bonus.liquidity_risk} para sua margem atual — avalie se a anuidade é sustentável."
                )

        confidence = self._adjust_confidence_budget(
            confidence=confidence,
            monthly_payment=monthly_payment,
            monthly_income=request.monthly_income,
            transactions_df=transactions_df,
            strategy=base_response.recommended_strategy,
            warnings=accumulated_warnings,
            data_sources=data_sources,
        )

        confidence = self._adjust_confidence_goals(
            confidence=confidence,
            monthly_payment=monthly_payment,
            user_id=request.user_id,
            strategy=base_response.recommended_strategy,
            warnings=accumulated_warnings,
            data_sources=data_sources,
        )

        return monthly_payment, liquidity, confidence, data_sources, card_bonus

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
        market_rates: dict,
    ) -> float:
        """
        Estima a parcela mensal efetiva da estratégia recomendada.

        Usado como entrada do LiquidityValidator. Cada estratégia tem
        uma lógica diferente para chegar ao compromisso mensal de caixa.

        - FINANCING (PRICE): parcela fixa = custo total / prazo
        - FINANCING (SAC):   primeira parcela (mais alta) = amort + juros sobre principal cheio
        - SAVE_INVEST:       custo total / meses de acumulação (aporte mensal)
        - CONSORTIUM:        custo total / meses de acumulação (parcela mensal)
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
            if request.amortization_method == AmortizationMethod.SAC:
                # SAC: primeira parcela (mais alta) = amortização + juros sobre principal inteiro.
                # Conservador para o LiquidityValidator — garante que mês 1 é coberto.
                principal    = max(request.target_amount - request.down_payment, 0.0)
                cet_annual   = market_rates.get("best_cet_annual", 0.20)
                monthly_rate = (1 + cet_annual) ** (1 / 12) - 1
                n            = max(request.financing_months, 1)
                first_payment = principal / n + principal * monthly_rate
                return round(first_payment, 2)
            # PRICE: parcela fixa = custo_total / prazo
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
        threshold_conservative: float = 0.35,
        threshold_aggressive: float = 0.65,
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

            committed_pct        = 0.0
            committed_available  = False
            investment_ratio     = None
            reserve_depth_of     = None
            of = request.open_finance_features

            # Renda inferida da F1 — usada como fallback quando não declarada no request.
            # Calculada aqui para estar disponível no C4 proxy abaixo e no updates final.
            inferred_income = (
                income_profile.monthly_net_income
                if income_profile.confidence >= 0.4 and income_profile.monthly_net_income > 0
                else None
            )
            effective_monthly_income = request.monthly_income or inferred_income

            if of is not None:
                if of.comprometimento_renda_pct is not None:
                    committed_pct       = of.comprometimento_renda_pct
                    committed_available = True
                investment_ratio = of.composicao_rv_pct

                # C4 proxy: reserva estimada / (6 × despesa mensal).
                # savings_rate decresce com dívida — quem tem MENOS comprometimento poupa MAIS.
                # Requer renda + comprometimento + streak; sem qualquer um cai para user_profile.
                if (
                    of.meses_consecutivos_poupanca is not None
                    and effective_monthly_income is not None
                    and effective_monthly_income > 0
                    and of.comprometimento_renda_pct is not None
                ):
                    income    = effective_monthly_income
                    committed = of.comprometimento_renda_pct
                    streak    = of.meses_consecutivos_poupanca

                    # Despesa total: intercepto 0.80 + slope 0.20 (cap 0.97).
                    # Slope 2× mais agressivo que 0.85+0.10: captura que comprometimento
                    # alto deixa pouca margem e o expense_rate sobe mais rápido.
                    expense_rate    = min(0.80 + committed * 0.20, 0.97)
                    monthly_expense = income * expense_rate

                    # Capacidade de poupança: monotônica inversa ao comprometimento
                    savings_rate    = max(0.0, (1.0 - committed) * 0.20)
                    monthly_saving  = income * savings_rate

                    estimated_reserve = monthly_saving * streak
                    months_covered    = estimated_reserve / monthly_expense if monthly_expense > 0 else 0.0
                    reserve_depth_of  = round(min(months_covered / 6.0, 1.0), 4)

            # C3 proxy a partir de transações recorrentes quando OF não disponível.
            # is_recurring=True já foi marcado pelo ETL da F1 (recurring_detector).
            # committed_pct = despesas_recorrentes_mensais / renda_líquida_mensal.
            if not committed_available and inferred_income is not None and inferred_income > 0:
                monthly_recurring = ArchitectService._monthly_recurring_expenses(transactions_df)
                if monthly_recurring > 0:
                    committed_pct       = round(min(monthly_recurring / inferred_income, 1.0), 4)
                    committed_available = True

            risk_result = RiskScorer.score(
                request=request,
                income_profile=income_profile,
                user_profile=fin_profile,
                transactions_df=transactions_df,
                committed_pct=committed_pct,
                committed_available=committed_available,
                investment_ratio=investment_ratio,
                reserve_depth_override=reserve_depth_of,
                threshold_conservative=threshold_conservative,
                threshold_aggressive=threshold_aggressive,
            )

            tier = getattr(fin_profile, "behavior_tier", fin_profile.profile_type)
            resilience = getattr(fin_profile, "resilience_score", fin_profile.financial_health_score)

            updates: dict = {
                "risk_score":            risk_result.score,
                "risk_score_confidence": risk_result.confidence,
            }

            # Popula monthly_income da F1 quando não declarado pelo usuário.
            # Necessário para card_optimization_bonus, BudgetAdvisor e C4 via OF.
            if request.monthly_income is None and inferred_income is not None:
                updates["monthly_income"] = round(inferred_income, 2)

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
            from app.core.database import SessionLocal
            from app.architect.models import StrategyType

            with SessionLocal() as db:
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
    def _monthly_recurring_expenses(transactions_df) -> float:
        """
        Calcula a média mensal de despesas recorrentes a partir do DataFrame de transações.

        Usa a coluna is_recurring marcada pelo ETL da F1 (recurring_detector).
        Retorna 0.0 se o DataFrame não tiver as colunas necessárias ou estiver vazio.
        """
        try:
            import polars as pl

            required = {"amount", "is_recurring"}
            if transactions_df is None or not required.issubset(set(transactions_df.columns)):
                return 0.0

            col_date = next(
                (c for c in ("transaction_date", "date") if c in transactions_df.columns), None
            )
            if col_date is None:
                return 0.0

            recurring = (
                transactions_df
                .filter(
                    (pl.col("is_recurring") == True) &  # noqa: E712
                    (pl.col("amount") < 0)
                )
                .with_columns(
                    (pl.col(col_date).dt.year() * 100 + pl.col(col_date).dt.month()).alias("ym")
                )
                .group_by("ym")
                .agg(pl.col("amount").sum().abs().alias("monthly_recurring"))
            )

            if recurring.is_empty():
                return 0.0

            return float(recurring["monthly_recurring"].mean() or 0.0)

        except Exception:
            return 0.0

    @staticmethod
    def _build_financing_followups(
        request: "SimulationRequest",
        base_response: "SimulationResponse",
    ) -> list | None:
        """
        Perguntas de acompanhamento quando FINANCING/FINANCING_RENTAL é recomendado
        e o comprometimento de renda é HIGH ou CRITICAL (|liquidity_impact| > 0.40).

        Objetivo: coletar dados que podem reduzir a parcela ou personalizar o CET,
        transformando uma simulação de alto risco em uma viável.
        """
        from app.architect.models import AssetType, FollowUpQuestion

        follow_up: list = []

        if request.open_finance_features is None:
            follow_up.append(FollowUpQuestion(
                question_id="open_finance_cet",
                question=(
                    "Compartilhe seu Open Finance para obtermos seu CET real e "
                    "comprometimento de renda atual."
                ),
                field_to_populate="open_finance_features",
                priority="HIGH",
                rationale=(
                    "O CET praticado pelo seu banco pode ser diferente da média de mercado. "
                    "Com Open Finance, calculamos se o financiamento é sustentável para "
                    "sua renda específica e identificamos taxas melhores disponíveis."
                ),
            ))

        follow_up.append(FollowUpQuestion(
            question_id="higher_down_payment",
            question=(
                f"Você tem condições de aumentar a entrada além dos "
                f"R$ {request.down_payment:,.0f} atuais? "
                "Cada R$ 10.000 a mais reduz a parcela diretamente."
            ),
            field_to_populate="down_payment",
            priority="HIGH",
            rationale=(
                "Uma entrada maior reduz o principal financiado e, consequentemente, "
                "a parcela mensal — aliviando o comprometimento de renda sem precisar "
                "mudar o prazo ou a estratégia."
            ),
        ))

        if request.asset_type == AssetType.IMOVEL and request.financing_months < 360:
            extended = min(request.financing_months + 60, 360)
            follow_up.append(FollowUpQuestion(
                question_id="extend_term",
                question=(
                    f"Aumentar o prazo de {request.financing_months} para {extended} meses "
                    "reduziria a parcela mensal. Você prefere prazo mais longo?"
                ),
                field_to_populate="financing_months",
                priority="MEDIUM",
                rationale=(
                    "Prazo mais longo reduz a parcela a custo de um total pago maior. "
                    "Para imóvel, isso pode tornar o financiamento viável dentro do orçamento "
                    "sem comprometer reserva de emergência."
                ),
            ))

        if request.asset_type == AssetType.IMOVEL and request.expected_rental_income is None:
            follow_up.append(FollowUpQuestion(
                question_id="rental_income",
                question=(
                    "Você planeja alugar o imóvel (ou parte dele)? "
                    "A renda de aluguel pode cobrir parte das parcelas."
                ),
                field_to_populate="expected_rental_income",
                priority="MEDIUM",
                rationale=(
                    "A estratégia FINANCIAMENTO + ALUGUEL pode reduzir o custo líquido "
                    "mensal significativamente, tornando o financiamento mais sustentável."
                ),
            ))

        return follow_up or None

    @staticmethod
    def _build_consortium_followups(
        request: "SimulationRequest",
        base_response: "SimulationResponse",
    ) -> list | None:
        """
        Perguntas de acompanhamento quando CONSORTIUM/CONSORTIUM_SELIC_RENTAL é recomendado
        e o comprometimento de renda é HIGH ou CRITICAL.
        """
        from app.architect.models import FollowUpQuestion

        follow_up: list = []

        if request.open_finance_features is None:
            follow_up.append(FollowUpQuestion(
                question_id="open_finance_consortium",
                question=(
                    "Compartilhe seu Open Finance para verificarmos seu "
                    "comprometimento real de renda com as parcelas do consórcio."
                ),
                field_to_populate="open_finance_features",
                priority="HIGH",
                rationale=(
                    "Com dados reais de comprometimento, podemos verificar se as "
                    "parcelas do consórcio cabem no seu orçamento sem risco de inadimplência."
                ),
            ))

        follow_up.append(FollowUpQuestion(
            question_id="consortium_bid",
            question=(
                "Você tem recursos disponíveis para dar um lance no consórcio "
                "e antecipar a contemplação?"
            ),
            field_to_populate="prefers_consortium",
            priority="MEDIUM",
            rationale=(
                "Um lance de 20–30% do valor do bem aumenta significativamente a "
                "probabilidade de contemplação nos primeiros meses, reduzindo o período "
                "em que você paga parcela sem usar o bem."
            ),
        ))

        return follow_up or None

    @staticmethod
    def _build_save_invest_analysis(
        request: "SimulationRequest",
        base_response: "SimulationResponse",
    ) -> tuple:
        """
        Gera análise de urgência e perguntas de acompanhamento quando SAVE_INVEST é recomendado.

        Urgência (quando target_date informado): compara months_to_achieve com o prazo disponível.
          OK       → prazo confortável, SAVE_INVEST é viável.
          TIGHT    → prazo apertado (70–100% do necessário), sugerir CONSORTIUM.
          CRITICAL → inviável no prazo, sugerir FINANCING.

        Perguntas (campo follow_up_questions): coletam dados que melhoram a análise:
          1. Prazo desejado (target_date)        — HIGH, sempre que target_date não informado
          2. Aluguel atual (current_monthly_rent) — HIGH, IMOVEL sem aluguel declarado
          3. Orçamento mensal (max_monthly_budget) — MEDIUM, quando não declarado
          4. Histórico de crédito (open_finance)  — LOW, quando OF ausente
        """
        from datetime import date as _date
        from app.architect.models import (
            AssetType, FollowUpQuestion, StrategyType, UrgencyAnalysis,
        )

        savings_months = base_response.months_to_achieve
        urgency = None
        follow_up: list = []

        # ── Análise de urgência (quando target_date informado) ────────
        if request.target_date is not None:
            today = _date.today()
            months_available = max(1, round((request.target_date - today).days / 30.44))
            months_gap = months_available - savings_months

            if months_available >= savings_months:
                level = "OK"
                narrative = (
                    f"Seu prazo de {months_available} meses é confortável: o plano de poupança "
                    f"leva {savings_months} meses, deixando {months_gap} meses de folga. "
                    "A estratégia SAVE_INVEST é viável no cronograma desejado."
                )
                alt = None
            elif months_available >= int(savings_months * 0.70):
                shortfall = savings_months - months_available
                level = "TIGHT"
                narrative = (
                    f"Prazo apertado: você tem {months_available} meses, mas acumular o valor "
                    f"levaria {savings_months} meses — déficit de {shortfall} meses. "
                    "Qualquer interrupção nos aportes pode comprometer o prazo. "
                    "Considere aumentar o aporte mensal ou avaliar CONSÓRCIO como alternativa mais veloz."
                )
                alt = StrategyType.CONSORTIUM
            else:
                shortfall = savings_months - months_available
                level = "CRITICAL"
                narrative = (
                    f"Prazo inviável para SAVE_INVEST: você tem {months_available} meses, "
                    f"mas acumular o valor levaria {savings_months} meses "
                    f"(déficit de {shortfall} meses — {shortfall / savings_months:.0%} do necessário). "
                    "Para respeitar o prazo desejado, FINANCIAMENTO ou CONSÓRCIO são mais adequados."
                )
                alt = StrategyType.FINANCING

            urgency = UrgencyAnalysis(
                desired_months=months_available,
                savings_months=savings_months,
                months_gap=months_gap,
                urgency_level=level,
                narrative=narrative,
                alternative_strategy=alt,
            )
        else:
            follow_up.append(FollowUpQuestion(
                question_id="deadline",
                question=(
                    f"Em quanto tempo você precisa ou quer adquirir esse bem? "
                    f"(Poupando mensalmente, você chegaria ao valor em cerca de {savings_months} meses.)"
                ),
                field_to_populate="target_date",
                priority="HIGH",
                rationale=(
                    "O prazo define se SAVE_INVEST é viável ou se financiamento/consórcio "
                    "atendem melhor sua necessidade. Um prazo curto muda completamente a recomendação."
                ),
            ))

        # ── Aluguel atual (IMOVEL sem current_monthly_rent) ───────────
        if (
            request.asset_type == AssetType.IMOVEL
            and request.current_monthly_rent is None
        ):
            follow_up.append(FollowUpQuestion(
                question_id="current_rent",
                question="Você paga aluguel atualmente? Se sim, quanto por mês (R$)?",
                field_to_populate="current_monthly_rent",
                priority="HIGH",
                rationale=(
                    "Quem poupa para comprar continua pagando aluguel durante o período de acumulação. "
                    "Esse custo pode tornar financiamento mais vantajoso do que parece."
                ),
            ))

        # ── Orçamento mensal para poupança ────────────────────────────
        if request.max_monthly_budget is None:
            follow_up.append(FollowUpQuestion(
                question_id="monthly_budget",
                question="Quanto você consegue guardar por mês para esse objetivo (R$)?",
                field_to_populate="max_monthly_budget",
                priority="MEDIUM",
                rationale=(
                    "O aporte mensal define o prazo de acumulação. "
                    "Com um valor declarado, calculamos exatamente em quantos meses você atinge o objetivo."
                ),
            ))

        # ── Histórico de crédito ──────────────────────────────────────
        if request.open_finance_features is None:
            follow_up.append(FollowUpQuestion(
                question_id="credit_history",
                question="Você tem ou já teve financiamentos ou empréstimos ativos?",
                field_to_populate="open_finance_features.experiencia_financiamento",
                priority="LOW",
                rationale=(
                    "O histórico de crédito influencia o CET disponível para você. "
                    "Bons pagadores obtêm taxas melhores, o que pode mudar a comparação entre estratégias."
                ),
            ))

        return urgency, follow_up or None

    @staticmethod
    def _compute_confidence(
        base_confidence: float,
        has_f1_data: bool,
        used_fallback_rates: bool,
        warning_count: int,
        has_open_finance_data: bool = False,
    ) -> float:
        """
        Ajusta o score de confiança baseado na qualidade dos dados disponíveis.

        Base (do engine):           0.75–0.85 (risk_score_confidence ou fallback)
        + Open Finance presente:   +0.10 → base sobe para ~0.95 (dados reais eliminam suposições)
        + dados reais da F1:       +0.10 (safe_to_spend + transações validam capacidade real)
        - taxas de fallback:       -0.05
        - por aviso gerado:        -0.02 (máx: -0.10)

        Clamped em [0.30, 1.00].
        """
        score = base_confidence

        if has_open_finance_data:
            score += 0.10   # rendimento real + CET personalizado eliminam as maiores suposições

        if has_f1_data:
            score += 0.10   # safe_to_spend real valida capacidade de pagamento

        if used_fallback_rates:
            score -= 0.05

        score -= min(warning_count * 0.02, 0.10)

        return max(0.30, min(1.00, score))

    @staticmethod
    def _apply_open_finance_overrides(
        market_rates: dict,
        features: OpenFinanceFeatures,
        request: SimulationRequest,
    ) -> tuple[dict, list[str]]:
        """
        Personaliza market_rates com dados reais do Open Finance do usuário.

        Overrides aplicados:
          best_cet_annual → CET real do usuário (cet_historico_real ou cet_medio_historico)
                            quando menor que o CET de mercado. Bom pagador (adimplência ≥ 95%)
                            recebe desconto adicional de 0.5 p.p.

        Warnings gerados (não-bloqueantes):
          - CET personalizado informado (com diferença em p.p.)
          - Adimplência baixa (< 90%) → risco de não-aprovação
          - Comprometimento de renda > 30% → margem insuficiente
          - Poupança inconsistente (< 3 meses) vs orçamento declarado alto
          - Meses de baixa receita (sazonalidade < 85%) onde a parcela pode pesar

        Returns:
            (updated_market_rates, warnings)
        """
        overrides: dict = {}
        warnings: list[str] = []

        # ── CET personalizado ─────────────────────────────────────────
        personalized_cet = features.cet_historico_real or features.cet_medio_historico
        if personalized_cet is not None:
            market_cet = market_rates.get("best_cet_annual", float("inf"))
            adimpl_discount = 0.005 if (features.adimplencia_pct or 0.0) >= 0.95 else 0.0
            effective_cet = max(0.05, personalized_cet - adimpl_discount)
            if effective_cet < market_cet:
                overrides["best_cet_annual"] = round(effective_cet, 4)
                diff_pp = (market_cet - effective_cet) * 100
                source = "financiamentos anteriores" if features.cet_historico_real else "histórico de crédito"
                warnings.append(
                    f"CET personalizado ({source}): {effective_cet:.1%} a.a. "
                    f"({diff_pp:.1f} p.p. abaixo do mercado)."
                )

        # ── Adimplência baixa ─────────────────────────────────────────
        if features.adimplencia_pct is not None and features.adimplencia_pct < 0.90:
            warnings.append(
                f"Histórico bancário: {features.adimplencia_pct:.0%} de adimplência — "
                "bancos podem exigir maior entrada ou CET mais alto. "
                "Consulte seu gerente antes de formalizar a proposta."
            )

        # ── Comprometimento de renda ──────────────────────────────────
        if (
            features.comprometimento_renda_pct is not None
            and features.comprometimento_renda_pct > 0.30
        ):
            pct = features.comprometimento_renda_pct
            warnings.append(
                f"Renda já comprometida com dívidas: {pct:.0%} "
                f"(limite recomendado: 30%). "
                "Considere quitar contratos existentes antes de assumir novos compromissos."
            )

        # ── Padrão de poupança inconsistente ─────────────────────────
        if (
            features.meses_consecutivos_poupanca is not None
            and features.meses_consecutivos_poupanca < 3
            and request.max_monthly_budget is not None
        ):
            meses = features.meses_consecutivos_poupanca
            warnings.append(
                f"Dados bancários: apenas {meses} "
                f"{'mês' if meses == 1 else 'meses'} consecutivo{'s' if meses != 1 else ''} "
                f"com sobra mensal — verifique se o orçamento de "
                f"R$ {request.max_monthly_budget:,.0f}/mês é sustentável."
            )

        # ── Sazonalidade: meses de baixa receita ─────────────────────
        if features.sazonalidade_receita is not None and request.max_monthly_budget is not None:
            month_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            lean = [
                month_labels[i]
                for i, m in enumerate(features.sazonalidade_receita)
                if m < 0.85
            ]
            if lean:
                min_mult = min(features.sazonalidade_receita)
                warnings.append(
                    f"Meses de receita reduzida: {', '.join(lean)} "
                    f"(até {(1 - min_mult):.0%} abaixo da média) — "
                    "confirme que a parcela caberá no orçamento nesses meses."
                )

        return {**market_rates, **overrides}, warnings


__all__ = ["ArchitectService"]
