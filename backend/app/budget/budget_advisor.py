"""
app/cashflow/budget_advisor.py — Orçamento Inteligente por Categoria (M1.3)

RESPONSABILIDADE:
    Baseado no histórico de 3+ meses, analisa a distribuição de gastos por
    categoria e sugere limites usando a regra 50/30/20 adaptada ao perfil real.

REGRA 50/30/20:
    - 50% da renda → Essenciais   (moradia, alimentacao, transporte, saude, educacao)
    - 30% da renda → Desejos      (lazer, vestuario, assinaturas, outros)
    - 20% da renda → Poupança     (investimentos, poupanca, reserva)

SAÍDA:
    "Com base nos seus últimos 3 meses, seu padrão: Essenciais 58% (acima do ideal de
    50%). Sugestão: reduza R$380/mês em alimentação para equilibrar."

INTEGRAÇÃO:
    - Mesmo padrão de BurnRateAnalyzer: recebe pl.DataFrame de transações
    - Exposto via GET /api/v1/cashflow/budget (novo endpoint)
    - Integrado ao CashflowEngine.analyze() via campo 'budget_advice'

USAGE:
    >>> advisor = BudgetAdvisor()
    >>> suggestion = advisor.suggest(transactions_df, monthly_income=8000.0)
    >>> print(suggestion.summary_text)
    "Essenciais: 58% (ideal 50%) — acima. Lazer: 22% (ideal 30%) — dentro."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import polars as pl

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONSTANTES — REGRA 50/30/20
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Categorias classificadas por grupo (adaptado ao padrão de categorias do sistema)
ESSENTIALS: frozenset[str] = frozenset([
    "moradia", "habitacao", "aluguel",
    "alimentacao", "supermercado", "mercado",
    "transporte", "combustivel", "uber", "onibus",
    "saude", "farmacia", "medico", "plano_de_saude",
    "educacao", "escola",
])

WANTS: frozenset[str] = frozenset([
    "lazer", "entretenimento", "streaming",
    "vestuario", "roupas", "moda",
    "restaurante", "delivery", "bar",
    "viagem", "turismo",
    "assinaturas", "outros",
])

SAVINGS: frozenset[str] = frozenset([
    "investimentos", "poupanca", "previdencia",
    "reserva_emergencia", "aplicacao",
])

# Metas ideais padrão (regra 50/30/20)
_TARGET_PCT: dict[str, float] = {
    "essenciais": 0.50,
    "desejos":    0.30,
    "poupanca":   0.20,
}

# Metas ajustadas por cluster de estilo de vida.
# Apenas os 5 clusters com padrão de gasto claramente diferente do 50/30/20 padrão.
# Clusters não listados aqui herdam _TARGET_PCT.
_CLUSTER_TARGETS: dict[str, dict] = {
    "EXPLORADOR_GLOBAL": {
        "essenciais": 0.47,
        "desejos":    0.35,  # viagem é estilo de vida, não desperdício
        "poupanca":   0.18,
        "rule_label": "47/35/18 (viajante)",
        "note": (
            "Viajante frequente: alocamos 35% para Desejos (inclui viagens como estilo de vida) "
            "e reduzimos a meta de Poupança para 18%."
        ),
    },
    "INVESTIDOR_CAUTELOSO": {
        "essenciais": 0.50,
        "desejos":    0.20,  # menos consumo para investir mais
        "poupanca":   0.30,  # eleva poupança para 30%
        "rule_label": "50/20/30 (investidor)",
        "note": (
            "Investidor ativo: meta de Poupança elevada para 30% para alimentar aportes mensais. "
            "Desejos limitados a 20%."
        ),
    },
    "ESTRESSE_FINANCEIRO": {
        "essenciais": 0.55,  # provavelmente estouram essenciais
        "desejos":    0.15,  # corte agressivo de desejos
        "poupanca":   0.30,  # prioriza reserva de emergência
        "rule_label": "55/15/30 (foco em estabilidade)",
        "note": (
            "⚠️ Pressão financeira detectada: Desejos reduzidos a 15% e reserva de emergência "
            "priorizada (30%). Foque em estabilizar antes de qualquer gasto discricionário."
        ),
    },
    "FAMILIA_ESTRUTURADA": {
        "essenciais": 0.55,  # escola, saúde e alimentação são naturalmente maiores
        "desejos":    0.25,
        "poupanca":   0.20,
        "rule_label": "55/25/20 (família)",
        "note": (
            "Família com filhos: Essenciais ajustados para 55% — escola, saúde e alimentação "
            "naturalmente ultrapassam os 50% do padrão."
        ),
    },
    "MICROEMPREENDEDOR": {
        "essenciais": 0.50,
        "desejos":    0.30,
        "poupanca":   0.20,
        "rule_label": "50/30/20 (apenas fluxo PF)",
        "note": (
            "⚠️ MEI/autônomo detectado: este orçamento considera SOMENTE o fluxo pessoal (PF). "
            "Receitas e despesas PJ devem ser gerenciadas em conta separada para não distorcer a análise."
        ),
    },
}

# Status de alocação
_STATUS_OVER  = "OVER"    # acima do ideal
_STATUS_UNDER = "UNDER"   # abaixo do ideal (bom para poupança, ruim para essenciais)
_STATUS_OK    = "WITHIN"  # dentro do ideal

# Tolerância antes de sinalizar OVER/UNDER (+/- 3 p.p.)
_TOLERANCE_PCT = 0.03

# Mínimo de meses históricos para sugestão confiável
_MIN_HISTORY_MONTHS = 1

# Número de meses a usar como histórico (padrão: 3)
_DEFAULT_HISTORY_MONTHS = 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CategoryAllocation:
    """
    Alocação atual vs. sugerida para uma categoria de gasto.

    Attributes:
        category:         Nome da categoria (ex: "alimentacao")
        group:            Grupo 50/30/20: "essenciais" | "desejos" | "poupanca"
        current_amount:   Média mensal atual nos últimos N meses (R$)
        current_pct:      % do total de gastos (ex: 0.28 = 28%)
        suggested_amount: Limite sugerido pela regra 50/30/20 (R$)
        suggested_pct:    % alvo do grupo (ex: 0.50 para essenciais / nº categorias)
        status:           WITHIN | OVER | UNDER
    """
    category: str
    group: str
    current_amount: float
    current_pct: float
    suggested_amount: float
    suggested_pct: float
    status: str

    def to_dict(self) -> dict:
        return {
            "category":        self.category,
            "group":           self.group,
            "current_amount":  round(self.current_amount, 2),
            "current_pct":     round(self.current_pct * 100, 1),
            "suggested_amount": round(self.suggested_amount, 2),
            "suggested_pct":   round(self.suggested_pct * 100, 1),
            "status":          self.status,
        }


@dataclass
class BudgetCut:
    """
    Corte sugerido em uma categoria específica.

    Attributes:
        category:    Categoria a cortar
        group:       Grupo 50/30/20
        current:     Gasto médio atual (R$)
        suggested:   Limite proposto (R$)
        saving:      Economia mensal potencial (R$)
        reasoning:   Justificativa em linguagem natural
    """
    category: str
    group: str
    current: float
    suggested: float
    saving: float
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "category":  self.category,
            "group":     self.group,
            "current":   round(self.current, 2),
            "suggested": round(self.suggested, 2),
            "saving":    round(self.saving, 2),
            "reasoning": self.reasoning,
        }


@dataclass
class GroupSummary:
    """
    Resumo de um grupo 50/30/20 (essenciais / desejos / poupança).

    Attributes:
        group:          Nome do grupo
        current_amount: Total médio mensal atual (R$)
        current_pct:    % da renda atual
        target_pct:     % alvo ideal
        suggested_amount: Limite ideal (R$) = renda × target_pct
        status:         WITHIN | OVER | UNDER
        delta_pct:      Diferença vs. alvo em p.p. (positivo = acima)
    """
    group: str
    current_amount: float
    current_pct: float
    target_pct: float
    suggested_amount: float
    status: str
    delta_pct: float

    def to_dict(self) -> dict:
        return {
            "group":            self.group,
            "current_amount":   round(self.current_amount, 2),
            "current_pct":      round(self.current_pct * 100, 1),
            "target_pct":       round(self.target_pct * 100, 1),
            "suggested_amount": round(self.suggested_amount, 2),
            "status":           self.status,
            "delta_pct":        round(self.delta_pct * 100, 1),
        }


@dataclass
class BudgetSuggestion:
    """
    Sugestão completa de orçamento 50/30/20 para o usuário.

    Attributes:
        income:              Renda mensal usada como base (R$)
        history_months:      Meses de histórico analisados
        total_expenses_avg:  Média mensal de despesas no período (R$)
        expenses_pct_income: % da renda comprometido em despesas (ex: 0.78 = 78%)
        savings_gap:         Quanto falta para atingir a meta de 20% de poupança (R$)
        group_summary:       Resumo dos 3 grupos (essenciais/desejos/poupança)
        allocations:         Detalhamento por categoria
        actionable_cuts:     Cortes concretos sugeridos (ordenados por economia)
        rule_applied:        Descrição da regra usada
        summary_text:        Texto resumo em linguagem natural
        confidence:          0.0–1.0 — menor quando histórico curto ou sem renda
    """
    income: float
    history_months: int
    total_expenses_avg: float
    expenses_pct_income: float
    savings_gap: float
    group_summary: list[GroupSummary]
    allocations: list[CategoryAllocation]
    actionable_cuts: list[BudgetCut]
    rule_applied: str = "50/30/20 adaptado"
    summary_text: str = ""
    confidence: float = 1.0
    lifestyle_cluster: str = "NAO_CLASSIFICADO"
    cluster_note: str = ""

    def to_dict(self) -> dict:
        return {
            "income":              round(self.income, 2),
            "history_months":      self.history_months,
            "total_expenses_avg":  round(self.total_expenses_avg, 2),
            "expenses_pct_income": round(self.expenses_pct_income * 100, 1),
            "savings_gap":         round(self.savings_gap, 2),
            "group_summary":       [g.to_dict() for g in self.group_summary],
            "allocations":         [a.to_dict() for a in self.allocations],
            "actionable_cuts":     [c.to_dict() for c in self.actionable_cuts],
            "rule_applied":        self.rule_applied,
            "summary_text":        self.summary_text,
            "confidence":          round(self.confidence, 2),
            "lifestyle_cluster":   self.lifestyle_cluster,
            "cluster_note":        self.cluster_note,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUDGET ADVISOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BudgetAdvisor:
    """
    Analisa o histórico de transações e sugere orçamentos por categoria
    usando a regra 50/30/20 adaptada ao perfil real do usuário.

    Fluxo:
        1. Filtra despesas dos últimos N meses (excluindo mês atual incompleto)
        2. Calcula média mensal por categoria via Polars (vetorizado)
        3. Classifica cada categoria no grupo 50/30/20
        4. Calcula % atual vs. % alvo por grupo
        5. Identifica categorias com excesso e sugere cortes concretos
        6. Gera texto de sugestão em linguagem natural

    Args:
        history_months: Meses de histórico para calcular a média. Padrão: 3.

    Example:
        >>> advisor = BudgetAdvisor()
        >>> suggestion = advisor.suggest(transactions_df, monthly_income=8000.0)
        >>> print(suggestion.summary_text)
        "Essenciais: 58% da renda (ideal 50%) — acima do ideal em 8 p.p."
    """

    def __init__(self, history_months: int = _DEFAULT_HISTORY_MONTHS):
        self._history_months = history_months

    def suggest(
        self,
        transactions_df: pl.DataFrame,
        monthly_income: float,
        reference_month: Optional[tuple[int, int]] = None,
        lifestyle_cluster: str = "NAO_CLASSIFICADO",
    ) -> BudgetSuggestion:
        """
        Gera sugestão de orçamento baseada no histórico de transações.

        Args:
            transactions_df: DataFrame com colunas:
                - transaction_date (Date ou Datetime)
                - amount (Float, negativos = despesa)
                - category (Str)
            monthly_income: Renda mensal líquida (R$). Obrigatório para
                calcular % e sugestões da regra 50/30/20.
            reference_month: (ano, mês) de referência para calcular histórico.
                Padrão: mês atual.
            lifestyle_cluster: Cluster comportamental do usuário (via ConsumptionProfiler).
                Ajusta os targets ideais de cada grupo. Padrão: "NAO_CLASSIFICADO" (50/30/20).

        Returns:
            BudgetSuggestion com alocações, cortes e texto de sugestão.
        """
        if monthly_income <= 0:
            raise ValueError("monthly_income deve ser positivo")

        # Resolve targets e nota do cluster — padrão 50/30/20 para clusters não mapeados
        cluster_cfg   = _CLUSTER_TARGETS.get(lifestyle_cluster, {})
        active_targets = {
            "essenciais": cluster_cfg.get("essenciais", _TARGET_PCT["essenciais"]),
            "desejos":    cluster_cfg.get("desejos",    _TARGET_PCT["desejos"]),
            "poupanca":   cluster_cfg.get("poupanca",   _TARGET_PCT["poupanca"]),
        }
        cluster_note  = cluster_cfg.get("note", "")
        rule_label    = cluster_cfg.get("rule_label", "50/30/20 adaptado")

        if transactions_df.is_empty():
            return self._empty_suggestion(monthly_income, lifestyle_cluster, cluster_note, rule_label)

        required = {"transaction_date", "amount", "category"}
        missing = required - set(transactions_df.columns)
        if missing:
            logger.warning("Colunas faltando no DataFrame: %s", missing)
            return self._empty_suggestion(monthly_income)

        # ── 1. Preparar DataFrame ──────────────────────────────────────
        df = transactions_df
        if df.schema.get("transaction_date") != pl.Datetime:
            df = df.with_columns(pl.col("transaction_date").cast(pl.Datetime))

        df = df.with_columns([
            pl.col("transaction_date").dt.year().alias("_year"),
            pl.col("transaction_date").dt.month().alias("_month"),
            (
                pl.col("transaction_date").dt.year().cast(pl.Utf8)
                + "-"
                + pl.col("transaction_date").dt.month().cast(pl.Utf8)
            ).alias("_ym"),
        ])

        # Apenas despesas (amount < 0)
        df_expenses = df.filter(pl.col("amount") < 0)
        if df_expenses.is_empty():
            return self._empty_suggestion(monthly_income)

        # ── 2. Determinar meses de histórico ──────────────────────────
        from datetime import date as _date
        if reference_month is None:
            today = _date.today()
            ref_year, ref_month = today.year, today.month
        else:
            ref_year, ref_month = reference_month

        hist_months = _previous_months(ref_year, ref_month, self._history_months)
        hist_ym_set = {f"{y}-{m}" for y, m in hist_months}
        months_found = int(
            df_expenses.filter(pl.col("_ym").is_in(hist_ym_set))
            .select("_ym").unique().height
        )

        df_hist = df_expenses.filter(pl.col("_ym").is_in(hist_ym_set))

        if df_hist.is_empty():
            # Fallback: usa o mês de referência corrente
            current_ym = f"{ref_year}-{ref_month}"
            df_hist = df_expenses.filter(pl.col("_ym") == current_ym)
            months_found = 1
            if df_hist.is_empty():
                return self._empty_suggestion(monthly_income)

        # ── 3. Média mensal por categoria ─────────────────────────────
        n_months = max(1, months_found)
        avg_by_cat = (
            df_hist
            .group_by("category")
            .agg(pl.col("amount").abs().sum().alias("total"))
            .with_columns((pl.col("total") / n_months).alias("monthly_avg"))
            .sort("monthly_avg", descending=True)
        )
        # ── 4. Classificar categorias nos grupos ─────────────────────
        rows = avg_by_cat.to_dicts()
        group_totals: dict[str, float] = {
            "essenciais": 0.0,
            "desejos":    0.0,
            "poupanca":   0.0,
        }
        cat_groups: dict[str, str] = {}

        for row in rows:
            cat = (row["category"] or "outros").lower().strip()
            group = _classify_category(cat)
            cat_groups[row["category"]] = group
            
            # Somes apenas despesas reais (ignora saídas que já são declaradamente reservas/investimentos)
            if group != "poupanca":
                group_totals[group] += row["monthly_avg"]

        # Recalcula o total de despesas sem a poupança explícita
        total_expenses_avg = group_totals["essenciais"] + group_totals["desejos"]

        # ── Poupança Real (Residual) ──────────────────────────────────
        # A regra 50/30/20 e o Health Score concordam que a poupança é a receita menos as despesas:
        # Se a pessoa gasta 70% em essenciais e 20% em desejos, sobram 10% de poupança passiva (mesmo se não os investiu).
        group_totals["poupanca"] = max(0.0, monthly_income - total_expenses_avg)

        # ── 5. Calcular GroupSummary ──────────────────────────────────
        group_summaries: list[GroupSummary] = []
        for group, target_pct in active_targets.items():
            amt = group_totals.get(group, 0.0)
            current_pct = amt / monthly_income if monthly_income > 0 else 0.0
            delta = current_pct - target_pct

            if delta > _TOLERANCE_PCT:
                status = _STATUS_OVER
            elif delta < -_TOLERANCE_PCT:
                status = _STATUS_UNDER
            else:
                status = _STATUS_OK

            group_summaries.append(GroupSummary(
                group=group,
                current_amount=round(amt, 2),
                current_pct=round(current_pct, 4),
                target_pct=target_pct,
                suggested_amount=round(monthly_income * target_pct, 2),
                status=status,
                delta_pct=round(delta, 4),
            ))

        # ── 6. CategoryAllocation por categoria ────────────────────────
        allocations: list[CategoryAllocation] = []
        for row in rows:
            cat = row["category"]
            group = cat_groups[cat]
            if group == "poupanca":
                continue
            
            amt = row["monthly_avg"]
            current_pct = amt / monthly_income if monthly_income > 0 else 0.0
            target_pct_group = active_targets.get(group, 0.0)

            # Número de categorias no grupo → split proporcional do target
            n_in_group = sum(1 for g in cat_groups.values() if g == group)
            suggested_pct = target_pct_group / max(1, n_in_group)
            suggested_amt = monthly_income * suggested_pct

            if current_pct > suggested_pct + _TOLERANCE_PCT:
                status = _STATUS_OVER
            elif current_pct < suggested_pct - _TOLERANCE_PCT:
                status = _STATUS_UNDER
            else:
                status = _STATUS_OK

            allocations.append(CategoryAllocation(
                category=cat,
                group=group,
                current_amount=round(amt, 2),
                current_pct=round(current_pct, 4),
                suggested_amount=round(suggested_amt, 2),
                suggested_pct=round(suggested_pct, 4),
                status=status,
            ))

        # ── 7. Actionable cuts ────────────────────────────────────────
        actionable_cuts: list[BudgetCut] = []
        over_groups = {g.group for g in group_summaries if g.status == _STATUS_OVER}

        for alloc in allocations:
            if alloc.status != _STATUS_OVER:
                continue
            saving = alloc.current_amount - alloc.suggested_amount
            if saving < 10.0:  # não sugere cortes de menos de R$10
                continue
            group_delta = next(
                (g.delta_pct for g in group_summaries if g.group == alloc.group), 0.0
            )
            reasoning = _build_reasoning(alloc, group_delta, monthly_income, n_months)
            actionable_cuts.append(BudgetCut(
                category=alloc.category,
                group=alloc.group,
                current=alloc.current_amount,
                suggested=alloc.suggested_amount,
                saving=round(saving, 2),
                reasoning=reasoning,
            ))

        # Ordenar por economia decrescente
        actionable_cuts.sort(key=lambda c: c.saving, reverse=True)

        # ── 8. Savings gap ────────────────────────────────────────────
        savings_group = next((g for g in group_summaries if g.group == "poupanca"), None)
        savings_gap = 0.0
        if savings_group and savings_group.status == _STATUS_UNDER:
            savings_gap = savings_group.suggested_amount - savings_group.current_amount

        # ── 9. Texto de resumo ─────────────────────────────────────────
        expenses_pct_income = total_expenses_avg / monthly_income if monthly_income > 0 else 0.0
        summary_text = _build_summary_text(
            group_summaries, savings_gap, monthly_income, n_months, cluster_note
        )

        # Confiança: menor com pouco histórico ou income estimado
        confidence = min(1.0, 0.5 + 0.5 * (n_months / self._history_months))

        logger.info(
            "BudgetAdvisor | cluster=%s | renda=R$%.0f | %d meses | "
            "essenciais=%.0f%% | desejos=%.0f%% | poupança=%.0f%% | cortes=%d",
            lifestyle_cluster,
            monthly_income,
            n_months,
            group_totals.get("essenciais", 0) / monthly_income * 100,
            group_totals.get("desejos", 0) / monthly_income * 100,
            group_totals.get("poupanca", 0) / monthly_income * 100,
            len(actionable_cuts),
        )

        return BudgetSuggestion(
            income=round(monthly_income, 2),
            history_months=n_months,
            total_expenses_avg=round(total_expenses_avg, 2),
            expenses_pct_income=round(expenses_pct_income, 4),
            savings_gap=round(savings_gap, 2),
            group_summary=group_summaries,
            allocations=allocations,
            actionable_cuts=actionable_cuts,
            rule_applied=rule_label,
            summary_text=summary_text,
            confidence=round(confidence, 2),
            lifestyle_cluster=lifestyle_cluster,
            cluster_note=cluster_note,
        )

    # ─────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _empty_suggestion(
        self,
        monthly_income: float,
        lifestyle_cluster: str = "NAO_CLASSIFICADO",
        cluster_note: str = "",
        rule_label: str = "50/30/20 adaptado",
    ) -> BudgetSuggestion:
        """Retorna sugestão neutra quando não há dados suficientes."""
        cluster_cfg = _CLUSTER_TARGETS.get(lifestyle_cluster, {})
        targets = {
            "essenciais": cluster_cfg.get("essenciais", _TARGET_PCT["essenciais"]),
            "desejos":    cluster_cfg.get("desejos",    _TARGET_PCT["desejos"]),
            "poupanca":   cluster_cfg.get("poupanca",   _TARGET_PCT["poupanca"]),
        }
        group_summaries = [
            GroupSummary(
                group=group,
                current_amount=0.0,
                current_pct=0.0,
                target_pct=target,
                suggested_amount=round(monthly_income * target, 2),
                status=_STATUS_UNDER,
                delta_pct=-target,
            )
            for group, target in targets.items()
        ]
        savings_target = targets["poupanca"]
        return BudgetSuggestion(
            income=round(monthly_income, 2),
            history_months=0,
            total_expenses_avg=0.0,
            expenses_pct_income=0.0,
            savings_gap=round(monthly_income * savings_target, 2),
            group_summary=group_summaries,
            allocations=[],
            actionable_cuts=[],
            rule_applied=rule_label,
            summary_text="Sem dados históricos suficientes para gerar orçamento.",
            confidence=0.0,
            lifestyle_cluster=lifestyle_cluster,
            cluster_note=cluster_note,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS UTILITÁRIOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _classify_category(category: str) -> str:
    """Classifica uma categoria no grupo 50/30/20."""
    cat = category.lower().strip()
    if cat in ESSENTIALS:
        return "essenciais"
    if cat in SAVINGS:
        return "poupanca"
    # Desejos por padrão (inclui 'outros')
    return "desejos"


def _previous_months(year: int, month: int, n: int) -> list[tuple[int, int]]:
    """Retorna os N meses anteriores a (year, month)."""
    result = []
    y, m = year, month
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        result.append((y, m))
    return result


def _build_reasoning(
    alloc: CategoryAllocation,
    group_delta_pct: float,
    income: float,
    n_months: int,
) -> str:
    """Gera justificativa para um corte sugerido."""
    saving = alloc.current_amount - alloc.suggested_amount
    pct_over = (alloc.current_pct - alloc.suggested_pct) * 100
    cat_label = alloc.category.replace("_", " ").title()

    parts = [
        f"Seu gasto médio em {cat_label} nos últimos {n_months} "
        f"{'mês' if n_months == 1 else 'meses'} foi de "
        f"R${alloc.current_amount:,.0f}/mês ({alloc.current_pct*100:.0f}% da renda)."
    ]

    if pct_over >= 5:
        parts.append(
            f"Está {pct_over:.0f} p.p. acima do ideal ({alloc.suggested_pct*100:.0f}%)."
        )

    parts.append(
        f"Reduzir para R${alloc.suggested_amount:,.0f}/mês liberaria "
        f"R${saving:,.0f}/mês para poupança ou objetivos."
    )

    if group_delta_pct > 0.05:
        group_label = {"essenciais": "Essenciais", "desejos": "Desejos"}.get(
            alloc.group, alloc.group.title()
        )
        parts.append(
            f"O grupo {group_label} está {group_delta_pct*100:.0f} p.p. acima do ideal."
        )

    return " ".join(parts)


def _build_summary_text(
    groups: list[GroupSummary],
    savings_gap: float,
    income: float,
    n_months: int,
    cluster_note: str = "",
) -> str:
    """Gera texto de resumo em linguagem natural."""
    period_label = f"últimos {n_months} {'mês' if n_months == 1 else 'meses'}"
    parts = []
    if cluster_note:
        parts.append(cluster_note)
    parts.append(f"Com base nos {period_label}:")

    labels = {"essenciais": "Essenciais", "desejos": "Desejos", "poupanca": "Poupança"}
    for g in groups:
        label = labels.get(g.group, g.group.title())
        cur = g.current_pct * 100
        tgt = g.target_pct * 100
        if g.status == _STATUS_OVER:
            parts.append(
                f"{label}: {cur:.0f}% (ideal {tgt:.0f}%) — acima do ideal "
                f"em {abs(g.delta_pct)*100:.0f} p.p."
            )
        elif g.status == _STATUS_UNDER and g.group == "poupanca":
            parts.append(
                f"{label}: {cur:.0f}% (ideal {tgt:.0f}%) — abaixo do ideal. "
                f"Faltam R${savings_gap:,.0f}/mês para atingir a meta."
            )
        else:
            parts.append(f"{label}: {cur:.0f}% (ideal {tgt:.0f}%) — dentro do esperado.")

    return " ".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVENIENCE FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def suggest_budget(
    transactions_df: pl.DataFrame,
    monthly_income: float,
    history_months: int = _DEFAULT_HISTORY_MONTHS,
    reference_month: Optional[tuple[int, int]] = None,
) -> BudgetSuggestion:
    """
    Convenience wrapper — gera sugestão de orçamento sem instanciar BudgetAdvisor.

    Example:
        >>> from app.budget.budget_advisor import suggest_budget
        >>> suggestion = suggest_budget(df, monthly_income=8000.0)
        >>> suggestion.summary_text
        "Com base nos últimos 3 meses: Essenciais: 58% (ideal 50%) — acima..."
    """
    return BudgetAdvisor(history_months=history_months).suggest(
        transactions_df, monthly_income, reference_month
    )


__all__ = [
    "BudgetAdvisor",
    "BudgetSuggestion",
    "CategoryAllocation",
    "BudgetCut",
    "GroupSummary",
    "suggest_budget",
    "ESSENTIALS",
    "WANTS",
    "SAVINGS",
]
