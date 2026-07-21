import sys
from pathlib import Path

import pytest

# Adiciona a raiz do backend no PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _disable_rate_limit():
    """
    Desativa o rate limiter do slowapi durante a suíte.

    Motivo: /auth/token tem limite de 10/min por IP. Isolado, cada arquivo
    passa; na suíte completa, os logins de arquivos anteriores consomem a
    cota do mesmo minuto e todo fixture de token subsequente recebe 429
    (eram os 67 erros de test_integracao_completa). Com Redis local ativo
    o contador ainda persiste ENTRE execuções da suíte, tornando o
    resultado dependente do relógio.

    Produção não é afetada — o toggle só existe dentro do pytest.
    """
    # O projeto tem VÁRIAS instâncias de Limiter (main.py global + rotas
    # com limites próprios) — todas precisam ser desativadas.
    modules_with_limiter = (
        "app.main",
        "app.api.v1.routes.auth",
        "app.forecast.router",
        "app.agent.router",
    )
    import importlib

    for module_name in modules_with_limiter:
        try:
            module = importlib.import_module(module_name)
            limiter = getattr(module, "limiter", None)
            if limiter is not None:
                limiter.enabled = False
        except Exception:
            # módulo indisponível (testes puramente unitários) — nada a fazer
            pass
    yield


@pytest.fixture(scope="session", autouse=True)
def _isolate_live_product_catalog(tmp_path_factory):
    """
    Isola a suíte do catálogo vivo do OPP.

    app/opportunities/data/product_catalog.json é gerado em RUNTIME pelo job
    product_catalog_refresh (varredura diária do Open Finance Dados Abertos)
    e muda a cada dia/máquina. O BankComparator prefere esse arquivo quando
    existe — testes que dependessem dele seriam não-determinísticos (a suíte
    passaria no CI, onde o arquivo não existe, e falharia numa máquina onde o
    job rodou). Aponta o caminho para um arquivo inexistente: todos os testes
    usam o catálogo curado versionado (backend/data/bank_products.json).

    Precisa ser session-scoped: fixtures module-scoped (ex.: o comparator de
    test_bank_comparator.py) são criadas antes de fixtures function-scoped e
    cacheiam o catálogo por TTL. Testes do reload do catálogo vivo
    (test_catalog_reload) sobrescrevem o caminho com monkeypatch próprio.
    """
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    try:
        import app.opportunities.services.bank_comparator as bc_module

        mp.setattr(
            bc_module,
            "_LIVE_CATALOG_PATH",
            tmp_path_factory.mktemp("opp_catalog") / "nonexistent_catalog.json",
        )
    except Exception:
        pass
    # Mesmo isolamento para o baseline vivo de tarifas (job market_fees_refresh)
    try:
        import app.costs.market_fees_db as fees_module

        mp.setattr(
            fees_module,
            "_LIVE_FEES_PATH",
            tmp_path_factory.mktemp("market_fees") / "nonexistent_fees.json",
        )
    except Exception:
        pass
    yield
    mp.undo()
