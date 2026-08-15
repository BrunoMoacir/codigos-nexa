#!/usr/bin/env python3
"""
Auditoria da limpeza do ETL contra EXTRATO REAL.

╔══════════════════════════════════════════════════════════════════════╗
║ POR QUE ESTE SCRIPT EXISTE                                           ║
╚══════════════════════════════════════════════════════════════════════╝

Toda a limpeza (chave canônica, stopwords, lista de marcas, prefixos de
adquirente, tiers por banco) foi calibrada contra dado SINTÉTICO. Ela
acerta no que foi imaginado — ninguém sabe se acerta no que os bancos
realmente mandam.

Este script pega o extrato de verdade e mostra, em uma tela, onde a
limpeza está comendo demais e onde está deixando passar. É a diferença
entre "parece funcionar" e "medi".

╔══════════════════════════════════════════════════════════════════════╗
║ COMO USAR                                                            ║
╚══════════════════════════════════════════════════════════════════════╝

Depois de conectar uma conta real pelo widget e rodar o sync:

    cd backend
    python scripts/calibrate_etl_real_extract.py --user-id <SEU_USER_ID>

Ou a partir de um arquivo exportado do banco (CSV/JSON com uma coluna de
descrição):

    python scripts/calibrate_etl_real_extract.py --csv extrato.csv
    python scripts/calibrate_etl_real_extract.py --json transacoes.json

O relatório é texto puro — pode colar inteiro numa conversa para análise.
NÃO imprime valores nem saldos por padrão (`--incluir-valores` libera):
descrição já basta para calibrar e vaza menos.

╔══════════════════════════════════════════════════════════════════════╗
║ O QUE OLHAR NO RELATÓRIO                                             ║
╚══════════════════════════════════════════════════════════════════════╝

1. CHAVES VAZIAS      → limpeza comeu tudo; a transação perde recorrência
                        e categoria. Deve ficar perto de 0%.
2. CHAVES LONGAS      → limpeza não removeu o ruído; cada mês vira uma
                        série nova e assinatura não é detectada.
3. COLAPSOS SUSPEITOS → descrições muito diferentes viraram a mesma chave;
                        é onde a limpeza junta o que não devia.
4. TAXA DE 'Outros'   → acima de ~25% significa keywords insuficientes
                        para o vocabulário real dos seus bancos.
5. TOKENS FREQUENTES  → palavras que aparecem em muitas descrições e não
                        estão nas stopwords são candidatas óbvias.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import polars as pl  # noqa: E402

from app.forecast.etl.classifier import TransactionClassifier  # noqa: E402
from app.forecast.etl.text_normalizer import (  # noqa: E402
    MARCAS_CONHECIDAS,
    STOPWORDS,
    canonical_key,
)

LARGURA = 78


def _titulo(texto: str) -> None:
    print(f"\n{'═' * LARGURA}\n {texto}\n{'═' * LARGURA}")


def _secao(texto: str) -> None:
    print(f"\n▶ {texto}\n{'-' * LARGURA}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARGA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def carregar_do_banco(user_id: str) -> list[dict]:
    """Extrato já sincronizado (transactions_clean)."""
    from app.core.db.queries import get_transactions_for_user

    df = get_transactions_for_user(user_id)
    if df is None or df.is_empty():
        return []
    return df.to_dicts()


def carregar_de_csv(caminho: str) -> list[dict]:
    df = pl.read_csv(caminho, infer_schema_length=10_000)
    return df.to_dicts()


def carregar_de_json(caminho: str) -> list[dict]:
    dados = json.loads(Path(caminho).read_text())
    if isinstance(dados, dict):
        dados = dados.get("results") or dados.get("transactions") or []
    return [d for d in dados if isinstance(d, dict)]


def extrair_descricao(linha: dict) -> str:
    for campo in ("description", "descricao", "descriptionRaw", "description_raw", "memo", "historico"):
        valor = linha.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANÁLISES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def analisar_chaves(descricoes: list[str]) -> dict:
    chaves = [canonical_key(d) for d in descricoes]
    pares = list(zip(descricoes, chaves))

    vazias = [d for d, k in pares if not k]
    longas = [(d, k) for d, k in pares if len(k.split()) >= 4]

    # Colapsos: mesma chave vinda de descrições bem diferentes
    por_chave: dict[str, set[str]] = defaultdict(set)
    for d, k in pares:
        if k:
            por_chave[k].add(d.lower())

    suspeitos = [
        (k, sorted(ds)[:4])
        for k, ds in por_chave.items()
        if len(ds) >= 2 and len({d.split()[0] if d.split() else "" for d in ds}) > 1
    ]
    suspeitos.sort(key=lambda x: -len(x[1]))

    return {
        "chaves": chaves,
        "vazias": vazias,
        "longas": longas,
        "grupos": por_chave,
        "suspeitos": suspeitos,
    }


def tokens_candidatos(descricoes: list[str], chaves: list[str]) -> list[tuple[str, int]]:
    """Tokens que sobrevivem à limpeza e aparecem em muitas descrições.

    Token muito frequente que não identifica ninguém é candidato a
    stopword nova (ex.: um prefixo de adquirente que só o seu banco usa).
    """
    contador: Counter[str] = Counter()
    for chave in chaves:
        for token in set(chave.split()):
            contador[token] += 1

    total = max(len(chaves), 1)
    return [
        (token, n)
        for token, n in contador.most_common(30)
        if n / total >= 0.03 and token not in MARCAS_CONHECIDAS
    ]


def analisar_categorias(linhas: list[dict], descricoes: list[str], chaves: list[str]) -> pl.DataFrame:
    df = pl.DataFrame(
        {
            "description": descricoes,
            "merchant_key": chaves,
            "merchant": [str(l.get("merchant") or "") for l in linhas],
        }
    )
    return TransactionClassifier().predict(df)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RELATÓRIO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibra a limpeza do ETL contra extrato real")
    fonte = parser.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--user-id", help="Lê transactions_clean deste usuário")
    fonte.add_argument("--csv", help="Arquivo CSV com coluna de descrição")
    fonte.add_argument("--json", help="Arquivo JSON (payload cru da Pluggy serve)")
    parser.add_argument("--limite", type=int, default=15, help="Exemplos por seção")
    parser.add_argument(
        "--incluir-valores", action="store_true", help="Mostra valores (default: só descrições)"
    )
    args = parser.parse_args()

    if args.user_id:
        linhas = carregar_do_banco(args.user_id)
        origem = f"transactions_clean (user {args.user_id})"
    elif args.csv:
        linhas = carregar_de_csv(args.csv)
        origem = args.csv
    else:
        linhas = carregar_de_json(args.json)
        origem = args.json

    descricoes = [d for d in (extrair_descricao(l) for l in linhas) if d]

    _titulo("AUDITORIA DA LIMPEZA — EXTRATO REAL")
    print(f" Origem : {origem}")
    print(f" Linhas : {len(linhas)} ({len(descricoes)} com descrição)")

    if not descricoes:
        print("\n❌ Nenhuma descrição encontrada. Confira a coluna de origem.")
        return 1

    total = len(descricoes)
    resultado = analisar_chaves(descricoes)
    chaves = resultado["chaves"]

    # 1. Saúde geral da chave
    _secao("1. SAÚDE DA CHAVE CANÔNICA")
    vazias, longas = resultado["vazias"], resultado["longas"]
    unicas = len({k for k in chaves if k})
    print(f"   chaves distintas ...... {unicas} para {total} transações")
    print(f"   chaves VAZIAS ......... {len(vazias)} ({len(vazias)/total:.1%})   ← alvo: ~0%")
    print(f"   chaves longas (4+ tok). {len(longas)} ({len(longas)/total:.1%})   ← ruído sobrando")

    if vazias:
        print("\n   ❌ A limpeza comeu tudo nestas (perdem recorrência e categoria):")
        for d in vazias[: args.limite]:
            print(f"      {d[:70]!r}")

    if longas:
        print("\n   ⚠️  Ruído sobrando (assinatura não fecha série):")
        for d, k in longas[: args.limite]:
            print(f"      {d[:46]!r:<50} → {k!r}")

    # 2. Colapsos
    _secao("2. COLAPSOS — descrições diferentes que viraram a mesma chave")
    if resultado["suspeitos"]:
        print("   (confirme se são o mesmo estabelecimento; se não, a chave está agressiva)")
        for chave, exemplos in resultado["suspeitos"][: args.limite]:
            print(f"\n   chave {chave!r}:")
            for exemplo in exemplos:
                print(f"      • {exemplo[:66]}")
    else:
        print("   nenhum colapso entre descrições de origem diferente.")

    # 3. Tokens candidatos a stopword
    _secao("3. TOKENS FREQUENTES QUE SOBRARAM (candidatos a stopword)")
    candidatos = tokens_candidatos(descricoes, chaves)
    if candidatos:
        print("   token           em % das chaves")
        for token, n in candidatos:
            marcador = "  ← revisar" if n / total >= 0.10 else ""
            print(f"   {token:<15} {n/total:>6.1%} ({n}){marcador}")
    else:
        print("   nenhum token dominante — vocabulário bem distribuído.")

    # 4. Categorias
    _secao("4. CLASSIFICAÇÃO DE CATEGORIA")
    classificado = analisar_categorias(linhas, descricoes, chaves)
    dist = (
        classificado.group_by("predicted_category")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
    )
    outros = 0
    for linha in dist.iter_rows(named=True):
        pct = linha["n"] / total
        if linha["predicted_category"] == "Outros":
            outros = pct
        barra = "█" * int(pct * 40)
        print(f"   {linha['predicted_category']:<16} {pct:>6.1%} {barra}")

    if outros > 0.25:
        print(f"\n   ⚠️  'Outros' em {outros:.1%} — keywords não cobrem seu vocabulário real.")
        nao_classificadas = classificado.filter(pl.col("predicted_category") == "Outros")
        print("   Exemplos para virar keyword nova:")
        for d in nao_classificadas["description"].head(args.limite).to_list():
            print(f"      {d[:70]!r}")

    # 5. Séries (candidatas a assinatura)
    _secao("5. SÉRIES REPETIDAS (candidatas a assinatura/parcelamento)")
    series = sorted(
        ((k, len(ds)) for k, ds in resultado["grupos"].items()),
        key=lambda x: -x[1],
    )
    recorrentes = [(k, n) for k, n in series if n >= 3][: args.limite]
    if recorrentes:
        for chave, n in recorrentes:
            print(f"   {chave:<40} {n} lançamentos")
    else:
        print("   nenhuma chave com 3+ ocorrências (extrato curto?).")

    _titulo("O QUE FAZER COM ISTO")
    print(
        " 1. Chave vazia ou colapso errado → ajustar STOPWORDS/MARCAS_CONHECIDAS\n"
        "    em app/forecast/etl/text_normalizer.py\n"
        " 2. 'Outros' alto → acrescentar keywords em CATEGORY_KEYWORDS\n"
        "    (app/forecast/etl/classifier.py)\n"
        " 3. Cada ajuste tem que vir com caso novo em\n"
        "    tests/test_etl_pluggy_sujo_producao.py — foi teste que pegou os\n"
        "    últimos bugs, não leitura de código.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
