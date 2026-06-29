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


class RightsResponse(BaseModel):
    user_id: str
    generated_at: datetime
    rights: list[ForgottenRight]
    total_estimated_recoverable: float
    disclaimer: str
    context_note: Optional[str] = None
