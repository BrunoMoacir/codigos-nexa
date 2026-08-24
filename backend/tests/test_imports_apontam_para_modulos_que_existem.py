"""
Toda linha `from app.X import ...` tem que apontar para um módulo que existe.

É a guarda que faltava. O F13 carregou por meses, em DUAS cópias:

    from app.profile.user_profile_analyzer import UserProfileAnalyzer

`app.profile` nunca existiu. O `ModuleNotFoundError` caía num `except
Exception` e o Score Nexa voltava 50 para todo usuário — abaixo do piso de 70,
então o gatilho `HEALTH_SCORE_ALTO` ficou morto para 100% dos usuários, e o 50
ainda ia para o prompt do Claude e para o roteiro que o usuário levaria ao
gerente. Nada disso aparecia em teste nenhum: a suíte mockava o helper.

Um import dentro de `try/except Exception` não falha no import do módulo — só
em runtime, em silêncio, no caminho que o usuário percorre. Este teste é
estático: lê a árvore sintática e pergunta se o módulo existe, sem executar.

A segunda parte varre docstrings. Elas não quebram nada sozinhas, mas são de
onde a próxima pessoa copia o caminho errado — seis exemplos apontavam para
`app.schemas.*` e `app.etl.*`, que sumiram num refactor.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re

import pytest

_APP = pathlib.Path(__file__).resolve().parent.parent / "app"
_IGNORAR = {"__pycache__"}

# Módulos citados DE PROPÓSITO como contraexemplo — o docstring de
# `negotiator/health_score.py` reproduz o import quebrado que originou a
# guarda. A exemção é segura porque
# `test_o_import_que_originou_esta_guarda_continua_impossivel` afirma que eles
# continuam não existindo: se um deles ressuscitar, aquele teste cai.
_CITADOS_COMO_CONTRAEXEMPLO = {
    "app.profile.user_profile_analyzer",
    "app.domain.finance_engine",
}


def _arquivos() -> list[pathlib.Path]:
    return sorted(
        p for p in _APP.rglob("*.py")
        if not any(parte in _IGNORAR for parte in p.parts)
    )


def _existe(modulo: str) -> bool:
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _relativo(p: pathlib.Path) -> str:
    return str(p.relative_to(_APP.parent))


class TestImportsReais:

    def test_todo_from_app_aponta_para_modulo_existente(self):
        quebrados: list[str] = []

        for arquivo in _arquivos():
            try:
                arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            except SyntaxError as exc:                      # pragma: no cover
                pytest.fail(f"{_relativo(arquivo)} não parseia: {exc}")

            for no in ast.walk(arvore):
                if not isinstance(no, ast.ImportFrom) or no.level:
                    continue
                modulo = no.module or ""
                if not modulo.startswith("app."):
                    continue
                if not _existe(modulo):
                    quebrados.append(
                        f"{_relativo(arquivo)}:{no.lineno} → {modulo}"
                    )

        assert not quebrados, (
            "import(s) apontando para módulo inexistente — se estiverem dentro "
            "de try/except, falham em silêncio em produção:\n  "
            + "\n  ".join(quebrados)
        )

    def test_o_import_que_originou_esta_guarda_continua_impossivel(self):
        assert not _existe("app.profile.user_profile_analyzer")
        assert not _existe("app.domain.finance_engine")


class TestImportsEmDocstring:
    """
    Documentação não executa — mas é de onde se copia.
    """

    _PADRAO = re.compile(r"from\s+(app\.[A-Za-z0-9_.]+)\s+import", re.MULTILINE)

    def test_exemplos_de_uso_apontam_para_modulo_existente(self):
        quebrados: list[str] = []

        for arquivo in _arquivos():
            texto = arquivo.read_text(encoding="utf-8")
            try:
                arvore = ast.parse(texto)
            except SyntaxError:                             # pragma: no cover
                continue

            reais = {
                no.module for no in ast.walk(arvore)
                if isinstance(no, ast.ImportFrom) and no.module
            }
            docstrings = [
                ast.get_docstring(no) or ""
                for no in ast.walk(arvore)
                if isinstance(
                    no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                )
            ]
            for doc in docstrings:
                for modulo in self._PADRAO.findall(doc):
                    if modulo in reais or modulo in _CITADOS_COMO_CONTRAEXEMPLO:
                        continue
                    if _existe(modulo):
                        continue
                    quebrados.append(f"{_relativo(arquivo)} → {modulo}")

        assert not quebrados, (
            "exemplo(s) de uso em docstring apontando para módulo inexistente:\n  "
            + "\n  ".join(sorted(set(quebrados)))
        )
