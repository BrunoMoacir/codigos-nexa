"""
app/defense/models.py — Schemas para Defesa do Consumidor (D1–D6)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


Severity       = Literal["high", "medium", "low", "info"]
Detector       = Literal["D1", "D2", "D3", "D4", "D5", "D6"]
CorrectionIndex = Literal["IPCA", "SELIC", "INPC"]
FindingStatus  = Literal["pending", "confirmed", "dismissed", "resolved"]
EvidenceSource = Literal["transactions", "fee_history", "negotiation_history", "olinda", "bacen_sgs", "manual"]


class DefenseFinding(BaseModel):
    detector:           Detector
    severity:           Severity
    bank_name:          str
    title:              str
    description:        str
    amount_disputed:    float                       # valor contestável estimado (R$)
    legal_basis:        str                         # norma / jurisprudência aplicável
    recommended_action: str
    evidence_points:    list[str]

    # Campos opcionais adicionados v2
    confidence:         float         = Field(default=0.8, ge=0.0, le=1.0)
    status:             FindingStatus = "pending"   # pending até confirmação do usuário
    evidence_source:    EvidenceSource = "transactions"
    requires_user_confirmation: bool  = False       # D1 exige confirmação antes de doc formal
    legal_review_level: Literal["auto", "review_recommended", "review_required"] = "auto"
    estimated_vs_claimed: Optional[str] = None      # "estimativa" ou "valor exato"


class MonetaryCorrection(BaseModel):
    original_value:   float
    charge_date:      date
    reference_date:   date
    index:            CorrectionIndex
    correction_factor: float
    corrected_value:  float
    correction_brl:   float
    monthly_rates_used: int = 0     # quantos meses foram acumulados (IPCA/INPC mensal)


class EvidenceDossier(BaseModel):
    user_id:                str
    generated_at:           datetime
    findings:               list[DefenseFinding]
    total_findings:         int
    total_disputed_amount:  float
    monetary_correction:    Optional[MonetaryCorrection] = None
    contestation_letter:    str
    procon_narrative:       str
    jec_petition:           str
    disclaimer:             str = (
        "AVISO LEGAL: Este documento foi gerado automaticamente pela Nexa AI com base "
        "em dados financeiros do usuário e fontes públicas do Banco Central do Brasil. "
        "As informações constituem indícios educacionais e organizacionais, NÃO constituindo "
        "parecer jurídico ou garantia de resultado. Recomenda-se consulta a advogado "
        "especializado antes de protocolar qualquer documento judicial."
    )


class DefenseResponse(BaseModel):
    user_id:               str
    generated_at:          datetime
    findings:              list[DefenseFinding]
    total_findings:        int
    high_severity:         int
    medium_severity:       int
    low_severity:          int
    total_disputed_amount: float
    summary:               str
    disclaimer:            str = (
        "Os valores apresentados são estimativas educacionais baseadas em indícios. "
        "Não constituem garantia de recuperação judicial ou extrajudicial."
    )


class PortabilitySimulationRequest(BaseModel):
    """Dados mínimos para simular uma proposta de portabilidade."""

    balance: float = Field(gt=0, description="Saldo devedor atual em reais.")
    current_monthly_rate: float = Field(
        gt=0, le=1, description="Taxa mensal atual em formato decimal."
    )
    target_monthly_rate: float = Field(
        gt=0, le=1, description="Taxa mensal proposta em formato decimal."
    )
    remaining_months: int = Field(ge=1, le=360)
    current_payment: Optional[float] = Field(default=None, gt=0)


class PortabilitySimulationResponse(BaseModel):
    """Resultado educacional, sem solicitação ou execução de portabilidade."""

    balance: float
    remaining_months: int
    current_monthly_rate: float
    target_monthly_rate: float
    current_payment: float
    target_payment: float
    current_total_cost: float
    target_total_cost: float
    estimated_savings: float
    status: Literal["ADVANTAGEOUS", "NO_ADVANTAGE", "INVALID_TARGET"]
    recommendation: str
    disclaimer: str
