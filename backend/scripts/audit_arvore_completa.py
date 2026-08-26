#!/usr/bin/env python3
"""
scripts/audit_arvore_completa.py — catraca de CVE na árvore TRANSITIVA.

O job `security-audit` do CI roda `pip-audit -r requirements.txt --no-deps`:
audita só os pins DIRETOS. Medido em 2026-08-25, a árvore resolvida tinha
**156 vulnerabilidades conhecidas em 33 pacotes** — urllib3, tornado,
cryptography, aiohttp, pillow, setuptools e outros — todas invisíveis para
aquele job.

Corrigir as 33 de uma vez é uma rodada de dependências, não de segurança de
aplicação, e arrisca a suíte inteira. O que dá para fazer hoje é impedir que o
número CRESÇA: esta catraca compara a contagem atual com uma linha de base
versionada e falha se subir. Não se paga a dívida hoje; não se contrai a
próxima.

Uso:
    python3 scripts/audit_arvore_completa.py            # verifica a catraca
    python3 scripts/audit_arvore_completa.py --atualizar-base
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import date

_BASE = pathlib.Path(__file__).resolve().parent.parent / "security_baseline.json"


def _contar() -> tuple[int, int, dict[str, int]]:
    """(total de vulnerabilidades, pacotes afetados, por pacote)."""
    saida = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--skip-editable", "--format", "json"],
        capture_output=True, text=True,
    )
    if not saida.stdout.strip():
        print("pip-audit não produziu saída:", saida.stderr[-400:], file=sys.stderr)
        sys.exit(2)

    dados = json.loads(saida.stdout)
    deps = dados.get("dependencies", dados if isinstance(dados, list) else [])
    por_pacote = {
        d["name"]: len(d.get("vulns", []))
        for d in deps if d.get("vulns")
    }
    return sum(por_pacote.values()), len(por_pacote), por_pacote


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atualizar-base", action="store_true")
    args = parser.parse_args()

    total, pacotes, por_pacote = _contar()

    if args.atualizar_base or not _BASE.exists():
        _BASE.write_text(
            json.dumps(
                {
                    "_comentario": (
                        "Catraca de CVE da árvore transitiva. O número só pode "
                        "DESCER. Ao corrigir dependências, rode "
                        "`python3 scripts/audit_arvore_completa.py --atualizar-base`."
                    ),
                    "medido_em": date.today().isoformat(),
                    "total_vulnerabilidades": total,
                    "pacotes_afetados": pacotes,
                    "por_pacote": dict(sorted(por_pacote.items())),
                },
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"Linha de base gravada: {total} vulnerabilidades em {pacotes} pacotes.")
        return

    base = json.loads(_BASE.read_text(encoding="utf-8"))
    limite = base["total_vulnerabilidades"]

    print(f"árvore transitiva: {total} vulnerabilidades em {pacotes} pacotes "
          f"(base: {limite}, medida em {base['medido_em']})")

    if total > limite:
        novos = {
            nome: qtd - base["por_pacote"].get(nome, 0)
            for nome, qtd in por_pacote.items()
            if qtd > base["por_pacote"].get(nome, 0)
        }
        print(f"\n❌ subiu {total - limite}. Pacotes que pioraram: {novos}")
        print("   Corrija a dependência ou justifique atualizando a base.")
        sys.exit(1)

    if total < limite:
        print(f"\n✅ caiu {limite - total}. Rode --atualizar-base para travar o ganho.")
    else:
        print("\n✅ sem regressão.")


if __name__ == "__main__":
    main()
