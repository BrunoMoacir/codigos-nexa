"""
app/goals/tracker.py — Sistema de Metas Financeiras (MX.2)

RESPONSABILIDADE:
    Gerencia metas financeiras do usuário: criação, progresso e projeções.

FUNCIONALIDADES:
    - create_goal:     registra uma nova meta com cálculo automático de
                       contribuição mensal necessária
    - update_progress: incrementa o current_amount e detecta conclusão
    - get_projection:  calcula se a meta está no ritmo certo, data estimada
                       de conclusão e gap de contribuição mensal

INTEGRAÇÃO:
    - DuckDB via app.db.queries
    - Exposto via GET/POST/PATCH /api/v1/goals/{user_id}

EXEMPLO:
    >>> tracker = GoalTracker()
    >>> goal = tracker.create_goal(
    ...     user_id="u1",
    ...     name="Entrada do apartamento",
    ...     target_amount=50_000.0,
    ...     target_date="2028-03-01",
    ...     current_amount=5_000.0,
    ... )
    >>> proj = tracker.get_projection(goal)
    >>> print(proj.suggestion)
    "Você precisa guardar R$ 1.875/mês. Atual: R$ 800/mês. Faltam R$ 1.075/mês."
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODELOS DE DOMÍNIO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class Goal:
    """Representa uma meta financeira persistida."""
    goal_id: str
    user_id: str
    name: str
    goal_type: str
    target_amount: float
    current_amount: float
    target_date: Optional[str]              # 'YYYY-MM-DD' ou None
    monthly_contribution_needed: Optional[float]
    monthly_contribution_actual: Optional[float]
    status: str                             # ACTIVE | COMPLETED | ABANDONED
    created_at: str
    updated_at: str
    version: int = field(default=1)         # controle de concorrência otimista

    @property
    def progress_pct(self) -> float:
        """Percentual de progresso (0-100)."""
        if self.target_amount <= 0:
            return 100.0
        return min(100.0, self.current_amount / self.target_amount * 100)

    @property
    def remaining(self) -> float:
        """Valor restante para atingir a meta."""
        return max(0.0, self.target_amount - self.current_amount)

    def to_dict(self) -> dict:
        return {
            "goal_id":                    self.goal_id,
            "user_id":                    self.user_id,
            "name":                       self.name,
            "goal_type":                  self.goal_type,
            "target_amount":              round(self.target_amount, 2),
            "current_amount":             round(self.current_amount, 2),
            "progress_pct":               round(self.progress_pct, 1),
            "remaining":                  round(self.remaining, 2),
            "target_date":                self.target_date,
            "monthly_contribution_needed": (
                round(self.monthly_contribution_needed, 2)
                if self.monthly_contribution_needed is not None else None
            ),
            "monthly_contribution_actual": (
                round(self.monthly_contribution_actual, 2)
                if self.monthly_contribution_actual is not None else None
            ),
            "status":                     self.status,
            "created_at":                 self.created_at,
            "updated_at":                 self.updated_at,
        }


@dataclass
class GoalProjection:
    """Projeção de conclusão de uma meta."""
    goal_id: str
    on_track: bool
    projected_completion_date: Optional[str]  # 'YYYY-MM-DD' — None se sem data alvo e sem contribuição
    months_remaining: Optional[float]
    monthly_needed: float                     # quanto precisa guardar por mês para bater a meta
    current_monthly_actual: float             # quanto está guardando (0.0 se desconhecido)
    gap: float                                # gap = monthly_needed - current_monthly_actual
    suggestion: str

    def to_dict(self) -> dict:
        return {
            "goal_id":                    self.goal_id,
            "on_track":                   self.on_track,
            "projected_completion_date":  self.projected_completion_date,
            "months_remaining":           (
                round(self.months_remaining, 1) if self.months_remaining is not None else None
            ),
            "monthly_needed":             round(self.monthly_needed, 2),
            "current_monthly_actual":     round(self.current_monthly_actual, 2),
            "gap":                        round(self.gap, 2),
            "suggestion":                 self.suggestion,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GOAL TRACKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GoalTracker:
    """
    Gerencia o ciclo de vida das metas financeiras.

    Recebe uma Session SQLAlchemy via injeção de dependência — não abre
    sessões internamente.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ─────────────────────────────────────────────────────────────────────
    # CRUD
    # ─────────────────────────────────────────────────────────────────────

    def create_goal(
        self,
        user_id: str,
        name: str,
        target_amount: float,
        target_date: Optional[str] = None,
        current_amount: float = 0.0,
        goal_type: str = "outros",
    ) -> Goal:
        """
        Cria uma nova meta e a persiste no DuckDB.

        A `monthly_contribution_needed` é calculada automaticamente:
        - Se `target_date` definido: remaining / meses_restantes
        - Caso contrário: None (sem prazo)

        Args:
            user_id:        ID do usuário.
            name:           Nome da meta (ex: "Entrada do apartamento").
            target_amount:  Valor alvo em R$.
            target_date:    Data alvo no formato 'YYYY-MM-DD' (opcional).
            current_amount: Quanto já foi acumulado (default 0).
            goal_type:      Tipo: "imovel" | "viagem" | "carro" | "educacao" | "outros"

        Returns:
            Goal criado e persistido.
        """
        goal_id = str(uuid.uuid4())
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        monthly_needed = self._calc_monthly_needed(current_amount, target_amount, target_date)

        goal = Goal(
            goal_id=goal_id,
            user_id=user_id,
            name=name,
            goal_type=goal_type,
            target_amount=target_amount,
            current_amount=current_amount,
            target_date=target_date,
            monthly_contribution_needed=monthly_needed,
            monthly_contribution_actual=None,
            status="ACTIVE",
            created_at=now_str,
            updated_at=now_str,
        )

        self._persist(goal)
        logger.info(f"[GoalTracker] Meta criada: {goal_id} | {name} | R${target_amount}")
        return goal

    def update_progress(
        self,
        goal_id: str,
        amount_to_add: float,
        monthly_actual: Optional[float] = None,
    ) -> Goal:
        """
        Adiciona ao current_amount da meta e marca como COMPLETED se atingida.

        Args:
            goal_id:         ID da meta.
            amount_to_add:   Valor a adicionar (ex: R$ 500 guardados este mês).
            monthly_actual:  Contribuição mensal detectada nas transações (opcional).

        Returns:
            Goal atualizada.

        Raises:
            LookupError: se goal_id não existir.
        """
        goal = self._load(goal_id)
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        new_amount = Decimal(str(goal.current_amount)) + Decimal(str(amount_to_add))
        goal.current_amount = float(new_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        goal.updated_at = now_str

        if monthly_actual is not None:
            goal.monthly_contribution_actual = monthly_actual

        # Recalcular monthly_needed com o novo current_amount
        goal.monthly_contribution_needed = self._calc_monthly_needed(
            goal.current_amount, goal.target_amount, goal.target_date
        )

        # Conclusão automática
        if goal.current_amount >= goal.target_amount:
            goal.status = "COMPLETED"
            logger.info(f"[GoalTracker] Meta concluída: {goal_id}")

        self._update(goal)
        return goal

    def get_projection(self, goal: Goal) -> GoalProjection:
        """
        Calcula a projeção de conclusão da meta.

        Considera:
        - Quanto precisa guardar por mês (monthly_needed)
        - Quanto está guardando hoje (monthly_contribution_actual ou 0)
        - Se está no ritmo para bater a meta na data alvo

        Returns:
            GoalProjection completo.
        """
        monthly_needed = goal.monthly_contribution_needed or 0.0
        monthly_actual = goal.monthly_contribution_actual or 0.0
        remaining = goal.remaining

        # Projetar data de conclusão com a contribuição atual
        projected_date_str: Optional[str] = None
        projected_months: Optional[float] = None

        if monthly_actual > 0:
            projected_months = math.ceil(remaining / monthly_actual)
            proj_date = _add_months(date.today(), projected_months)
            projected_date_str = proj_date.isoformat()

        # On track: dentro de 1 mês da data alvo (ou sem data → basta ter ritmo)
        on_track = False
        if goal.target_date:
            target = date.fromisoformat(goal.target_date)
            if projected_date_str:
                on_track = date.fromisoformat(projected_date_str) <= target
        else:
            # Sem prazo: on_track se tiver alguma contribuição
            on_track = monthly_actual >= monthly_needed * 0.9 if monthly_needed > 0 else monthly_actual > 0

        gap = max(0.0, monthly_needed - monthly_actual)

        suggestion = self._build_suggestion(goal, monthly_needed, monthly_actual, gap, projected_months)

        return GoalProjection(
            goal_id=goal.goal_id,
            on_track=on_track,
            projected_completion_date=projected_date_str,
            months_remaining=projected_months,
            monthly_needed=monthly_needed,
            current_monthly_actual=monthly_actual,
            gap=gap,
            suggestion=suggestion,
        )

    def list_goals(
        self,
        user_id: str,
        status: str = "ACTIVE",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Goal]:
        """Lista metas do usuário filtradas por status, com paginação."""
        from app.goals.models import FinancialGoal
        try:
            rows = (
                self.db.query(FinancialGoal)
                .filter(
                    FinancialGoal.user_id == user_id,
                    FinancialGoal.status == status,
                )
                .order_by(FinancialGoal.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [self._row_to_goal({c.name: getattr(r, c.name) for c in r.__table__.columns}) for r in rows]
        except Exception as e:
            logger.error(f"[GoalTracker] Erro ao listar metas: {e}")
            return []

    def abandon_goal(self, goal_id: str) -> Goal:
        """Marca a meta como ABANDONED."""
        goal = self._load(goal_id)
        goal.status = "ABANDONED"
        goal.updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        self._update(goal)
        return goal

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS PRIVADOS
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_monthly_needed(
        current: float,
        target: float,
        target_date: Optional[str],
    ) -> Optional[float]:
        """Calcula contribuição mensal necessária. None se sem prazo."""
        if not target_date:
            return None
        remaining = Decimal(str(target)) - Decimal(str(current))
        if remaining <= 0:
            return 0.0
        months = _months_until(date.fromisoformat(target_date))
        if months <= 0:
            return float(remaining.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        result = remaining / Decimal(str(months))
        return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _persist(self, goal: Goal) -> None:
        """Insere a meta no PostgreSQL via SQLAlchemy."""
        from app.goals.models import FinancialGoal
        row = FinancialGoal(
            goal_id=goal.goal_id, user_id=goal.user_id, name=goal.name,
            goal_type=goal.goal_type, target_amount=goal.target_amount,
            current_amount=goal.current_amount, target_date=goal.target_date,
            monthly_contribution_needed=goal.monthly_contribution_needed,
            monthly_contribution_actual=goal.monthly_contribution_actual,
            status=goal.status, version=goal.version,
            created_at=goal.created_at, updated_at=goal.updated_at,
        )
        self.db.add(row)
        self.db.commit()

    def _update(self, goal: Goal) -> None:
        """
        Atualiza a meta no PostgreSQL via SQLAlchemy com lock otimista.

        O UPDATE só acontece se a versão no banco ainda corresponde à versão
        carregada — garante que atualizações concorrentes não se sobrescrevam
        silenciosamente.

        Raises:
            RuntimeError: se nenhuma linha for afetada (conflito de versão).
        """
        from app.goals.models import FinancialGoal
        rows_affected = (
            self.db.query(FinancialGoal)
            .filter(
                FinancialGoal.goal_id == goal.goal_id,
                FinancialGoal.version == goal.version,
            )
            .update({
                FinancialGoal.current_amount: goal.current_amount,
                FinancialGoal.monthly_contribution_needed: goal.monthly_contribution_needed,
                FinancialGoal.monthly_contribution_actual: goal.monthly_contribution_actual,
                FinancialGoal.status: goal.status,
                FinancialGoal.updated_at: goal.updated_at,
                FinancialGoal.version: goal.version + 1,
            })
        )
        if rows_affected == 0:
            self.db.rollback()
            raise RuntimeError(
                f"Conflito de concorrência ao atualizar meta {goal.goal_id} "
                f"(versão esperada={goal.version}). Recarregue e tente novamente."
            )
        goal.version += 1
        self.db.commit()

    def _load(self, goal_id: str) -> Goal:
        """Carrega uma meta do PostgreSQL. Lança LookupError se não encontrada."""
        from app.goals.models import FinancialGoal
        row = self.db.query(FinancialGoal).filter(FinancialGoal.goal_id == goal_id).first()
        if not row:
            raise LookupError(f"Meta não encontrada: {goal_id}")
        return self._row_to_goal({c.name: getattr(row, c.name) for c in row.__table__.columns})

    @staticmethod
    def _row_to_goal(row: dict) -> Goal:
        return Goal(
            goal_id=row["goal_id"],
            user_id=row["user_id"],
            name=row["name"],
            goal_type=row.get("goal_type", "outros") or "outros",
            target_amount=float(row["target_amount"]),
            current_amount=float(row.get("current_amount") or 0.0),
            target_date=row.get("target_date"),
            monthly_contribution_needed=_float_or_none(row.get("monthly_contribution_needed")),
            monthly_contribution_actual=_float_or_none(row.get("monthly_contribution_actual")),
            status=row.get("status", "ACTIVE"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=int(row.get("version") or 1),
        )

    @staticmethod
    def _build_suggestion(
        goal: Goal,
        monthly_needed: float,
        monthly_actual: float,
        gap: float,
        projected_months: Optional[float],
    ) -> str:
        """Gera texto de sugestão em português natural."""
        parts: list[str] = []

        if goal.status == "COMPLETED":
            return f"🎉 Meta '{goal.name}' concluída! Parabéns!"

        if goal.status == "ABANDONED":
            return f"Meta '{goal.name}' foi abandonada."

        # Progresso
        parts.append(
            f"Meta '{goal.name}': {goal.progress_pct:.0f}% concluída "
            f"(R$ {goal.current_amount:,.0f} / R$ {goal.target_amount:,.0f})."
        )

        # Contribuição necessária
        if monthly_needed > 0:
            parts.append(f"Você precisa guardar R$ {monthly_needed:,.0f}/mês.")
        
        if monthly_actual > 0:
            parts.append(f"Contribuição atual detectada: R$ {monthly_actual:,.0f}/mês.")

        # Gap
        if gap > 0:
            parts.append(
                f"Faltam R$ {gap:,.0f}/mês para estar no ritmo. "
                f"Considere reduzir R$ {gap:,.0f} em despesas variáveis."
            )
        elif monthly_needed > 0:
            parts.append("✅ Você está no ritmo para atingir a meta!")

        # Projeção
        if projected_months is not None and monthly_actual > 0:
            if goal.target_date:
                target = date.fromisoformat(goal.target_date)
                proj_date = _add_months(date.today(), int(projected_months))
                if proj_date <= target:
                    parts.append(f"📅 Projeção: meta atingida antes do prazo!")
                else:
                    delay = (proj_date.year - target.year) * 12 + (proj_date.month - target.month)
                    parts.append(
                        f"⚠️ Projeção: meta atingida em ~{projected_months:.0f} meses "
                        f"({delay} {'mês' if delay==1 else 'meses'} de atraso)."
                    )
            else:
                parts.append(f"📅 Com este ritmo: meta em ~{projected_months:.0f} meses.")
        elif monthly_actual == 0 and monthly_needed > 0:
            parts.append(
                f"⚠️ Nenhuma contribuição detectada. Comece guardando R$ {monthly_needed:,.0f}/mês."
            )

        return " ".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS UTILITÁRIOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _months_until(target: date) -> int:
    """Número de meses completos entre hoje e a data alvo (mínimo 0)."""
    today = date.today()
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day >= today.day:
        months += 1
    return max(0, months)


def _add_months(d: date, months: int) -> date:
    """Adiciona `months` meses a uma data, ajustando último dia do mês."""
    m = d.month + months - 1
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def _float_or_none(v) -> Optional[float]:
    return float(v) if v is not None else None


__all__ = ["GoalTracker", "Goal", "GoalProjection"]
