# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import router as api_router
from app.api.v1.routes.dashboard import router as dashboard_router

# Rate limiter global (por IP)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Nexa API",
    version="0.1.0"
)

# Registra o limiter e o handler de erro 429
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Registra as rotas da API v1
app.include_router(api_router, prefix="/api/v1")

app.include_router(dashboard_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": "0.1.0"}