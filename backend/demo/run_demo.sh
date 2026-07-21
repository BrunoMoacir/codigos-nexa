#!/usr/bin/env bash
# demo/run_demo.sh — sobe o demo Nexa do zero (seed + Streamlit).
# Uso:  cd backend && bash demo/run_demo.sh
set -euo pipefail

cd "$(dirname "$0")/.."   # → backend/

echo "==> 1/3 Aplicando migrações (alembic upgrade head)"
python3 -m alembic upgrade head || echo "   (aviso: alembic falhou — seguindo)"

echo "==> 2/3 Semeando personas pelo ETL real"
python3 -m demo.seed

echo "==> 3/3 Subindo o Streamlit em http://localhost:8501"
exec streamlit run demo/streamlit_app.py
