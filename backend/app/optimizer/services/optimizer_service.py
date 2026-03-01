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
from app.optimizer.validators.input_validator import InputValidator
from app.db.queries.optimizer_queries import save_optimization_report

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
        logger.info(f"Iniciando análise de otimização para user_id={request.user_id}")

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

        # 3. Filtrar cartões elegíveis
        eligible_cards = self.knowledge_base.filter_eligible(
            annual_income=annual_income,
            current_card_ids=request.current_cards,
            exclude_consigned=True,  # Por padrão excluímos consignados para ser conservador
        )

        # 4. Simular cada cartão e calcular a pontuação de elegibilidade
        simulated_results = []
        for card in eligible_cards:
            # Simular retorno financeiro
            result = self.simulator.simulate(
                card=card,
                profile=profile,
                safe_to_spend=request.safe_to_spend,
            )

            # Calcular score de elegibilidade realística e adicionar os warnings na simulação
            eligibility_score, eligibility_reasons = (
                self.knowledge_base.compute_eligibility_score(
                    card=card,
                    annual_income=annual_income,
                    spending_stability=profile.spending_stability,
                    issuers_in_transactions=set(),  # TODO: Extrair da lista de transações se possível
                )
            )

            result.eligibility_score = eligibility_score
            result.eligibility_reasons = eligibility_reasons
            simulated_results.append(result)

        # 5. Ranqueamento e Penalidades
        ranked_results = self.ranking.rank(
            results=simulated_results,
            profile=profile,
        )

        # 6. Formatar o Relatório
        return self._build_report(
            request=request, ranked_results=ranked_results, profile_data=profile
        )

    def _build_report(
        self,
        request: OptimizationRequest,
        ranked_results: list,
        profile_data,
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
        recommendation_type = RecommendationType.SWITCH_RECOMMENDED

        # Se o melhor cartão dá prejuízo, recomendamos não trocar
        if best_card_result.net_gain_expected <= 0:
            recommendation_type = RecommendationType.KEEP_CURRENT
            strategy_text = "Nenhum cartão simulado gerou ganhos líquidos positivos para o seu padrão de gastos. Fique com seu cartão atual."
            best_card_result = None
        else:
            strategy_text = "Encontramos cartões que podem melhorar seu retorno financeiro líquido."

        import uuid
        
        report = OptimizationReport(
            report_id=str(uuid.uuid4()),
            user_id=request.user_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            recommendation_type=recommendation_type,
            best_card=best_card_result,
            all_cards=ranked_results,
            strategy_text=strategy_text,
            warnings=warnings,
            data_sources=["pluggy", "internal_knowledge_base"],
        )

        try:
            # Salvar usando as queries do DuckDB
            save_optimization_report(json.loads(report.model_dump_json()))
        except Exception as e:
            logger.error(f"Erro ao salvar relatório de otimização: {e}", exc_info=True)

        return report
