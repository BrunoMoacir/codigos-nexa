# app/agent/tools/get_peer_comparison.py
"""
Tool: get_peer_comparison
Compara o perfil de gastos do usuário com benchmarks IBGE/POF para sua faixa de renda.
Mostra em quais categorias o usuário gasta acima ou abaixo da média de pessoas similares.

Use SEMPRE que o usuário perguntar sobre:
- Como meus gastos se comparam com outras pessoas de renda similar
- Estou gastando mais ou menos que a media em alimentacao, moradia, etc
- Percentil de poupança em relação a pessoas com a mesma renda
- Benchmarks financeiros por faixa de renda
"""
from langchain_core.tools import tool
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@tool
def get_peer_comparison(
    user_id: str,
    monthly_income: float,
    history_months: int = 3,
) -> str:
    """
    Compara o perfil de gastos do usuário com benchmarks da Pesquisa de Orçamentos
    Familiares (POF/IBGE) para a faixa de renda declarada.

    Retorna posicionamento por categoria ('acima', 'na_media', 'abaixo'),
    percentil estimado de poupança e um resumo textual acionável.

    Use esta ferramenta quando o usuário perguntar sobre:
    - Como seus gastos se comparam com pessoas de renda parecida
    - Se gasta mais ou menos que a media em alguma categoria (moradia, alimentacao, lazer)
    - Qual seu percentil de poupanca em relacao a outros com a mesma renda

    Args:
        user_id: ID do usuário (obrigatório).
        monthly_income: Renda mensal líquida em R$ (obrigatório — determina a faixa de referência).
        history_months: Meses de histórico de transações a considerar (padrão: 3, máx: 12).
    """
    logger.info(
        "[Tool] get_peer_comparison user=%s income=R$%.0f history=%dm",
        user_id, monthly_income, history_months,
    )
    if monthly_income <= 0:
        return "FALHA: Para usar o get_peer_comparison, você precisa saber a renda mensal do usuário (monthly_income > 0). PERGUNTE ao usuário qual é a sua faixa de renda ou salário mensal para poder compará-lo aos pares."
        
    try:
        from app.peers.peer_comparison import PeerComparator
        from app.db.queries import get_transactions_for_user
        import polars as pl
        import datetime

        # Buscar transações do PostgreSQL
        try:
            df = get_transactions_for_user(user_id)
        except Exception as db_err:
            logger.warning("[Tool] get_peer_comparison: erro ao buscar transacoes: %s", db_err)
            df = pl.DataFrame()

        # Filtrar por janela e pegar apenas débitos
        if not df.is_empty() and "date" in df.columns:
            cutoff = datetime.date.today() - datetime.timedelta(days=history_months * 30)
            df = df.filter(pl.col("date").cast(pl.Date) >= cutoff)
            debit_rows = df.filter(pl.col("amount") < 0).select(["amount", "category"]).to_dicts()
        else:
            debit_rows = []

        if not debit_rows:
            # Sem dados reais: responde com os benchmarks da faixa apenas
            return _fallback_benchmark_only(monthly_income)

        # Agregar por categoria (media mensal)
        raw: dict[str, float] = {}
        for row in debit_rows:
            cat = (row.get("category") or "outros").lower().strip()
            raw[cat] = raw.get(cat, 0.0) + abs(float(row["amount"]))

        category_spending = (
            {k: v / history_months for k, v in raw.items()}
            if history_months > 1
            else raw
        )

        comparator = PeerComparator()
        report = comparator.compare(
            monthly_income=monthly_income,
            category_spending=category_spending,
        )

        lines = [
            f"Comparacao com Pares — Faixa: {report.bracket_label}",
            f"Renda referencia: R$ {monthly_income:,.0f}/mês",
            f"Indice de Poupanca: {report.user_savings_rate * 100:.1f}% "
            f"(benchmark: {report.benchmark_savings_rate * 100:.1f}%)",
            f"Seu percentil de poupanca: {report.savings_percentile_label}",
            "-" * 40,
        ]

        # Categorias acima da média (prioridade)
        acima = [c for c in report.categories if c.status == "acima"]
        abaixo = [c for c in report.categories if c.status == "abaixo"]
        na_media = [c for c in report.categories if c.status == "na_media"]

        if acima:
            lines.append("Voce gasta ACIMA da media em:")
            for c in acima:
                lines.append(
                    f"  {c.label}: {c.user_pct:.1f}% da renda "
                    f"(media: {c.benchmark_pct:.1f}%, delta: +{c.delta_pct:.1f} p.p.)"
                )
                if c.insight:
                    lines.append(f"    → {c.insight}")
            lines.append("")

        if abaixo:
            lines.append("Voce gasta ABAIXO da media em:")
            for c in abaixo:
                lines.append(
                    f"  {c.label}: {c.user_pct:.1f}% da renda "
                    f"(media: {c.benchmark_pct:.1f}%, delta: {c.delta_pct:.1f} p.p.)"
                )
            lines.append("")

        if na_media:
            labels = ", ".join(c.label for c in na_media)
            lines.append(f"Na media: {labels}")
            lines.append("")

        lines.append(f"Resumo: {report.summary_text}")

        return "\n".join(lines)

    except Exception as e:
        logger.error("[Tool] get_peer_comparison erro: %s", e, exc_info=True)
        return _fallback_benchmark_only(monthly_income)


def _fallback_benchmark_only(monthly_income: float) -> str:
    """
    Resposta quando não há dados de transações do usuário.
    Usa PeerComparator.compare() com gastos zerados para obter
    os benchmarks da faixa pela API pública, sem acessar internos.
    """
    try:
        from app.peers.peer_comparison import PeerComparator

        report = PeerComparator().compare(
            monthly_income=monthly_income,
            category_spending={},   # sem gastos → benchmarks puros da faixa
            savings_amount=0.0,
        )

        lines = [
            f"Benchmarks IBGE/POF para {report.bracket_label}:",
            "(Sem transacoes suficientes para comparacao personalizada — mostrando medias da faixa)",
            "-" * 40,
        ]
        # Ordena por benchmark_pct desc para mostrar categorias mais relevantes primeiro
        for c in sorted(report.categories, key=lambda x: -x.benchmark_pct):
            lines.append(f"  {c.label}: {c.benchmark_pct * 100:.0f}% da renda (media da faixa)")
        lines.append("")
        lines.append(
            "Para ver como seus gastos se comparam com a media, "
            "conecte suas contas bancarias via Open Finance."
        )
        return "\n".join(lines)
    except Exception:
        return (
            "Nao foi possivel comparar seus gastos com a media agora. "
            "Conecte suas contas bancarias para uma analise personalizada."
        )
