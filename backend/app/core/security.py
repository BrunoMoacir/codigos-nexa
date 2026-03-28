import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

# Configurações do JWT
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas — token comprometido expira em no máximo 1 dia

# Prefixo Redis para blacklist de tokens revogados
_BLACKLIST_PREFIX = "nexa:blacklist:"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

class TokenData(BaseModel):
    user_id: Optional[str] = None
    jti: Optional[str] = None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)

    to_encode.update({
        "exp": expire,
        "jti": str(uuid.uuid4()),  # ID único do token — usado para revogação
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def revoke_token(jti: str, expires_in_seconds: int) -> None:
    """
    Insere o jti do token na blacklist Redis.

    O TTL é alinhado à expiração do token para que a entrada seja
    removida automaticamente quando o token já não seria válido de qualquer forma.
    """
    from app.core.cache import get_redis
    client = get_redis()
    if client:
        try:
            client.setex(f"{_BLACKLIST_PREFIX}{jti}", expires_in_seconds, "1")
        except Exception:
            # Cache indisponível — token continua válido até expirar; registrar e seguir.
            import logging
            logging.getLogger(__name__).warning(
                "[Security] Redis indisponível ao revogar token jti=%s — token não foi blacklistado.", jti
            )


def _is_token_revoked(jti: str) -> bool:
    """
    Retorna True se o jti estiver na blacklist Redis.

    Comportamento quando Redis está indisponível:
      - Fail-open: tokens revogados por logout são temporariamente aceitos.
      - Trade-off consciente: bloquear todos os usuários quando Redis cai é
        pior para disponibilidade do que aceitar tokens recentemente revogados
        por um curto período.
      - Mitigação: TTL máximo de 24h garante expiração natural dos tokens.
      - Monitore alertas de Redis para detectar janelas de fail-open.
    """
    from app.core.cache import get_redis
    import logging as _log
    client = get_redis()
    if not client:
        _log.getLogger(__name__).warning(
            "[Security] Redis indisponível — verificação de token revogado ignorada (fail-open). "
            "Tokens revogados por logout podem ser aceitos até o Redis se recuperar."
        )
        return False
    try:
        return client.exists(f"{_BLACKLIST_PREFIX}{jti}") == 1
    except Exception:
        return False


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> str:
    """
    Dependency para proteger rotas.

    Validações em ordem:
      1. Assinatura e expiração do JWT.
      2. Claim 'sub' presente.
      3. Token não está na blacklist Redis (revogado por logout).
      4. Usuário existe no banco e está ativo.

    Retorna o user_id extraído do token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        jti: Optional[str] = payload.get("jti")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id, jti=jti)
    except JWTError:
        raise credentials_exception

    # Verificar blacklist Redis (logout/revogação)
    if token_data.jti and _is_token_revoked(token_data.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revogado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verificar existência e status ativo no banco
    from app.core.models.user import User
    user = db.query(User).filter(User.user_id == token_data.user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return token_data.user_id


def validate_user_id(user_id: str) -> str:
    """
    Valida que user_id é um UUID v4 bem formado.

    Uso nos endpoints:
        user_id: str = Depends(lambda uid: validate_user_id(uid))
    Ou inline:
        validate_user_id(user_id)

    Raises:
        HTTPException 422 se o formato for inválido.
    """
    import re
    _UUID_RE = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE,
    )
    if not _UUID_RE.match(user_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id deve ser um UUID v4 válido.",
        )
    return user_id


async def get_current_token_data(token: str = Depends(oauth2_scheme)) -> TokenData:
    """
    Dependency auxiliar que retorna o TokenData completo (com jti).
    Usada no endpoint de logout para poder revogar o token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        jti: Optional[str] = payload.get("jti")
        exp: Optional[int] = payload.get("exp")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id, jti=jti)
        # Anexa exp ao objeto para uso no logout
        token_data.__dict__["exp"] = exp
        return token_data
    except JWTError:
        raise credentials_exception
