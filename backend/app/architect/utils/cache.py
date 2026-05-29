"""
app/architect/utils/cache.py - Cache Multi-nível de Simulações

Feature: F3 - Nexa Architect
Version: 3.0.0 (Fase 3)

Responsabilidade:
    Cache de dois níveis para resultados de simulação e sensibilidade.
    Evita re-executar cálculos caros (math + rede) para inputs idênticos.

Níveis:
    L1 — Memória  → dict em processo, sub-milissegundo, ephemeral (limpo ao reiniciar)
    L2 — Disco    → arquivo JSON por chave, persiste entre restarts, ~1ms

Decisões de design:
    - Stdlib apenas: hashlib, json, os, pathlib, time — sem Redis, sem dependências novas.
    - Eviction L1: LRU-like (expira entradas inválidas antes de remover a mais antiga).
    - Disco L2: um arquivo JSON por chave, com campo "expires_at" (unix timestamp).
    - Chave de simulação: SHA-256 dos parâmetros matemáticos relevantes (exclui user_id).
    - Chave de sensibilidade: simulation_id + hash das taxas atuais.

Uso:
    from app.architect.utils.cache import SimulationCache, make_simulation_key

    cache = SimulationCache()                            # singleton recomendado
    key   = make_simulation_key(req.model_dump(), rates)

    result = cache.get(key)
    if result is None:
        result = service.simulate(req)
        cache.set(key, result.model_dump(mode="json"))
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Diretório padrão do cache de disco — sobrescrevível via variável de ambiente
_DEFAULT_CACHE_DIR = Path(os.getenv("NEXA_CACHE_DIR", "/tmp/nexa_cache"))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRADA L1 — MEMÓRIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _MemoryEntry:
    """Entrada individual no cache L1 (memória)."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl_seconds: int) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl_seconds

    @property
    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CACHE PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SimulationCache:
    """
    Cache multi-nível (L1: memória, L2: disco) para resultados da F3.

    Estratégia de consulta:
        get(key) → L1 hit → retorna imediatamente
                 → L1 miss → L2 hit → promove para L1, retorna
                 → L2 miss → retorna None (caller deve calcular e chamar set())

    Eviction L1 (quando max_memory_entries é atingido):
        1. Remove entradas expiradas.
        2. Se ainda cheio, remove a entrada com o menor expires_at (mais antiga).

    Disco L2:
        Cada chave → arquivo `{key}.json` com `{"expires_at": <unix>, "value": <payload>}`.
        Entradas expiradas são removidas no momento da leitura (lazy deletion).

    Args:
        cache_dir:          Diretório raiz para cache de disco. Default: /tmp/nexa_cache.
        l1_ttl:             TTL padrão L1 em segundos. Default: 3600 (1 hora).
        l2_ttl:             TTL padrão L2 em segundos. Default: 86400 (24 horas).
        max_memory_entries: Máximo de entradas em L1. Default: 256.

    Usage:
        cache = SimulationCache()
        key = make_simulation_key(req.model_dump(), market_rates)

        result = cache.get(key)
        if result is None:
            result = service.simulate(req).model_dump(mode="json")
            cache.set(key, result)
    """

    DEFAULT_TTL_L1: int = 3_600    # 1 hora
    DEFAULT_TTL_L2: int = 86_400   # 24 horas

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        l1_ttl: int = DEFAULT_TTL_L1,
        l2_ttl: int = DEFAULT_TTL_L2,
        max_memory_entries: int = 256,
    ) -> None:
        self._l1: Dict[str, _MemoryEntry] = {}
        self._l1_default_ttl = l1_ttl
        self._l2_default_ttl = l2_ttl
        self._max_memory = max_memory_entries

        # Inicializar diretório de disco
        self._l2_dir: Optional[Path] = Path(cache_dir or _DEFAULT_CACHE_DIR)
        try:
            self._l2_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "Cache de disco indisponível (%s) — usando apenas L1 (memória).", exc
            )
            self._l2_dir = None

    # ── API pública ──────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        """
        Retorna o valor armazenado ou None se não encontrado / expirado.

        Consulta L1 → L2. Um hit em L2 promove o valor para L1.
        """
        # L1
        entry = self._l1.get(key)
        if entry is not None and entry.is_valid:
            logger.debug("cache L1 HIT: %.16s…", key)
            return entry.value

        # L2
        value = self._read_disk(key)
        if value is not None:
            logger.debug("cache L2 HIT: %.16s… (promovendo para L1)", key)
            self._write_l1(key, value, self._l1_default_ttl)
            return value

        logger.debug("cache MISS: %.16s…", key)
        return None

    def set(
        self,
        key: str,
        value: Any,
        l1_ttl: Optional[int] = None,
        l2_ttl: Optional[int] = None,
    ) -> None:
        """
        Armazena valor em L1 e L2 com os TTLs especificados.

        Args:
            key:    Chave de cache (use make_simulation_key / make_sensitivity_key).
            value:  Valor serializável (dict, list, str, int, float — sem objetos Pydantic).
            l1_ttl: TTL em segundos para L1. Default: self._l1_default_ttl.
            l2_ttl: TTL em segundos para L2. Default: self._l2_default_ttl.
        """
        self._write_l1(key, value, l1_ttl or self._l1_default_ttl)
        self._write_disk(key, value, l2_ttl or self._l2_default_ttl)

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], T],
        l1_ttl: Optional[int] = None,
        l2_ttl: Optional[int] = None,
    ) -> T:
        """
        Retorna valor do cache ou chama compute_fn e armazena o resultado.

        Útil para envolver chamadas custosas sem boilerplate de get/set:

            result = cache.get_or_compute(
                key=make_simulation_key(req.model_dump(), rates),
                compute_fn=lambda: service.simulate(req).model_dump(mode="json"),
                l1_ttl=3600,
            )

        **Thread-safety:** não é thread-safe entre o get() e o set(). Em ambiente
        multi-thread, duas threads com a mesma chave podem calcular simultaneamente
        (at-most-once semântica não garantida). No contexto do projeto — FastAPI com
        asyncio e compute_fn síncrona — isso não é problema pois o event loop é
        single-threaded. Se migrar para multi-worker, proteja com threading.Lock externo.

        Args:
            key:        Chave de cache.
            compute_fn: Função zero-arg que retorna o valor a ser cacheado.
            l1_ttl:     TTL L1 (opcional, usa default se None).
            l2_ttl:     TTL L2 (opcional, usa default se None).

        Returns:
            Valor do cache ou resultado de compute_fn.
        """
        cached = self.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        value = compute_fn()
        self.set(key, value, l1_ttl=l1_ttl, l2_ttl=l2_ttl)
        return value

    def delete(self, key: str) -> None:
        """Remove entrada de ambos os níveis."""
        self._l1.pop(key, None)
        if self._l2_dir:
            (self._l2_dir / f"{key}.json").unlink(missing_ok=True)

    def invalidate_pattern(self, prefix: str) -> int:
        """
        Remove todas as entradas cujo key começa com `prefix`.

        Útil para invalidar em massa: ex. `cache.invalidate_pattern("sim_")`.

        Returns:
            Número de chaves únicas removidas (independente de quantos níveis
            cada uma ocupava).
        """
        removed_keys: set = set()

        # L1
        to_delete = [k for k in list(self._l1) if k.startswith(prefix)]
        for k in to_delete:
            del self._l1[k]
            removed_keys.add(k)

        # L2 — stem do arquivo = chave (sem ".json")
        if self._l2_dir:
            for path in self._l2_dir.glob(f"{prefix}*.json"):
                removed_keys.add(path.stem)
                path.unlink(missing_ok=True)

        count = len(removed_keys)
        logger.info("invalidate_pattern('%s'): %d chaves removidas", prefix, count)
        return count

    def clear(self) -> None:
        """Limpa completamente L1 e L2."""
        self._l1.clear()
        if self._l2_dir:
            for path in self._l2_dir.glob("*.json"):
                path.unlink(missing_ok=True)
        logger.info("Cache limpo (L1 + L2)")

    @property
    def stats(self) -> Dict[str, int]:
        """
        Estatísticas básicas do estado atual do cache.

        Nota: `l2_total` conta arquivos físicos no diretório, incluindo entradas
        expiradas que ainda não foram deletadas (lazy deletion). Não representa
        necessariamente o número de entradas válidas em disco.

        Returns:
            {
              "l1_total":  total de entradas em L1 (incluindo expiradas não eviccionadas),
              "l1_valid":  entradas L1 ainda dentro do TTL,
              "l2_total":  arquivos .json físicos em disco (inclui expirados),
            }
        """
        valid_l1 = sum(1 for e in self._l1.values() if e.is_valid)
        disk_count = (
            sum(1 for _ in self._l2_dir.glob("*.json")) if self._l2_dir else 0
        )
        return {
            "l1_total": len(self._l1),
            "l1_valid": valid_l1,
            "l2_total": disk_count,
        }

    # ── Internals ────────────────────────────────────────────────────────────

    def _write_l1(self, key: str, value: Any, ttl: int) -> None:
        """Escreve em L1 com eviction quando necessário."""
        if len(self._l1) >= self._max_memory:
            # Passo 1: remover expiradas
            expired_keys = [k for k, e in self._l1.items() if not e.is_valid]
            for k in expired_keys:
                del self._l1[k]
            # Passo 2: se ainda cheio, remover a que expira primeiro
            if len(self._l1) >= self._max_memory:
                lru_key = min(self._l1, key=lambda k: self._l1[k].expires_at)
                del self._l1[lru_key]
                logger.debug("cache L1 eviction: %.16s…", lru_key)
        self._l1[key] = _MemoryEntry(value, ttl)

    def _read_disk(self, key: str) -> Optional[Any]:
        """Lê entrada do disco. Retorna None se não existir ou expirada."""
        if self._l2_dir is None:
            return None
        path = self._l2_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() > data["expires_at"]:
                path.unlink(missing_ok=True)  # lazy delete
                return None
            return data["value"]
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.debug("Erro ao ler cache de disco '%s': %s", path.name, exc)
            return None

    def _write_disk(self, key: str, value: Any, ttl: int) -> None:
        """Serializa entrada para disco."""
        if self._l2_dir is None:
            return
        path = self._l2_dir / f"{key}.json"
        try:
            # Sem default=str: TypeError deve subir para forçar o caller a passar
            # apenas tipos JSON-serializáveis (dict, list, str, int, float, bool, None).
            # Use model.model_dump(mode="json") antes de chamar set().
            payload = json.dumps(
                {"expires_at": time.time() + ttl, "value": value},
                ensure_ascii=False,
            )
            path.write_text(payload, encoding="utf-8")
        except TypeError as exc:
            logger.error(
                "Cache de disco: valor não-serializável para '%.16s…': %s. "
                "Converta com .model_dump(mode='json') antes de chamar set().",
                key, exc,
            )
        except OSError as exc:
            logger.warning(
                "Falha ao escrever cache de disco '%.16s…': %s", key, exc
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS DE CHAVE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def make_simulation_key(
    request_dict: dict,
    market_rates: dict,
    calibration_version: int = 0,
) -> str:
    """
    Gera uma chave de cache determinística para uma simulação.

    A chave é derivada apenas dos parâmetros que afetam o resultado
    matemático — user_id e target_date são excluídos intencionalmente
    (o mesmo veículo de R$50k terá o mesmo resultado para qualquer usuário).

    Args:
        request_dict:         dict de SimulationRequest.model_dump(mode="json")
        market_rates:         dict de taxas de mercado (selic_annual, cdi_annual, ...)
        calibration_version:  versão atual da CalibrationState — incrementada a cada
                              recalibração, garante que simulações obsoletas sejam
                              recalculadas automaticamente.

    Returns:
        String "sim_{48 hex chars}" — segura para uso como nome de arquivo.

    Example:
        >>> key = make_simulation_key(req.model_dump(mode="json"), rates, cal_version=3)
        >>> cache.get(key)  # None no primeiro acesso
    """
    # Parâmetros que determinam o resultado matemático (subset intencional)
    relevant_request = {
        "target_amount":      request_dict.get("target_amount"),
        "down_payment":       request_dict.get("down_payment"),
        "max_monthly_budget": request_dict.get("max_monthly_budget"),
        "financing_months":   request_dict.get("financing_months"),
        "amortization_method": request_dict.get("amortization_method"),
        "include_consortium": request_dict.get("include_consortium"),
        "risk_profile":       request_dict.get("risk_profile"),
        "asset_type":         request_dict.get("asset_type"),
        # Flags de execução determinísticas — fast_mode e full_mode têm entradas separadas
        "include_macro":                  request_dict.get("include_macro", True),
        "include_breakeven_distribution": request_dict.get("include_breakeven_distribution", True),
        # Versão da calibração — muda quando RiskScorer ou MC de consórcio recalibra
        "calibration_version": calibration_version,
    }

    # Arredondar taxas em 6 casas para evitar colisões por float impreciso
    rounded_rates = {
        k: round(float(v), 6)
        for k, v in market_rates.items()
        if isinstance(v, (int, float))
    }

    payload = json.dumps(
        {"request": relevant_request, "rates": rounded_rates},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sim_{digest[:48]}"  # 192 bits — resistência a colisão adequada


def make_sensitivity_key(simulation_id: str, market_rates: dict) -> str:
    """
    Gera chave de cache para um relatório de sensibilidade.

    Combina o ID da simulação (que identifica os parâmetros base) com um hash
    das taxas atuais. Se as taxas de mercado mudarem, a chave muda e a análise
    é recalculada automaticamente.

    Args:
        simulation_id: UUID da simulação persistida no banco.
        market_rates:  Taxas de mercado atuais.

    Returns:
        String "sens_{simulation_id}_{16 hex chars}".

    Example:
        >>> key = make_sensitivity_key("550e8400-...", rates)
        >>> cache.get(key)
    """
    rates_str = json.dumps(
        {k: round(float(v), 6) for k, v in market_rates.items() if isinstance(v, (int, float))},
        sort_keys=True,
    )
    rates_hash = hashlib.sha256(rates_str.encode("utf-8")).hexdigest()[:24]  # 96 bits
    return f"sens_{simulation_id}_{rates_hash}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INSTÂNCIA COMPARTILHADA (singleton de processo)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Singleton pronto para uso — importar diretamente nos endpoints:
#   from app.architect.utils.cache import simulation_cache
simulation_cache = SimulationCache()


__all__ = [
    "SimulationCache",
    "make_simulation_key",
    "make_sensitivity_key",
    "simulation_cache",
]
