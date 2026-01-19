from fastapi import FastAPI
from app.api.v1.router import router as api_router

app = FastAPI(
    title="Nexa API",
    version="0.1.0"
)

# Registra as rotas da API v1
app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/version")
def version():
    return {"version": "0.1.0"}
# Endpoint simples para checar a saúde da aplicação
# Endpoint para retornar a versão da aplicação