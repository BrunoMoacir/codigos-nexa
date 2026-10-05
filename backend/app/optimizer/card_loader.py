# app/optimizer/card_loader.py
# CardKnowledgeBase - carrega e filtra cartões da base de conhecimento local

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.optimizer.models import CardRecord, CardFlag, BenefitTag
from app.core.formatacao import brl

if TYPE_CHECKING:
    from app.forecast.etl.income_profiler import IncomeProfile, IncomePattern

# Limiar de estabilidade abaixo do qual renda PJ/MIXED é penalizada
_PJ_INSTABILITY_THRESHOLD: float = 0.5
# Fator de penalidade aplicado ao income_factor quando renda PJ é instável
_PJ_INSTABILITY_PENALTY: float = 0.85

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENVELHECIMENTO DA CURADORIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A base é curada à mão e benefício de cartão muda o tempo todo. Não existe
# API pública de metadados de cartão no Brasil, então não há como atualizar
# sozinho — mas dá para PARAR DE CONFIAR sozinho.
#
# Cada registro tem last_updated; a confiança decai a partir do prazo de
# revisão. Como data_trust_score multiplica direto na confiança da simulação
# (simulator._compute_confidence), dado velho passa a produzir recomendação
# com menos peso e, se envelhecer muito, para de gerar insight — em vez de
# afirmar com a mesma segurança de sempre uma condição que pode ter mudado.

# Prazo de revisão da curadoria: um trimestre.
_CURATION_FRESH_DAYS = 90
# A partir daqui o registro é considerado obsoleto (piso de confiança).
_CURATION_STALE_DAYS = 365
# Piso: mesmo obsoleto o registro não vale zero — os campos estruturais
# (bandeira, tipo, emissor) não mudam; o que muda é taxa e benefício.
_CURATION_MIN_FACTOR = 0.6


def curation_freshness_factor(last_updated: str | None, today: date | None = None) -> float:
    """
    Multiplicador de confiança pela idade da curadoria (1.0 → 0.6).

    Decai linearmente entre 90 e 365 dias desde last_updated. Data ausente
    ou ilegível é tratada como obsoleta: não saber quando o dado foi
    conferido é pior do que saber que ele é velho.
    """
    if not last_updated:
        return _CURATION_MIN_FACTOR

    try:
        conferido = date.fromisoformat(str(last_updated)[:10])
    except (TypeError, ValueError):
        logger.warning("last_updated ilegível (%r) — tratando como obsoleto", last_updated)
        return _CURATION_MIN_FACTOR

    dias = ((today or date.today()) - conferido).days
    if dias <= _CURATION_FRESH_DAYS:
        return 1.0
    if dias >= _CURATION_STALE_DAYS:
        return _CURATION_MIN_FACTOR

    proporcao = (dias - _CURATION_FRESH_DAYS) / (_CURATION_STALE_DAYS - _CURATION_FRESH_DAYS)
    return 1.0 - proporcao * (1.0 - _CURATION_MIN_FACTOR)

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
        except FileNotFoundError:
            logger.error("Arquivo de cartões não encontrado: %s", self._path)
            return []
        except Exception as e:
            logger.error("Erro ao carregar cartões: %s", e)
            return []

        loaded: list[CardRecord] = []
        for item in raw:
            try:
                loaded.append(CardRecord(**item))
            except Exception as _item_err:
                logger.warning(
                    "CardKnowledgeBase: item ignorado (card_id=%r) — %s",
                    item.get("card_id", "?") if isinstance(item, dict) else "?",
                    _item_err,
                )

        self._cards = loaded
        logger.info("CardKnowledgeBase: %s cartões carregados de %s", len(self._cards), self._path)
        return self._cards

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
                logger.debug("Excluindo %s: usuário já possui", card.card_id)
                continue

            # Hard filter: renda anual mínima
            if annual_income < card.min_income:
                logger.debug(
                    f"Excluindo {card.card_id}: renda {annual_income:.0f} < mínimo {card.min_income:.0f}"
                )
                continue

            # Excluir secured_card se 15x renda já cobre convencionais
            if card.secured_card and exclude_secured and annual_income > 0:
                logger.debug("Excluindo %s: cartão garantido desnecessário", card.card_id)
                continue

            # Excluir consignado por padrão (sem vínculo empregatício detectado)
            if card.consigned and exclude_consigned:
                logger.debug("Excluindo %s: consignado excluído", card.card_id)
                continue

            eligible.append(card)

        logger.info(
            f"filter_eligible: {len(eligible)}/{len(self._cards)} cartões elegíveis "
            f"(renda anual {brl(annual_income, 0)})"
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
                    f"Renda estimada de {brl(annual_income / 12, 0)}/mês está bem acima "
                    f"do mínimo exigido ({brl(card.min_income / 12, 0)}/mês)"
                )
            elif income_ratio >= 1.5:
                income_factor = 0.80
                reasons.append(
                    f"Renda estimada de {brl(annual_income / 12, 0)}/mês está acima "
                    f"do mínimo exigido ({brl(card.min_income / 12, 0)}/mês)"
                )
            elif income_ratio >= 1.2:
                income_factor = 0.70
                reasons.append(
                    f"Renda estimada de {brl(annual_income / 12, 0)}/mês cobre o "
                    f"mínimo exigido ({brl(card.min_income / 12, 0)}/mês)"
                )
            else:
                income_factor = 0.60
                reasons.append(
                    f"Renda no limite mínimo — aprovação provável mas não garantida "
                    f"({brl(annual_income / 12, 0)}/mês vs {brl(card.min_income / 12, 0)}/mês)"
                )

        # --- Penalidade por instabilidade de renda PJ/MIXED (MI.3) ---
        if income_profile is not None:
            from app.forecast.etl.income_profiler import IncomePattern
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
