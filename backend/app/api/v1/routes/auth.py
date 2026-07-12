from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    revoke_token,
    get_current_token_data,
    TokenData,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.core.db.users import get_user_by_email, get_user_by_id, create_user
from app.core.database import get_db
from app.core import audit
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)

# Hash fictício usado para equalizar o tempo de resposta quando o usuário
# não é encontrado — evita timing attack / enumeração de contas.
_DUMMY_HASH = get_password_hash("__nexa_dummy_password_never_used__")

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str | None = None

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    full_name: str | None = None
    refresh_token: str | None = None   # sessão longa vive aqui; access dura 30min


class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)

    db_user = get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já registrado",
        )

    hashed_password = get_password_hash(user.password)
    new_user = create_user(
        db=db,
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name
    )

    if not new_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar usuário",
        )

    audit.log_register(
        user_id=new_user["user_id"],
        email=user.email,
        ip=ip,
        request_id=req_id,
    )

    # Cria linha de preferências padrão para o novo usuário
    try:
        from app.settings.router import create_default_settings
        create_default_settings(user_id=new_user["user_id"], db=db)
    except Exception:
        pass  # nunca bloqueia o cadastro

    return {"message": "Usuário criado com sucesso", "user_id": new_user["user_id"]}


@router.post("/token", response_model=Token)
@limiter.limit("10/minute")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)

    user = get_user_by_email(db, form_data.username)
    if not user:
        # Executa verify_password com hash fictício para equalizar tempo de resposta.
        # Sem isso, o tempo de retorno quando o email não existe é visivelmente menor,
        # permitindo enumeração de usuários cadastrados (timing attack).
        verify_password(form_data.password, _DUMMY_HASH)
        audit.log_login_failure(
            email=form_data.username,
            ip=ip,
            reason="email_not_found",
            request_id=req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user["hashed_password"]):
        audit.log_login_failure(
            email=form_data.username,
            ip=ip,
            reason="wrong_password",
            request_id=req_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["user_id"]}, expires_delta=access_token_expires
    )

    audit.log_login_success(user_id=user["user_id"], ip=ip, request_id=req_id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user["user_id"],
        "full_name": user.get("full_name"),
        "refresh_token": create_refresh_token(user["user_id"]),
    }


@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")
async def refresh_access_token(
    request: Request,
    body: RefreshRequest,
    db: Session = Depends(get_db),
):
    """
    Troca um refresh token válido por um novo par access + refresh.

    Rotação: o refresh token usado é revogado (blacklist) no mesmo ato —
    cada refresh vale exatamente um uso. Reuso de um token já rotacionado
    retorna 401 (indício de vazamento; o portador legítimo refaz login).
    """
    token_data = decode_refresh_token(body.refresh_token)

    user = get_user_by_id(db, token_data.user_id)
    if user is None or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inexistente ou inativo",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Rotação: revoga o refresh usado pelo tempo de vida restante dele
    if token_data.jti and token_data.exp:
        from datetime import datetime, timezone
        remaining = max(0, token_data.exp - int(datetime.now(timezone.utc).timestamp()))
        revoke_token(token_data.jti, remaining or 60)

    access_token = create_access_token(
        data={"sub": token_data.user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": token_data.user_id,
        "full_name": user.get("full_name"),
        "refresh_token": create_refresh_token(token_data.user_id),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, token_data: TokenData = Depends(get_current_token_data)):
    """
    Revoga o token atual adicionando o jti à blacklist Redis.
    O token deixa de ser aceito imediatamente, mesmo antes de expirar.
    """
    if token_data.jti:
        exp = token_data.__dict__.get("exp")
        remaining = 0
        if exp:
            from datetime import datetime, timezone
            remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
        revoke_token(token_data.jti, remaining or ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)
    audit.log_logout(user_id=token_data.user_id, ip=ip, request_id=req_id)
