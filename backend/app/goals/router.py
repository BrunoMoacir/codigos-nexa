# app/api/v1/routes/goals.py
# MX.2 — Sistema de Metas Financeiras

"""
Endpoints para gerenciar metas financeiras:

    POST   /goals/{user_id}              Criar nova meta
    GET    /goals/{user_id}              Listar metas do usuário
    GET    /goals/{user_id}/{goal_id}    Detalhe de uma meta + projeção
    PATCH  /goals/{user_id}/{goal_id}/progress   Atualizar progresso
    DELETE /goals/{user_id}/{goal_id}    Abandonar meta
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from app.core.security import get_current_user, validate_user_id
from app.core.database import get_db
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/goals", tags=["Metas Financeiras (MX.2)"])


# ── Schemas de request ────────────────────────────────────────────────────────

GOAL_TYPES = Literal["imovel", "viagem", "carro", "educacao", "emergencia", "outros"]


class CreateGoalRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Nome da meta")
    goal_type: GOAL_TYPES = Field(default="outros", description="Tipo da meta")
    target_amount: float = Field(..., gt=0, description="Valor alvo em R$")
    current_amount: float = Field(default=0.0, ge=0.0, description="Valor já acumulado em R$")
    target_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Data alvo no formato YYYY-MM-DD (opcional)",
    )

    @model_validator(mode="after")
    def validate_target_date(self):
        if self.target_date:
            from datetime import date
            try:
                d = date.fromisoformat(self.target_date)
            except ValueError:
                raise ValueError("target_date inválida")
            if d <= date.today():
                raise ValueError("target_date deve ser uma data futura")
        return self


class UpdateProgressRequest(BaseModel):
    amount_to_add: float = Field(..., gt=0, description="Valor a adicionar em R$")
    monthly_actual: Optional[float] = Field(
        default=None, ge=0.0,
        description="Contribuição mensal atual detectada nas transações (opcional)",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

# Todos os endpoints usam `def` (síncrono) porque GoalTracker executa I/O
# síncrono via psycopg2. FastAPI roda `def` endpoints em thread pool
# automaticamente, evitando bloqueio do event loop do uvicorn.

@router.post("/{user_id}", status_code=201)
def create_goal(
    user_id: str,
    body: CreateGoalRequest,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    MX.2 — Cria uma nova meta financeira para o usuário.

    Calcula automaticamente a contribuição mensal necessária baseada
    no valor restante e na data alvo.
    """
    validate_user_id(user_id)
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    from app.goals.tracker import GoalTracker
    try:
        goal = GoalTracker(db).create_goal(
            user_id=user_id,
            name=body.name,
            goal_type=body.goal_type,
            target_amount=body.target_amount,
            current_amount=body.current_amount,
            target_date=body.target_date,
        )
        return goal.to_dict()
    except Exception as e:
        logger.error(f"[Goals] Erro ao criar meta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao criar meta financeira.")


@router.get("/{user_id}")
def list_goals(
    user_id: str,
    status: str = Query(default="ACTIVE", description="Status: ACTIVE | COMPLETED | ABANDONED"),
    limit: int = Query(default=50, ge=1, le=200, description="Máximo de metas retornadas"),
    offset: int = Query(default=0, ge=0, description="Número de metas a pular (paginação)"),
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    MX.2 — Lista as metas do usuário filtradas por status, com projeções.

    Suporta paginação via `limit` e `offset`.
    """
    validate_user_id(user_id)
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    from app.goals.tracker import GoalTracker
    tracker = GoalTracker(db)
    goals = tracker.list_goals(user_id=user_id, status=status, limit=limit, offset=offset)
    return {
        "user_id": user_id,
        "status_filter": status,
        "limit": limit,
        "offset": offset,
        "total": len(goals),
        "goals": [
            {
                **g.to_dict(),
                "projection": tracker.get_projection(g).to_dict(),
            }
            for g in goals
        ],
    }


@router.get("/{user_id}/{goal_id}")
def get_goal(user_id: str, goal_id: str, _: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    MX.2 — Detalhe de uma meta com projeção completa.
    """
    from app.goals.tracker import GoalTracker
    tracker = GoalTracker(db)
    try:
        goal = tracker._load(goal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Meta {goal_id} não encontrada.")

    if goal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    return {
        **goal.to_dict(),
        "projection": tracker.get_projection(goal).to_dict(),
    }


@router.patch("/{user_id}/{goal_id}/progress")
def update_progress(
    user_id: str,
    goal_id: str,
    body: UpdateProgressRequest,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    MX.2 — Atualiza o progresso de uma meta (adiciona ao current_amount).

    Se current_amount atingir target_amount, a meta é marcada como COMPLETED.
    """
    from app.goals.tracker import GoalTracker
    tracker = GoalTracker(db)
    try:
        goal = tracker._load(goal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Meta {goal_id} não encontrada.")

    if goal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    if goal.status != "ACTIVE":
        raise HTTPException(status_code=422, detail=f"Meta com status '{goal.status}' não pode ser atualizada.")

    try:
        updated = tracker.update_progress(
            goal_id=goal_id,
            amount_to_add=body.amount_to_add,
            monthly_actual=body.monthly_actual,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        **updated.to_dict(),
        "projection": tracker.get_projection(updated).to_dict(),
    }


@router.delete("/{user_id}/{goal_id}", status_code=200)
def abandon_goal(user_id: str, goal_id: str, _: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    MX.2 — Abandona uma meta (marca como ABANDONED).
    """
    from app.goals.tracker import GoalTracker
    tracker = GoalTracker(db)
    try:
        goal = tracker._load(goal_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Meta {goal_id} não encontrada.")

    if goal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    try:
        updated = tracker.abandon_goal(goal_id=goal_id)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"message": f"Meta '{updated.name}' abandonada.", "goal": updated.to_dict()}
