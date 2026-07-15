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
