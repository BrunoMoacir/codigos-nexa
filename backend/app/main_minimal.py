# app/main_minimal.py - Versão minimalista para debug no Railway
import logging
import os
import sys

# Configurar logging primeiro
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("🚀 NEXA API - Minimal Version (Debug)")
logger.info("=" * 60)
logger.info("📦 Python: %s", sys.version)
logger.info("🌍 APP_ENV: %s", os.getenv('APP_ENV', 'not set'))
logger.info("🔗 DATABASE_URL: %s", "✅" if os.getenv("DATABASE_URL") else "❌")
logger.info("🔑 SECRET_KEY: %s", "✅" if os.getenv("SECRET_KEY") else "❌")
logger.info("🚪 PORT: %s", os.getenv('PORT', '8000'))
logger.info("=" * 60)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Nexa API (Minimal)",
    version="0.1.0-debug"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Health check - sem dependências"""
    logger.info("✅ Health check called")
    return {
        "status": "ok",
        "service": "nexa-api-minimal",
        "env": os.getenv("APP_ENV", "unknown")
    }


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Nexa API is running (minimal version)",
        "docs": "/docs",
        "health": "/health"
    }


@app.on_event("startup")
async def startup():
    logger.info("🎯 API startup complete - ready to receive requests")
    logger.info("🌐 Listening on 0.0.0.0:%s", os.getenv('PORT', '8000'))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
