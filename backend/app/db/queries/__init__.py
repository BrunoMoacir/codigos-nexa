# app/db/queries/__init__.py
#
# COMPATIBILIDADE RETROATIVA:
# O código existente importa `from app.db.queries import save_context_override`
# (aponta para o antigo app/db/queries.py — F4 Divider).
# Agora que app/db/queries/ é um pacote, re-exportamos essas funções aqui.
#
# Para F3 (Architect), use:
#   from app.db.queries.architect_queries import save_simulation

import importlib.util
import pathlib

# Localiza e carrega app/db/queries.py pelo caminho absoluto,
# dando a ele um nome de módulo único (_queries_legacy) para
# evitar shadowing com este pacote (mesmo nome no sys.modules).
_queries_file = pathlib.Path(__file__).parent.parent / "queries.py"
_spec = importlib.util.spec_from_file_location("_queries_legacy", _queries_file)
assert _spec is not None and _spec.loader is not None, (
    f"Não foi possível carregar {_queries_file}"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

# Re-exportar funções usadas pelo código existente da aplicação
get_connection          = _mod.get_connection
get_context_overrides   = _mod.get_context_overrides
save_context_override   = _mod.save_context_override
get_override_stats      = _mod.get_override_stats
save_transactions_clean = _mod.save_transactions_clean

__all__ = [
    "get_connection",
    "get_context_overrides",
    "save_context_override",
    "get_override_stats",
    "save_transactions_clean",
]
