# app/optimizer/services/optimizer_service.py
# OptimizerService — orquestrador do Nexa Optimizer
# Passo 2.4 — Funcionalidade 2: Nexa Optimizer

from __future__ import annotations

import logging
from datetime import datetime, timezone
import json

import polars as pl

from app.optimizer.models import (
    OptimizationRequest,
    OptimizationReport,
    RecommendationType,
    LiquidityRisk,
)
from app.optimizer.card_loader import CardKnowledgeBase
from app.optimizer.profiler import ConsumptionProfiler
from app.optimizer.simulator import CardSimulator
from app.optimizer.ranking import CardRanking
from app.optimizer.insight_generator import InsightGenerator
from app.optimizer.validators.input_validator import InputValidator
from app.optimizer.queries import save_optimization_report

# ── Camada 3 Anti-Falsos-Positivos — Gates globais ───────────────────────
# ConfidenceGate: threshold abaixo do qual o resultado não é surfaçado ao usuário
_CONFIDENCE_GATE = 0.65
# MinGainFilter: ganho mínimo mensal para recomendar (R$10/mês = R$120/ano)
_MIN_MONTHLY_GAIN_BRL = 10.0
_MIN_ANNUAL_GAIN_BRL = _MIN_MONTHLY_GAIN_BRL * 12


def _apply_anti_fp_gates(results: list, profile) -> list:
    """
    Camada 3 Anti-FP: filtros de qualidade sobre os resultados simulados.

    Escopo: filtros a nível de CARTÃO (não de insight).
    Os gates de confiança (0.65) e ganho mínimo (R$10/mês) em nível de INSIGHT
    são aplicados no InsightGenerator, conforme a árvore de decisão 12.1.

    Filtros aqui:
    - MinGainFilter: remove cartões com ganho negativo líquido — anuidade não se paga.
      Estes não devem aparecer como "best_card" nem em insights de troca.
    - Mantém todos os demais no ranking para permitir que o usuário veja o panorama
      completo, mesmo com confiança baixa (ranking já penaliza via × 0.5 se conf < 0.4).
    """
    filtered = []
    for r in results:
        # MinGainFilter: retorno líquido negativo → cartão piora a situação financeira
        if r.net_gain_expected < 0:
            logger.debug(
                "AntiFF MinGainFilter: descartando %s (net_gain=R$%.0f — negativo)",
                r.card_id, r.net_gain_expected,
            )
            continue
        filtered.append(r)
    return filtered


# ── Mapeamento issuer → padrões regex nas descrições de transações ────────
# Chave: nome canônico do issuer (deve coincidir com CardRecord.issuer)
# Valor: padrões case-insensitive que identificam o banco nas descrições
_ISSUER_PATTERNS: dict[str, list[str]] = {
    "Nubank":           [r"\bnubank\b", r"\bnu\s+pagamentos\b"],
    "Banco Inter":      [r"\binter\b", r"\bbanco\s+inter\b"],
    "Itaú":             [r"\bitau\b", r"\bita[uú]\b"],
    "C6 Bank":          [r"\bc6\s*bank\b", r"\bc6\b"],
    "Next (Bradesco)":  [r"\bnext\b", r"\bbradesco\b"],
    "XP":               [r"\bxp\s+invest\b", r"\bxp\s+cartao\b"],
    "PicPay":           [r"\bpicpay\b"],
}


def extract_issuers_from_transactions(transactions_df: "pl.DataFrame") -> set[str]:
    """
    Extrai nomes de emissores (issuers) presentes nas descrições das transações.

    Varre a coluna 'description' com padrões regex por issuer.
    Retorna o conjunto de issuers identificados — usado para calcular
    o bônus de relacionamento bancário no eligibility_score.

    Args:
        transactions_df: DataFrame de transações com coluna 'description'.

    Returns:
        Conjunto de nomes de issuers encontrados (ex: {"Nubank", "Itaú"}).
    """
    import re
    import polars as pl

    if transactions_df is None or transactions_df.is_empty():
        return set()
    if "description" not in transactions_df.columns:
        return set()

    # Coleta todas as descrições em uma única string para scan eficiente
    descriptions = " ".join(
        transactions_df.get_column("description").drop_nulls().to_list()
    ).lower()

    found: set[str] = set()
    for issuer, patterns in _ISSUER_PATTERNS.items():
        if any(re.search(p, descriptions, re.IGNORECASE) for p in patterns):
            found.add(issuer)

    if found:
        logger.debug("Issuers identificados nas transações: %s", found)

    return found

logger = logging.getLogger(__name__)


class OptimizerService:
    """
    Orquestrador principal do Nexa Optimizer.

    Fluxo:
    1. Valida a requisição (InputValidator)
    2. Constrói o perfil do usuário (ConsumptionProfiler) a partir de transações e contas futuras
    3. Carrega e filtra cartões elegíveis (CardKnowledgeBase)
    4. Simula o retorno para cada cartão (CardSimulator)
    5. Ordena os resultados com base no retorno ajustado por risco e elegibilidade (CardRanking)
    6. Formata a recomendação, salva o relatório e retorna (OptimizationReport)
    """

    def __init__(
        self,
        knowledge_base: CardKnowledgeBase | None = None,
        profiler: ConsumptionProfiler | None = None,
        simulator: CardSimulator | None = None,
        ranking: CardRanking | None = None,
        validator: InputValidator | None = None,
    ):
        self.knowledge_base = knowledge_base or CardKnowledgeBase()
        self.profiler = profiler or ConsumptionProfiler()
        self.simulator = simulator or CardSimulator()
        self.ranking = ranking or CardRanking()
        self.insight_generator = InsightGenerator()
        self.validator = validator or InputValidator()

        # Garante que a base foi carregada
        if not self.knowledge_base._cards:
            self.knowledge_base.load()

    def analyze(
        self,
        request: OptimizationRequest,
        transactions_df: pl.DataFrame,
        shadow_invoices_df: pl.DataFrame | None = None,
        reference_date: datetime | str | None = None,
    ) -> OptimizationReport:
        """
        Executa a análise completa de otimização de cartões.

        Args:
            request: Dados da requisição (user_id, current_cards, etc).
            transactions_df: Histórico de transações limpas do usuário (da F1).
            shadow_invoices_df: Eventos futuros projetados (da F1).
            reference_date: Data base para cálculos (usado principalmente em testes).

        Returns:
            OptimizationReport contendo a recomendação final, simulações e status.
        """
        logger.info("Iniciando análise de otimização para user_id=%s", request.user_id)

        # 1. Validar request
        self.validator.validate(request)

        # 2. Construir perfil de consumo
        profile = self.profiler.build(
            transactions_df=transactions_df,
            shadow_invoices_df=shadow_invoices_df,
            safe_to_spend=request.safe_to_spend,
            reference_date=reference_date,
        )

        # Hierarquia de renda (melhor estimativa disponível → menos confiável):
        #   1. monthly_income declarado pelo usuário (fonte mais confiável)
        #   2. income_profile.monthly_net_income com confidence ≥ 0.5 (IncomeProfiler)
        #   3. estimated_monthly_income (soma bruta de créditos — pode estar inflado)
        if request.monthly_income:
            annual_income = request.monthly_income * 12
        elif (
            profile.income_profile is not None
            and profile.income_profile.confidence >= 0.5
            and profile.income_profile.monthly_net_income > 0
        ):
            annual_income = profile.income_profile.monthly_net_income * 12
            logger.info(
                f"Usando income_profile (net={profile.income_profile.monthly_net_income:.0f}/mês, "
                f"pattern={profile.income_profile.income_pattern}, "
                f"conf={profile.income_profile.confidence:.2f}) para elegibilidade"
            )
        else:
            annual_income = profile.estimated_monthly_income * 12
            if annual_income > 0:
                logger.info(
                    f"Usando estimated_monthly_income={profile.estimated_monthly_income:.0f}/mês "
                    f"(IncomeProfiler conf={getattr(profile.income_profile, 'confidence', 0):.2f} < 0.5)"
                )

        # Spend override ou fallback:
        # 1. Se o usuário declarou explicitamente o gasto mensal (ex: via chat), usa esse valor.
        # 2. Senão, se não há gastos detectados nas transações mas temos renda, estima 40% como gasto.
        # Sem isso, todo cartão com anuidade recebe net_gain < 0 e é filtrado —
        # causando viés sistemático para cartões gratuitos independente do perfil real.
        from dataclasses import replace as _replace
        if request.monthly_spend and request.monthly_spend > 0:
            if request.monthly_spend > profile.monthly_avg_spend:
                profile = _replace(profile, monthly_avg_spend=request.monthly_spend)
                logger.info(
                    "monthly_spend declarado (R$%.0f) > perfil (R$%.0f) — usando valor declarado",
                    request.monthly_spend, profile.monthly_avg_spend,
                )
        elif profile.monthly_avg_spend == 0 and annual_income > 0:
            estimated_spend = annual_income / 12 * 0.40
            profile = _replace(profile, monthly_avg_spend=estimated_spend, spend_is_estimated=True)
            logger.info(
                "monthly_avg_spend=0 com renda conhecida — estimando R$%.0f/mês (40%% da renda anual de R$%.0f)",
                estimated_spend, annual_income,
            )

        # 3. Filtrar cartões elegíveis
        eligible_cards = self.knowledge_base.filter_eligible(
            annual_income=annual_income,
            current_card_ids=request.current_cards,
            exclude_consigned=True,  # Por padrão excluímos consignados para ser conservador
        )

        # Fallback de liquidez: quando safe_to_spend não vem da F1, usa 30% da renda
        # mensal estimada. Sem isso, todos os cartões com anuidade recebem CRITICAL (×0.2).
        effective_safe_to_spend = request.safe_to_spend or (
            (annual_income / 12 * 0.30) if annual_income > 0 else None
        )

        # 4. Simular cada cartão e calcular a pontuação de elegibilidade
        issuers = extract_issuers_from_transactions(transactions_df)

        simulated_results = []
        for card in eligible_cards:
            # Simular retorno financeiro
            result = self.simulator.simulate(
                card=card,
                profile=profile,
                safe_to_spend=effective_safe_to_spend,
            )

            # Calcular score de elegibilidade realística e adicionar os warnings na simulação
            eligibility_score, eligibility_reasons = (
                self.knowledge_base.compute_eligibility_score(
                    card=card,
                    annual_income=annual_income,
                    spending_stability=profile.spending_stability,
                    issuers_in_transactions=issuers,
                    income_profile=profile.income_profile,  # MI.3: penalizar PJ instável
                )
            )

            result.eligibility_score = eligibility_score
            result.eligibility_reasons = eligibility_reasons
            simulated_results.append(result)

        # 5. Camada 3 Anti-FP: MinGainFilter (cartões com ganho negativo)
        # ConfidenceGate (0.65) e MinGainFilter por insight são aplicados no InsightGenerator.
        simulated_results = _apply_anti_fp_gates(simulated_results, profile)

        # Fase 2 — FSS (opera sobre todas as transações para cheque especial / IOF)
        # Family/Temporal/Airbnb já rodaram dentro do ConsumptionProfiler.build().
        from app.optimizer.detectors.fss_calculator import FSSCalculator

        fss_result = FSSCalculator().calc_fss(
            profile, transactions_df,
            resilience_score=int(profile.resilience_score),
        )
        profile.fss = fss_result["fss"]
        profile.fss_level = fss_result["fss_level"]

        if fss_result["fss_level"] == "CRITICO":
            logger.warning(
                "FSS CRÍTICO (score=%.0f) para usuário — ativando modo defesa.",
                fss_result["fss"],
            )

        # Detecção de eventos de vida (T2.1)
        from app.optimizer.detectors.life_events_detector import LifeEventsDetector
        from datetime import date as _date, timedelta as _timedelta
        life_events_raw: list[dict] = []
        try:
            _ref = reference_date or _date.today()
            _cutoff_recent = _ref - _timedelta(days=60)
            _cutoff_hist_end = _ref - _timedelta(days=180)
            _cutoff_hist_start = _ref - _timedelta(days=540)

            if "date" in transactions_df.columns:
                _txns_recent = transactions_df.filter(
                    pl.col("date") >= _cutoff_recent
                )
                _txns_history = transactions_df.filter(
                    (pl.col("date") >= _cutoff_hist_start) &
                    (pl.col("date") < _cutoff_hist_end)
                )

                # Renda recente: do perfil atual (90 dias, já filtrado pelo profiler)
                _income_recent = (
                    profile.income_profile.monthly_net_income
                    if profile.income_profile
                    else profile.estimated_monthly_income
                )

                # Renda histórica: média de créditos na janela 6–18 meses
                # Calculada diretamente da série histórica para detectar variações reais.
                _income_historical = _income_recent  # fallback se sem histórico
                if not _txns_history.is_empty() and "amount" in _txns_history.columns:
                    _hist_credits = _txns_history.filter(pl.col("amount") > 0)
                    if not _hist_credits.is_empty():
                        _hist_months = (
                            _hist_credits
                            .with_columns(
                                (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym")
                            )
                            .select("ym").unique().height
                        )
                        if _hist_months > 0:
                            _income_historical = float(_hist_credits["amount"].sum()) / _hist_months

                detected = LifeEventsDetector().detect_all(
                    txns_recent=_txns_recent,
                    txns_history=_txns_history,
                    income_recent=_income_recent,
                    income_historical=_income_historical,
                )
                life_events_raw = [
                    {
                        "event": e.event,
                        "confidence": e.confidence,
                        "detected_at": e.detected_at.isoformat(),
                        "trigger_action": e.trigger_action,
                        "supporting_signals": e.supporting_signals,
                    }
                    for e in detected
                ]
        except Exception as _exc:
            logger.warning("LifeEventsDetector falhou: %s", _exc)

        # ── A/B Testing — resolver variantes para este usuário ───────────────
        from app.core.ab_testing import ABVariant, get_variant, log_exposure

        _uid = str(request.user_id)
        ab_ranker = get_variant(_uid, "ranker_v2_hyperpersonalized")
        ab_tone   = get_variant(_uid, "cluster_tone_personalization")
        ab_events = get_variant(_uid, "life_events_nudge")
        log_exposure(_uid, "ranker_v2_hyperpersonalized", ab_ranker)
        log_exposure(_uid, "cluster_tone_personalization", ab_tone)
        log_exposure(_uid, "life_events_nudge", ab_events)

        # 6. Ranqueamento e Penalidades
        if ab_ranker is ABVariant.TREATMENT:
            ranked_results = self.ranking.rank_hyperpersonalized(
                results=simulated_results,
                profile=profile,
            )
        else:
            ranked_results = self.ranking.rank(
                results=simulated_results,
                profile=profile,
            )

        # 8. Camada 5 — Gerar insights acionáveis
        current_card_id = request.current_cards[0] if request.current_cards else None

        # Retorno mensal do cartão atual — necessário para TROCAR_PRIMARIO ser incremental.
        # Sem isso, o insight mostraria o ganho total do novo cartão, não o ganho adicional.
        current_card_monthly_return = 0.0
        if current_card_id:
            current_card_record = self.knowledge_base.get_by_id(current_card_id)
            if current_card_record is None:
                logger.warning(
                    "current_card_id='%s' não encontrado na knowledge base — "
                    "TROCAR_PRIMARIO usará baseline 0 (ganho pode estar superestimado).",
                    current_card_id,
                )
            else:
                try:
                    roi = self.simulator.calculate_current_card_roi(current_card_record, profile)
                    current_card_monthly_return = roi.net_roi / 12
                except Exception:
                    pass  # fallback seguro: 0.0 (insight superestima, não trava)

        insights = self.insight_generator.generate(
            ranked_results=ranked_results,
            profile=profile,
            current_card_id=current_card_id,
            current_card_monthly_return=current_card_monthly_return,
            enable_cluster_tone=ab_tone is ABVariant.TREATMENT,
        )

        # 9. Formatar o Relatório
        # life_events_nudge CONTROL → relatório sem eventos (nudge desativado)
        active_life_events = life_events_raw if ab_events is ABVariant.TREATMENT else []
        return self._build_report(
            request=request, ranked_results=ranked_results, profile_data=profile,
            insights=insights, life_events=active_life_events,
        )

    def _build_report(
        self,
        request: OptimizationRequest,
        ranked_results: list,
        profile_data,
        insights: list | None = None,
        life_events: list | None = None,
    ) -> OptimizationReport:

        warnings = []
        if profile_data.data_coverage_months < 2:
            warnings.append(
                "Histórico de transações muito curto para uma projeção altamente confiável."
            )

        if not request.safe_to_spend:
            warnings.append(
                "O Safe to Spend não foi informado; o risco de anuidade não pôde ser avaliado com precisão."
            )

        income_conf = getattr(profile_data.income_profile, "confidence", 0.0)
        if not request.monthly_income and income_conf < 0.5:
            warnings.append(
                "Não foi possível estimar sua renda com confiança a partir do histórico. "
                "Informar a renda mensal melhora a precisão das recomendações de cartão."
            )

        if getattr(profile_data, "spend_is_estimated", False):
            warnings.append(
                "Nenhum histórico de transações encontrado. As recomendações foram geradas com "
                "gasto estimado (40% da renda declarada) e têm confiança limitada. "
                "Conecte sua conta bancária para análise personalizada."
            )

        if not ranked_results:
            import uuid
            return OptimizationReport(
                report_id=str(uuid.uuid4()),
                user_id=request.user_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
                recommendation_type=RecommendationType.INSUFFICIENT_DATA,
                strategy_text="Não encontramos cartões elegíveis para o seu perfil e renda atuais no momento.",
                warnings=warnings,
                all_cards=[],
                data_sources=[],
            )

        best_card_result = ranked_results[0]

        # GoalContext: avisa quando anuidade do melhor cartão compromete aportes nas metas.
        if request.monthly_goals_commitment > 0:
            annuity_monthly = best_card_result.annuity_effective / 12
            total_committed  = annuity_monthly + request.monthly_goals_commitment
            estimated_savings = profile_data.monthly_avg_spend * getattr(profile_data, "savings_rate", 0.0) / 100
            if estimated_savings > 0 and total_committed > estimated_savings * 0.80:
                warnings.append(
                    f"A anuidade do {best_card_result.card_name} (R$ {annuity_monthly:,.0f}/mês) "
                    f"somada aos aportes nas metas ativas (R$ {request.monthly_goals_commitment:,.0f}/mês) "
                    f"totaliza R$ {total_committed:,.0f}/mês — verifique a compatibilidade com sua margem disponível."
                )
        recommendation_type = RecommendationType.SWITCH_RECOMMENDED

        # Se o melhor cartão dá prejuízo, recomendamos não trocar
        if best_card_result.net_gain_expected <= 0:
            recommendation_type = RecommendationType.KEEP_CURRENT
            strategy_text = "Nenhum cartão simulado gerou ganhos líquidos positivos para o seu padrão de gastos. Fique com seu cartão atual."
            best_card_result = None
        elif getattr(profile_data, "spend_is_estimated", False):
            # Gasto 100% estimado: não podemos afirmar com confiança que vale trocar.
            recommendation_type = RecommendationType.LOW_CONFIDENCE
            strategy_text = (
                "Encontramos cartões compatíveis com seu perfil de renda, mas sem histórico de "
                "transações não é possível personalizar a recomendação. Conecte sua conta bancária "
                "para uma análise mais precisa."
            )
        else:
            strategy_text = "Encontramos cartões que podem melhorar seu retorno financeiro líquido."

        import uuid
        
        user_profile_summary = {
            "lifestyle_cluster":  getattr(profile_data, "lifestyle_cluster",  "NAO_CLASSIFICADO"),
            "fss_level":          getattr(profile_data, "fss_level",          "SAUDAVEL"),
            "fss":                round(getattr(profile_data, "fss", 0.0), 1),
            "investor_type":      getattr(profile_data, "investor_type",      "NONE"),
            "savings_rate":       round(getattr(profile_data, "savings_rate", 0.0), 1),
            "monthly_avg_spend":  round(getattr(profile_data, "monthly_avg_spend", 0.0), 2),
            "is_likely_mei":      getattr(profile_data, "is_likely_mei",      False),
            "is_family_with_kids":getattr(profile_data, "is_family_with_kids",False),
        }

        report = OptimizationReport(
            report_id=str(uuid.uuid4()),
            user_id=request.user_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            recommendation_type=recommendation_type,
            best_card=best_card_result,
            all_cards=ranked_results,
            insights=insights or [],
            strategy_text=strategy_text,
            warnings=warnings,
            data_sources=["pluggy", "internal_knowledge_base"],
            life_events=life_events or [],
            user_profile_summary=user_profile_summary,
        )

        try:
            # Salvar usando as queries do DuckDB
            save_optimization_report(json.loads(report.model_dump_json()))
        except Exception as e:
            logger.error("Erro ao salvar relatório de otimização: %s", e, exc_info=True)

        return report
