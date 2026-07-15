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


__all__ = ["banks_match", "find_matching"]
