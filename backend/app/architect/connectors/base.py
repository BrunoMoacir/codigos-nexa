"""
app/architect/connectors/base.py - Connector abstrato para APIs externas

Feature: F3 - Nexa Architect
Version: 1.0.1

Responsabilidade:
    Classe base para todos os conectores de taxas de mercado.
    Fornece cache em memória com TTL e fallback automático quando
    a API externa falha.

Subclasses obrigatórias:
    - fetch_rates()         → busca dados da API real (deve usar self.timeout)
    - get_fallback_rates()  → valores conservadores para quando a API falha

Uso:
    from app.architect.connectors.bacen import BacenConnector
    connector = BacenConnector()
    rates = connector.get_rates()   # cache → API → fallback
    selic = rates["selic_annual"]

Cache:
    - Fetch bem-sucedido: cached por cache_ttl_seconds (padrão 1h)
    - Fetch com falha: fallback cached por fallback_cache_ttl_seconds (padrão 60s)
      Isso evita spam de requests quando a API está temporariamente fora.
    - Cada instância tem seu próprio cache (não compartilhado entre instâncias).
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConnectorError(Exception):
    """
    Levantada quando o connector falha e não há fallback disponível.

    Em condições normais nunca deve chegar ao caller, pois get_rates()
    sempre retorna fallback antes de propagar erro.
    """


class BaseConnector(ABC):
    """
    Classe base para conectores de APIs externas de taxas de mercado.

    Fluxo de get_rates():
        1. Verifica cache em memória (retorna imediatamente se válido)
        2. Chama fetch_rates() da subclasse
        3. Se fetch falha → loga aviso, cacheia fallback por fallback_cache_ttl_seconds
           e retorna get_fallback_rates()

    Args:
        cache_ttl_seconds:          Tempo de vida do cache após fetch bem-sucedido
                                    (padrão: 3600 = 1 hora). Deve ser > 0.
        timeout_seconds:            Timeout por request HTTP — subclasses devem
                                    usar self.timeout ao chamar a API (padrão: 5s).
        fallback_cache_ttl_seconds: Tempo de vida do cache quando o fetch falha.
                                    Evita tentativas repetidas enquanto a API está
                                    fora (padrão: 60s). Deve ser > 0.

    Note:
        cache_key = self.__class__.__name__, portanto instâncias da mesma
        subclasse têm caches independentes (cada instância tem seu próprio dict).

    Example:
        >>> connector = BacenConnector(cache_ttl_seconds=1800)
        >>> rates = connector.get_rates()
        >>> selic = rates["selic_annual"]   # ex: 0.1075
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 3600,
        timeout_seconds: int = 5,
        fallback_cache_ttl_seconds: int = 60,
    ) -> None:
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds deve ser maior que zero")
        if fallback_cache_ttl_seconds <= 0:
            raise ValueError("fallback_cache_ttl_seconds deve ser maior que zero")

        self.cache_ttl = cache_ttl_seconds
        self.timeout = timeout_seconds
        self.fallback_cache_ttl = fallback_cache_ttl_seconds

        self._cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, datetime] = {}  # stores absolute expiry time

    # ── Interface obrigatória ─────────────────────────────────────────────

    @abstractmethod
    def fetch_rates(self) -> Dict[str, float]:
        """
        Busca taxas diretamente da API externa (sem cache).

        Implementações devem usar self.timeout ao fazer requests HTTP
        para evitar bloqueio indefinido.

        Returns:
            Dict de {nome_taxa: valor_decimal}
            Ex: {"selic_annual": 0.1075}

        Raises:
            ConnectorError: Se a API não responde ou retorna dado inválido.
        """
        ...

    @abstractmethod
    def get_fallback_rates(self) -> Dict[str, float]:
        """
        Retorna taxas hardcoded conservadoras para uso quando a API falha.

        Os valores devem representar estimativas razoáveis e recentes,
        atualizadas a cada trimestre pelo time de engenharia.

        Returns:
            Dict de {nome_taxa: valor_decimal}
        """
        ...

    # ── Cache ─────────────────────────────────────────────────────────────

    def _is_cache_valid(self, key: str) -> bool:
        """Retorna True se a entrada de cache ainda não expirou."""
        expiry = self._cache_expiry.get(key)
        return expiry is not None and datetime.now(timezone.utc) < expiry

    def _set_cache(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        Armazena valor no cache com expiração absoluta.

        Args:
            key:         Chave de cache.
            value:       Valor a armazenar.
            ttl_seconds: TTL em segundos. Se None, usa self.cache_ttl.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.cache_ttl
        self._cache[key] = value
        self._cache_expiry[key] = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    def _get_cache(self, key: str) -> Optional[Any]:
        """Retorna valor do cache se ainda válido, None caso contrário."""
        return self._cache.get(key) if self._is_cache_valid(key) else None

    # ── API pública ───────────────────────────────────────────────────────

    def fetch_rates_secondary(self) -> Optional[Dict[str, float]]:
        """
        Fonte secundária de dados — chamada quando fetch_rates() falha.

        Subclasses devem sobrescrever para fornecer uma fonte alternativa
        (ex: IBGE para IPCA, derivação de outra taxa para CDI).
        Retornar None indica "sem fonte secundária disponível".

        Returns:
            Dict de {nome_taxa: valor_decimal} ou None.
        """
        return None

    def get_rates(self) -> Dict[str, float]:
        """
        Retorna taxas com cache automático e cadeia de fallback em 3 níveis.

        Fluxo:
            1. Cache válido → retorna imediatamente
            2. fetch_rates() bem-sucedido → cacheia por cache_ttl_seconds e retorna
            3. fetch_rates_secondary() bem-sucedido → cacheia por fallback_cache_ttl e retorna
            4. Ambas falharam → loga aviso, cacheia hardcoded por fallback_cache_ttl
               e retorna get_fallback_rates()

        Returns:
            Dict de {nome_taxa: valor_decimal} — sempre retorna algo válido.

        Example:
            >>> rates = connector.get_rates()
            >>> rates["selic_annual"]
            0.1075
        """
        cache_key = self.__class__.__name__

        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        # Nível 1: fonte primária
        try:
            rates = self.fetch_rates()
            self._set_cache(cache_key, rates)
            logger.debug(
                "[%s] Taxas atualizadas via API primária: %s",
                self.__class__.__name__,
                list(rates.keys()),
            )
            return rates
        except Exception as exc:
            logger.warning(
                "[%s] Fonte primária falhou (%s: %s). Tentando fonte secundária.",
                self.__class__.__name__,
                type(exc).__name__,
                exc,
            )

        # Nível 2: fonte secundária (implementada pela subclasse)
        try:
            secondary = self.fetch_rates_secondary()
            if secondary is not None:
                self._set_cache(cache_key, secondary, ttl_seconds=self.fallback_cache_ttl)
                logger.info(
                    "[%s] Taxas obtidas via fonte secundária: %s",
                    self.__class__.__name__,
                    list(secondary.keys()),
                )
                return secondary
        except Exception as exc2:
            logger.warning(
                "[%s] Fonte secundária também falhou (%s: %s). Usando hardcoded.",
                self.__class__.__name__,
                type(exc2).__name__,
                exc2,
            )

        # Nível 3: fallback hardcoded
        logger.warning(
            "[%s] Todas as fontes falharam. Usando valores hardcoded por %ds.",
            self.__class__.__name__,
            self.fallback_cache_ttl,
        )
        fallback = self.get_fallback_rates()
        self._set_cache(cache_key, fallback, ttl_seconds=self.fallback_cache_ttl)
        return fallback

    def invalidate_cache(self) -> None:
        """Limpa o cache, forçando re-fetch na próxima chamada."""
        self._cache.clear()
        self._cache_expiry.clear()

    @property
    def is_cache_warm(self) -> bool:
        """True se há dados válidos em cache para este connector."""
        return self._is_cache_valid(self.__class__.__name__)


__all__ = ["BaseConnector", "ConnectorError"]
