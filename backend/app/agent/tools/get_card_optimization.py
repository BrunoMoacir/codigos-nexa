# app/agent/tools/get_card_optimization.py
from langchain_core.tools import tool
from typing import Optional
import polars as pl
import logging

from app.optimizer.models import OptimizationRequest
from app.optimizer.services.optimizer_service import OptimizerService

logger = logging.getLogger(__name__)

@tool
def get_card_optimization(
    user_id: str, 
    monthly_income: Optional[float] = None, 
    safe_to_spend: Optional[float] = None
) -> str:
    """
    Analisa o perfil financeiro do usuário e recomenda o melhor cartão de crédito.
    Use esta ferramenta SEMPRE que o usuário perguntar sobre:
    - Qual cartão de crédito deve pedir/solicitar.
    - Como otimizar seus pontos, milhas ou cashback.
    - Se vale a pena pagar anuidade em um cartão específico.
    
    Args:
        user_id: ID do usuário (obrigatório).
        monthly_income: Renda mensal do usuário (opcional, use se o usuário informar).
        safe_to_spend: Valor seguro para gastos mensais no cartão (opcional, use se o usuário informar).
    """
    logger.info(f"[Tool] Chamando get_card_optimization para {user_id}")
    try:
        # Buscar transações REAIS do DuckDB para recomendar cartão pelo perfil real
        transactions_df = pl.DataFrame(schema={
            "date": pl.Date,
            "amount": pl.Float64,
            "description": pl.Utf8,
            "category": pl.Utf8,
            "pf_pj_label": pl.Utf8,
            "type": pl.Utf8
        })
        try:
            from app.runner import NexaRunner
            runner = NexaRunner(mode="dev")
            result = runner.run_from_db(user_id=user_id, horizon_days=30)
            if result and result.get("status") == "success":
                raw_df = result.get("transactions", {}).get("clean_df", pl.DataFrame())
                if not raw_df.is_empty():
                    # Mapear colunas para o schema do optimizer
                    needed = {"date", "amount", "description", "category", "pf_pj_label", "type"}
                    if "context_type" in raw_df.columns and "pf_pj_label" not in raw_df.columns:
                        raw_df = raw_df.rename({"context_type": "pf_pj_label"})
                    if "transaction_type" in raw_df.columns and "type" not in raw_df.columns:
                        raw_df = raw_df.rename({"transaction_type": "type"})
                    available = set(raw_df.columns) & needed
                    if available:
                        transactions_df = raw_df.select(list(available))
                        logger.info(f"[Tool] {len(transactions_df)} transações reais carregadas para otimização de cartão")
                # Pegar renda real se não informada
                if not monthly_income:
                    income_profile = result.get("analysis", {}).get("income_profile")
                    if income_profile and income_profile.confidence >= 0.5:
                        monthly_income = income_profile.monthly_net_income
                # Pegar safe_to_spend real se não informado
                if not safe_to_spend:
                    proj = result.get("projections", {})
                    safe = proj.get("safe_to_spend")
                    if safe:
                        safe_to_spend = safe.safe_to_spend_total
        except Exception as e:
            logger.debug(f"[Tool] Erro ao carregar dados reais para cartão (usando fallback): {e}")

        if not monthly_income and not safe_to_spend:
            return "Preciso saber sua renda mensal ou quanto você gasta por mês no cartão para fazer uma recomendação precisa."

        request = OptimizationRequest(
            user_id=user_id,
            monthly_income=monthly_income,
            safe_to_spend=safe_to_spend,
            current_cards=[]
        )
        
        service = OptimizerService()
        report = service.analyze(
            request=request,
            transactions_df=transactions_df,
            shadow_invoices_df=None
        )

        # MI.8: contexto de renda para o LLM — sinaliza fonte e confiança
        from app.etl.income_profiler import IncomeProfiler
        income_context_lines = []
        if monthly_income:
            income_context_lines.append(
                f"Renda: R$ {monthly_income:,.0f}/mês (declarada pelo usuário — alta confiança)"
            )
        else:
            # Tenta estimar via IncomeProfiler no df vazio → UNKNOWN, mas traz o padrão de aviso
            income_est = IncomeProfiler().build(transactions_df)
            if income_est.confidence >= 0.5:
                income_context_lines.append(
                    f"Renda estimada: R$ {income_est.monthly_net_income:,.0f}/mês "
                    f"(padrão {income_est.income_pattern.value}, "
                    f"confiança {income_est.confidence:.0%})"
                )
            else:
                income_context_lines.append(
                    "Renda: não declarada e não foi possível estimar com confiança "
                    "— recomendação pode ser menos precisa. "
                    "Informe monthly_income para melhorar a análise."
                )

        # Formata o output para o LLM ler e gerar resposta amigável
        output = [
            f"Relatório de Otimização (ID: {report.report_id})",
            f"Recomendação Principal: {report.recommendation_type.value}",
            f"Estratégia: {report.strategy_text}",
        ]
        output.extend(income_context_lines)
        output.append("-" * 30)
        
        if report.best_card:
            c = report.best_card
            output.append(f"Card Vencedor: {c.card_name} (ID: {c.card_id})")
            output.append(f"Valor de Benefícios Projetado: R$ {c.points_value_expected:.2f}")
            output.append(f"Anuidade Efetiva: R$ {c.annuity_effective:.2f}")
            output.append(f"> Lucro Líquido Anual: R$ {c.net_gain_expected:.2f} <")
            if c.eligibility_reasons:
                output.append(f"Elegibilidade: {'; '.join(c.eligibility_reasons[:2])}")
        
        if report.warnings:
            output.append("-" * 30)
            output.append("Avisos:")
            for w in report.warnings:
                output.append(f"- {w}")
                
        # Top 3 simulados
        if len(report.all_cards) > 1:
            output.append("-" * 30)
            output.append("Outros cartões analisados no top 3:")
            for rank_card in report.all_cards[1:4]:
                output.append(f"- {rank_card.card_name} (Lucro Liq: R$ {rank_card.net_gain_expected:.2f})")
                
        return "\n".join(output)
        
    except ValueError as ve:
        return f"Não foi possível analisar: {str(ve)}"
    except Exception as e:
        logger.error(f"Erro na tool get_card_optimization: {e}", exc_info=True)
        return "Desculpe, ocorreu um erro interno ao tentar calcular as opções de cartões."
