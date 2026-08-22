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


class SinalDeRelevancia(BaseModel):
    """
    Número heurístico com o rótulo do que ele REALMENTE mede.

    Existe porque a heurística é útil — saber que há R$ 9.900 de IRRF no ano
    muda a prioridade de olhar a restituição — mas o número não é dinheiro a
    receber, e antes era publicado como se fosse. `estimated_amount` somava
    depósito de FGTS de emprego ativo, um valor de abono que era constante e
    o IRRF retido, e o total virava `total_estimated_recoverable`.

    Aqui o valor vem sempre acompanhado do que ele é (`rotulo`) e de como foi
    obtido (`base`), e nunca entra em soma de valor recuperável.
    """

    valor: Optional[float] = None
    rotulo: str
    base: str
    nao_e_valor_a_receber: bool = True


class ForgottenRight(BaseModel):
    category: RightsCategory
    title: str
    description: str
    #: Valor obtido em CONSULTA REAL (hoje, só a restituição via SERPRO).
    #: Heurística nunca preenche este campo — vai em `sinal`.
    estimated_amount: Optional[float] = None
    estimated_confidence: Confidence = "unknown"
    sinal: Optional[SinalDeRelevancia] = None
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
    """
    A varredura automática NUNCA soma valor a receber.

    É a mesma regra que `app/fiscal/rights_monitor` já seguia e que
    `tests/fiscal/test_rights_monitor.py` já exigia (`estimated_amount` sempre
    0.0) — os dois endpoints da mesma funcionalidade tinham políticas opostas
    sobre a mesma pergunta, e este aqui, que é a porta de entrada, era o
    permissivo. Agora vale uma regra só.
    """

    user_id: str
    generated_at: datetime
    rights: list[ForgottenRight]
    #: Soma apenas de valores CONFIRMADOS em consulta real. Numa varredura
    #: automática, que não faz consulta nenhuma, é sempre 0.0.
    total_estimated_recoverable: float
    disclaimer: str
    context_note: Optional[str] = None
