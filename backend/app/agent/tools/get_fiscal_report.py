# app/agent/tools/get_fiscal_report.py
"""
Tool: get_fiscal_report
Gera relatório fiscal para usuários PJ/MEI: receitas, despesas por subcategoria,
lucro estimado e DAS estimado pelo Simples Nacional (Anexo III).

Use SEMPRE que o usuário perguntar sobre:
- Relatório fiscal ou contábil do mês/ano
- Quanto deve de DAS / Simples Nacional
- Receitas e despesas do negócio (PJ / MEI)
- Imposto de nota fiscal, faturamento, lucro da empresa
"""
from langchain_core.tools import tool
from typing import Optional
import logging
from datetime import date

logger = logging.getLogger(__name__)


@tool
def get_fiscal_report(
    user_id: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> str:
    """
    Gera relatório fiscal para MEI ou PJ com base nas transações classificadas
    como contexto PJ no histórico do usuário.

    Inclui: receitas por subcategoria, despesas dedutíveis, lucro estimado e
    DAS estimado pelo Simples Nacional (Anexo III — Serviços).

    Use esta ferramenta quando o usuário perguntar sobre:
    - Quanto vai pagar de DAS / Simples Nacional este mês ou ano
    - Relatório de receitas e despesas do negócio
    - Faturamento, lucro ou resultado financeiro PJ
    - Notas fiscais, deduções, impostos da empresa

    Args:
        user_id: ID do usuário (obrigatório).
        year: Ano do relatório (padrão: ano atual).
        month: Mês 1-12 (opcional — se omitido, gera relatório anual).
    """
    today = date.today()
    year = year or today.year
    logger.info("[Tool] get_fiscal_report user=%s year=%d month=%s", user_id, year, month)

    try:
        from app.etl.fiscal_report import FiscalReportService

        service = FiscalReportService()
        report = service.generate(user_id=user_id, year=year, month=month)

        period = report.period_label
        lines = [
            f"Relatorio Fiscal PJ — {period}",
            f"Total de transacoes PJ analisadas: {report.total_transactions}",
            "-" * 40,
        ]

        if report.total_transactions == 0:
            lines.append(
                "Nenhuma transacao PJ encontrada para este periodo. "
                "Certifique-se de que suas transacoes estao conectadas via Open Finance "
                "e classificadas como PJ."
            )
            return "\n".join(lines)

        # Receitas
        if report.receitas:
            lines.append(f"RECEITAS — Total: R$ {report.total_receita:,.2f}")
            for r in report.receitas:
                lines.append(f"  {r.label}: R$ {r.total:,.2f} ({r.count} transacoes)")
        else:
            lines.append("RECEITAS — Nenhuma receita PJ identificada no periodo.")
        lines.append("")

        # Despesas
        if report.despesas:
            lines.append(f"DESPESAS DEDUTIVEIS — Total: R$ {report.total_despesa:,.2f}")
            for d in report.despesas:
                lines.append(f"  {d.label}: R$ {d.total:,.2f} ({d.count} transacoes)")
        else:
            lines.append("DESPESAS — Nenhuma despesa PJ identificada no periodo.")
        lines.append("")

        # Resultado
        lucro_emoji = "✅" if report.lucro_estimado >= 0 else "⚠️"
        lines.append(f"{lucro_emoji} Lucro Estimado: R$ {report.lucro_estimado:,.2f}")
        lines.append("")

        # DAS
        lines.append("DAS — Simples Nacional (Estimativa):")
        if report.das_estimado > 0:
            lines.append(f"  {report.das_faixa}")
            lines.append(f"  RBT12 (receita bruta 12 meses): R$ {report.rbt12_anualizado:,.2f}")
            lines.append(f"  Aliquota efetiva: {report.das_aliquota_efetiva:.2f}%")
            lines.append(f"  DAS estimado sobre receita do periodo: R$ {report.das_estimado:,.2f}")
        elif report.das_faixa:
            lines.append(f"  {report.das_faixa}")
        else:
            lines.append("  Sem receita — DAS nao aplicavel.")

        lines.append("")
        lines.append(
            "Importante: Esta e uma estimativa baseada em transacoes classificadas automaticamente. "
            "Consulte seu contador para declaracoes oficiais."
        )

        return "\n".join(lines)

    except Exception as e:
        logger.error("[Tool] get_fiscal_report erro: %s", e, exc_info=True)
        return (
            "Nao foi possivel gerar o relatorio fiscal agora. "
            "Verifique se ha transacoes PJ conectadas via Open Finance."
        )
