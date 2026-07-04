"""
app/opportunities/services/savings_rate.py

Ticket OPP4-B (docs/OPP4_POUPANCA_CDI_PLANO.md) — fórmula oficial de
remuneração da poupança, para comparação com CDI (OPP4-C).

Regra (Lei 8.177/1991, na redação dada pela Lei 12.703/2012 — vigente desde
04/05/2012, então referida como MP 567/2012 antes da conversão):

    Se a meta SELIC ao ano for SUPERIOR a 8,5% a.a.:
        remuneração mensal = 0,5% + TR
    Se a meta SELIC ao ano for IGUAL OU INFERIOR a 8,5% a.a.:
        remuneração mensal = 70% da meta SELIC mensalizada + TR

A TR entra nos dois ramos da regra — não é exclusiva de um deles.

⚠️ Confirmar com jurídico/compliance antes de usar este cálculo como base de
orientação financeira ativa ao usuário (push, e-mail, recomendação forte) —
ver docs/OPP4_POUPANCA_CDI_PLANO.md, seção 7 ("Riscos e decisões em aberto").
Esta implementação reflete o entendimento best-effort da regra pública, não
substitui validação jurídica.

Não copiar os hardcodes antigos de app/fiscal/services/tax_radar.py
(poupanca_rate = 6.17, self._selic_rate_pct = 11.25) — esta função é a única
fonte de verdade para "quanto rende a poupança hoje" no repositório.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.opportunities.models import SavingsRateResult

# Limiar da Lei 12.703/2012 — SELIC meta anual acima do qual vale a regra
# antiga (0,5% a.m. + TR) em vez da regra dos 70% da SELIC.
_SELIC_THRESHOLD_ANNUAL = 0.085   # 8,5% a.a.
_RULE_1_MONTHLY_BASE = 0.005      # 0,5% a.m.
_RULE_2_SELIC_SHARE = 0.70        # 70% da SELIC meta mensalizada


def calculate_savings_rate(
    selic_annual: float,
    tr_monthly: float,
    source: str = "BACEN",
) -> SavingsRateResult:
    """
    Calcula a remuneração oficial da poupança a partir de SELIC e TR.

    Função pura — não busca dados, não faz I/O. O chamador é responsável por
    obter selic_annual/tr_monthly via conectores (ex: BacenConnector) e
    informar `source` ("BACEN" quando os valores vieram de fetch bem-sucedido,
    "FALLBACK" quando vieram do fallback hardcoded do conector).

    Args:
        selic_annual: Taxa SELIC meta anual em decimal (ex: 0.1475 = 14,75% a.a.).
        tr_monthly:   Taxa Referencial mensal em decimal (ex: 0.0 quando zerada).
        source:       "BACEN" ou "FALLBACK" — repassado ao resultado para
                      transparência (não usado no cálculo em si).

    Returns:
        SavingsRateResult com a taxa mensal e anualizada, e qual ramo da
        regra foi aplicado.

    Example:
        >>> calculate_savings_rate(0.1475, 0.0).rule_branch
        'SELIC_GT_8_5'
        >>> calculate_savings_rate(0.07, 0.0).rule_branch
        'SELIC_LTE_8_5'
    """
    if selic_annual > _SELIC_THRESHOLD_ANNUAL:
        savings_monthly = _RULE_1_MONTHLY_BASE + tr_monthly
        rule_branch = "SELIC_GT_8_5"
    else:
        selic_monthly = (1 + selic_annual) ** (1 / 12) - 1  # mensalizar por composição
        savings_monthly = _RULE_2_SELIC_SHARE * selic_monthly + tr_monthly
        rule_branch = "SELIC_LTE_8_5"

    savings_annual = (1 + savings_monthly) ** 12 - 1

    return SavingsRateResult(
        selic_annual=selic_annual,
        tr_monthly=tr_monthly,
        savings_monthly=round(savings_monthly, 6),
        savings_annual=round(savings_annual, 6),
        rule_branch=rule_branch,
        source=source,
        generated_at=datetime.now(timezone.utc),
    )
