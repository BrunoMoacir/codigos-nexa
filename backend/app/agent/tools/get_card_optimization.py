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
        if not monthly_income and not safe_to_spend:
            # Requeremos pelo menos um para o simulador não estourar Exception
            # Em prod, a LangGraph ou a F1 injetaria o safe_to_spend real.
            return "Preciso saber sua renda mensal ou quanto você gasta por mês no cartão para fazer uma recomendação precisa."

        request = OptimizationRequest(
            user_id=user_id,
            monthly_income=monthly_income,
            safe_to_spend=safe_to_spend,
            current_cards=[] # TODO: Expandir para ler cartões atuais do banco
        )
        
        # Fallback empty dataframe se não tiver F1 rodando
        transactions_df = pl.DataFrame(schema={
            "date": pl.Date,
            "amount": pl.Float64,
            "description": pl.Utf8,
            "category": pl.Utf8,
            "pf_pj_label": pl.Utf8,
            "type": pl.Utf8
        })
        
        service = OptimizerService()
        report = service.analyze(
            request=request, 
            transactions_df=transactions_df, 
            shadow_invoices_df=None
        )
        
        # Formata o output para o LLM ler e gerar resposta amigável
        output = [
            f"Relatório de Otimização (ID: {report.report_id})",
            f"Recomendação Principal: {report.recommendation_type.value}",
            f"Estratégia: {report.strategy_text}",
            "-" * 30
        ]
        
        if report.best_card:
            c = report.best_card
            output.append(f"Card Vencedor: {c.card_name} (ID: {c.card_id})")
            output.append(f"Motivo Elegibilidade: Renda OK, Risco Controlado")
            output.append(f"Milhas Anuais Projetadas: {c.yearly_miles_expected:,.0f}")
            output.append(f"Cashback Anual Projetado: R$ {c.yearly_cashback_expected:.2f}")
            output.append(f"Ganho Bruto Anual (Moeda): R$ {c.gross_gain_expected:.2f}")
            output.append(f"Anuidade Total: R$ {c.yearly_fee_final:.2f}")
            output.append(f"> Lucro Líquido Anual: R$ {c.net_gain_expected:.2f} <")
        
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
