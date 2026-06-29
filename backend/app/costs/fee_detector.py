"""
app/costs/fee_detector.py — F5: Detector de Tarifas Bancárias

Responsabilidades:
  1. Mapear institution_id → nome legível do banco
  2. Detectar tarifas em transações via regex (description + merchant)
  3. Retornar lista de FeeEntry para o BankFeeAnalyzer agregar

Critério de detecção:
  - Apenas débitos (amount < 0)
  - Description ou merchant bate com ao menos um padrão de FeeType
  - Valor absoluto > R$ 0,50 (filtra estornos parciais e IOF de centavos isolados)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from typing import Optional

import polars as pl

from app.costs.models import FeeEntry, FeeType

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAPA: institution_id (Pluggy) → nome legível do banco
# Fonte: IDs públicos do sandbox Pluggy + mapeamento manual
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INSTITUTION_ID_MAP: dict[str, str] = {
    # Nubank
    "nubank": "Nubank",
    "291": "Nubank",
    # Itaú
    "itau": "Itaú",
    "341": "Itaú",
    # Bradesco
    "bradesco": "Bradesco",
    "237": "Bradesco",
    # Banco do Brasil
    "bb": "Banco do Brasil",
    "001": "Banco do Brasil",
    # Santander
    "santander": "Santander",
    "033": "Santander",
    # Caixa Econômica
    "caixa": "Caixa Econômica",
    "104": "Caixa Econômica",
    # Inter
    "inter": "Banco Inter",
    "077": "Banco Inter",
    # C6 Bank
    "c6": "C6 Bank",
    "336": "C6 Bank",
    # Next (Bradesco digital)
    "next": "Next",
    # XP
    "xp": "XP",
    "102": "XP",
    # PicPay
    "picpay": "PicPay",
}

# Fallback: detecta banco a partir de palavras-chave na descrição
_BANK_KEYWORDS: list[tuple[str, str]] = [
    (r"\bnubank\b",          "Nubank"),
    (r"\bitau\b",            "Itaú"),
    (r"\bbradesco\b",        "Bradesco"),
    (r"\bbanco do brasil\b", "Banco do Brasil"),
    (r"\bsantander\b",       "Santander"),
    (r"\bcaixa\b",           "Caixa Econômica"),
    (r"\binter\b",           "Banco Inter"),
    (r"\bc6\b",              "C6 Bank"),
    (r"\bnext\b",            "Next"),
    (r"\bxp\b",              "XP"),
    (r"\bpicpay\b",          "PicPay"),
]
_BANK_KEYWORD_RES = [(re.compile(p), name) for p, name in _BANK_KEYWORDS]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PADRÕES DE DETECÇÃO DE TARIFA
# Ordem importa: mais específico primeiro
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_FEE_PATTERNS: list[tuple[FeeType, re.Pattern]] = [
    (FeeType.ANUIDADE_CARTAO,    re.compile(r"\banuidade\b|\bannual.?fee\b")),
    (FeeType.SEGURO_PRESTAMISTA, re.compile(r"\bseguro\s+(prestamista|vida|credito|credit)\b")),
    # SEGURO_EMBUTIDO: seguros não-crédito vinculados a produtos bancários — correlação D1 completa fica em defense/
    (FeeType.SEGURO_EMBUTIDO,    re.compile(r"\bseguro\s+(habitacional|automovel|residencial|protecao|garantia|cobertura)\b")),
    (FeeType.PACOTE_SERVICOS,    re.compile(r"\bpacote\s+(de\s+)?(servicos?|tarifas?)\b")),
    (FeeType.JUROS_ROTATIVO,     re.compile(r"\bjuros\b|\bencargo\b|\brotativo\b|\bjuro\s+rotativo\b")),
    (FeeType.IOF,                re.compile(r"\biof\b|\bimposto\s+sobre\s+operac")),
    (FeeType.SAQUE,              re.compile(r"\bsaque\b")),
    (FeeType.TED_DOC,            re.compile(r"\b(ted|doc)\b(?!.*pix)")),  # exclui quando contexto é PIX
    (FeeType.TARIFA_MANUTENCAO,  re.compile(
        r"\btarifa\b|\btaxa\s+(de\s+)?(manutencao|conta|servico|cadastro)\b"
        r"|\bcusto\s+(de\s+)?conta\b|\bmensalidade\s+(conta|cartao)\b"
    )),
]

_MIN_FEE_VALUE = 0.50  # R$ — filtra micro-cobranças isoladas


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FeeDetector
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FeeDetector:
    """
    Detecta tarifas bancárias em um DataFrame de transações.

    Usage:
        detector = FeeDetector()
        fees = detector.detect(transactions_df)
    """

    def detect(self, transactions_df: pl.DataFrame) -> list[FeeEntry]:
        """
        Varre as transações e retorna cada cobrança de tarifa identificada.

        Args:
            transactions_df: DataFrame com colunas obrigatórias:
                transaction_date, amount, description, institution_id.
                Coluna merchant é opcional (usada como fallback de texto).

        Returns:
            Lista de FeeEntry ordenada por data (mais recente primeiro).
        """
        if transactions_df.is_empty():
            return []

        # Compatibilidade com diferentes fontes: algumas pipelines usam `date`
        # ao invés de `transaction_date`.
        if "transaction_date" not in transactions_df.columns and "date" in transactions_df.columns:
            transactions_df = transactions_df.with_columns(
                pl.col("date").alias("transaction_date")
            )

        # institution_id pode não estar disponível em alguns fluxos locais.
        # Nesses casos mantemos vazio e aplicamos fallback por descrição.
        if "institution_id" not in transactions_df.columns:
            transactions_df = transactions_df.with_columns(
                pl.lit("").alias("institution_id")
            )

        required = {"transaction_date", "amount", "description"}
        missing = required - set(transactions_df.columns)
        if missing:
            logger.warning("FeeDetector | colunas ausentes: %s — retornando vazio", missing)
            return []

        fees: list[FeeEntry] = []

        # Apenas débitos acima do limiar mínimo
        debits = transactions_df.filter(pl.col("amount") < -_MIN_FEE_VALUE)

        # PERF NOTE: iter_rows em Python puro — limitação conhecida.
        # _classify aplica até 8 regex sequenciais por linha para garantir
        # prioridade de match (específico → genérico). Vetorizar com
        # pl.col().str.contains() exigiria múltiplas passes sem controle de
        # ordem, o que produziria classificações ambíguas (ex: "tarifa de juros"
        # poderia cair em TARIFA_MANUTENCAO antes de JUROS_ROTATIVO).
        # Aceitável para o volume atual (MVP, <10K transações/usuário).
        # TODO: Fase 2 — implementar via pl.when().then() em cadeia para
        # execução em Rust mantendo a ordem de prioridade.
        for row in debits.iter_rows(named=True):
            raw_desc = row.get("description") or ""
            raw_merchant = row.get("merchant") or ""
            text = _normalize_text(f"{raw_desc} {raw_merchant}".strip())

            fee_type = self._classify(text)
            if fee_type is None:
                continue

            institution_id = str(row.get("institution_id") or "")
            bank_name = self._resolve_bank_name(institution_id, text)

            tx_date = row["transaction_date"]
            if hasattr(tx_date, "date"):
                tx_date = tx_date.date()

            fees.append(
                FeeEntry(
                    transaction_date=tx_date,
                    fee_type=fee_type,
                    amount=abs(float(row["amount"])),
                    bank_name=bank_name,
                    institution_id=institution_id,
                    description=row.get("description") or "",
                )
            )

        fees.sort(key=lambda f: f.transaction_date, reverse=True)
        logger.info("FeeDetector | %d tarifa(s) detectada(s) em %d transações", len(fees), debits.height)
        return fees

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _classify(text: str) -> Optional[FeeType]:
        """Retorna o FeeType do primeiro padrão que casar, ou None."""
        for fee_type, pattern in _FEE_PATTERNS:
            if pattern.search(text):
                return fee_type
        return None

    @staticmethod
    def _resolve_bank_name(institution_id: str, text: str) -> str:
        """
        Resolve o nome do banco em duas etapas:
          1. Lookup direto por institution_id
          2. Fallback: keyword na descrição da transação
        """
        name = INSTITUTION_ID_MAP.get(institution_id.lower())
        if name:
            return name

        for pattern, bank_name in _BANK_KEYWORD_RES:
            if pattern.search(text):
                return bank_name

        return f"Banco ({institution_id})" if institution_id else "Banco desconhecido"


def _normalize_text(value: str) -> str:
    """Normaliza acentos e caixa para melhorar matching por regex."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return no_accents.lower()
