# app/optimizer/card_loader.py
# CardKnowledgeBase - carrega e filtra cartões da base de conhecimento local

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.optimizer.models import CardRecord, CardFlag, BenefitTag

if TYPE_CHECKING:
    from app.etl.income_profiler import IncomeProfile, IncomePattern

# Limiar de estabilidade abaixo do qual renda PJ/MIXED é penalizada
_PJ_INSTABILITY_THRESHOLD: float = 0.5
# Fator de penalidade aplicado ao income_factor quando renda PJ é instável
_PJ_INSTABILITY_PENALTY: float = 0.85

logger = logging.getLogger(__name__)

# Caminho para data/cards/knowledge_cards.json (relativo ao repo)
_CARDS_PATH = Path(__file__).parent.parent.parent / "data" / "cards" / "knowledge_cards.json"


class CardKnowledgeBase:
    """
    Carrega e mantém em memória os cartões disponíveis.
    Responsável por:
      - Carregar knowledge_cards.json
      - Filtrar cartões elegíveis para um perfil
      - Calcular eligibility_score por cartão
    """

    def __init__(self, cards_path: Optional[Path] = None):
        self._path = cards_path or _CARDS_PATH
        self._cards: list[CardRecord] = []

    def load(self) -> list[CardRecord]:
        """Lê e parseia o JSON de cartões. Retorna lista de CardRecord."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._cards = [CardRecord(**item) for item in raw]
            logger.info(f"CardKnowledgeBase: {len(self._cards)} cartões carregados de {self._path}")
            return self._cards
        except FileNotFoundError:
            logger.error(f"Arquivo de cartões não encontrado: {self._path}")
            return []
        except Exception as e:
            logger.error(f"Erro ao carregar cartões: {e}")
            return []

    def get_by_id(self, card_id: str) -> Optional[CardRecord]:
        """Retorna um cartão pelo card_id, ou None se não encontrado."""
        if not self._cards:
            self.load()
        return next((c for c in self._cards if c.card_id == card_id), None)

    def filter_eligible(
        self,
        annual_income: float,
        current_card_ids: list[str] | None = None,
        exclude_secured: bool = True,
        exclude_consigned: bool = True,
    ) -> list[CardRecord]:
        """
        Aplica hard constraints e devolve cartões elegíveis.

        Hard constraints:
        - Renda anual do usuário >= card.min_income
        - Remove cartões que o usuário já possui
        - Remove secured_card se renda suficiente para convencionais
        - Remove consigned se não há vínculo empregatício formal (default)
        """
        if not self._cards:
            self.load()

        current_ids: set[str] = set(current_card_ids or [])
        eligible: list[CardRecord] = []

        for card in self._cards:
            # Excluir cartões que o usuário já tem
            if card.card_id in current_ids:
                logger.debug(f"Excluindo {card.card_id}: usuário já possui")
                continue

            # Hard filter: renda anual mínima
            if annual_income < card.min_income:
                logger.debug(
                    f"Excluindo {card.card_id}: renda {annual_income:.0f} < mínimo {card.min_income:.0f}"
                )
                continue

            # Excluir secured_card se 15x renda já cobre convencionais
            if card.secured_card and exclude_secured and annual_income > 0:
                logger.debug(f"Excluindo {card.card_id}: cartão garantido desnecessário")
                continue

            # Excluir consignado por padrão (sem vínculo empregatício detectado)
            if card.consigned and exclude_consigned:
                logger.debug(f"Excluindo {card.card_id}: consignado excluído")
                continue

            eligible.append(card)

        logger.info(
            f"filter_eligible: {len(eligible)}/{len(self._cards)} cartões elegíveis "
            f"(renda anual R$ {annual_income:,.0f})"
        )
        return eligible

    def compute_eligibility_score(
        self,
        card: CardRecord,
        annual_income: float,
        spending_stability: float = 1.0,
        issuers_in_transactions: set[str] | None = None,
        income_profile: Optional["IncomeProfile"] = None,
    ) -> tuple[float, list[str]]:
        """
        Calcula eligibility_score (0.0–1.0) e lista de razões humanas.

        Args:
            income_profile: Quando fornecido e income_stability < 0.5 com padrão
                PJ ou MIXED, aplica penalidade de 15% ao income_factor.
                Renda variável aumenta o risco percebido de inadimplência pelo emissor.

        Retorna: (score, reasons)
        """
        reasons: list[str] = []

        # --- Fator renda ---
        if card.min_income == 0:
            income_factor = 1.0
        else:
            income_ratio = annual_income / card.min_income
            if income_ratio >= 2.0:
                income_factor = 0.95
                reasons.append(
                    f"Renda estimada de R$ {annual_income / 12:,.0f}/mês está bem acima "
                    f"do mínimo exigido (R$ {card.min_income / 12:,.0f}/mês)"
                )
            elif income_ratio >= 1.5:
                income_factor = 0.80
                reasons.append(
                    f"Renda estimada de R$ {annual_income / 12:,.0f}/mês está acima "
                    f"do mínimo exigido (R$ {card.min_income / 12:,.0f}/mês)"
                )
            elif income_ratio >= 1.2:
                income_factor = 0.70
                reasons.append(
                    f"Renda estimada de R$ {annual_income / 12:,.0f}/mês cobre o "
                    f"mínimo exigido (R$ {card.min_income / 12:,.0f}/mês)"
                )
            else:
                income_factor = 0.60
                reasons.append(
                    f"Renda no limite mínimo — aprovação provável mas não garantida "
                    f"(R$ {annual_income / 12:,.0f}/mês vs R$ {card.min_income / 12:,.0f}/mês)"
                )

        # --- Penalidade por instabilidade de renda PJ/MIXED (MI.3) ---
        if income_profile is not None:
            from app.etl.income_profiler import IncomePattern
            is_variable_income = income_profile.income_pattern in (
                IncomePattern.PJ, IncomePattern.MIXED
            )
            if is_variable_income and income_profile.income_stability < _PJ_INSTABILITY_THRESHOLD:
                income_factor *= _PJ_INSTABILITY_PENALTY
                reasons.append(
                    f"Renda {income_profile.income_pattern.value} com variabilidade elevada "
                    f"(estabilidade {income_profile.income_stability:.0%}) — "
                    f"histórico irregular pode reduzir chances de aprovação"
                )

        score = income_factor * spending_stability

        # --- Bônus de relacionamento ---
        existing_issuers = issuers_in_transactions or set()
        if card.issuer in existing_issuers:
            score = min(score + 0.10, 1.0)
            reasons.append(
                f"Você já tem relacionamento com {card.issuer} — aumenta chance de aprovação"
            )

        if spending_stability >= 0.8:
            reasons.append(
                f"Histórico de gastos estável — reduz percepção de risco de inadimplência"
            )

        score = round(min(score, 1.0), 4)
        return score, reasons
