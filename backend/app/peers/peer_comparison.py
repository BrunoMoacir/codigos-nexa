"""
app/peers/peer_comparison.py — Comparação Anônima com Perfis Similares (MX.4)

RESPONSABILIDADE:
    Compara o perfil de gastos do usuário com benchmarks agregados baseados na
    Pesquisa de Orçamentos Familiares (POF) 2022-2023 do IBGE.

    Para o MVP os benchmarks são hardcoded por faixa de renda.
    Em produção V2, substituir pelos dados agregados anônimos da própria base.

FONTE DOS BENCHMARKS:
    IBGE — Pesquisa de Orçamentos Familiares 2022-2023.
    Ajustes aplicados em relação à POF 2017-2018:
    - Alimentacao:  +1-2 p.p. (pressão inflacionária pós-2020)
    - Saude:        +1 p.p.   (maior consciência e gasto pós-COVID)
    - Outros:       +1 p.p.   (crescimento de streaming e assinaturas digitais)
    - Vestuario:    -1 p.p.   (home office reduziu gastos com roupas formais)
    - Poupanca:     ajuste para refletir menor capacidade de poupança nas faixas BAIXA/MEDIA

FAIXAS DE RENDA:
    BAIXA:   até R$ 3.000/mês
    MEDIA:   R$ 3.001 – R$ 8.000/mês
    ALTA:    R$ 8.001 – R$ 20.000/mês
    PREMIUM: R$ 20.001+/mês

CATEGORIAS COMPARADAS:
    moradia, alimentacao, transporte, saude, lazer,
    educacao, vestuario, outros, poupanca

USAGE:
    comparator = PeerComparator()
    report = comparator.compare(
        monthly_income=8000,
        category_spending={"moradia": 2400, "alimentacao": 1200, ...},
    )
    print(report.summary_text)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from app.core.formatacao import numero


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BENCHMARKS — IBGE/POF 2022-2023 (% da renda líquida)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BENCHMARKS: dict[str, dict[str, float]] = {
    # Renda até R$ 3.000/mês: maior peso em alimentação e moradia.
    # POF 2022-2023 mostra pressão inflacionária elevando share de alimentos +2 p.p.
    # Poupança reduzida pelo aumento do custo de vida.
    "BAIXA": {
        "moradia":      0.40,
        "alimentacao":  0.27,
        "transporte":   0.11,
        "saude":        0.06,
        "lazer":        0.03,
        "educacao":     0.02,
        "vestuario":    0.02,
        "outros":       0.06,
        "poupanca":     0.03,
    },
    # Renda R$ 3.001–R$ 8.000/mês: classe média com melhor diversificação.
    # Crescimento de streaming/assinaturas digitais eleva "outros" +1 p.p.
    # Vestuário cai -1 p.p. (home office pós-pandemia).
    "MEDIA": {
        "moradia":      0.30,
        "alimentacao":  0.19,
        "transporte":   0.10,
        "saude":        0.06,
        "lazer":        0.08,
        "educacao":     0.05,
        "vestuario":    0.03,
        "outros":       0.08,
        "poupanca":     0.11,
    },
    # Renda R$ 8.001–R$ 20.000/mês: menor share em necessidades básicas,
    # mais espaço para lazer, educação e investimentos.
    "ALTA": {
        "moradia":      0.24,
        "alimentacao":  0.12,
        "transporte":   0.08,
        "saude":        0.07,
        "lazer":        0.12,
        "educacao":     0.07,
        "vestuario":    0.03,
        "outros":       0.08,
        "poupanca":     0.19,
    },
    # Renda acima de R$ 20.000/mês: maior capacidade de poupança e investimento.
    # Saúde sobe para 8% (planos premium, check-ups, bem-estar).
    "PREMIUM": {
        "moradia":      0.18,
        "alimentacao":  0.08,
        "transporte":   0.05,
        "saude":        0.08,
        "lazer":        0.15,
        "educacao":     0.08,
        "vestuario":    0.03,
        "outros":       0.08,
        "poupanca":     0.27,
    },
}

_INCOME_RANGES: list[tuple[str, float, float]] = [
    ("BAIXA",   0.0,      3_000.0),
    ("MEDIA",   3_001.0,  8_000.0),
    ("ALTA",    8_001.0,  20_000.0),
    ("PREMIUM", 20_001.0, float("inf")),
]

_BRACKET_LABEL: dict[str, str] = {
    "BAIXA":   "renda baixa (até R$ 3.000/mês)",
    "MEDIA":   "renda média (R$ 3.001–R$ 8.000/mês)",
    "ALTA":    "renda alta (R$ 8.001–R$ 20.000/mês)",
    "PREMIUM": "renda premium (acima de R$ 20.000/mês)",
}

_CATEGORY_LABELS: dict[str, str] = {
    "moradia":     "Moradia",
    "alimentacao": "Alimentação",
    "transporte":  "Transporte",
    "saude":       "Saúde",
    "lazer":       "Lazer",
    "educacao":    "Educação",
    "vestuario":   "Vestuário",
    "outros":      "Outros",
    "poupanca":    "Poupança",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OFFSETS POR CLUSTER — deltas (p.p.) sobre o benchmark de faixa de renda
#
# Representam o padrão observado de cada cluster: o que pessoas com esse
# estilo de vida gastam a mais/menos em cada categoria vs. a média da faixa.
# Somados ao benchmark IBGE/POF resultam no benchmark efetivo do cluster.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_CLUSTER_OFFSETS: dict[str, dict[str, float]] = {
    # Viajante frequente: mais transporte e lazer (passagens, hotéis, experiências),
    # compensa reduzindo moradia (apê menor ou alugado) e poupança.
    "EXPLORADOR_GLOBAL": {
        "transporte":  +0.05,
        "lazer":       +0.05,
        "moradia":     -0.03,
        "alimentacao": -0.01,
        "poupanca":    -0.04,
        "outros":      +0.01,
    },
    # Investidor ativo: poupança/investimentos elevados, reduz lazer e consumo discricionário.
    "INVESTIDOR_CAUTELOSO": {
        "poupanca":    +0.10,
        "lazer":       -0.04,
        "vestuario":   -0.02,
        "outros":      -0.04,
    },
    # Família com filhos: mais moradia (espaço), alimentação e educação;
    # lazer individual cai, poupança comprimida pelas despesas fixas.
    "FAMILIA_ESTRUTURADA": {
        "moradia":     +0.04,
        "alimentacao": +0.03,
        "educacao":    +0.05,
        "lazer":       -0.03,
        "vestuario":   -0.01,
        "poupanca":    -0.05,
    },
    # MEI/autônomo: mais "outros" (ferramentas PJ, coworking, NF-e) e transporte
    # (deslocamentos de negócio); poupança irregular.
    "MICROEMPREENDEDOR": {
        "outros":      +0.06,
        "transporte":  +0.02,
        "poupanca":    -0.03,
        "lazer":       -0.02,
        "alimentacao": -0.01,
    },
    # Sob pressão financeira: moradia e alimentação consomem fatia maior;
    # lazer e poupança comprimidos.
    "ESTRESSE_FINANCEIRO": {
        "moradia":     +0.05,
        "alimentacao": +0.03,
        "poupanca":    -0.06,
        "lazer":       -0.02,
    },
}

# Rótulo de cluster para uso em frases de insight
_CLUSTER_LABELS: dict[str, str] = {
    "EXPLORADOR_GLOBAL":    "viajantes frequentes",
    "INVESTIDOR_CAUTELOSO": "investidores ativos",
    "FAMILIA_ESTRUTURADA":  "famílias com filhos",
    "MICROEMPREENDEDOR":    "microempreendedores",
    "ESTRESSE_FINANCEIRO":  "perfis sob pressão financeira",
}

# Limiar de desvio para classificar "acima"/"abaixo" da média (3 p.p.)
_DELTA_THRESHOLD = 0.03


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATACLASSES DE RESULTADO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CategoryComparison:
    """Posicionamento do usuário em uma categoria vs. benchmark da faixa."""
    category: str
    label: str
    user_pct: float               # % da renda do usuário (decimal)
    benchmark_pct: float          # % da renda da faixa (decimal)
    user_amount_brl: float        # R$ gastos pelo usuário
    benchmark_amount_brl: float   # R$ de referência da faixa
    delta_pct: float              # user_pct - benchmark_pct
    status: str                   # "acima" | "na_media" | "abaixo"
    insight: str                  # frase explicativa


@dataclass
class PeerComparisonReport:
    """Resultado completo da comparação com perfis similares."""
    income_bracket: str
    bracket_label: str
    monthly_income: float
    user_savings_rate: float        # % de poupança do usuário (decimal)
    benchmark_savings_rate: float   # % de poupança da faixa (decimal)
    savings_percentile_label: str   # "top 10%", "top 40%", etc.
    categories: list[CategoryComparison]
    highlights_above: list[str]     # categorias acima da média (nomes amigáveis)
    highlights_below: list[str]     # categorias com controle acima da média
    summary_text: str
    lifestyle_cluster: str = "NAO_CLASSIFICADO"
    cluster_label: str = ""          # ex: "viajantes frequentes"
    benchmark_source: str = "IBGE/POF 2022-2023"

    def to_dict(self) -> dict:
        return {
            "income_bracket":           self.income_bracket,
            "bracket_label":            self.bracket_label,
            "monthly_income":           self.monthly_income,
            "user_savings_rate":        round(self.user_savings_rate * 100, 1),
            "benchmark_savings_rate":   round(self.benchmark_savings_rate * 100, 1),
            "savings_percentile_label": self.savings_percentile_label,
            "lifestyle_cluster":        self.lifestyle_cluster,
            "cluster_label":            self.cluster_label,
            "benchmark_source":         self.benchmark_source,
            "categories": [
                {
                    "category":             c.category,
                    "label":                c.label,
                    "user_pct":             round(c.user_pct * 100, 1),
                    "benchmark_pct":        round(c.benchmark_pct * 100, 1),
                    "user_amount_brl":       round(c.user_amount_brl, 2),
                    "benchmark_amount_brl":  round(c.benchmark_amount_brl, 2),
                    "delta_pct":            round(c.delta_pct * 100, 1),
                    "status":               c.status,
                    "insight":              c.insight,
                }
                for c in self.categories
            ],
            "highlights_above": self.highlights_above,
            "highlights_below": self.highlights_below,
            "summary_text":     self.summary_text,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMPARADOR PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PeerComparator:
    """
    Compara o perfil de gastos do usuário com benchmarks por faixa de renda.

    Categorias desconhecidas são agrupadas automaticamente em 'outros'.
    A poupança pode ser informada explicitamente ou calculada como residual.

    Example:
        >>> cmp = PeerComparator()
        >>> report = cmp.compare(
        ...     monthly_income=8000,
        ...     category_spending={"moradia": 2400, "alimentacao": 1200},
        ... )
        >>> print(report.summary_text)
    """

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _get_bracket(monthly_income: float) -> str:
        for bracket, lo, hi in _INCOME_RANGES:
            if lo <= monthly_income <= hi:
                return bracket
        return "PREMIUM"

    @staticmethod
    def _effective_benchmarks(
        bracket: str,
        lifestyle_cluster: str,
    ) -> tuple[dict[str, float], str, str]:
        """
        Retorna (benchmarks_efetivos, cluster_label, benchmark_source).

        Aplica os offsets de cluster sobre o benchmark IBGE/POF da faixa de renda.
        Categorias são clampeadas em [0, 1] após o ajuste.
        Quando cluster desconhecido, retorna o benchmark de faixa sem alteração.
        """
        base = dict(_BENCHMARKS[bracket])
        offsets = _CLUSTER_OFFSETS.get(lifestyle_cluster, {})

        if not offsets:
            return base, "", "IBGE/POF 2022-2023"

        effective = {
            cat: max(0.0, min(1.0, base.get(cat, 0.0) + offsets.get(cat, 0.0)))
            for cat in base
        }
        cluster_label    = _CLUSTER_LABELS.get(lifestyle_cluster, "perfis similares")
        benchmark_source = f"IBGE/POF 2022-2023 + cluster {lifestyle_cluster}"
        return effective, cluster_label, benchmark_source

    @staticmethod
    def _savings_percentile_label(
        user_rate: float,
        benchmark_rate: float,
    ) -> str:
        """Estima o percentil do usuário com base no desvio da poupança vs. faixa."""
        if benchmark_rate <= 0:
            return "top 50%"
        ratio = user_rate / benchmark_rate
        if ratio >= 1.5:
            return "top 10%"
        elif ratio >= 1.2:
            return "top 25%"
        elif ratio >= 1.0:
            return "top 40%"
        elif ratio >= 0.8:
            return "metade inferior"
        elif ratio >= 0.5:
            return "30% inferiores"
        return "10% inferiores"

    @staticmethod
    def _normalize_category(cat: str) -> str:
        """Normaliza nome de categoria para a chave canônica."""
        mapping = {
            "habitacao": "moradia",
            "aluguel": "moradia",
            "supermercado": "alimentacao",
            "mercado": "alimentacao",
            "combustivel": "transporte",
            "uber": "transporte",
            "onibus": "transporte",
            "farmacia": "saude",
            "medico": "saude",
            "plano_de_saude": "saude",
            "escola": "educacao",
            "entretenimento": "lazer",
            "streaming": "lazer",
            "restaurante": "lazer",
            "delivery": "lazer",
            "bar": "lazer",
            "viagem": "lazer",
            "turismo": "lazer",
            "roupas": "vestuario",
            "moda": "vestuario",
            "assinaturas": "outros",
        }
        import unicodedata
        key = "".join(
            c for c in unicodedata.normalize("NFD", cat or "") if unicodedata.category(c) != "Mn"
        ).lower().strip().replace(" ", "_")
        return mapping.get(key, key)

    # ── Método principal ─────────────────────────────────────────────

    def compare(
        self,
        monthly_income: float,
        category_spending: dict[str, float],
        savings_amount: Optional[float] = None,
        lifestyle_cluster: str = "NAO_CLASSIFICADO",
    ) -> PeerComparisonReport:
        """
        Compara gastos por categoria com benchmarks IBGE/POF ajustados ao cluster.

        Args:
            monthly_income:    Renda mensal líquida (R$).
            category_spending: Dict categoria → valor gasto no mês (R$, valores positivos).
                               Categorias desconhecidas são somadas em 'outros'.
            savings_amount:    Valor poupado no mês (R$). Se None, calculado como
                               max(0, income - total_expenses).
            lifestyle_cluster: Cluster comportamental do usuário (optional).
                               Quando fornecido, aplica offsets específicos do cluster
                               sobre os benchmarks IBGE/POF, gerando comparações
                               como "viajantes frequentes com sua renda gastam X%".

        Returns:
            PeerComparisonReport com posicionamento por categoria e texto de resumo.

        Raises:
            ValueError: Se monthly_income for <= 0.
        """
        if monthly_income <= 0:
            raise ValueError("monthly_income deve ser positivo")

        bracket = self._get_bracket(monthly_income)
        benchmarks, cluster_label, benchmark_source = self._effective_benchmarks(
            bracket, lifestyle_cluster
        )
        known_cats = set(benchmarks.keys()) - {"poupanca"}

        # Agrupar gastos nas categorias canônicas
        normalized: dict[str, float] = {k: 0.0 for k in known_cats}
        for cat, amount in category_spending.items():
            key = self._normalize_category(cat)
            if key in normalized:
                normalized[key] += abs(float(amount))
            else:
                normalized["outros"] = normalized.get("outros", 0.0) + abs(float(amount))

        total_expenses = sum(normalized.values())

        if savings_amount is None:
            savings_amount = max(0.0, monthly_income - total_expenses)
        user_savings_rate = savings_amount / monthly_income
        benchmark_savings_rate = benchmarks["poupanca"]

        # Construir comparações por categoria
        comparisons: list[CategoryComparison] = []
        for cat in sorted(known_cats):
            user_amt   = normalized.get(cat, 0.0)
            user_pct   = user_amt / monthly_income
            bench_pct  = benchmarks.get(cat, 0.0)
            bench_amt  = bench_pct * monthly_income
            delta      = user_pct - bench_pct
            label      = _CATEGORY_LABELS.get(cat, cat.title())

            peer_ref = (
                f"{cluster_label} com sua renda"
                if cluster_label else
                "perfis similares"
            )
            if delta > _DELTA_THRESHOLD:
                status  = "acima"
                insight = (
                    f"Você gasta {numero(user_pct*100, 1)}% da renda em {label.lower()} "
                    f"— {numero(delta*100, 1)} p.p. acima do esperado para {peer_ref} ({numero(bench_pct*100, 1)}%)."
                )
            elif delta < -_DELTA_THRESHOLD:
                status  = "abaixo"
                insight = (
                    f"Você gasta {numero(user_pct*100, 1)}% em {label.lower()} "
                    f"— {numero(abs(delta)*100, 1)} p.p. abaixo do esperado para {peer_ref} ({numero(bench_pct*100, 1)}%). "
                    "Ótimo controle."
                )
            else:
                status  = "na_media"
                insight = (
                    f"Seu gasto em {label.lower()} ({numero(user_pct*100, 1)}%) "
                    f"está dentro do esperado para {peer_ref} ({numero(bench_pct*100, 1)}%)."
                )

            comparisons.append(CategoryComparison(
                category=cat,
                label=label,
                user_pct=user_pct,
                benchmark_pct=bench_pct,
                user_amount_brl=user_amt,
                benchmark_amount_brl=bench_amt,
                delta_pct=delta,
                status=status,
                insight=insight,
            ))

        # Adicionar poupança como categoria especial
        savings_delta = user_savings_rate - benchmark_savings_rate
        peer_ref_savings = (
            f"{cluster_label} com sua renda"
            if cluster_label else
            f"perfis similares ({_BRACKET_LABEL[bracket]})"
        )
        if savings_delta > _DELTA_THRESHOLD:
            savings_status  = "acima"
            savings_insight = (
                f"Seu índice de poupança ({numero(user_savings_rate*100, 1)}%) está "
                f"{numero(savings_delta*100, 1)} p.p. acima do esperado para {peer_ref_savings} "
                f"({numero(benchmark_savings_rate*100, 1)}%). Excelente!"
            )
        elif savings_delta < -_DELTA_THRESHOLD:
            savings_status  = "abaixo"
            savings_insight = (
                f"Seu índice de poupança ({numero(user_savings_rate*100, 1)}%) está "
                f"{numero(abs(savings_delta)*100, 1)} p.p. abaixo do esperado para {peer_ref_savings} "
                f"({numero(benchmark_savings_rate*100, 1)}%)."
            )
        else:
            savings_status  = "na_media"
            savings_insight = (
                f"Seu índice de poupança ({numero(user_savings_rate*100, 1)}%) "
                f"está dentro do esperado para {peer_ref_savings} ({numero(benchmark_savings_rate*100, 1)}%)."
            )

        comparisons.append(CategoryComparison(
            category="poupanca",
            label=_CATEGORY_LABELS["poupanca"],
            user_pct=user_savings_rate,
            benchmark_pct=benchmark_savings_rate,
            user_amount_brl=savings_amount,
            benchmark_amount_brl=benchmark_savings_rate * monthly_income,
            delta_pct=savings_delta,
            status=savings_status,
            insight=savings_insight,
        ))

        # Listas de destaques (excluindo poupança — já aparece no resumo)
        highlights_above = [
            c.label for c in comparisons
            if c.status == "acima" and c.category != "poupanca"
        ]
        highlights_below = [
            c.label for c in comparisons
            if c.status == "abaixo" and c.category != "poupanca"
        ]

        percentile_label = self._savings_percentile_label(user_savings_rate, benchmark_savings_rate)

        # Texto de resumo
        parts: list[str] = []
        peer_group = (
            f"{cluster_label} com renda similar"
            if cluster_label else
            f"perfis similares ({_BRACKET_LABEL[bracket]})"
        )
        if highlights_above:
            parts.append(f"Gasta acima do esperado em: {', '.join(highlights_above[:3])}.")
        if highlights_below:
            parts.append(f"Controle acima do esperado em: {', '.join(highlights_below[:3])}.")
        parts.append(
            f"Índice de poupança ({numero(user_savings_rate*100, 1)}%) — {percentile_label} "
            f"dos {peer_group}."
        )
        summary_text = " ".join(parts)

        return PeerComparisonReport(
            income_bracket=bracket,
            bracket_label=_BRACKET_LABEL[bracket],
            monthly_income=monthly_income,
            user_savings_rate=user_savings_rate,
            benchmark_savings_rate=benchmark_savings_rate,
            savings_percentile_label=percentile_label,
            categories=comparisons,
            highlights_above=highlights_above,
            highlights_below=highlights_below,
            summary_text=summary_text,
            lifestyle_cluster=lifestyle_cluster,
            cluster_label=cluster_label,
            benchmark_source=benchmark_source,
        )


__all__ = ["PeerComparator", "PeerComparisonReport", "CategoryComparison"]
