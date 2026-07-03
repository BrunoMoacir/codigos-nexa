from typing import Optional, Literal
from pydantic import BaseModel
from datetime import datetime

RightSource = Literal["SVR_BACEN", "FGTS", "PIS_PASEP", "IR_RESTITUTION", "B3_DIVIDENDS"]
RightStatus = Literal["AVAILABLE", "PENDING_VERIFICATION", "NOT_FOUND", "ERROR"]

class ForgottenRightCandidate(BaseModel):
    source: RightSource
    status: RightStatus
    estimated_amount: float
    description: str
    action_url: Optional[str] = None
    last_checked_at: datetime
    error_message: Optional[str] = None

class ForgottenRightsReport(BaseModel):
    user_id: str
    total_estimated_amount: float
    candidates: list[ForgottenRightCandidate]
    generated_at: datetime
