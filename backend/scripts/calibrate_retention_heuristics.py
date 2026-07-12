"""
scripts/calibrate_retention_heuristics.py — Calibração das heurísticas de
retenção (R2.c/R1.a) contra corpora reais de transações.

Roda as heurísticas de:
  1. Detecção de salário          (profile_probe._detect_salary — padrões)
  2. Sinal de MEI/DAS             (profile_probe._DAS_PATTERNS)
  3. Inferência de meio de pagto  (post_purchase._infer_paid_method)
  4. Filtro de não-compra         (post_purchase._NON_PURCHASE_PATTERNS)
  5. Marcador de parcelamento     (post_purchase._INSTALLMENT_PATTERN)

contra qualquer fonte de transações e imprime, por heurística, os matches,
os quase-matches suspeitos (falso-positivo provável) e as taxas por padrão,
para inspeção manual e ajuste dos regex/LIKEs.

Fontes suportadas:
  --duckdb data/transactions.duckdb        (tabela transactions)
  --pg postgresql://user:pass@host/db      (tabela transactions_clean)

Uso:
  python3 scripts/calibrate_retention_heuristics.py --duckdb ../data/transactions.duckdb
  python3 scripts/calibrate_retention_heuristics.py --pg postgresql://nexa_user:nexa_secret@localhost/nexa_db
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.purchase.post_purchase import (  # noqa: E402
    _INSTALLMENT_PATTERN,
    _NON_PURCHASE_PATTERNS,
    PostPurchaseAnalyzer,
)
from app.seasonality.profile_probe import (  # noqa: E402  — fonte de verdade
    MEI_REGEX as MEI_RE,
    SALARY_REGEX as SALARY_RE,
)

# Padrão ANTIGO (LIKE '%das %') mantido só para medir o falso positivo que
# motivou a troca pelo MEI_REGEX
MEI_OLD_LIKE = re.compile(r"das ", re.IGNORECASE)


def load_duckdb(path: str) -> list[dict]:
    import duckdb

    con = duckdb.connect(path, read_only=True)
    rows = con.execute(
        "SELECT description, merchant, amount FROM transactions"
    ).fetchall()
    con.close()
    return [
        {"description": r[0] or "", "merchant": r[1] or "", "amount": float(r[2] or 0)}
        for r in rows
    ]


def load_pg(url: str) -> list[dict]:
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    with engine.connect() as con:
        rows = con.execute(
            text("SELECT description, '', amount FROM transactions_clean")
        ).fetchall()
    return [
        {"description": r[0] or "", "merchant": r[1] or "", "amount": float(r[2] or 0)}
        for r in rows
    ]


def _sample(items: list[str], n: int = 8) -> str:
    uniq = list(dict.fromkeys(items))
    shown = "\n    ".join(uniq[:n])
    extra = f"\n    … +{len(uniq) - n} distintas" if len(uniq) > n else ""
    return f"    {shown}{extra}" if uniq else "    (nenhuma)"


def report(txns: list[dict], source: str) -> None:
    print(f"\n{'═' * 70}\nCORPUS: {source} — {len(txns)} transações\n{'═' * 70}")

    # ── 1. Salário ────────────────────────────────────────────────────
    credits = [t for t in txns if t["amount"] > 0]
    salary_hits = [t["description"] for t in credits if SALARY_RE.search(t["description"])]
    big_credits_missed = [
        t["description"] for t in credits
        if t["amount"] >= 2000 and not SALARY_RE.search(t["description"])
    ]
    print(f"\n── 1. SALÁRIO — {len(salary_hits)}/{len(credits)} créditos casam ──")
    print("  Matches:")
    print(_sample(salary_hits))
    print("  Créditos ≥R$2.000 SEM match (possível salário perdido):")
    print(_sample(big_credits_missed))

    # ── 2. MEI/DAS ────────────────────────────────────────────────────
    debits = [t for t in txns if t["amount"] < 0]
    mei_new = [t["description"] for t in debits if MEI_RE.search(t["description"])]
    mei_old = [t["description"] for t in debits if MEI_OLD_LIKE.search(t["description"])]
    old_fp = [d for d in mei_old if not MEI_RE.search(d)]
    print(f"\n── 2. MEI/DAS — novo regex: {len(mei_new)} | LIKE antigo '%das %': {len(mei_old)} ──")
    print("  Matches do regex novo:")
    print(_sample(mei_new))
    print("  FALSOS POSITIVOS do LIKE antigo (casa '%das %' mas não é DAS):")
    print(_sample(old_fp))

    # ── 3. Meio de pagamento ──────────────────────────────────────────
    infer = PostPurchaseAnalyzer._infer_paid_method
    dist: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for t in debits:
        method, _ = infer(t["description"])
        dist[method] += 1
        examples[method].append(t["description"])
    print(f"\n── 3. MEIO DE PAGAMENTO (débitos: {len(debits)}) ──")
    for method, count in dist.most_common():
        pct = count / max(1, len(debits)) * 100
        print(f"  {method}: {count} ({pct:.1f}%)")
        print(_sample(examples[method], 4))

    # ── 4. Filtro de não-compra ───────────────────────────────────────
    big_debits = [t for t in debits if abs(t["amount"]) >= 300]
    excluded = [t["description"] for t in big_debits
                if _NON_PURCHASE_PATTERNS.search(t["description"])]
    kept = [t["description"] for t in big_debits
            if not _NON_PURCHASE_PATTERNS.search(t["description"])]
    print(f"\n── 4. NÃO-COMPRA (débitos ≥R$300: {len(big_debits)}) ──")
    print(f"  Excluídos ({len(excluded)}):")
    print(_sample(excluded))
    print(f"  Mantidos como compra ({len(kept)}) — conferir se são compra mesmo:")
    print(_sample(kept))

    # ── 5. Parcelamento ───────────────────────────────────────────────
    inst = [t["description"] for t in debits if _INSTALLMENT_PATTERN.search(t["description"])]
    print(f"\n── 5. PARCELAMENTO — {len(inst)} débitos marcados ──")
    print(_sample(inst))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duckdb", help="caminho de um .duckdb com tabela transactions")
    ap.add_argument("--pg", help="URL postgres com tabela transactions_clean")
    args = ap.parse_args()

    if not args.duckdb and not args.pg:
        ap.error("informe --duckdb e/ou --pg")

    if args.duckdb:
        report(load_duckdb(args.duckdb), f"duckdb:{args.duckdb}")
    if args.pg:
        report(load_pg(args.pg), "postgres:transactions_clean")


if __name__ == "__main__":
    main()
