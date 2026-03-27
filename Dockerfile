FROM python:3.12-slim

# Definir variaveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PORT=8000

WORKDIR /app/backend

# Instalar dependencias do sistema necessarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Copiar projeto
COPY backend/ /app/backend/

# Expor porta (Railway usa a variável $PORT)
EXPOSE $PORT

# Comando de inicializacao da API
# Railway define $PORT automaticamente
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
