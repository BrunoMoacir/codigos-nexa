"""
app/rights/models.py — T3: Monitor de Direitos Esquecidos

Modelos Pydantic para o módulo de direitos financeiros.
Todos os valores são estimativas baseadas em transações; verificação real
é feita pelo usuário nos canais oficiais.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


RightsCategory = Literal["svr_bacen", "fgts", "pis_pasep", "ir_restituicao"]
Confidence = Literal["high", "medium", "low", "unknown"]

# Como a Nexa consegue verificar cada fonte:
#   assisted_real   — consulta real na API pública oficial, com o usuário
#                     resolvendo o captcha oficial dentro do app (SVR)
#   authorized_real — consulta real via API oficial mediante autorização do
#                     titular (restituição IRPF via e-CAC + SERPRO)
#   guided          — sem API para terceiros; roteiro orientativo (FGTS, PIS)
Capability = Literal["assisted_real", "authorized_real", "guided"]


class ForgottenRight(BaseModel):
    category: RightsCategory
    title: str
    description: str
    estimated_amount: Optional[float] = None
    estimated_confidence: Confidence = "unknown"
    relevance_reason: str
    official_channel: str
    official_url: str
    action_steps: list[str]
    warning: Optional[str] = None
    capability: Capability = "guided"
    check_endpoint: Optional[str] = None


# ── Consulta assistida SVR (captcha oficial resolvido pelo usuário) ────────


class SvrCaptchaOut(BaseModel):
    imagem_base64: str
    hash: str
    audio_base64: Optional[str] = None
    instrucao: str


class SvrCheckIn(BaseModel):
    cpf: str
    data_nascimento: str  # YYYY-MM-DD
    captcha_hash: str
    captcha_resposta: str


class SvrCheckOut(BaseModel):
    tem_valor_a_receber: bool
    consultado_em_nome_de: str  # CPF mascarado
    fonte: str = "Consulta pública oficial do SVR/BACEN"
    proximos_passos: list[str]


# ── Consulta autorizada de restituição IRPF (e-CAC + SERPRO) ───────────────


class IrCheckIn(BaseModel):
    token_compartilhamento: str


class IrCheckOut(BaseModel):
    status: Literal["encontrada", "sem_restituicao", "nao_configurado"]
    valor: Optional[float] = None
    situacao_codigo: Optional[str] = None
    situacao_descricao: Optional[str] = None
    banco_codigo: Optional[str] = None
    titular_cpf_mascarado: Optional[str] = None
    campos_nao_decriptados: bool = False
    detalhe: Optional[str] = None
    aviso_legal: Optional[str] = None
    proximos_passos: list[str] = []


class RightsResponse(BaseModel):
    user_id: str
    generated_at: datetime
    rights: list[ForgottenRight]
    total_estimated_recoverable: float
    disclaimer: str
    context_note: Optional[str] = None
