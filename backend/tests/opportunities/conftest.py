# tests/opportunities/conftest.py
#
# A isolação do catálogo vivo do OPP (product_catalog.json gerado em runtime
# pelo job product_catalog_refresh) é feita em tests/conftest.py (raiz), com
# escopo de sessão — precisa ser session-scoped porque fixtures module-scoped
# (ex.: o comparator de test_bank_comparator.py) são instanciadas antes de
# qualquer fixture function-scoped e cacheiam o catálogo por TTL.
