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
    get_current_user,
    TokenData,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.core.db.users import get_user_by_email, get_user_by_id, create_user
from app.core.database import get_db
from app.core import audit
from sqlalchemy.orm import Session

import logging

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)
logger_auth = logging.getLogger(__name__)

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


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str


_MIN_PASSWORD_LEN = 8


def _frontend_url(path: str) -> str:
    from app.core.config import settings

    base = (getattr(settings, "FRONTEND_BASE_URL", "") or "http://localhost:8501").rstrip("/")
    return f"{base}{path}"


def _send_reset_email(email: str, token: str) -> None:
    from app.core.notifications.email_sender import send_email

    link = _frontend_url(f"/reset-password?token={token}")
    send_email(
        to=email,
        subject="Nexa — redefinição de senha",
        html_body=(
            "<p>Recebemos um pedido para redefinir a senha da sua conta Nexa.</p>"
            f'<p><a href="{link}">Clique aqui para criar uma nova senha</a> '
            "(o link vale por 60 minutos e só pode ser usado uma vez).</p>"
            "<p>Se você não pediu a redefinição, ignore este e-mail — sua senha "
            "continua a mesma. A Nexa nunca pede sua senha por e-mail.</p>"
        ),
    )


def _send_verification_email(email: str, token: str) -> None:
    from app.core.notifications.email_sender import send_email

    link = _frontend_url(f"/verify-email?token={token}")
    send_email(
        to=email,
        subject="Nexa — confirme seu e-mail",
        html_body=(
            "<p>Bem-vindo(a) à Nexa! Confirme seu e-mail para proteger sua conta:</p>"
            f'<p><a href="{link}">Confirmar meu e-mail</a> (o link vale por 48 horas).</p>'
            "<p>Se você não criou uma conta na Nexa, ignore este e-mail.</p>"
        ),
    )

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

    # Dispara verificação de e-mail (best-effort — nunca bloqueia o cadastro)
    try:
        from app.core.account_tokens import PURPOSE_EMAIL_VERIFY, issue_token
        _send_verification_email(user.email, issue_token(new_user["user_id"], PURPOSE_EMAIL_VERIFY))
    except Exception:
        pass

    return {"message": "Usuário criado com sucesso", "user_id": new_user["user_id"]}


@router.post("/token", response_model=Token)
@limiter.limit("10/minute")
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)

    # Segunda camada, POR CONTA. O @limiter acima é por IP e não segura
    # credential stuffing distribuído: mil IPs testando dez senhas por minuto
    # na mesma conta passam inteiros por baixo dele. Ver core/login_throttle.py
    # — a contagem é pelo e-mail SUBMETIDO, exista ele ou não, para o bloqueio
    # não virar oráculo de existência de conta.
    from app.core import login_throttle

    if login_throttle.esta_bloqueada(form_data.username):
        audit.log_login_failure(
            email=form_data.username, ip=ip, reason="account_throttled", request_id=req_id
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Muitas tentativas de login. Aguarde alguns minutos ou "
                "redefina sua senha."
            ),
        )

    user = get_user_by_email(db, form_data.username)
    if not user:
        # Executa verify_password com hash fictício para equalizar tempo de resposta.
        # Sem isso, o tempo de retorno quando o email não existe é visivelmente menor,
        # permitindo enumeração de usuários cadastrados (timing attack).
        verify_password(form_data.password, _DUMMY_HASH)
        login_throttle.registrar_falha(form_data.username)
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
        login_throttle.registrar_falha(form_data.username)
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

    login_throttle.limpar(form_data.username)
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

    # O corte de sessão vale para o refresh também — e aqui é onde mais importa:
    # o refresh vive 14 dias, contra 30 min do access. Trocar a senha sem isto
    # derrubaria a sessão por meia hora e a devolveria no próximo refresh.
    from app.core.security import sessao_invalidada

    if sessao_invalidada(token_data.iat, user.get("sessions_valid_from")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão encerrada. Faça login novamente.",
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


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Inicia o fluxo "esqueci minha senha".

    Anti-enumeração: a resposta é SEMPRE 202 com a mesma mensagem, exista ou
    não a conta — quem pergunta não descobre quais e-mails estão cadastrados.
    O e-mail com o link (token de uso único, 60min) só é enviado se a conta
    existir.
    """
    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)

    user = get_user_by_email(db, body.email)
    if user:
        try:
            from app.core.account_tokens import PURPOSE_PASSWORD_RESET, issue_token

            _send_reset_email(body.email, issue_token(user["user_id"], PURPOSE_PASSWORD_RESET))
            audit.log_password_reset_requested(
                user_id=user["user_id"], ip=ip, request_id=req_id
            )
        except Exception:
            logger_auth.exception("forgot-password: envio falhou (resposta segue 202)")

    return {"message": "Se o e-mail estiver cadastrado, enviamos as instruções de redefinição."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Conclui o reset: valida o token (uso único, 60min) e troca a senha.
    Token inválido/expirado/reusado → 400 genérico (sem oráculo de estado).
    """
    if len(body.new_password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A nova senha precisa de pelo menos {_MIN_PASSWORD_LEN} caracteres.",
        )

    from app.core.account_tokens import PURPOSE_PASSWORD_RESET, consume_token

    user_id = consume_token(body.token, PURPOSE_PASSWORD_RESET)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link inválido ou expirado. Solicite uma nova redefinição.",
        )

    from app.core.db.users import update_user_password

    if not update_user_password(db, user_id, get_password_hash(body.new_password)):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar a senha. Tente novamente.",
        )

    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)
    audit.log_password_reset_completed(user_id=user_id, ip=ip, request_id=req_id)

    return {"message": "Senha redefinida com sucesso. Faça login com a nova senha."}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    """Confirma o e-mail do usuário via token de uso único (48h)."""
    from app.core.account_tokens import PURPOSE_EMAIL_VERIFY, consume_token

    user_id = consume_token(body.token, PURPOSE_EMAIL_VERIFY)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link inválido ou expirado. Peça um novo e-mail de confirmação.",
        )

    from app.core.db.users import mark_email_verified

    mark_email_verified(db, user_id)

    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)
    audit.log_email_verified(user_id=user_id, ip=ip, request_id=req_id)

    return {"message": "E-mail confirmado com sucesso."}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,
    body: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    """Reenvia o e-mail de confirmação. Sempre 202 (anti-enumeração)."""
    user = get_user_by_email(db, body.email)
    if user:
        try:
            from app.core.account_tokens import PURPOSE_EMAIL_VERIFY, issue_token

            _send_verification_email(body.email, issue_token(user["user_id"], PURPOSE_EMAIL_VERIFY))
        except Exception:
            logger_auth.exception("resend-verification: envio falhou (resposta segue 202)")

    return {"message": "Se o e-mail estiver cadastrado, enviamos um novo link de confirmação."}


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_devices(
    request: Request,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Encerra TODAS as sessões do usuário, em todo dispositivo.

    Diferente de `/logout`, que revoga só o token da requisição pelo `jti`:
    aqui o corte é `users.sessions_valid_from`, e todo token já emitido —
    access e refresh, deste e de qualquer outro aparelho — passa a ser
    recusado por `security.sessao_invalidada`.

    Duas propriedades que o logout comum não tem:
      * alcança o REFRESH, que vive 14 dias (o access morre em 30 min sozinho);
      * vive no banco, então NÃO tem fail-open — a blacklist por `jti` depende
        do Redis e aceita tokens revogados enquanto ele estiver fora.

    É o mesmo mecanismo que o reset de senha aciona. Aqui ele fica disponível
    sem exigir troca de senha: quem perdeu o celular não precisa mudar a senha
    para expulsar o aparelho.
    """
    from app.core.db.users import encerrar_sessoes

    if not encerrar_sessoes(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível encerrar as sessões. Tente novamente.",
        )

    ip = request.client.host if request.client else "unknown"
    req_id = getattr(request.state, "request_id", None)
    audit.log_logout(user_id=current_user, ip=ip, request_id=req_id)


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
