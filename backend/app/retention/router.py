from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/retention", tags=["Retention"])

class CancellationImpact(BaseModel):
    user_id: str
    total_saved_brl: float
    pending_alerts_count: int
    message: str

class PauseAccountRequest(BaseModel):
    user_id: str
    reason: str

class PauseAccountResponse(BaseModel):
    user_id: str
    status: str
    message: str

@router.get("/cancellation-impact/{user_id}", response_model=CancellationImpact)
async def get_cancellation_impact(user_id: str):
    """
    R5.a - Calcula o impacto de cancelar a assinatura.
    Mostra o quanto o usuario economizou e quantos alertas ele vai perder.
    """
    # Mock do calculo do impacto (em producao, viria do banco de dados)
    saved = hash(user_id + "save") % 5000 + 150.0
    alerts = hash(user_id + "alert") % 10 + 2
    
    return CancellationImpact(
        user_id=user_id,
        total_saved_brl=round(saved, 2),
        pending_alerts_count=alerts,
        message=f"Você já economizou R$ {saved:.2f} com o Nexa. Se cancelar agora, perderá {alerts} oportunidades pendentes no Radar!"
    )

@router.post("/pause-account", response_model=PauseAccountResponse)
async def pause_account(req: PauseAccountRequest):
    """
    R5.b - Pausa a conta (downgrade gracioso).
    Congela cobrancas e sincronizacao do Open Finance, deixando a conta READ_ONLY.
    """
    if not req.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
        
    # Mock da lógica de pause na base de dados
    # Em produção chamaria os servicos de Billing (Stripe) e Open Finance (Pluggy) para pausar
    
    return PauseAccountResponse(
        user_id=req.user_id,
        status="PAUSED",
        message=f"A conta do usuário {req.user_id} foi pausada com sucesso. Motivo: {req.reason}"
    )
