# app/api/v1/routes/context_override.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Literal, Optional
from sqlalchemy.orm import Session
import logging

from app.core.db.queries import save_context_override, get_context_overrides, get_override_stats
from app.core.database import get_db
from app.core.security import require_owner

router = APIRouter(prefix="/context", tags=["Context Override"])
logger = logging.getLogger(__name__)

# --- Schemas ---

class ContextOverrideRequest(BaseModel):
    transaction_id: str
    corrected_context: Literal["PF", "PJ"]
    reason: Optional[str] = None
    original_context: Optional[str] = None # Opcional, frontend pode mandar se souber

class ContextOverrideResponse(BaseModel):
    success: bool
    transaction_id: str
    corrected_context: str
    message: str

class OverrideItem(BaseModel):
    transaction_id: str
    original_context: Optional[str]
    corrected_context: str
    reason: Optional[str]
    created_at: str # Simplificado como str para JSON

# --- Endpoints ---

@router.post("/override", response_model=ContextOverrideResponse)
def override_transaction_context(
    request: ContextOverrideRequest,
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
):
    logger.info("Recebido override user=%s txn=%s -> %s", user_id, request.transaction_id, request.corrected_context)
    
    try:
        success = save_context_override(
            db=db,
            user_id=user_id,
            transaction_id=request.transaction_id,
            corrected_context=request.corrected_context,
            original_context=request.original_context,
            reason=request.reason
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Erro ao salvar override no banco de dados.")

        return ContextOverrideResponse(
            success=True,
            transaction_id=request.transaction_id,
            corrected_context=request.corrected_context,
            message="Classificação corrigida com sucesso"
        )
        
    except Exception as e:
        logger.error("Erro no endpoint override user=%s txn=%s: %s", user_id, request.transaction_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao salvar classificação.")

@router.get("/overrides", response_model=List[OverrideItem])
def list_user_overrides(
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """
    Lista histórico de correções manuais do usuário.
    """
    try:
        overrides_data = get_context_overrides(db, user_id)
        
        # Converter datetime para string se necessário (Pydantic faz auto, mas explicito é bom)
        results = []
        for x in overrides_data:
            results.append(OverrideItem(
                transaction_id=x['transaction_id'],
                original_context=x['original_context'],
                corrected_context=x['corrected_context'],
                reason=x['reason'],
                created_at=str(x['created_at'])
            ))
            
        return results
        
    except Exception as e:
        logger.error("Erro ao listar overrides: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao buscar histórico.")

@router.get("/overrides/stats")
def get_stats(
    user_id: str = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """
    Retorna contagem de overrides (ex: {"PF": 5, "PJ": 2}).
    """
    try:
        return get_override_stats(db, user_id)
    except Exception as e:
        logger.error("Erro ao obter stats: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao calcular estatísticas.")
