"""
app/opportunities/services/bank_names.py

Matching tolerante de nomes de instituição — fonte única para todo o OPP.

O mesmo banco aparece com grafias diferentes conforme a fonte:
  Pluggy connector_name  → "Nu Pagamentos S.A.", "Banco Inter S.A."
  Catálogo de produtos   → "Nubank", "Banco Inter"
  Emissor de cartão (F2) → "Nubank", "Inter"
  Detector de tarifas    → "NUBANK", "inter"

Regras:
  1. igualdade/substring case-insensitive (strings com mais de 3 chars);
  2. interseção de tokens significativos, ignorando palavras genéricas que
     causariam falso-positivo ("bank" casaria Nubank com C6 Bank);
  3. prefixo entre tokens (>= 2 chars) — "nu" de "Nu Pagamentos" casa "nubank".
"""

from __future__ import annotations

import re

_GENERIC_TOKENS = {
    "bank", "banco", "banca", "s.a.", "s/a", "sa", "ltda", "de", "do", "da",
    "e", "investimentos", "pagamentos", "financeira", "credito", "crédito",
    "brasil", "direto", "pactual",
}


def _tokens(name: str) -> set[str]:
    return {
        t for t in name.lower().replace(",", " ").split()
        if len(t) >= 2 and t not in _GENERIC_TOKENS
    }


def banks_match(a: str, b: str) -> bool:
    """True quando os dois nomes provavelmente se referem à mesma instituição."""
    if not a or not b:
        return False
    a_l, b_l = a.lower().strip(), b.lower().strip()
    if a_l == b_l:
        return True
    if (len(a_l) > 3 and a_l in b_l) or (len(b_l) > 3 and b_l in a_l):
        return True

    a_tokens, b_tokens = _tokens(a_l), _tokens(b_l)
    if a_tokens & b_tokens:
        return True
    # prefixo entre tokens: "nu" (Nu Pagamentos) → "nubank"
    for at in a_tokens:
        for bt in b_tokens:
            if at.startswith(bt) or bt.startswith(at):
                return True
    return False


def find_matching(name: str, candidates: dict[str, float] | set[str]) -> str | None:
    """Primeira chave/valor de candidates que casa com name (ou None)."""
    for candidate in candidates:
        if banks_match(name, candidate):
            return candidate
    return None


# ── Canonicalização de marca (exibição/deduplicação) ─────────────────────────
#
# O opendata devolve razões sociais fragmentadas ("ITAU UNIBANCO S A",
# "Itau", "Itaú Unibanco SA" são a mesma marca). canonical_brand() normaliza
# para um nome de exibição único — usado pelo catálogo vivo do OPP para não
# contar o mesmo banco várias vezes.

_CORPORATE_SUFFIX = re.compile(
    r"\b(s[./ ]?a[./]?|s/a|ltda[.]?|cfi|scfi|c\.?f\.?i\.?|"
    r"credito,? financiamento e investimento|sociedade de credito.*|"
    r"instituicao de pagamento|servicos s\.?a\.?)\b[.,]?",
    re.IGNORECASE,
)

# Aliases por substring normalizada (minúscula, sem acento) → marca canônica
_BRAND_ALIASES: tuple[tuple[str, str], ...] = (
    ("itau", "Itaú"),
    ("nubank", "Nubank"),
    ("nu pagamentos", "Nubank"),
    ("nu financeira", "Nubank"),
    ("btg", "BTG Pactual"),
    ("banco inter", "Banco Inter"),
    ("picpay", "PicPay"),
    ("mercado credito", "Mercado Pago"),
    ("mercado pago", "Mercado Pago"),
    ("midway", "Midway (Riachuelo)"),
    ("stone", "Stone"),
    ("banco do brasil", "Banco do Brasil"),
    ("santander", "Santander"),
    ("bradesco", "Bradesco"),
    ("caixa economica", "Caixa Econômica"),
    ("safra", "Banco Safra"),
    ("banrisul", "Banrisul"),
    ("banco de brasilia", "BRB"),
    ("banco do nordeste", "Banco do Nordeste"),
    ("mercantil", "Banco Mercantil"),
    ("sicredi", "Sicredi"),
    ("sicoob", "Sicoob"),
    ("unicred", "Unicred"),
    ("neon", "Neon"),
    ("digio", "Digio"),
    ("banco pan", "Banco Pan"),
    ("banco bv", "Banco BV"),
    ("bv financeira", "Banco BV"),
    ("xp investimentos", "XP Investimentos"),
    ("rico", "Rico (XP)"),
    ("clear", "Clear (XP)"),
    ("modal", "Banco Modal"),
    ("c6", "C6 Bank"),
)


def _strip_accents(text: str) -> str:
    import unicodedata

    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def canonical_brand(raw_name: str) -> str:
    """
    Nome de exibição canônico para uma instituição vinda do opendata.

    "ITAU UNIBANCO S.A." → "Itaú" · "MERCADO CREDITO" → "Mercado Pago" ·
    nomes desconhecidos são limpos (sem sufixo societário, Title Case).
    """
    if not raw_name:
        return raw_name
    normalized = _strip_accents(raw_name).lower()
    for needle, brand in _BRAND_ALIASES:
        if needle in normalized:
            return brand

    cleaned = _CORPORATE_SUFFIX.sub("", raw_name).strip(" .,-–")
    if not cleaned:
        cleaned = raw_name.strip()
    # Title Case apenas quando o nome veio gritado em maiúsculas
    if cleaned.isupper():
        cleaned = cleaned.title()
    return cleaned


__all__ = ["banks_match", "find_matching", "canonical_brand"]
