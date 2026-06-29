"""
app/rights/services/pis_pasep_checker.py — PIS/PASEP Esquecido

Cotas do fundo PIS (setor privado) ou PASEP (setor público), especialmente
para trabalhadores com carteira assinada registrada antes de 04/10/1988.

Não existe API pública para consulta de saldo PIS/PASEP por CPF.
Implementação orientativa: usa renda média para sinalizar relevância.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from app.rights.models import ForgottenRight

logger = logging.getLogger(__name__)

_ABONO_SALARIAL_TETO = 5 * 1412.0  # 5 salários mínimos (2024)


class PisPasepChecker:
    """
    Orienta o usuário sobre PIS/PASEP e verifica elegibilidade para
    abono salarial com base na renda média das transações.
    """

    def check(self, user_id: str) -> ForgottenRight:
        avg_income, is_eligible_abono, reason = self._check_abono_eligibility(user_id)

        if is_eligible_abono:
            estimated = self._estimate_abono(avg_income)
            confidence = "medium"
        else:
            estimated = None
            confidence = "unknown"

        return ForgottenRight(
            category="pis_pasep",
            title="PIS/PASEP — Cotas e Abono Salarial",
            description=(
                "PIS (trabalhador setor privado) ou PASEP (setor público): "
                "cotas acumuladas de quem trabalhou com carteira assinada ANTES de 04/10/1988 "
                "podem estar esquecidas. Além disso, trabalhadores com carteira assinada e renda "
                "mensal de até 5 salários mínimos têm direito ao Abono Salarial anual (até 1 salário mínimo)."
            ),
            estimated_amount=estimated,
            estimated_confidence=confidence,
            relevance_reason=reason,
            official_channel="Caixa Econômica (PIS) · Banco do Brasil (PASEP) · Gov.br",
            official_url="https://www.gov.br/pt-br/servicos/consultar-pis-pasep",
            action_steps=[
                "Abono Salarial: verifique no Calendário Abono Salarial (gov.br) se tem direito e quando sacar.",
                "PIS: acesse o app Caixa Tem ou vá a uma agência CEF com CPF e CTPS.",
                "PASEP: acesse o Banco do Brasil (agência ou app) com CPF.",
                "Cotas pré-1988: se trabalhou com carteira assinada antes de 04/10/1988, consulte o BB ou CEF — "
                "esses valores têm correção histórica e podem ser significativos.",
                "Trabalhadores que nunca sacaram há mais de 10 anos devem ligar para 0800-726-0207 (CEF).",
            ],
            warning=(
                "Cotas PIS/PASEP pré-1988 têm correção especial (BTN + 3% a.a.). "
                "O valor real só pode ser consultado presencialmente ou via app oficial."
            ),
        )

    def _check_abono_eligibility(
        self, user_id: str
    ) -> tuple[Optional[float], bool, str]:
        try:
            from app.core.db.queries import get_transactions_for_user
            import polars as pl

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return None, False, (
                    "Sem transações disponíveis. Verifique abono salarial se teve emprego formal no ano passado."
                )

            date_col = "transaction_date" if "transaction_date" in df.columns else "date"
            cutoff = date.today() - timedelta(days=365)
            df_year = df.filter(pl.col(date_col) >= cutoff)
            income = df_year.filter(pl.col("amount") > 0)

            if income.is_empty():
                return None, False, "Sem créditos detectados no último ano."

            monthly_avg = round(float(income["amount"].mean()), 2)
            if monthly_avg <= _ABONO_SALARIAL_TETO:
                return monthly_avg, True, (
                    f"Renda média detectada R$ {monthly_avg:,.2f}/mês — "
                    "dentro do teto do Abono Salarial (5 salários mínimos). "
                    "Verifique se trabalhou com carteira assinada no ano-base."
                )
            return monthly_avg, False, (
                f"Renda média detectada R$ {monthly_avg:,.2f}/mês — acima do teto do Abono Salarial. "
                "Verifique cotas PIS/PASEP pré-1988 se aplicável."
            )

        except Exception as exc:
            logger.warning("[PisPasepChecker] user=%s: %s", user_id, exc)
            return None, False, "Consulte o portal gov.br ou CEF/BB para verificar PIS/PASEP."

    @staticmethod
    def _estimate_abono(monthly_income: float) -> float:
        salario_minimo = 1412.0
        if monthly_income <= salario_minimo:
            return salario_minimo
        months_worked = 12
        return round((months_worked / 12) * salario_minimo, 2)
