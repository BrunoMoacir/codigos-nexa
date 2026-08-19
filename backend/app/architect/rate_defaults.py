"""
app/architect/rate_defaults.py — Fonte única dos defaults de taxa (F3)

Feature: F3 - Nexa Architect

Problema que este módulo resolve:
    O dicionário `market_rates` é montado por `ArchitectService._fetch_market_rates`
    e consumido por StrategyEngine, SensitivityAnalyzer e ArchitectService. Quando
    um conector cai, cada consumidor tinha o SEU próprio default embutido no
    `.get(chave, literal)` — e eles divergiam:

        best_cet_annual        →  0.15 (7 lugares), 0.1950 (router), 0.20 (2)
        consortium_admin_rate  →  0.17 (4 lugares),   0.18 (strategy_engine:466)

    Ou seja: a MESMA queda de conector produzia números diferentes conforme o
    caminho do código, e nada na resposta dizia que um fallback tinha sido usado.

Como usar:
    Leia taxa de `market_rates` por `rate(rates, "selic_annual")`, nunca por
    `rates.get("selic_annual", <literal>)`. A ausência da chave passa a ser
    registrada em log e contabilizada, em vez de virar um número silencioso.

    Para montar um dicionário de fallback COMPLETO (rotas que precisam responder
    mesmo com os conectores fora), use `fallback_market_rates(asset_type)`.

Onde ficam os números:
    Aqui não. `fallback_market_rates` compõe os fallbacks que já existem e são
    testados nos próprios conectores (BacenConnector, AnbimaConnector,
    MarketRatesConnector, IPCAConnector, ConsortiumRateProvider). O único papel
    deste módulo é garantir que exista UM caminho até eles.

    `_DEFAULTS` abaixo é a rede de segurança de último recurso, para o caso de
    uma chave sumir do dicionário. Se ela for usada, aparece no log.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Rede de último recurso ───────────────────────────────────────────────────
# Só é consultada quando a chave não está no dicionário recebido. Os valores
# espelham os fallbacks dos conectores; divergir daqui é bug, e o teste
# tests/architect/test_paridade_e_defaults.py trava isso.
_DEFAULTS: Dict[str, float] = {
    "selic_annual":                      0.1475,   # BacenConnector
    "cdi_annual":                        0.1465,   # AnbimaConnector
    "ipca_annual":                       0.045,    # IPCAConnector (meta CMN)
    "best_cet_annual":                   0.15,     # MarketRatesConnector (cet_*_min)
    "consortium_admin_rate":             0.17,
    "consortium_months":                 72.0,
    "consortium_reserve_fund_rate":      0.02,
    "consortium_group_size":             100.0,
    "consortium_contemplated_per_month": 2.0,
    "consortium_annual_adjustment_rate": 0.045,
    "bid_mean_initial":                  0.35,
    "bid_std":                           0.12,
}


class MissingRateError(KeyError):
    """Chave pedida que não existe nem no dicionário nem nos defaults."""


def rate(rates: Dict[str, Any], key: str) -> float:
    """
    Lê uma taxa do dicionário de mercado, com fallback ÚNICO e observável.

    Substitui `rates.get(key, <literal>)`: o literal espalhado pelo código era
    a origem da divergência. Aqui existe um valor só por chave, e o uso do
    fallback vira log — no fluxo normal `_fetch_market_rates` entrega todas as
    chaves, então um WARNING aqui significa que alguém montou o dicionário à mão
    ou que um provider mudou de contrato.

    Args:
        rates: dicionário de taxas de mercado.
        key:   chave a ler.

    Returns:
        O valor do dicionário, ou o default canônico.

    Raises:
        MissingRateError: chave desconhecida (erro de digitação, tipicamente).
    """
    if key in rates and rates[key] is not None:
        return float(rates[key])

    if key not in _DEFAULTS:
        raise MissingRateError(
            f"'{key}' não está em market_rates nem em rate_defaults._DEFAULTS"
        )

    fallback = _DEFAULTS[key]
    logger.warning(
        "[rate_defaults] '%s' ausente em market_rates — usando default %.4f. "
        "No fluxo normal ArchitectService._fetch_market_rates entrega essa chave.",
        key, fallback,
    )
    return fallback


def rate_int(rates: Dict[str, Any], key: str) -> int:
    """`rate()` para chaves inteiras (prazo, tamanho do grupo)."""
    return int(rate(rates, key))


def missing_keys(rates: Dict[str, Any]) -> list[str]:
    """
    Chaves canônicas ausentes do dicionário — o que vai cair em default.

    Serve para a resposta poder dizer ao usuário que a simulação rodou sobre
    dados de referência, em vez de deixar isso só no log do servidor.
    """
    return sorted(k for k in _DEFAULTS if k not in rates or rates[k] is None)


def fallback_market_rates(
    asset_type: Optional[str] = None,
    *,
    consortium_provider: Any = None,
    market_rates_connector: Any = None,
) -> Dict[str, float]:
    """
    Dicionário de mercado COMPLETO para quando os conectores estão fora.

    As rotas de sensibilidade e de timing montavam esse fallback à mão, cada
    uma com o seu CET (0,1950 e 0,20) e ambas OMITINDO as chaves de consórcio
    e o IPCA — que os consumidores lá embaixo então preenchiam com um terceiro
    conjunto de defaults. Esta função devolve o conjunto inteiro, composto a
    partir dos fallbacks que já existem e são testados nos conectores.

    Args:
        asset_type: tipo do bem (IMOVEL, VEICULO…) para escolher o CET certo.
        consortium_provider / market_rates_connector: injeção para teste; quando
            omitidos, instancia os padrões.

    Returns:
        Dicionário com todas as chaves de `_DEFAULTS`.
    """
    from app.architect.connectors.anbima import AnbimaConnector
    from app.architect.connectors.bacen import BacenConnector
    from app.architect.connectors.consortium_rate_provider import ConsortiumRateProvider
    from app.architect.connectors.ipca import IPCAConnector
    from app.architect.connectors.market_rates import MarketRatesConnector

    out: Dict[str, float] = {}

    def _merge(fn, chaves: tuple[str, ...]) -> None:
        """Puxa do fallback do conector; se ele próprio falhar, usa a rede."""
        try:
            vindo = fn()
        except Exception as exc:                      # pragma: no cover - defensivo
            logger.warning("[rate_defaults] fallback do conector falhou: %s", exc)
            vindo = {}
        for c in chaves:
            if c in vindo and vindo[c] is not None:
                out[c] = float(vindo[c])

    _merge(BacenConnector().get_fallback_rates,  ("selic_annual",))
    _merge(AnbimaConnector().get_fallback_rates, ("cdi_annual",))
    _merge(IPCAConnector().get_fallback_rates,   ("ipca_annual",))

    # CET depende do bem: o mesmo fallback que ArchitectService usa.
    mrc = market_rates_connector or MarketRatesConnector()
    try:
        cets = mrc.get_fallback_rates()
        chave_cet = f"cet_{asset_type}_min" if asset_type else None
        if chave_cet and chave_cet in cets:
            out["best_cet_annual"] = float(cets[chave_cet])
    except Exception as exc:                          # pragma: no cover - defensivo
        logger.warning("[rate_defaults] CET de fallback indisponível: %s", exc)

    # Consórcio: reaproveita get_fallback_params, que já normaliza o tipo de bem
    # e deriva contemplated_per_month de group_size / months.
    try:
        provider = consortium_provider or ConsortiumRateProvider()
        out.update(provider.get_fallback_params(asset_type or "VEICULO").to_rates_dict())
    except Exception as exc:                          # pragma: no cover - defensivo
        logger.warning("[rate_defaults] parâmetros de consórcio de fallback: %s", exc)

    # Completa o que sobrou (bid_mean_initial/bid_std não têm conector próprio).
    for chave, valor in _DEFAULTS.items():
        out.setdefault(chave, valor)

    return out
