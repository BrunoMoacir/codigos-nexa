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

BANCO_NAO_IDENTIFICADO = "Banco desconhecido"
_NOMES_CONHECIDOS = frozenset(INSTITUTION_ID_MAP.values())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PADRÕES DE DETECÇÃO DE TARIFA
# Ordem importa: mais específico primeiro
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Marcador explícito de COBRANÇA. É o que separa "TED" (a transferência que o
# usuário fez) de "TARIFA TED" (os R$ 10 que o banco cobrou por ela).
_MARCADOR_COBRANCA = r"(?:tarifa|tar|taxa|encargo|cobranca|deb\s+tar)"

_FEE_PATTERNS: list[tuple[FeeType, re.Pattern]] = [
    (FeeType.ANUIDADE_CARTAO,    re.compile(r"\banuidade\b|\bannual.?fee\b")),
    (FeeType.SEGURO_PRESTAMISTA, re.compile(r"\bseguro\s+(prestamista|vida|credito|credit)\b")),
    # SEGURO_EMBUTIDO: seguros não-crédito vinculados a produtos bancários — correlação D1 completa fica em defense/
    (FeeType.SEGURO_EMBUTIDO,    re.compile(r"\bseguro\s+(habitacional|automovel|residencial|protecao|garantia|cobertura)\b")),
    (FeeType.PACOTE_SERVICOS,    re.compile(r"\bpacote\s+(de\s+)?(servicos?|tarifas?)\b")),
    # ROTATIVO é específico do crédito rotativo do cartão — o produto predatório.
    # `\bjuros\b` sozinho casava em "PAGAMENTO JUROS EMPRESTIMO", que é custo de
    # crédito legítimo, não tarifa: o valor da linha é a prestação, não o encargo.
    (FeeType.JUROS_ROTATIVO,     re.compile(
        r"\brotativo\b|\b(juros|encargos?)\b.{0,20}\b(cartao|fatura|rotativ)"
        r"|\b(cartao|fatura)\b.{0,20}\b(juros|encargos?)\b"
    )),
    (FeeType.IOF,                re.compile(r"\biof\b|\bimposto\s+sobre\s+operac")),
    # SAQUE e TED/DOC exigem MARCADOR: sem ele, o valor casado é o da operação
    # (o dinheiro sacado, o dinheiro transferido), não o da cobrança. Era o
    # defeito de maior magnitude do F5 — uma TED de R$ 2.500 virava "tarifa de
    # R$ 2.500", e o relatório inflava 114x num extrato realista.
    (FeeType.SAQUE,              re.compile(
        rf"{_MARCADOR_COBRANCA}\b.{{0,25}}\bsaque\b|\bsaque\b.{{0,25}}\b{_MARCADOR_COBRANCA}\b"
    )),
    (FeeType.TED_DOC,            re.compile(
        rf"{_MARCADOR_COBRANCA}\b.{{0,25}}\b(ted|doc|transferencia)\b"
        rf"|\b(ted|doc|transferencia)\b.{{0,25}}\b{_MARCADOR_COBRANCA}\b"
    )),
    (FeeType.TARIFA_MANUTENCAO,  re.compile(
        r"\btarifa\b|\btaxa\s+(de\s+)?(manutencao|conta|servico|cadastro)\b"
        r"|\bcusto\s+(de\s+)?conta\b|\bmensalidade\s+(conta|cartao)\b"
    )),
]

_MIN_FEE_VALUE = 0.50  # R$ — filtra micro-cobranças isoladas

# PIX é gratuito para pessoa física — cobrança sobre PIX não é tarifa de TED.
# A exclusão é checada explicitamente em _classify(), e não por lookahead dentro
# do padrão: `(?!.*pix)` no início só vale para a posição testada, e re.search
# varre todas — bastava haver texto antes do "pix" para o lookahead passar numa
# posição posterior. Um guard legível não tem essa armadilha.
_RE_PIX = re.compile(r"\bpix\b")

# Teto de plausibilidade por tipo, em R$ por cobrança. NÃO é calibração — é
# sanidade: segunda linha de defesa para quando a descrição engana o regex.
# Uma cobrança acima do teto é descartada COM LOG, nunca em silêncio, porque
# falso negativo silencioso também é defeito (é o gap nº 1 da doc).
#
# IOF e JUROS_ROTATIVO ficam de fora de propósito: os dois escalam com o
# principal da operação e não têm ordem de grandeza fixa (IOF de crédito é 3%
# do principal; rotativo sobre fatura grande passa fácil de R$ 1.000).
_FEE_CEILINGS: dict[FeeType, float] = {
    FeeType.TARIFA_MANUTENCAO:  200.0,    # pacote mais caro do varejo fica < R$ 100
    FeeType.PACOTE_SERVICOS:    300.0,
    FeeType.TED_DOC:            150.0,    # tarifa de TED no varejo: R$ 5–30
    FeeType.SAQUE:              150.0,    # saque em rede parceira: R$ 5–20
    FeeType.ANUIDADE_CARTAO:   2500.0,    # cartão black à vista, sem parcelar
    FeeType.SEGURO_PRESTAMISTA: 800.0,    # prêmio mensal
    FeeType.SEGURO_EMBUTIDO:    800.0,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NORMALIZAÇÃO DO EXTRATO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def normalizar_extrato(
    transactions_df: pl.DataFrame, user_id: str | None = None
) -> pl.DataFrame:
    """
    Põe o extrato no vocabulário que o F5 espera, UMA vez, para todo mundo.

    Antes cada consumidor normalizava por conta própria — e o `FeeDetector`
    renomeava `date` → `transaction_date` só na sua CÓPIA LOCAL. O
    `BankFeeAnalyzer._calc_period` recebia o DataFrame original, não achava a
    coluna e devolvia 1 mês para qualquer histórico: a projeção anual saía
    inflada exatamente pelo número de meses de dados (12x para quem tem um
    ano). É a mesma deriva `date`/`transaction_date` que zerava a renda no ETL.

    Faz três coisas:
      1. `date` → `transaction_date` (o banco entrega `date`);
      2. preenche `institution_id` a partir de `account_id` quando há user_id;
      3. garante que a coluna `institution_id` exista.
    """
    if transactions_df.is_empty():
        return transactions_df

    if ("transaction_date" not in transactions_df.columns
            and "date" in transactions_df.columns):
        transactions_df = transactions_df.with_columns(
            pl.col("date").alias("transaction_date")
        )

    if user_id:
        transactions_df = enriquecer_institution_id(user_id, transactions_df)

    if "institution_id" not in transactions_df.columns:
        transactions_df = transactions_df.with_columns(
            pl.lit("").alias("institution_id")
        )

    return transactions_df


def enriquecer_institution_id(user_id: str, transactions_df: pl.DataFrame) -> pl.DataFrame:
    """
    Preenche `institution_id` via `account_id` → `account_balances`.

    `transactions_clean` NÃO tem coluna de instituição, e
    `get_transactions_for_user` não devolve nenhuma — então a resolução de banco
    do F5 colapsava na keyword da descrição. Só que extrato do Itaú diz
    "TARIFA MANUTENCAO CONTA", não "TARIFA ITAU": na prática toda tarifa caía em
    "Banco desconhecido", era comparada contra a média dos bancos tradicionais e
    virava conselho de migração fabricado — inclusive para quem já está num
    banco digital.

    Esta função existia em `BankMatchService._enrich_institution_id`, usada por
    1 dos 8 consumidores do analyzer. Foi promovida para cá para valer em todos.

    Só preenche onde está vazio — metadado existente nunca é sobrescrito.
    Falha aberta: qualquer problema devolve o DataFrame original.
    """
    try:
        from app.core.db.balances import get_account_bank_map
        from app.opportunities.services.bank_names import banks_match

        if "account_id" not in transactions_df.columns:
            return transactions_df
        bank_by_account = get_account_bank_map(user_id)
        if not bank_by_account:
            return transactions_df

        key_by_account: dict[str, str] = {}
        for account_id, bank_name in bank_by_account.items():
            for key, readable in INSTITUTION_ID_MAP.items():
                if banks_match(bank_name, readable):
                    key_by_account[account_id] = key
                    break

        if not key_by_account:
            return transactions_df

        mapper = pl.col("account_id").cast(pl.Utf8).replace_strict(
            key_by_account, default=""
        )
        if "institution_id" in transactions_df.columns:
            filled = (
                pl.when(
                    pl.col("institution_id").is_null()
                    | (pl.col("institution_id").cast(pl.Utf8) == "")
                )
                .then(mapper)
                .otherwise(pl.col("institution_id"))
            )
            return transactions_df.with_columns(filled.alias("institution_id"))
        return transactions_df.with_columns(mapper.alias("institution_id"))
    except Exception as exc:
        logger.debug("enriquecer_institution_id | user=%s: %s", user_id, exc)
        return transactions_df


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

        # Normalização compartilhada — ver normalizar_extrato(). Renomear aqui
        # dentro era o que fazia o cálculo de período divergir da detecção.
        transactions_df = normalizar_extrato(transactions_df)

        required = {"transaction_date", "amount", "description"}
        missing = required - set(transactions_df.columns)
        if missing:
            logger.warning("FeeDetector | colunas ausentes: %s — retornando vazio", missing)
            return []

        fees: list[FeeEntry] = []
        descartadas = 0

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

            valor = abs(float(row["amount"]))
            teto = _FEE_CEILINGS.get(fee_type)
            if teto is not None and valor > teto:
                # Segunda linha de defesa: a descrição enganou o regex e o valor
                # casado é o da operação, não o da cobrança. Descartar em
                # silêncio seria trocar um falso positivo por um falso negativo
                # invisível — por isso o WARNING.
                descartadas += 1
                logger.warning(
                    "FeeDetector | %s de R$ %.2f acima do teto de R$ %.2f — "
                    "descartada como provável valor de operação: %r",
                    fee_type.value, valor, teto, (row.get("description") or "")[:60],
                )
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
                    amount=valor,
                    bank_name=bank_name,
                    institution_id=institution_id,
                    description=row.get("description") or "",
                )
            )

        fees.sort(key=lambda f: f.transaction_date, reverse=True)
        logger.info(
            "FeeDetector | %d tarifa(s) em %d débitos (%d descartada(s) por teto)",
            len(fees), debits.height, descartadas,
        )
        return fees

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _classify(text: str) -> Optional[FeeType]:
        """Retorna o FeeType do primeiro padrão que casar, ou None."""
        tem_pix = bool(_RE_PIX.search(text))
        for fee_type, pattern in _FEE_PATTERNS:
            if fee_type is FeeType.TED_DOC and tem_pix:
                continue
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

        return f"Banco ({institution_id})" if institution_id else BANCO_NAO_IDENTIFICADO


def banco_identificado(bank_name: str) -> bool:
    """
    O banco foi resolvido de verdade, ou é só um balde de sobra?

    Sem isso, "Banco desconhecido" — que em produção continha TODAS as tarifas,
    porque transactions_clean não tem coluna de instituição — era comparado com
    a média dos bancos tradicionais e virava promessa de economia em reais.
    Comparar o custo de um usuário contra a média de bancos que talvez não
    sejam os dele não é benchmark, é ruído com casas decimais.
    """
    return bank_name in _NOMES_CONHECIDOS


def _normalize_text(value: str) -> str:
    """Normaliza acentos e caixa para melhorar matching por regex."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    no_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return no_accents.lower()
