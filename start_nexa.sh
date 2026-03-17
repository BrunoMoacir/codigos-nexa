#!/bin/bash
# Exibe cores no terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Iniciando Nexa ===${NC}"

# 1. Garante que o docker local antigo está parado para liberar o banco
echo -e "${BLUE}[1/3] Parando containers Docker antigos (para liberar o banco)...${NC}"
cd "/home/bruno/Área de trabalho/nexa/codigos-nexa/"
sudo docker-compose down

# 2. Inicia o Backend
echo -e "${BLUE}[2/3] Iniciando o Backend FastAPI...${NC}"
cd "/home/bruno/Área de trabalho/nexa/codigos-nexa/backend"
source ../venv/bin/activate
# Roda em background
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
sleep 3

# 3. Inicia o Frontend
echo -e "${BLUE}[3/3] Iniciando o Frontend Streamlit...${NC}"
cd "/home/bruno/Área de trabalho/nexa/codigos-nexa/"
source venv/bin/activate
streamlit run frontend/app.py &
FRONTEND_PID=$!

echo -e "${GREEN}=== Tudo rodando! ===${NC}"
echo -e "Backend: http://localhost:8000/docs"
echo -e "Frontend: http://localhost:8501"
echo -e "\nPressione CTRL+C para parar tudo."

# Espera CTRL+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
