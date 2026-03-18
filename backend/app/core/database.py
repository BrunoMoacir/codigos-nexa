from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# Conexão síncrona com PostgreSQL via psycopg2
engine = create_engine(
    settings.DATABASE_URL, 
    pool_pre_ping=True, 
    pool_size=5, 
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base Declarativa para os modelos do ORM
Base = declarative_base()

def get_db():
    """
    Dependency para injeção de sessão do banco no FastAPI.
    Garante que a conexão seja fechada ao final do request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
