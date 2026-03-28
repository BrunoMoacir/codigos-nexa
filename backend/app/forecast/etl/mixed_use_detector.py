"""
app/etl/mixed_use_detector.py - Deteccao de Uso Misto PF/PJ (M4.3)

Identifica transacoes que podem ter uso parcialmente PJ (ex: plano de celular
usado para trabalho e pessoal) e sugere percentual de rateio.

Util para declaracao de IR: despesas de uso misto podem ser parcialmente
deduzidas como despesa operacional PJ.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from app.core.db.queries import get_transactions_for_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regras de uso misto
# Cada entrada: (label_amigavel, pct_pj_sugerido, keywords_de_descricao_ou_merchant)
# pct_pj: percentual da despesa que pode ser considerado PJ (0.0 a 1.0)
# ---------------------------------------------------------------------------
# Nota: keywords prefixadas com r"\b" usam word boundary (re.search).
# Isso resolve o problema de nomes de operadoras/marcas que aparecem
# no final da string (ex: "fatura claro", "pagamento tim").
#
# Hierarquia de classificacao:
# O MixedUseDetector opera APENAS sobre transacoes com context_type PF ou
# UNCERTAIN (_fetch_pf_transactions filtra isso). Se o PFPJClassifier ja
# rotulou a transacao como PJ, ela nao chega aqui — o percentual sugerido
# abaixo e um fallback para quando a classificacao PJ falha, nao substitui
# a classificacao completa como PJ.
_MIXED_USE_RULES: list[tuple[str, float, list[str]]] = [
    ("Telefone / Celular", 0.50, [
        "celular", "telefone", r"\btim\b", r"\bclaro\b", r"\bvivo\b", r"\boi\b",
        "nextel", "tim empresa", "plano celular", "tim black", "claro controle",
        "tim controle", "operadora", "fatura celular",
    ]),
    ("Internet / Banda Larga", 0.30, [
        "internet", "banda larga", "fibra", r"\bnet\b", "claro net", "vivo fibra",
        "tim live", "oi fibra", "giga", "provedor internet",
    ]),
    ("Combustivel", 0.40, [
        "combustivel", "gasolina", "etanol", "diesel", r"\bposto\b", "shell",
        "ipiranga", "br distribuidora", "petroleo", "abastecimento",
    ]),
    ("Energia Eletrica", 0.20, [
        "energia", "cemig", r"\blight\b", r"\benel\b", "copel", "cpfl", "coelba",
        "celpe", "eletricidade", "fatura energia", "conta de luz",
    ]),
    ("Almoco / Refeicao de Trabalho", 0.30, [
        "almoco", "almoco reuniao", "jantar negocios", "reuniao almoco",
        "refeicao trabalho", "ifood trabalho", "business lunch",
    ]),
    # LinkedIn e ferramentas profissionais: o PJSubcategoryClassifier ja os
    # classifica como despesa_software (PJ = 100%) se PFPJClassifier rotular
    # como PJ. Este bloco cobre o caso de escape (rotulado como PF por engano).
    ("Assinatura Profissional", 0.70, [
        "linkedin premium", r"\blinkedin\b", "coursera", "udemy", "alura",
        "pluralsight", "skillshare", r"\bmedium\b", "substack", "kindle unlimited",
        "office 365 pessoal", "microsoft 365 personal",
    ]),
    ("Transporte / Pedagio", 0.40, [
        "pedagio", "sem parar", "conectcar", r"\bveloe\b", "move mais",
        "estacionamento", "parking",
    ]),
    ("Home Office / Escritorio", 0.25, [
        "cadeira", "mesa escritorio", "monitor home", "headset", "webcam",
        "ergonomia", "home office",
    ]),
]


@dataclass
class MixedUseCandidate:
    transaction_id: str
    description: str
    amount: float                  # valor total (absoluto)
    date: str
    matched_rule: str              # ex: "Telefone / Celular"
    suggested_pj_pct: float        # ex: 0.50
    pj_amount: float               # amount * pct_pj
    pf_amount: float               # amount * (1 - pct_pj)
    explanation: str               # texto amigavel para o usuario


@dataclass
class MixedUseReport:
    user_id: str
    period_label: str
    candidates: list[MixedUseCandidate] = field(default_factory=list)
    total_mixed_spend: float = 0.0
    total_pj_deductible: float = 0.0   # soma dos pj_amount de todos os candidatos


class MixedUseDetector:
    """
    Detecta transacoes com potencial de uso misto PF/PJ.

    Analisa transacoes classificadas como PF (ou UNCERTAIN) e verifica se
    descricao/merchant bate com padroes de despesas tipicamente compartilhadas.
    """

    def detect(
        self,
        user_id: str,
        year: int,
        month: Optional[int] = None,
    ) -> MixedUseReport:
        period_label = f"{year:04d}-{month:02d}" if month else str(year)
        logger.info("Detectando uso misto user=%s periodo=%s", user_id, period_label)

        rows = self._fetch_pf_transactions(user_id, year, month)
        report = MixedUseReport(user_id=user_id, period_label=period_label)

        for row in rows:
            candidate = self._check_mixed_use(row)
            if candidate:
                report.candidates.append(candidate)
                report.total_mixed_spend += candidate.amount
                report.total_pj_deductible += candidate.pj_amount

        report.total_mixed_spend = round(report.total_mixed_spend, 2)
        report.total_pj_deductible = round(report.total_pj_deductible, 2)

        logger.info(
            f"Uso misto: {len(report.candidates)} candidatos, "
            f"dedutivel PJ estimado = R$ {report.total_pj_deductible:.2f}"
        )
        return report

    # ------------------------------------------------------------------

    def _fetch_pf_transactions(
        self, user_id: str, year: int, month: Optional[int]
    ) -> list[dict]:
        import polars as pl
        try:
            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            # Filtrar context_type PF/UNCERTAIN e débitos
            df = df.with_columns(pl.col("date").cast(pl.Date))
            df = df.filter(
                pl.col("context_type").is_in(["PF", "UNCERTAIN"]) &
                (pl.col("amount") < 0)
            )

            # Filtrar por ano
            df = df.filter(pl.col("date").dt.year() == year)
            if month is not None:
                df = df.filter(pl.col("date").dt.month() == month)

            rows = df.select(["transaction_id", "description", "amount", "date"]).to_dicts()
            return [
                {
                    "transaction_id": r["transaction_id"],
                    "description": r.get("description") or "",
                    "amount": abs(float(r["amount"] or 0.0)),
                    "date": str(r["date"]) if r["date"] else "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Erro ao buscar transacoes PF para uso misto: %s", e)
            return []

    def _check_mixed_use(self, row: dict) -> Optional[MixedUseCandidate]:
        text = row["description"].lower()

        for rule_label, pct_pj, keywords in _MIXED_USE_RULES:
            if any(re.search(kw, text) if kw.startswith(r"\b") else kw in text for kw in keywords):
                amount = row["amount"]
                pj_amount = round(amount * pct_pj, 2)
                pf_amount = round(amount * (1 - pct_pj), 2)
                pct_display = int(pct_pj * 100)

                explanation = (
                    f"{rule_label}: {pct_display}% pode ser deduzido como despesa PJ "
                    f"(R$ {pj_amount:.2f} de R$ {amount:.2f}). "
                    f"Registre o rateio na sua contabilidade."
                )

                return MixedUseCandidate(
                    transaction_id=row["transaction_id"],
                    description=row["description"],
                    amount=amount,
                    date=row["date"],
                    matched_rule=rule_label,
                    suggested_pj_pct=pct_pj,
                    pj_amount=pj_amount,
                    pf_amount=pf_amount,
                    explanation=explanation,
                )

        return None
