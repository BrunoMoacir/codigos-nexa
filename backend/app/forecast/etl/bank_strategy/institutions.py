"""
app/forecast/etl/bank_strategy/institutions.py — De conector Pluggy p/ slug interno.

╔══════════════════════════════════════════════════════════════════════╗
║ POR QUE ISTO EXISTE                                                  ║
╚══════════════════════════════════════════════════════════════════════╝

O sync resolvia o banco por um mapa de IDs numéricos
({"201": "nubank", "202": "itau", ...}) que casa com o pluggy_mock, não com
a API real. Somando isso ao fato de que o objeto Account da Pluggy não traz
`connector`, o institution_id caía em "unknown" em produção — e a
BankStrategy, que é a camada inteira de tratamento por banco, nunca rodava:
tudo ia para a DefaultStrategy, que não normaliza nada.

Aqui a resolução é por NOME do conector (que vem em GET /items/{id}), que é
estável e legível, com o ID numérico só como reforço. Nome desconhecido
continua caindo em "unknown" — mas agora por ausência real de match, não por
um mapa desalinhado.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Optional

# Slug interno → termos que aparecem no nome do conector.
# Ordem importa: o primeiro match vence, então termos mais específicos
# ("banco do brasil") precisam vir antes dos genéricos ("brasil").
_TERMOS_POR_SLUG: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nubank", ("nubank", "nu pagamentos", "nuconta")),
    ("itau", ("itau", "itaú", "unibanco")),
    ("inter", ("banco inter", "inter ")),
    ("bradesco", ("bradesco", "next")),
    ("santander", ("santander",)),
    ("caixa", ("caixa economica", "caixa econômica", "caixa")),
    ("banco_do_brasil", ("banco do brasil", "bb ")),
    ("c6", ("c6 bank", "c6bank", "banco c6")),
    ("btg", ("btg",)),
    ("original", ("banco original",)),
    ("safra", ("safra",)),
    ("sicredi", ("sicredi",)),
    ("sicoob", ("sicoob",)),
    ("banrisul", ("banrisul",)),
    ("brb", ("brb",)),
    ("pan", ("banco pan",)),
    ("neon", ("neon",)),
    ("will", ("will bank", "willbank")),
    ("picpay", ("picpay",)),
    ("mercadopago", ("mercado pago", "mercadopago")),
    ("pagbank", ("pagbank", "pagseguro")),
    ("xp", ("xp investimentos", "banco xp")),
    ("nomad", ("nomad",)),
    ("pluggy_sandbox", ("pluggy bank", "sandbox")),
)

# Reforço por ID numérico. Só entram IDs confirmados no ambiente do projeto —
# o mapa antigo tratava os IDs do mock como se fossem os da produção.
_SLUG_POR_ID: dict[str, str] = {
    "0": "pluggy_sandbox",
    "2": "pluggy_sandbox",
}

DESCONHECIDO = "unknown"


def _normalizar(texto: Any) -> str:
    if not texto:
        return ""
    nfd = unicodedata.normalize("NFD", str(texto))
    sem_acento = "".join(c for c in nfd if not unicodedata.combining(c))
    return f" {sem_acento.lower().strip()} "


def resolve_institution_id(
    connector_name: Optional[str] = None,
    connector_id: Optional[Any] = None,
) -> str:
    """
    Slug interno do banco (o mesmo que get_bank_strategy espera).

    >>> resolve_institution_id("Nubank")
    'nubank'
    >>> resolve_institution_id("Itaú Unibanco")
    'itau'
    >>> resolve_institution_id("Banco Cooperativo Qualquer")
    'unknown'
    """
    nome = _normalizar(connector_name)

    if nome:
        for slug, termos in _TERMOS_POR_SLUG:
            if any(termo.strip() and termo in nome for termo in termos):
                return slug

    if connector_id is not None:
        slug = _SLUG_POR_ID.get(str(connector_id).strip())
        if slug:
            return slug

    return DESCONHECIDO


def extract_connector(payload: Any) -> tuple[Optional[str], Optional[Any]]:
    """
    Extrai (nome, id) do conector de um item OU de uma conta da Pluggy.

    Item traz `connector` completo; Account, quando muito, `connectorId`.
    """
    if not isinstance(payload, dict):
        return None, None

    connector = payload.get("connector")
    if isinstance(connector, dict):
        return connector.get("name"), connector.get("id")

    return (
        payload.get("connectorName") or payload.get("institutionName"),
        payload.get("connectorId"),
    )
