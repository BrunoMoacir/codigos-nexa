"""
app/optimizer/promotion_tracker.py — M2.6: Alertas de Promoções de Transferência Bonificada

RESPONSABILIDADE:
    Mantém um registro de promoções ativas de transferência de pontos entre
    programas de fidelidade (ex: Livelo → LATAM Pass com 100% de bônus) e
    identifica oportunidades para o usuário com base nos cartões que possui
    e seu saldo estimado de pontos.

FONTE DE DADOS:
    data/cards/transfer_promotions.json — curado manualmente (futuro: web scraping).

SAÍDA:
    PromotionAlert com cálculo do valor potencial da transferência e texto
    amigável para exibição ao usuário e ingestão pelo LLM do agente.

INTEGRAÇÃO:
    GET /api/v1/optimizer/promotions?user_id={user_id}
    (Opcional) pode ser checado automaticamente no pipeline do agente
    quando o usuário pede análise de cartão.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Localiza o JSON relativo a este arquivo: ../../data/cards/transfer_promotions.json
_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "cards" / "transfer_promotions.json"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODELOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class TransferPromotion:
    """Representa uma promoção de transferência bonificada."""
    id: str
    loyalty_program: str            # ex: "livelo", "amex_membership_rewards"
    partner: str                    # ex: "LATAM Pass", "TudoAzul"
    bonus_pct: float                # ex: 100 (= 100% de bônus)
    normal_rate_per_1000: float     # valor normal de 1.000 pontos em R$
    effective_rate_per_1000: float  # valor efetivo com bônus em R$
    start_date: date
    end_date: date
    min_points: int                 # mínimo para transferir
    max_points: Optional[int]       # limite por transferência (None = sem limite)
    eligible_cards: list[str]       # nomes dos cartões elegíveis para esta promoção
    description: str
    source: str
    last_verified: str

    @property
    def is_active(self) -> bool:
        """Promoção está vigente hoje."""
        today = date.today()
        return self.start_date <= today <= self.end_date

    @property
    def days_remaining(self) -> int:
        """Dias até o fim da promoção (0 se encerrada)."""
        delta = (self.end_date - date.today()).days
        return max(0, delta)

    def to_dict(self) -> dict:
        return {
            "id":                      self.id,
            "loyalty_program":         self.loyalty_program,
            "partner":                 self.partner,
            "bonus_pct":               self.bonus_pct,
            "normal_rate_per_1000":    self.normal_rate_per_1000,
            "effective_rate_per_1000": self.effective_rate_per_1000,
            "start_date":              self.start_date.isoformat(),
            "end_date":                self.end_date.isoformat(),
            "days_remaining":          self.days_remaining,
            "min_points":              self.min_points,
            "max_points":              self.max_points,
            "eligible_cards":          self.eligible_cards,
            "description":             self.description,
            "source":                  self.source,
            "last_verified":           self.last_verified,
        }


@dataclass
class PromotionAlert:
    """Alerta de oportunidade de transferência para um usuário específico."""
    promotion: TransferPromotion
    user_card: str                  # cartão que o usuário possui, elegível
    estimated_points: int           # pontos estimados do usuário neste programa
    potential_value_normal: float   # valor dos pontos sem promoção (R$)
    potential_value_promo: float    # valor dos pontos com promoção (R$)
    extra_value: float              # quanto a mais o usuário ganha (R$)
    alert_text: str                 # texto amigável para o usuário/LLM

    def to_dict(self) -> dict:
        return {
            "promotion":            self.promotion.to_dict(),
            "user_card":            self.user_card,
            "estimated_points":     self.estimated_points,
            "potential_value_normal": round(self.potential_value_normal, 2),
            "potential_value_promo":  round(self.potential_value_promo, 2),
            "extra_value":          round(self.extra_value, 2),
            "alert_text":           self.alert_text,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROMOTION TRACKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PromotionTracker:
    """
    Rastreia promoções de transferência de pontos (M2.6).

    Example:
        >>> tracker = PromotionTracker()
        >>> active = tracker.get_active_promotions()
        >>> alerts = tracker.check_user_opportunities(
        ...     user_cards=["Inter Black"],
        ...     user_points_balance={"smiles": 15000}
        ... )
    """

    def __init__(self, data_path: Path = _DATA_PATH):
        self._data_path = data_path
        self._all_promotions: list[TransferPromotion] = self._load()

    # ─────────────────────────────────────────────────────────────────
    # CORE API
    # ─────────────────────────────────────────────────────────────────

    def get_active_promotions(self) -> list[TransferPromotion]:
        """Retorna somente as promoções vigentes hoje."""
        return [p for p in self._all_promotions if p.is_active]

    def get_all_promotions(self, include_expired: bool = False) -> list[TransferPromotion]:
        """Retorna todas ou somente as ativas."""
        if include_expired:
            return list(self._all_promotions)
        return self.get_active_promotions()

    def check_user_opportunities(
        self,
        user_cards: list[str],
        user_points_balance: dict[str, int],
    ) -> list[PromotionAlert]:
        """
        Identifica promoções vantajosas para o usuário.

        Args:
            user_cards:          Lista com nomes dos cartões do usuário
                                 (ex: ["Inter Black", "Amex Gold"]).
            user_points_balance: Saldo estimado de pontos por programa
                                 (ex: {"livelo": 25000, "smiles": 8000}).

        Returns:
            Lista de PromotionAlert, ordenada por extra_value decrescente.
        """
        alerts: list[PromotionAlert] = []
        active = self.get_active_promotions()

        for promo in active:
            # Verifica se o usuário tem algum cartão elegível
            matching_card = self._match_card(promo.eligible_cards, user_cards)
            if not matching_card:
                continue

            # Saldo do usuário neste programa de fidelidade
            points = user_points_balance.get(promo.loyalty_program, 0)

            # Verifica mínimo
            if points < promo.min_points:
                continue

            # Calcula potencial financeiro
            transferable = points
            if promo.max_points is not None:
                transferable = min(points, promo.max_points)

            val_normal = transferable / 1000 * promo.normal_rate_per_1000
            val_promo  = transferable / 1000 * promo.effective_rate_per_1000
            extra      = val_promo - val_normal

            text = self._build_alert_text(promo, matching_card, transferable, val_normal, val_promo, extra)

            alerts.append(PromotionAlert(
                promotion=promo,
                user_card=matching_card,
                estimated_points=transferable,
                potential_value_normal=val_normal,
                potential_value_promo=val_promo,
                extra_value=extra,
                alert_text=text,
            ))

        # Ordena por valor extra decrescente
        alerts.sort(key=lambda a: a.extra_value, reverse=True)
        return alerts

    # ─────────────────────────────────────────────────────────────────
    # HELPERS PRIVADOS
    # ─────────────────────────────────────────────────────────────────

    def _load(self) -> list[TransferPromotion]:
        """Carrega o JSON de promoções."""
        try:
            with open(self._data_path, encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
            promos = []
            for item in raw:
                promos.append(TransferPromotion(
                    id=item["id"],
                    loyalty_program=item["loyalty_program"],
                    partner=item["partner"],
                    bonus_pct=float(item["bonus_pct"]),
                    normal_rate_per_1000=float(item["normal_rate_per_1000"]),
                    effective_rate_per_1000=float(item["effective_rate_per_1000"]),
                    start_date=date.fromisoformat(item["start_date"]),
                    end_date=date.fromisoformat(item["end_date"]),
                    min_points=int(item["min_points"]),
                    max_points=int(item["max_points"]) if item.get("max_points") else None,
                    eligible_cards=item.get("eligible_cards", []),
                    description=item.get("description", ""),
                    source=item.get("source", "manual"),
                    last_verified=item.get("last_verified", ""),
                ))
            logger.info(f"[PromotionTracker] {len(promos)} promoções carregadas de {self._data_path}")
            return promos
        except FileNotFoundError:
            logger.warning(f"[PromotionTracker] Arquivo não encontrado: {self._data_path}")
            return []
        except Exception as e:
            logger.error(f"[PromotionTracker] Erro ao carregar promoções: {e}", exc_info=True)
            return []

    @staticmethod
    def _match_card(eligible: list[str], user_cards: list[str]) -> Optional[str]:
        """Retorna o primeiro cartão do usuário que está na lista de elegíveis."""
        eligible_lower = {c.lower() for c in eligible}
        for card in user_cards:
            if card.lower() in eligible_lower:
                return card
        return None

    @staticmethod
    def _build_alert_text(
        promo: TransferPromotion,
        card: str,
        points: int,
        val_normal: float,
        val_promo: float,
        extra: float,
    ) -> str:
        urgency = ""
        if promo.days_remaining <= 3:
            urgency = f"⚠️ URGENTE — termina em {promo.days_remaining} dia(s)! "
        elif promo.days_remaining <= 7:
            urgency = f"🕐 {promo.days_remaining} dias restantes. "

        return (
            f"🔥 {urgency}Promoção ativa: {promo.loyalty_program.title()} → {promo.partner} "
            f"com {promo.bonus_pct:.0f}% de bônus (até {promo.end_date.strftime('%d/%m/%Y')}). "
            f"Seus {points:,} pontos via {card} valem R$ {val_promo:,.0f} agora "
            f"(vs R$ {val_normal:,.0f} normalmente). "
            f"Você ganha R$ {extra:,.0f} a mais transferindo agora."
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONVENIÊNCIA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_active_promotions(data_path: Path = _DATA_PATH) -> list[TransferPromotion]:
    """Wrapper de conveniência para listar promoções ativas."""
    return PromotionTracker(data_path).get_active_promotions()


__all__ = [
    "PromotionTracker",
    "TransferPromotion",
    "PromotionAlert",
    "get_active_promotions",
]
