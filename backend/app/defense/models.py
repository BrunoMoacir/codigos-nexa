"""
app/defense/models.py — Schemas para Defesa do Consumidor (D1–D5)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel


Severity = Literal["high", "medium", "low"]
Detector = Literal["D1", "D2", "D3", "D4"]
CorrectionIndex = Literal["IPCA", "SELIC", "INPC"]


class DefenseFinding(BaseModel):
    detector: Detector
    severity: Severity
    bank_name: str
    title: str
    description: str
    amount_disputed: float          # valor contestável (R$)
    legal_basis: str                # resolução / lei aplicável
    recommended_action: str
    evidence_points: list[str]      # dados concretos que sustentam a contestação


class MonetaryCorrection(BaseModel):
    original_value: float
    charge_date: date
    reference_date: date
    index: CorrectionIndex
    correction_factor: float        # ex: 1.0512 para 5.12% de correção
    corrected_value: float
    correction_brl: float           # quanto a mais em R$


class EvidenceDossier(BaseModel):
    user_id: str
    generated_at: datetime
    findings: list[DefenseFinding]
    total_findings: int
    total_disputed_amount: float
    monetary_correction: Optional[MonetaryCorrection] = None
    contestation_letter: str        # carta preenchida (D2)
    procon_narrative: str           # relato para o PROCON (D5)
    jec_petition: str               # petição inicial simplificada (D5)


class DefenseResponse(BaseModel):
    user_id: str
    generated_at: datetime
    findings: list[DefenseFinding]
    total_findings: int
    high_severity: int
    medium_severity: int
    low_severity: int
    total_disputed_amount: float
    summary: str
