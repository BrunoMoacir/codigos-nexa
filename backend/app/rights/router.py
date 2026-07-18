"""
app/rights/router.py — T3: Monitor de Direitos Esquecidos

GET  /api/v1/rights/{user_id}                — visão geral (4 fontes + capacidades)
GET  /api/v1/rights/{user_id}/svr/captcha    — desafio oficial do BACEN (consulta assistida)
POST /api/v1/rights/{user_id}/svr/check      — consulta REAL na API pública do SVR
POST /api/v1/rights/{user_id}/ir/check       — consulta REAL da restituição (e-CAC + SERPRO)

Consultas reais usam exclusivamente canais oficiais: a consulta pública do SVR
(com captcha resolvido pelo próprio usuário) e a API Consulta Restituição do
SERPRO (mediante autorização do titular no e-CAC). CPF e data de nascimento
não são persistidos; logs registram apenas CPF mascarado (LGPD).
"""

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_owner
from app.rights.models import (
    ForgottenRight,
    IrCheckIn,
    IrCheckOut,
    RightsResponse,
    SvrCaptchaOut,
    SvrCheckIn,
    SvrCheckOut,
)
from app.rights.connectors.serpro_restituicao import (
    SerproIndisponivel,
    SerproNaoConfigurado,
    SerproRestituicaoConnector,
    SerproTokenAutorizacaoInvalido,
)
from app.rights.connectors.svr_public import (
    SvrCaptchaInvalido,
    SvrIndisponivel,
    SvrPublicConnector,
)
from app.rights.services.svr_bacen_client import SvrBacenClient
from app.rights.services.fgts_checker import FgtsChecker
from app.rights.services.pis_pasep_checker import PisPasepChecker
from app.rights.services.ir_restituicao_checker import IrRestituicaoChecker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rights", tags=["Rights (T3 — Direitos Esquecidos)"])

_svr = SvrBacenClient()
_fgts = FgtsChecker()
_pis = PisPasepChecker()
_ir = IrRestituicaoChecker()
_svr_public = SvrPublicConnector()
_serpro = SerproRestituicaoConnector()

_DISCLAIMER = (
    "Consultas reais são feitas apenas em canais oficiais: consulta pública do "
    "SVR/BACEN (com o desafio de segurança respondido por você) e API Consulta "
    "Restituição do SERPRO (mediante autorização gerada por você no e-CAC). "
    "Estimativas heurísticas são baseadas em transações e só podem ser "
    "confirmadas nos canais oficiais. A Nexa nunca pede sua senha GOV.BR e não "
    "armazena CPF ou data de nascimento usados nas consultas."
)

_SVR_POSITIVE_STEPS = [
    "Há valores em seu nome! Acesse valoresareceber.bcb.gov.br com sua conta GOV.BR (prata ou ouro) para ver o montante.",
    "Solicite o resgate via Pix — o banco tem até 12 dias úteis para pagar.",
    "⚠️ A Nexa nunca pede sua senha GOV.BR. O resgate só acontece no portal oficial.",
]

_SVR_NEGATIVE_STEPS = [
    "Nenhum valor disponível hoje — o SVR é atualizado periodicamente pelo BACEN.",
    "Vale reconsultar a cada 2–3 meses; a Nexa vai lembrar você.",
]

_IR_ECAC_STEPS = [
    "Acesse o Portal e-CAC (cav.receita.fazenda.gov.br) com sua conta GOV.BR.",
    "Abra 'Compartilha Receita Federal' e gere uma Autorização de Compartilhamento para a API Consulta Restituição.",
    "Cole o token gerado aqui na Nexa para vermos sua restituição em tempo real.",
]


@router.get("/{user_id}", response_model=RightsResponse)
def get_forgotten_rights(
    user_id: str = Depends(require_owner),
) -> RightsResponse:
    """
    **Monitor de Direitos Esquecidos (T3)**

    Verifica 4 fontes de direitos financeiros que podem estar esquecidos:

    | Fonte | O que verifica |
    |-------|---------------|
    | **SVR BACEN** | Saldos em contas encerradas, cheques não sacados, tarifas restituíveis |
    | **FGTS** | Saldo de contas de empregos anteriores (inclusive empresas extintas) |
    | **PIS/PASEP** | Cotas pré-1988 e abono salarial do ano-base |
    | **IR Restituição** | IRRF retido acima do devido, deduções esquecidas |

    **Importante:** nenhuma API privada ou área autenticada é consultada.
    Toda verificação real é feita pelo usuário nos canais oficiais indicados.
    """
    rights: list[ForgottenRight] = []
    context_note: str | None = None

    checkers = [
        ("svr_bacen", _svr),
        ("fgts", _fgts),
        ("pis_pasep", _pis),
        ("ir_restituicao", _ir),
    ]
    for name, checker in checkers:
        try:
            right = checker.check(user_id)
            _annotate_capability(right)
            rights.append(right)
        except Exception as exc:
            logger.error("[rights] checker=%s user=%s: %s", name, user_id, exc)

    # Soma apenas estimativas com confiança medium ou high
    recoverable = sum(
        r.estimated_amount
        for r in rights
        if r.estimated_amount and r.estimated_confidence in ("high", "medium")
    )

    # Contexto adicional de ganhos já identificados pelo Negociador
    negotiation_gain = _get_negotiation_gain(user_id)
    if negotiation_gain > 0:
        context_note = (
            f"O Negociador Nexa já identificou R$ {negotiation_gain:,.2f} em ganhos potenciais "
            "com seus bancos atuais. Combine com os direitos esquecidos acima para maximizar sua recuperação."
        )

    logger.info(
        "[rights] user=%s rights=%d estimated_recoverable=%.2f",
        user_id, len(rights), recoverable,
    )

    return RightsResponse(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc),
        rights=rights,
        total_estimated_recoverable=round(recoverable, 2),
        disclaimer=_DISCLAIMER,
        context_note=context_note,
    )


def _annotate_capability(right: ForgottenRight) -> None:
    """Marca como a Nexa consegue verificar cada fonte (real vs orientativo)."""
    if right.category == "svr_bacen":
        right.capability = "assisted_real"
        right.check_endpoint = "/api/v1/rights/{user_id}/svr/check"
    elif right.category == "ir_restituicao" and _serpro.is_configured:
        right.capability = "authorized_real"
        right.check_endpoint = "/api/v1/rights/{user_id}/ir/check"
    else:
        right.capability = "guided"


# ── Consulta assistida SVR — API pública oficial do BACEN ──────────────────


@router.get("/{user_id}/svr/captcha", response_model=SvrCaptchaOut)
def get_svr_captcha(user_id: str = Depends(require_owner)) -> SvrCaptchaOut:
    """
    **Etapa 1 da consulta assistida do SVR.**

    Retorna o desafio de segurança oficial do BACEN (imagem base64) para o
    usuário responder no app. A resposta digitada vai em `POST /svr/check`.
    """
    try:
        captcha = _svr_public.get_captcha()
    except SvrIndisponivel as exc:
        logger.warning("[rights] svr captcha indisponível: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Consulta pública do SVR indisponível no momento. Tente novamente em instantes.",
        )
    return SvrCaptchaOut(
        imagem_base64=captcha.imagem_base64,
        hash=captcha.hash,
        audio_base64=captcha.audio_base64,
        instrucao="Digite os caracteres da imagem — desafio de segurança oficial do BACEN.",
    )


@router.post("/{user_id}/svr/check", response_model=SvrCheckOut)
def check_svr(
    body: SvrCheckIn,
    user_id: str = Depends(require_owner),
) -> SvrCheckOut:
    """
    **Etapa 2 — consulta REAL na consulta pública do SVR/BACEN.**

    Responde se existe valor a receber para o CPF informado (o montante e o
    resgate são feitos pelo usuário no portal oficial, com login GOV.BR).
    CPF e data de nascimento não são persistidos.
    """
    try:
        nascimento = date.fromisoformat(body.data_nascimento)
    except ValueError:
        raise HTTPException(status_code=422, detail="data_nascimento deve ser YYYY-MM-DD.")

    try:
        resultado = _svr_public.consultar(
            cpf=body.cpf,
            data_nascimento=nascimento,
            captcha_hash=body.captcha_hash,
            captcha_resposta=body.captcha_resposta,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="CPF inválido.")
    except SvrCaptchaInvalido:
        raise HTTPException(
            status_code=412,
            detail="Resposta do desafio incorreta ou expirada. Gere um novo captcha e tente de novo.",
        )
    except SvrIndisponivel as exc:
        logger.warning("[rights] svr check indisponível user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Consulta pública do SVR indisponível no momento. Tente novamente em instantes.",
        )

    return SvrCheckOut(
        tem_valor_a_receber=resultado.tem_valor_a_receber,
        consultado_em_nome_de=resultado.consultado_em_nome_de,
        proximos_passos=(
            _SVR_POSITIVE_STEPS if resultado.tem_valor_a_receber else _SVR_NEGATIVE_STEPS
        ),
    )


# ── Consulta autorizada da restituição IRPF — e-CAC + SERPRO ───────────────


@router.post("/{user_id}/ir/check", response_model=IrCheckOut)
def check_ir_restituicao(
    body: IrCheckIn,
    user_id: str = Depends(require_owner),
) -> IrCheckOut:
    """
    **Consulta REAL da restituição de IRPF** via API oficial do SERPRO,
    usando o token de Autorização de Compartilhamento que o próprio usuário
    gera no Portal e-CAC. Sem credenciais SERPRO configuradas, retorna o
    passo a passo de habilitação em vez de erro.
    """
    if not _serpro.is_configured:
        return IrCheckOut(
            status="nao_configurado",
            detalhe=(
                "A consulta em tempo real ainda não está habilitada neste ambiente. "
                "Você pode verificar sua restituição diretamente no app Meu Imposto de Renda."
            ),
            proximos_passos=_IR_ECAC_STEPS,
        )

    try:
        resultado = _serpro.consultar(body.token_compartilhamento)
    except SerproTokenAutorizacaoInvalido as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SerproNaoConfigurado as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SerproIndisponivel as exc:
        logger.warning("[rights] serpro indisponível user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=503,
            detail="API do SERPRO indisponível no momento. Tente novamente em instantes.",
        )

    if not resultado.encontrada:
        return IrCheckOut(
            status="sem_restituicao",
            detalhe=resultado.detalhe,
            proximos_passos=[
                "Nenhuma restituição disponível no exercício atual.",
                "Se declarou há pouco tempo, o lote pode ainda não ter sido liberado — reconsulte no próximo lote.",
            ],
        )

    passos = ["Confirme os dados no app Meu Imposto de Renda (Receita Federal)."]
    if resultado.situacao_codigo == "04":
        passos.insert(0, "Sua restituição foi devolvida ao Tesouro — reagende o crédito no Portal BB (bb.com.br/irpf).")
    elif resultado.situacao_codigo == "02":
        passos.insert(0, "Você está na fila de restituição — o crédito sai automaticamente no banco indicado.")

    return IrCheckOut(
        status="encontrada",
        valor=resultado.valor,
        situacao_codigo=resultado.situacao_codigo,
        situacao_descricao=resultado.situacao_descricao,
        banco_codigo=resultado.banco_codigo,
        titular_cpf_mascarado=resultado.titular_cpf_mascarado,
        campos_nao_decriptados=resultado.campos_nao_decriptados,
        detalhe=resultado.detalhe,
        aviso_legal=resultado.aviso_legal,
        proximos_passos=passos,
    )


def _get_negotiation_gain(user_id: str) -> float:
    try:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT COALESCE(SUM(potential_gain), 0)"
                    " FROM negotiation_history WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).fetchone()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0
