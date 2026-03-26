"""
app/etl/fiscal_report.py - Relatorio Fiscal Automatizado (M4.1)

Gera resumo mensal ou anual das transacoes PJ com:
- Receitas e despesas por subcategoria PJ
- Lucro estimado
- DAS estimado (Simples Nacional)

Uso:
    service = FiscalReportService()
    report = service.generate(user_id="u1", year=2026, month=1)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from app.core.db.queries import get_transactions_for_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tabela simplificada do Simples Nacional — Anexo III (Servicos)
# Aliquota efetiva = (RBT12 * Aliq - PD) / RBT12
# Fonte: Lei Complementar 123/2006, tabela vigente 2024.
# ---------------------------------------------------------------------------
_SIMPLES_NACIONAL_ANEXO_III = [
    # (limite_RBT12_anual, aliquota_nominal, parcela_deduzir)
    (180_000,    0.060,       0),
    (360_000,    0.112,   9_360),
    (720_000,    0.135,  17_640),
    (1_800_000,  0.160,  35_640),
    (3_600_000,  0.210,  125_640),
    (4_800_000,  0.330,  648_000),
]

_SUBCATEGORIES_RECEITA = {"receita_servicos", "receita_produtos"}
_SUBCATEGORIES_DESPESA = {
    "despesa_software", "despesa_marketing", "despesa_transporte",
    "despesa_equipamento", "despesa_pessoal_pj", "despesa_imposto",
    "despesa_bancaria", "despesa_outros_pj",
}

_SUBCATEGORY_LABELS = {
    "receita_servicos":    "Receita de Servicos",
    "receita_produtos":    "Receita de Produtos",
    "despesa_software":    "Software / SaaS",
    "despesa_marketing":   "Marketing",
    "despesa_transporte":  "Transporte",
    "despesa_equipamento": "Equipamentos / Escritorio",
    "despesa_pessoal_pj":  "Pessoal (pro-labore / RH)",
    "despesa_imposto":     "Impostos",
    "despesa_bancaria":    "Tarifas Bancarias",
    "despesa_outros_pj":   "Outros PJ",
}


@dataclass
class SubcategoryLine:
    subcategory: str
    label: str
    total: float
    count: int


@dataclass
class FiscalReport:
    user_id: str
    year: int
    month: Optional[int]           # None = relatorio anual
    period_label: str

    receitas: list[SubcategoryLine] = field(default_factory=list)
    despesas: list[SubcategoryLine] = field(default_factory=list)

    total_receita: float = 0.0
    total_despesa: float = 0.0
    lucro_estimado: float = 0.0

    # DAS — Simples Nacional (Anexo III — Servicos)
    rbt12_anualizado: float = 0.0   # receita bruta anualizada usada no calculo
    das_aliquota_efetiva: float = 0.0
    das_estimado: float = 0.0
    das_faixa: str = ""

    total_transactions: int = 0


class FiscalReportService:
    """
    Gera relatorio fiscal a partir das transacoes PJ salvas em transactions_clean.

    Args:
        user_id: ID do usuario.
        year: Ano do relatorio (ex: 2026).
        month: Mes 1-12. Se None, gera relatorio anual.
    """

    def generate(
        self,
        user_id: str,
        year: int,
        month: Optional[int] = None,
    ) -> FiscalReport:

        period_label = (
            f"{year:04d}-{month:02d}" if month else str(year)
        )
        logger.info(f"Gerando relatorio fiscal user={user_id} periodo={period_label}")

        rows = self._fetch_pj_transactions(user_id, year, month)

        if not rows:
            logger.warning(f"Nenhuma transacao PJ encontrada para {user_id} em {period_label}")

        report = FiscalReport(
            user_id=user_id,
            year=year,
            month=month,
            period_label=period_label,
            total_transactions=len(rows),
        )

        self._aggregate(report, rows)
        self._compute_das(report, year, month)

        return report

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _fetch_pj_transactions(
        self,
        user_id: str,
        year: int,
        month: Optional[int],
    ) -> list[dict]:
        import polars as pl
        try:
            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            # Filtrar apenas PJ
            df = df.filter(pl.col("context_type") == "PJ")

            # Filtrar por ano
            df = df.with_columns(pl.col("date").cast(pl.Date))
            df = df.filter(pl.col("date").dt.year() == year)

            # Filtrar por mês se especificado
            if month is not None:
                df = df.filter(pl.col("date").dt.month() == month)

            rows = df.select(["amount", "pj_subcategory"]).to_dicts()
            return [{"amount": r["amount"], "pj_subcategory": r.get("pj_subcategory") or "despesa_outros_pj"} for r in rows]
        except Exception as e:
            logger.error(f"Erro ao buscar transacoes PJ: {e}")
            return []

    def _aggregate(self, report: FiscalReport, rows: list[dict]) -> None:
        totals: dict[str, list] = {}   # subcategory -> [total, count]

        for row in rows:
            sub = row["pj_subcategory"]
            amount = row["amount"] or 0.0
            if sub not in totals:
                totals[sub] = [0.0, 0]
            totals[sub][0] += amount
            totals[sub][1] += 1

        for sub, (total, count) in sorted(totals.items(), key=lambda x: -abs(x[1][0])):
            line = SubcategoryLine(
                subcategory=sub,
                label=_SUBCATEGORY_LABELS.get(sub, sub),
                total=round(abs(total), 2),
                count=count,
            )
            if sub in _SUBCATEGORIES_RECEITA:
                report.receitas.append(line)
                report.total_receita += abs(total)
            else:
                report.despesas.append(line)
                report.total_despesa += abs(total)

        report.total_receita = round(report.total_receita, 2)
        report.total_despesa = round(report.total_despesa, 2)
        report.lucro_estimado = round(report.total_receita - report.total_despesa, 2)

    def _fetch_rbt12(self, user_id: str, year: int, month: int) -> float:
        """
        Calcula RBT12 real: soma das receitas PJ dos ultimos 12 meses encerrados
        antes do mes de referencia (inclusive).
        """
        import polars as pl
        import datetime

        try:
            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return 0.0

            ref_date = datetime.date(year, month, 1)
            start_date = ref_date - datetime.timedelta(days=330)  # ~11 meses

            df = df.with_columns(pl.col("date").cast(pl.Date))
            df = df.filter(
                (pl.col("context_type") == "PJ") &
                (pl.col("amount") > 0) &
                (pl.col("date") >= start_date) &
                (pl.col("date") < datetime.date(year, month, 28) + datetime.timedelta(days=4))
            )

            total = df.select(pl.col("amount").sum()).item()
            return float(total) if total else 0.0
        except Exception as e:
            logger.warning(f"Nao foi possivel calcular RBT12 real, usando fallback x12: {e}")
            return 0.0

    def _compute_das(self, report: FiscalReport, year: int, month: Optional[int]) -> None:
        """
        Estima DAS pelo Simples Nacional Anexo III (Servicos).

        Para relatorio mensal: usa RBT12 real (soma dos ultimos 12 meses)
        para determinar a faixa, depois aplica a aliquota efetiva sobre
        a receita do mes. Fallback: receita_mes * 12 se historico insuficiente.
        Para relatorio anual: usa a receita total do ano diretamente.
        """
        if report.total_receita <= 0:
            report.das_estimado = 0.0
            report.das_faixa = "Sem receita"
            return

        if month is not None:
            rbt12 = self._fetch_rbt12(report.user_id, year, month)
            if rbt12 <= 0:
                rbt12 = report.total_receita * 12  # fallback
        else:
            rbt12 = report.total_receita

        # Obs 2: empresas acima do teto do Simples Nacional
        _TETO_SIMPLES = 4_800_000
        if rbt12 > _TETO_SIMPLES:
            report.rbt12_anualizado = round(rbt12, 2)
            report.das_estimado = 0.0
            report.das_aliquota_efetiva = 0.0
            report.das_faixa = (
                "Fora do Simples Nacional — RBT12 acima de R$ 4.800.000 "
                "(regime Lucro Presumido ou Real)"
            )
            return

        report.rbt12_anualizado = round(rbt12, 2)

        aliquota_nominal = 0.0
        parcela_deducao = 0
        faixa_num = 0

        for i, (limite, aliq, pd) in enumerate(_SIMPLES_NACIONAL_ANEXO_III, start=1):
            if rbt12 <= limite:
                aliquota_nominal = aliq
                parcela_deducao = pd
                faixa_num = i
                break

        # Aliquota efetiva = (RBT12 * aliq_nominal - PD) / RBT12
        aliquota_efetiva = max(0.0, (rbt12 * aliquota_nominal - parcela_deducao) / rbt12)

        # DAS sobre a receita do periodo (nao sobre RBT12)
        das = report.total_receita * aliquota_efetiva

        report.das_aliquota_efetiva = round(aliquota_efetiva * 100, 2)  # em %
        report.das_estimado = round(das, 2)
        report.das_faixa = f"Faixa {faixa_num} — Simples Nacional Anexo III"
