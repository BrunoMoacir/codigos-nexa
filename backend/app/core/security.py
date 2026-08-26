import re
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
from app.core.db.users import get_user_by_id

# Configurações do JWT
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
# Access curto + refresh rotativo (auditoria 2026-07): para app financeiro,
# access de 24h dava a um token vazado um dia inteiro de validade — e o
# fail-open do blacklist (Redis fora) estendia isso. Agora um access
# comprometido vale no máximo 30 min; a sessão longa vive no refresh token,
# que é rotacionado (e o antigo revogado) a cada uso.
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 14

# Prefixo Redis para blacklist de tokens revogados
_BLACKLIST_PREFIX = "nexa:blacklist:"

# Compilados uma vez no nível de módulo para evitar overhead por chamada
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE,
)
_SIMPLE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

class TokenData(BaseModel):
    user_id: Optional[str] = None
    jti: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None

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
        # `iat` é o que permite revogação EM MASSA: comparado com
        # `users.sessions_valid_from`, derruba de uma vez toda sessão aberta
        # antes de uma troca de senha. Sem ele só havia revogação individual
        # (por `jti`), que exige saber qual token revogar.
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "jti": str(uuid.uuid4()),  # ID único do token — usado para revogação
        "type": "access",
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: str) -> str:
    """
    Emite um refresh token (type=refresh, validade REFRESH_TOKEN_EXPIRE_DAYS).

    Refresh tokens NÃO são aceitos como credencial de API (get_current_user
    os rejeita) — servem exclusivamente para POST /auth/refresh, que os
    rotaciona: o token usado é revogado e um novo par é emitido.
    """
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_refresh_token(token: str) -> TokenData:
    """
    Valida um refresh token: assinatura, expiração, type=refresh e blacklist.

    Raises:
        HTTPException 401 para qualquer condição inválida.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise invalid

    if payload.get("type") != "refresh" or not payload.get("sub"):
        raise invalid

    jti = payload.get("jti")
    if jti and _is_token_revoked(jti):
        raise invalid

    return TokenData(
        user_id=payload["sub"], jti=jti,
        exp=payload.get("exp"), iat=payload.get("iat"),
    )


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
      - Mitigação, por tipo de token — e o segundo caso é o que importa:
          * ACCESS  expira em ACCESS_TOKEN_EXPIRE_MINUTES (30 min). Janela curta.
          * REFRESH expira em REFRESH_TOKEN_EXPIRE_DAYS (14 DIAS), e a rotação
            o revoga pelo tempo restante dele. Com Redis fora, um refresh
            vazado E JÁ ROTACIONADO segue aceito por até duas semanas — é a
            janela real do fail-open, não 30 minutos.
        (Este docstring dizia "TTL máximo de 24h garante expiração natural",
         o que estava errado por um fator de 14 justamente no caso perigoso.)
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


def sessao_invalidada(iat: Optional[int], corte) -> bool:
    """
    O token foi emitido antes do corte de sessão do usuário?

    Custo zero por request: `get_current_user` já carrega a linha do usuário
    para checar `is_active`. A doc de segurança listava esta revogação global
    como "anotada como melhoria" porque "exigiria claim iat + verificação por
    request" — a verificação já estava sendo paga.

    Comparação estrita, sem folga. Uma tolerância de 1 segundo — que esta
    função teve na primeira versão — abre um buraco de um segundo inteiro no
    corte, e o único caso que ela "protegia" (token emitido no mesmo segundo do
    corte) é justamente o token novo, legítimo, que precisa continuar valendo.

    Limite honesto: `iat` tem granularidade de SEGUNDO. Um token emitido em
    10:00:00,05 e um corte em 10:00:00,90 dão `iat == corte` e o token
    sobrevive — sub-segundo, inevitável com esse claim, e sem consequência
    prática diante de uma sessão de 30 minutos.
    """
    if iat is None or corte is None:
        return False
    try:
        if corte.tzinfo is None:
            corte = corte.replace(tzinfo=timezone.utc)
        return iat < int(corte.timestamp())
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
        # Refresh token não é credencial de API — só troca por access em
        # /auth/refresh. (Tokens antigos sem claim 'type' seguem aceitos.)
        if payload.get("type") == "refresh":
            raise credentials_exception
        token_data = TokenData(user_id=user_id, jti=jti, iat=payload.get("iat"))
    except JWTError:
        raise credentials_exception

    # Verificar blacklist Redis (logout/revogação)
    if token_data.jti and _is_token_revoked(token_data.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revogado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verificar existência e status ativo no banco (Postgres com fallback DuckDB)
    user = get_user_by_id(db, token_data.user_id)
    if user is None or not user.get("is_active", True):
        raise credentials_exception

    if sessao_invalidada(token_data.iat, user.get("sessions_valid_from")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão encerrada. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token_data.user_id


def require_owner(user_id: str, current_user: str = Depends(get_current_user)) -> str:
    """
    Dependency que combina validação de UUID e verificação de propriedade.

    Substitui o padrão repetido em todos os routers:
        validate_user_id(user_id)
        if current_user != user_id:
            raise HTTPException(403)

    Uso:
        @router.get("/{user_id}")
        def endpoint(user_id: str = Depends(require_owner)):
            ...
    """
    validate_user_id(user_id)
    if current_user != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado",
        )
    return user_id


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
    # EM PRODUÇÃO: só UUID v4. Fora dela, identificadores simples ('u1',
    # 'demo-ana') continuam valendo porque fixtures e seeds dependem deles.
    #
    # O comentário anterior dizia "se desejar apenas UUIDs em produção, altere
    # essa função" — e a doc de segurança já afirmava que a validação era de
    # UUID v4. Ficava valendo o mais frouxo nos dois ambientes. A metade da
    # PROPRIEDADE (comparar com o usuário do token) sempre funcionou e está
    # medida; era a de FORMATO que não era o que estava escrito.
    if _UUID_RE.match(user_id):
        return user_id

    from app.core.config import settings

    if settings.APP_ENV != "production" and _SIMPLE_ID_RE.match(user_id):
        return user_id

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="user_id inválido. Use UUID v4.",
    )


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
        token_data = TokenData(user_id=user_id, jti=jti, exp=exp)
        return token_data
    except JWTError:
        raise credentials_exception
