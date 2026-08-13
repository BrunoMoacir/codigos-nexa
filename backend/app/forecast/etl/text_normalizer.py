"""
app/forecast/etl/text_normalizer.py — Canonicalização de texto do extrato.

╔══════════════════════════════════════════════════════════════════════╗
║ O PROBLEMA                                                           ║
╚══════════════════════════════════════════════════════════════════════╝

A MESMA compra chega escrita de um jeito em cada banco:

    Nubank    "Netflix.com"
    Itaú      "COMPRA CARTAO 1234 NETFLIX.COM SAO PAULO BR"
    Bradesco  "DEB AUT NETFLIX*ASSINAT 08/26"      ← muda todo mês!
    Inter     "PAGAMENTO NETFLIX ENTRETENIMENTO LTDA"

Sem canonicalização:
    • o detector de assinatura agrupa por descrição exata → o Bradesco nunca
      forma série mensal (cada mês é uma string nova) e perde 100% das
      assinaturas;
    • o classificador vê o ruído do Itaú ("cartao 1234 ... sao paulo br") e
      erra a categoria.

╔══════════════════════════════════════════════════════════════════════╗
║ A SOLUÇÃO: merchant_key                                              ║
╚══════════════════════════════════════════════════════════════════════╝

Uma CHAVE canônica derivada da descrição/merchant, estável entre meses e
entre bancos. A descrição original NUNCA é alterada — a chave é uma coluna
nova (`merchant_key`), consumida por classificador e detector de recorrência.

    "DEB AUT NETFLIX*ASSINAT 08/26"               → "netflix"
    "COMPRA CARTAO 1234 NETFLIX.COM SAO PAULO BR" → "netflix"
    "PAGAMENTO BOLETO ENERGIA ENEL SP"            → "energia enel"

Etapas (todas vetorizadas em Polars, sem UDF por linha):
    1. lowercase + remoção de acentos
    2. remoção de datas embutidas (08/26, 12-01-2026)
    3. pontuação/símbolos viram espaço  ("ifd*ifood" → "ifd ifood")
    4. tokens puramente numéricos caem (nº de cartão, referência)
    5. tokens de ruído bancário caem (compra, cartao, deb, aut, ltda, br...)
    6. cidade/UF no fim da string cai (o adquirente anexa a praça)
    7. marca conhecida vence tudo (netflix, spotify, ifood...)
"""

from __future__ import annotations

import re
import unicodedata

import polars as pl

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TABELAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Ruído estrutural do extrato — nada aqui identifica estabelecimento.
STOPWORDS: frozenset[str] = frozenset({
    # meio de pagamento / natureza do lançamento
    "compra", "compras", "cartao", "cartoes", "credito", "debito", "deb", "cred",
    "aut", "automatico", "automatica", "pagamento", "pagto", "pgto", "pag",
    "tef", "ted", "doc", "boleto", "fatura", "lancamento", "movimentacao",
    "assinatura", "assinat", "mensalidade", "mensal", "parcela", "parcelamento",
    "parc", "recorrente", "autorizado", "aprovado",
    # entidade jurídica
    "ltda", "me", "epp", "sa", "eireli", "mei", "cia", "s",
    # web / geografia genérica
    "com", "www", "http", "https", "br", "bra", "brasil",
    # preposições e artigos
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas", "em", "e", "a", "o",
    # genéricos de estabelecimento
    "loja", "lj", "estab", "estabelecimento", "ref", "nr", "num", "numero",
})

# Praça anexada pelo adquirente no FIM da descrição. Removida só como sufixo
# (regex ancorada), nunca token a solto: "paulo" pode ser nome de comércio.
CIDADES = (
    "sao paulo", "rio de janeiro", "belo horizonte", "brasilia", "salvador",
    "fortaleza", "curitiba", "recife", "porto alegre", "manaus", "belem",
    "goiania", "campinas", "guarulhos", "sao goncalo", "duque de caxias",
    "natal", "campo grande", "teresina", "sao bernardo", "joao pessoa",
    "santo andre", "osasco", "ribeirao preto", "uberlandia", "sorocaba",
    "contagem", "aracaju", "feira de santana", "cuiaba", "joinville",
    "juiz de fora", "londrina", "niteroi", "florianopolis", "maceio",
    "vitoria", "macapa", "boa vista", "rio branco", "palmas", "porto velho",
    "sao luis", "sao jose", "santos", "santo amaro",
)

UFS = (
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms",
    "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc",
    "sp", "se", "to",
)

# Marcas cuja simples presença já identifica o estabelecimento. Só entram
# aqui nomes de alta precisão — "amazon", "google" e "apple" ficam de fora
# de propósito: vendem assinatura E varejo, e colapsá-los juntaria a
# assinatura mensal com a compra avulsa.
MARCAS_CONHECIDAS: tuple[str, ...] = (
    "netflix", "spotify", "deezer", "disney", "hbo", "max", "paramount",
    "globoplay", "youtube", "twitch", "crunchyroll", "mubi",
    "icloud", "dropbox", "onedrive", "adobe", "canva", "notion", "figma",
    "zoom", "slack", "chatgpt", "openai", "anthropic",
    "ifood", "rappi", "uber", "cabify", "99pop", "99app",
    "tim", "vivo", "claro", "oi", "nextel", "sky",
    "smartfit", "gympass", "totalpass",
)

# A cidade é comparada DEPOIS da remoção de stopwords, quando "rio de
# janeiro" já virou "rio janeiro" — por isso o padrão nasce da mesma
# filtragem, senão o sufixo escapa.
_CIDADES_NORM = tuple(
    sorted(
        {" ".join(t for t in cidade.split() if t not in STOPWORDS) for cidade in CIDADES},
        key=len,
        reverse=True,  # mais específico primeiro ("sao jose" antes de "sao")
    )
)

_RE_DATA = re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b")
_RE_NAO_ALFANUM = re.compile(r"[^a-z0-9]+")
_RE_SO_NUMERO = re.compile(r"\b\d+\b")
_RE_SUFIXO_CIDADE = re.compile(r"\s+(?:" + "|".join(_CIDADES_NORM) + r")$")
_RE_SUFIXO_UF = re.compile(r"\s+(?:" + "|".join(UFS) + r")$")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VERSÃO PYTHON (referência e uso pontual)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def strip_accents(texto: str) -> str:
    """'Farmácia São Paulo' → 'Farmacia Sao Paulo'."""
    nfd = unicodedata.normalize("NFD", texto)
    return "".join(c for c in nfd if not unicodedata.combining(c))


def canonical_key(texto: str | None) -> str:
    """
    Chave canônica de um lançamento. Devolve "" quando nada sobra —
    o chamador decide o fallback (normalmente a descrição original).

    >>> canonical_key("DEB AUT NETFLIX*ASSINAT 08/26")
    'netflix'
    >>> canonical_key("COMPRA CARTAO 1234 NETFLIX.COM SAO PAULO BR")
    'netflix'
    """
    if not texto or not isinstance(texto, str):
        return ""

    t = strip_accents(texto).lower()
    t = _RE_DATA.sub(" ", t)
    t = _RE_NAO_ALFANUM.sub(" ", t)
    t = _RE_SO_NUMERO.sub(" ", t)

    tokens = [tok for tok in t.split() if len(tok) > 1 and tok not in STOPWORDS]
    chave = " ".join(tokens).strip()

    # UF antes da cidade: o adquirente escreve "CIDADE UF" no fim
    # ("... sao jose sc"), então a sigla precisa sair primeiro.
    chave = _RE_SUFIXO_UF.sub("", chave)
    chave = _RE_SUFIXO_CIDADE.sub("", chave)
    chave = chave.strip()

    for marca in MARCAS_CONHECIDAS:
        if marca in chave.split():
            return marca

    return chave[:80]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VERSÃO POLARS (a que o ETL usa)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ACENTUADOS = "áàâãäéèêëíìîïóòôõöúùûüçñ"
_SEM_ACENTO = "aaaaaeeeeiiiiooooouuuucn"


def canonical_key_expr(coluna: str | pl.Expr) -> pl.Expr:
    """
    Mesma lógica de canonical_key(), vetorizada.

    Usa replace_many/list.eval em vez de map_elements: o ETL processa lotes
    de milhares de linhas por sync e uma UDF por linha custaria caro.
    """
    col = pl.col(coluna) if isinstance(coluna, str) else coluna

    limpo = (
        col.cast(pl.String)
        .fill_null("")
        .str.to_lowercase()
        .str.replace_many(list(_ACENTUADOS), list(_SEM_ACENTO))
        .str.replace_all(_RE_DATA.pattern, " ")
        .str.replace_all(_RE_NAO_ALFANUM.pattern, " ")
        .str.replace_all(_RE_SO_NUMERO.pattern, " ")
        .str.strip_chars()
    )

    sem_ruido = (
        limpo.str.split(" ")
        .list.eval(
            pl.element().filter(
                (pl.element().str.len_chars() > 1)
                & (~pl.element().is_in(list(STOPWORDS)))
            )
        )
        .list.join(" ")
        .str.replace_all(_RE_SUFIXO_UF.pattern, "")
        .str.replace_all(_RE_SUFIXO_CIDADE.pattern, "")
        .str.strip_chars()
        .str.slice(0, 80)
    )

    # Marca conhecida vence: unifica o mesmo serviço entre bancos diferentes.
    chave = sem_ruido
    for marca in MARCAS_CONHECIDAS:
        chave = (
            pl.when(sem_ruido.str.split(" ").list.contains(marca))
            .then(pl.lit(marca))
            .otherwise(chave)
        )

    return chave
