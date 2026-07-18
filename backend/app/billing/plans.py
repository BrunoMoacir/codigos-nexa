"""
app/billing/plans.py — Catálogo de planos da Nexa (fonte única).

Free / Pro / Total, conforme o modelo de negócio do README. Os preços em
Stripe vivem como Prices (env STRIPE_PRICE_*); aqui ficam a hierarquia de
tiers, os limites de uso do Free e a descrição exibida ao usuário.

Regra de gating:
  - require_plan("pro")   → Pro OU Total
  - require_plan("total") → somente Total
  - Limites de uso (Free): contadores por janela via UsageLimiter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_TOTAL = "total"

# Hierarquia: quem tem tier maior passa em qualquer gate de tier menor
_TIER_ORDER = {PLAN_FREE: 0, PLAN_PRO: 1, PLAN_TOTAL: 2}


def plan_satisfies(user_plan: str, required_plan: str) -> bool:
    return _TIER_ORDER.get(user_plan, 0) >= _TIER_ORDER.get(required_plan, 0)


@dataclass(frozen=True)
class UsageLimit:
    """Limite de uso para o plano Free (janela diária ou mensal)."""
    key: str            # identificador do contador (ex.: "chat_messages")
    limit: int          # máximo de usos na janela
    window: str         # "daily" | "monthly"
    description: str


@dataclass(frozen=True)
class Plan:
    plan_id: str
    name: str
    price_brl_monthly: float
    tagline: str
    features: list[str] = field(default_factory=list)
    free_limits: list[UsageLimit] = field(default_factory=list)


# Limites do Free (README: 1 banco, 3 Compra Inteligente/mês, 5 msgs IA/dia)
FREE_LIMITS: dict[str, UsageLimit] = {
    "chat_messages": UsageLimit(
        key="chat_messages", limit=5, window="daily",
        description="5 mensagens de IA por dia no plano Free",
    ),
    "purchase_checks": UsageLimit(
        key="purchase_checks", limit=3, window="monthly",
        description="3 consultas Compra Inteligente por mês no plano Free",
    ),
    "connected_banks": UsageLimit(
        key="connected_banks", limit=1, window="monthly",
        description="1 banco conectado no plano Free",
    ),
    "negotiator_scripts": UsageLimit(
        key="negotiator_scripts", limit=0, window="monthly",
        description="Negociador disponível a partir do plano Pro",
    ),
}

# Pro: Negociador 1/mês (limite próprio do Pro, não do Free)
PRO_LIMITS: dict[str, UsageLimit] = {
    "negotiator_scripts": UsageLimit(
        key="negotiator_scripts", limit=1, window="monthly",
        description="1 roteiro do Negociador por mês no plano Pro",
    ),
}

PLANS: dict[str, Plan] = {
    PLAN_FREE: Plan(
        plan_id=PLAN_FREE,
        name="Free",
        price_brl_monthly=0.0,
        tagline="Veja quanto os bancos lucram com você",
        features=[
            "1 banco conectado",
            "Dashboard básico e safe-to-spend",
            "3 consultas Compra Inteligente/mês",
            "5 mensagens de IA/dia",
            "Direitos esquecidos (consulta SVR assistida)",
        ],
        free_limits=list(FREE_LIMITS.values()),
    ),
    PLAN_PRO: Plan(
        plan_id=PLAN_PRO,
        name="Pro",
        price_brl_monthly=19.90,
        tagline="Recupere R$ 50+/mês — o plano se paga",
        features=[
            "Bancos ilimitados",
            "Raio-X completo de custos",
            "Radar de Oportunidades (catálogo vivo Open Finance)",
            "Chat com IA ilimitado",
            "Negociador (1 roteiro/mês)",
            "Digest diário por email",
            "Desafios mensais e badges",
        ],
    ),
    PLAN_TOTAL: Plan(
        plan_id=PLAN_TOTAL,
        name="Total",
        price_brl_monthly=39.90,
        tagline="Uma contestação recuperada paga o ano inteiro",
        features=[
            "Tudo do Pro",
            "Defesa do Consumidor completa (dossiê PROCON/JEC)",
            "Simulador de portabilidade total",
            "Otimizador de Imposto de Renda",
            "Wrapped trimestral",
            "Negociador ilimitado",
        ],
    ),
}

# Feature → tier mínimo (usado pelos routers via require_plan)
FEATURE_MIN_PLAN: dict[str, str] = {
    "opportunities": PLAN_PRO,
    "costs_xray": PLAN_PRO,
    "negotiator": PLAN_PRO,
    "defense": PLAN_TOTAL,
    "portability": PLAN_TOTAL,
    "tax_optimizer": PLAN_TOTAL,
}


__all__ = [
    "PLAN_FREE", "PLAN_PRO", "PLAN_TOTAL", "PLANS",
    "FREE_LIMITS", "PRO_LIMITS", "FEATURE_MIN_PLAN",
    "Plan", "UsageLimit", "plan_satisfies",
]
