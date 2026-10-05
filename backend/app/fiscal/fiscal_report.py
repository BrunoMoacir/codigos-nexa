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
from app.tax.parametros_fiscais import BASE_LEGAL_FATOR_R, anexo_por_fator_r
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tabela simplificada do Simples Nacional — Anexo III (Servicos)
# Aliquota efetiva = (RBT12 * Aliq - PD) / RBT12
# Fonte: Lei Complementar 123/2006, tabelas por ano de vigência.
#
# MANUTENÇÃO: ao início de cada ano fiscal, verificar se a Receita Federal
# atualizou os limites de faixa e adicionar uma nova entrada em _SIMPLES_TABLES.
# Consultar: https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm
# ---------------------------------------------------------------------------

# Cada entrada: (limite_RBT12_anual, aliquota_nominal, parcela_deduzir)
_TableRow = tuple  # (int, float, int)

# Anexo V (Serviços SEM Fator R) — LC 123/2006. A escolha entre III e V não é
# opcional: depende do Fator R (folha de 12 meses ÷ receita de 12 meses ≥ 28%).
# O relatório assumia Anexo III sempre, e a diferença na primeira faixa é de
# 6% para 15,5% — 2,6× — justamente no caso mais comum de quem usaria isto:
# prestador de serviço com folha pequena.
_SIMPLES_TABLES_V: dict[int, list[_TableRow]] = {
    2018: [
        (180_000,    0.155,        0),
        (360_000,    0.180,    4_500),
        (720_000,    0.195,    9_900),
        (1_800_000,  0.205,   17_100),
        (3_600_000,  0.230,   62_100),
        (4_800_000,  0.305,  540_000),
    ],
}
_SIMPLES_TABLES_V[2024] = _SIMPLES_TABLES_V[2018]
_SIMPLES_TABLES_V[2025] = _SIMPLES_TABLES_V[2018]
_SIMPLES_TABLES_V[2026] = _SIMPLES_TABLES_V[2018]

_SIMPLES_TABLES: dict[int, list[_TableRow]] = {
    2018: [
        (180_000,    0.060,       0),
        (360_000,    0.112,   9_360),
        (720_000,    0.135,  17_640),
        (1_800_000,  0.160,  35_640),
        (3_600_000,  0.210, 125_640),
        (4_800_000,  0.330, 648_000),
    ],
    # 2019–2023: mesmos limites e alíquotas da tabela 2018 (LC 123/2006 não alterada)
    2024: [
        (180_000,    0.060,       0),
        (360_000,    0.112,   9_360),
        (720_000,    0.135,  17_640),
        (1_800_000,  0.160,  35_640),
        (3_600_000,  0.210, 125_640),
        (4_800_000,  0.330, 648_000),
    ],
    # 2025 e 2026: verificar atualização — usar tabela 2024 até confirmação
    2025: [
        (180_000,    0.060,       0),
        (360_000,    0.112,   9_360),
        (720_000,    0.135,  17_640),
        (1_800_000,  0.160,  35_640),
        (3_600_000,  0.210, 125_640),
        (4_800_000,  0.330, 648_000),
    ],
    2026: [
        (180_000,    0.060,       0),
        (360_000,    0.112,   9_360),
        (720_000,    0.135,  17_640),
        (1_800_000,  0.160,  35_640),
        (3_600_000,  0.210, 125_640),
        (4_800_000,  0.330, 648_000),
    ],
}


def _get_simples_table(year: int, anexo: str = "III") -> list[_TableRow]:
    """
    Tabela do Simples Nacional vigente para o ano e o anexo informados.

    Ano sem entrada exata → a tabela do ano mais recente ≤ year, com aviso.
    """
    tabelas = _SIMPLES_TABLES if anexo == "III" else _SIMPLES_TABLES_V
    if year in tabelas:
        return tabelas[year]
    available = sorted(y for y in tabelas if y <= year)
    if available:
        fallback_year = available[-1]
        logger.warning(
            "Tabela Simples Nacional Anexo %s para %d não cadastrada — usando %d. "
            "Atualize _SIMPLES_TABLES em fiscal_report.py.",
            anexo, year, fallback_year,
        )
        return tabelas[fallback_year]
    oldest = min(tabelas)
    logger.warning(
        "Usando tabela Simples Nacional Anexo %s de %d para o ano %d.", anexo, oldest, year
    )
    return tabelas[oldest]

_SUBCATEGORIES_RECEITA = {"receita_servicos", "receita_produtos", "receita_nao_classificada"}
_SUBCATEGORIES_DESPESA = {
    "despesa_software", "despesa_marketing", "despesa_transporte",
    "despesa_equipamento", "despesa_pessoal_pj", "despesa_imposto",
    "despesa_bancaria", "despesa_outros_pj",
}

_SUBCATEGORY_LABELS = {
    "receita_servicos":    "Receita de Servicos",
    "receita_produtos":    "Receita de Produtos",
    "receita_nao_classificada": "Receita (nao classificada)",
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
    rbt12_anualizado: float = 0.0   # RBT12 usado para determinar a faixa
    das_aliquota_efetiva: float = 0.0
    das_estimado: float = 0.0
    das_faixa: str = ""
    das_anexo: str = "III"          # III (com Fator R) ou V (sem)
    fator_r: Optional[float] = None # folha 12m / receita 12m
    das_observacao: str = ""

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
        logger.info("Gerando relatorio fiscal user=%s periodo=%s", user_id, period_label)

        rows = self._fetch_pj_transactions(user_id, year, month)

        if not rows:
            logger.warning("Nenhuma transacao PJ encontrada para %s em %s", user_id, period_label)

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

            # Filtrar apenas PJ — fill_null garante que registros sem context_type não passem
            df = df.filter(pl.col("context_type").fill_null("") == "PJ")

            # Filtrar por ano
            df = df.with_columns(pl.col("date").cast(pl.Date))
            df = df.filter(pl.col("date").dt.year() == year)

            # Filtrar por mês se especificado
            if month is not None:
                df = df.filter(pl.col("date").dt.month() == month)

            rows = df.select(["amount", "pj_subcategory"]).to_dicts()
            # O default era `despesa_outros_pj` para QUALQUER lançamento sem
            # subcategoria, inclusive crédito. Uma receita que o classificador
            # não reconheceu virava despesa: receita a menos, despesa a mais,
            # lucro errado nas duas pontas e DAS a MENOR — a direção que gera
            # multa. O sinal do lançamento é o desempate óbvio.
            return [
                {
                    "amount": r["amount"],
                    "pj_subcategory": r.get("pj_subcategory") or (
                        "receita_nao_classificada" if (r["amount"] or 0) > 0
                        else "despesa_outros_pj"
                    ),
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Erro ao buscar transacoes PJ: %s", e)
            return []

    def _aggregate(self, report: FiscalReport, rows: list[dict]) -> None:
        """
        Soma por subcategoria preservando o SINAL do líquido.

        `abs()` era aplicado ao total do grupo, o que funciona enquanto o grupo
        fecha no sinal esperado — e inverte quando não fecha. Um mês em que os
        estornos superam as vendas (vendas 2.000, estornos 5.000, líquido
        −3.000) virava R$ 3.000 de RECEITA, e o DAS era cobrado sobre
        devoluções. A receita bruta do período não pode ser negativa nem
        positiva-por-inversão: é o líquido, com piso em zero.
        """
        totals: dict[str, list] = {}   # subcategory -> [total_com_sinal, count]

        for row in rows:
            sub = row["pj_subcategory"]
            amount = row["amount"] or 0.0
            if sub not in totals:
                totals[sub] = [0.0, 0]
            totals[sub][0] += amount
            totals[sub][1] += 1

        receita_liquida = 0.0
        despesa_liquida = 0.0

        for sub, (total, count) in sorted(totals.items(), key=lambda x: -abs(x[1][0])):
            eh_receita = sub in _SUBCATEGORIES_RECEITA
            line = SubcategoryLine(
                subcategory=sub,
                label=_SUBCATEGORY_LABELS.get(sub, sub),
                # Receita mostra o líquido com sinal (negativo = estornos
                # maiores que as vendas). Despesa é módulo, como sempre foi.
                total=round(total if eh_receita else abs(total), 2),
                count=count,
            )
            if eh_receita:
                report.receitas.append(line)
                receita_liquida += total
            else:
                report.despesas.append(line)
                despesa_liquida += abs(total)

        report.total_receita = round(max(receita_liquida, 0.0), 2)
        report.total_despesa = round(despesa_liquida, 2)
        report.lucro_estimado = round(receita_liquida - despesa_liquida, 2)

    def _janela_12_meses_anteriores(
        self, user_id: str, year: int, month: int
    ) -> tuple[float, float]:
        """
        `(receita_12m, folha_12m)` dos DOZE MESES ANTERIORES ao período de
        apuração — que é o que a LC 123/2006, art. 18, § 1º manda usar.

        A janela anterior era `data_ref − 330 dias` até o fim do mês de
        referência: começava cinco dias depois do início do 12º mês anterior,
        INCLUÍA o próprio mês de apuração e ainda alcançava os primeiros dias
        do mês seguinte. Consequência prática: um mês forte empurrava a si
        mesmo para a faixa de cima. Com receita de R$ 15.000/mês e um junho de
        R$ 30.000, o RBT12 saía R$ 195.000 (Faixa 2) quando o legal era
        R$ 170.000 (Faixa 1).

        A folha sai da mesma passada porque é o denominador do Fator R, que
        usa exatamente a mesma janela.
        """
        import datetime

        import polars as pl

        try:
            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return 0.0, 0.0

            fim = datetime.date(year, month, 1)                     # exclusivo
            inicio = fim
            for _ in range(12):
                inicio = (inicio - datetime.timedelta(days=1)).replace(day=1)

            df = df.with_columns(pl.col("date").cast(pl.Date))
            janela = df.filter(
                (pl.col("context_type").fill_null("") == "PJ")
                & (pl.col("date") >= inicio)
                & (pl.col("date") < fim)
            )
            if janela.is_empty():
                return 0.0, 0.0

            receita = janela.filter(pl.col("amount") > 0).select(
                pl.col("amount").sum()
            ).item() or 0.0
            folha = janela.filter(
                pl.col("pj_subcategory").fill_null("") == "despesa_pessoal_pj"
            ).select(pl.col("amount").sum()).item() or 0.0

            return float(receita), abs(float(folha))
        except Exception as exc:
            logger.warning("Nao foi possivel calcular a janela de 12 meses: %s", exc)
            return 0.0, 0.0

    def _compute_das(self, report: FiscalReport, year: int, month: Optional[int]) -> None:
        """
        Estima o DAS do Simples Nacional para atividade de serviço.

        A faixa vem do RBT12 (doze meses ANTERIORES ao período), e a alíquota
        efetiva incide sobre a receita DO PERÍODO — nunca sobre o RBT12. Esse
        ponto o código já acertava.

        O que faltava era o **Fator R**: serviço só é Anexo III quando a folha
        dos mesmos doze meses representa 28% ou mais da receita bruta; abaixo
        disso é Anexo V, cuja primeira faixa é 15,5% contra 6% — 2,6× mais. O
        relatório assumia Anexo III em silêncio, e a folha necessária para
        decidir já estava no próprio relatório, em `despesa_pessoal_pj`.
        """
        if report.total_receita <= 0:
            report.das_estimado = 0.0
            report.das_faixa = "Sem receita"
            report.das_observacao = (
                "Sem receita bruta no período — nada a apurar."
            )
            return

        if month is not None:
            rbt12, folha_12m = self._janela_12_meses_anteriores(report.user_id, year, month)
            if rbt12 <= 0:
                # Primeiro mês de operação: a lei manda proporcionalizar a
                # receita do mês de início. O ×12 é a mesma ideia.
                rbt12 = report.total_receita * 12
                folha_12m = sum(
                    l.total for l in report.despesas if l.subcategory == "despesa_pessoal_pj"
                ) * 12
                report.das_observacao = (
                    "Histórico de 12 meses insuficiente — RBT12 estimado pela "
                    "receita do mês × 12."
                )
        else:
            rbt12 = report.total_receita
            folha_12m = sum(
                l.total for l in report.despesas if l.subcategory == "despesa_pessoal_pj"
            )

        _TETO_SIMPLES = 4_800_000
        if rbt12 > _TETO_SIMPLES:
            report.rbt12_anualizado = round(rbt12, 2)
            report.das_estimado = 0.0
            report.das_aliquota_efetiva = 0.0
            report.das_faixa = (
                "Fora do Simples Nacional — RBT12 acima de R$ 4.800.000 "
                "(regime Lucro Presumido ou Real)"
            )
            report.das_observacao = BASE_LEGAL_FATOR_R
            return

        report.rbt12_anualizado = round(rbt12, 2)

        anexo, fator_r = anexo_por_fator_r(folha_12m, rbt12)
        report.das_anexo = anexo
        report.fator_r = fator_r

        tabela = _get_simples_table(year, anexo)
        aliquota_nominal = 0.0
        parcela_deducao = 0
        faixa_num = 0

        for i, (limite, aliq, pd) in enumerate(tabela, start=1):
            if rbt12 <= limite:
                aliquota_nominal = aliq
                parcela_deducao = pd
                faixa_num = i
                break

        aliquota_efetiva = max(0.0, (rbt12 * aliquota_nominal - parcela_deducao) / rbt12)
        das = report.total_receita * aliquota_efetiva

        report.das_aliquota_efetiva = round(aliquota_efetiva * 100, 2)
        report.das_estimado = round(das, 2)
        report.das_faixa = f"Faixa {faixa_num} — Simples Nacional Anexo {anexo}"

        if not report.das_observacao:
            if fator_r is None:
                report.das_observacao = (
                    "Sem receita nos 12 meses anteriores para calcular o Fator R — "
                    f"aplicado o Anexo V, que é o mais conservador. {BASE_LEGAL_FATOR_R}"
                )
            else:
                report.das_observacao = (
                    f"Fator R = {numero(fator_r * 100, 1)}% (folha de {brl(folha_12m)} sobre "
                    f"receita de {brl(rbt12)} nos 12 meses anteriores) → Anexo "
                    f"{anexo}. {BASE_LEGAL_FATOR_R}"
                )

        report.das_observacao += (
            " Atenção: este é o cálculo do Simples Nacional (ME/EPP). O MEI "
            "estrito recolhe DAS de valor FIXO mensal pelo SIMEI, não percentual."
        )
