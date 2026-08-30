"""
demo/ambiente.py — Resolve as variáveis de ambiente antes de importar `app`.

`app/core/config.py` procura o `.env` a partir de `backend/`. Neste repositório
o arquivo de desenvolvimento está na RAIZ, então `settings.ANTHROPIC_API_KEY`
sai `None` numa máquina que tem a chave — e o Chat do demo cairia no 503 de
"LLM não configurado" sem nenhum motivo real.

`carregar_env()` lê os dois arquivos, nesta ordem de precedência, e nunca
sobrescreve o que já está no ambiente do processo (quem exporta a variável
manda). Precisa ser chamada ANTES do primeiro import de `app.*`, porque
`Settings` é instanciado na importação do módulo.
"""

from __future__ import annotations

import os
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_RAIZ = _BACKEND.parent


def _ler(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        return {}
    valores: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def carregar_env() -> str:
    """Carrega backend/.env e depois o .env da raiz. Devolve a origem usada."""
    origens = []
    for rotulo, caminho in (("backend/.env", _BACKEND / ".env"),
                            (".env da raiz", _RAIZ / ".env")):
        valores = _ler(caminho)
        if not valores:
            continue
        origens.append(rotulo)
        for chave, valor in valores.items():
            os.environ.setdefault(chave, valor)
    return " + ".join(origens) if origens else "somente ambiente do processo"
