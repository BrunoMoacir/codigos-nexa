"""
Isolamento das taxas vivas do BACEN nos testes fiscais.

`TaxRadarService.__init__` busca SELIC (série 432) e TR (série 226) na API
do BCB — duas chamadas HTTP dentro de um construtor. O resultado decide se
o alerta de poupança dispara, então o teste passava ou falhava conforme o
que a rede devolvesse naquele instante: sozinho passava, dentro da suíte
completa falhava com `assert 0 == 1` (nenhum alerta gerado).

Mesma solução que a suíte já aplica ao catálogo vivo do OPP e ao baseline
vivo de tarifas (ver tests/conftest.py): teste não pergunta para a internet.
Os valores fixados são o fallback documentado do próprio BacenConnector, de
modo que o teste exercita a REGRA (poupança vs. Tesouro SELIC), não a
cotação do dia.

Quem quiser testar o conector de verdade continua livre para fazê-lo —
este isolamento vale só para o pacote fiscal.
"""

import pytest

# Fallback documentado do BacenConnector (COPOM mar/2026) — ver
# BacenConnector.get_fallback_rates().
_SELIC_ANUAL = 0.1475
_TR_MENSAL = 0.0


@pytest.fixture(autouse=True)
def _taxas_bacen_fixas(monkeypatch):
    from app.architect.connectors.bacen import BacenConnector

    monkeypatch.setattr(BacenConnector, "get_selic", lambda self: _SELIC_ANUAL)
    monkeypatch.setattr(BacenConnector, "get_tr_monthly", lambda self: _TR_MENSAL)
    yield
