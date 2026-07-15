"""
app/viral/models.py — V1/V2: Viral & Wrapped
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

AmountType = Literal["estimated_potential", "actual_fee", "realized_saving"]

DISCLAIMER_SAVINGS = (
    "Potencial estimado. Os valores dependem das condições do mercado e "
    "das ações do usuário. Não constitui garantia de economia."
)
DISCLAIMER_WRAPPED = (
    "Tarifas: valores efetivamente cobrados. "
    "Savings: estimativas de potencial — não garantidas."
)

CALCULATION_VERSION = "2.0"


class SavingsSource(BaseModel):
    name: str
    module: str
    annual_savings_brl: float
    description: str
    amount_type: AmountType = "estimated_potential"
    reference_period_start: Optional[date] = None
    reference_period_end: Optional[date] = None


class SavingsCard(BaseModel):
    user_id: str
    generated_at: datetime
    total_annual_savings_brl: float
    sources: list[SavingsSource]
    months_active: int
    tagline: str
    calculation_version: str = CALCULATION_VERSION
    disclaimer: str = DISCLAIMER_SAVINGS
    expires_at: Optional[datetime] = None


class WrappedHighlight(BaseModel):
    category: str
    title: str
    value_formatted: str
    description: str
    amount_type: AmountType = "estimated_potential"


class WrappedReport(BaseModel):
    user_id: str
    year: int
    generated_at: datetime
    highlights: list[WrappedHighlight]
    total_fees_paid_year: float
    total_savings_identified: float
    score_start: Optional[int] = None
    score_end: Optional[int] = None
    score_delta: Optional[int] = None
    badges_earned: list[str] = []
    summary_tagline: str
    calculation_version: str = CALCULATION_VERSION
    disclaimer: str = DISCLAIMER_WRAPPED
    is_partial_year: bool = False


class ShareEvent(BaseModel):
    user_id: str
    card_type: Literal["savings_card", "wrapped"]
    channel: str
    card_version: str = CALCULATION_VERSION
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None


class ShareResponse(BaseModel):
    share_id: str
    share_url: Optional[str] = None
    utm_link: Optional[str] = None
