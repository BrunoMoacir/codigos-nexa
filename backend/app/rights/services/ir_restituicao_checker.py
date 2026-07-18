"""
app/rights/services/ir_restituicao_checker.py — Restituição de Imposto de Renda

Escaneia transações em busca de "IR RETIDO NA FONTE" (IRRF) para estimar
o montante retido. A restituição real depende das deduções declaradas —
esta é apenas uma estimativa de base.

Canal oficial: e-CAC / app Meu Imposto de Renda (Receita Federal).
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Optional

from app.rights.models import ForgottenRight

logger = logging.getLogger(__name__)

_IR_KEYWORDS = re.compile(
    r"\b(ir retido|irrf|imposto renda|ir fonte|imposto de renda retido|ret fonte|ret ir)\b",
    re.IGNORECASE,
)

_COMMON_DEDUCTIONS = [
    "Despesas médicas (plano de saúde, consultas, exames)",
    "Previdência privada PGBL (até 12% da renda bruta)",
    "Dependentes (filhos, cônjuge, pais em certas condições)",
    "Despesas educacionais (teto R$ 3.561,50/dependente em 2024)",
    "Contribuição ao INSS (automaticamente deduzida)",
]


class IrRestituicaoChecker:
    """
    Estima IRRF retido na fonte a partir de transações e orienta a verificação
    da restituição via canais da Receita Federal.
    """

    def check(self, user_id: str) -> ForgottenRight:
        irrf_total, months, reason = self._scan_irrf_transactions(user_id)
        income_annual, _ = self._estimate_annual_income(user_id)

        if irrf_total and irrf_total > 0:
            estimated = irrf_total
            confidence = "medium" if months >= 3 else "low"
        elif income_annual and income_annual > 28_559.70:  # faixa tributável mínima 2024
            estimated = round(income_annual * 0.075, 2)  # alíquota média estimada
            confidence = "low"
            reason = (
                f"Renda anual estimada R$ {income_annual:,.2f} — "
                "acima do limite de isenção, provável IR retido na fonte. "
                "Deduções (saúde, previdência, dependentes) podem gerar restituição."
            )
        else:
            estimated = None
            confidence = "unknown"

        return ForgottenRight(
            category="ir_restituicao",
            title="Restituição de Imposto de Renda (IRPF)",
            description=(
                "IR retido na fonte acima do devido é restituído após a entrega da declaração anual. "
                "Despesas dedutíveis frequentemente esquecidas aumentam a restituição. "
                "Restituições não resgatadas ficam disponíveis por 5 anos."
            ),
            estimated_amount=estimated,
            estimated_confidence=confidence,
            relevance_reason=reason,
            official_channel="App Meu Imposto de Renda (Receita Federal) · e-CAC",
            official_url="https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda",
            action_steps=[
                "Consulte em tempo real pela Nexa: gere uma Autorização de Compartilhamento "
                "no e-CAC (Compartilha Receita Federal) e cole o token no app.",
                "Alternativa: baixe o app 'Meu Imposto de Renda' (iOS/Android) ou acesse o e-CAC.",
                "Consulte o extrato da declaração para ver se há restituição pendente.",
                "Se constar 'em análise' há mais de 60 dias, acesse 'Consultar Impugnação/Autuação'.",
                "Verifique deduções esquecidas: " + " · ".join(_COMMON_DEDUCTIONS[:3]) + ".",
                "Restituições de até 5 anos anteriores podem ser recuperadas se a declaração foi entregue.",
            ],
            warning=(
                "Estimativa Nexa baseada em IRRF detectado nas transações (R$ "
                f"{irrf_total:,.2f} em {months} lançamentos). "
                "O valor real depende das deduções declaradas."
            ) if irrf_total else None,
        )

    def _scan_irrf_transactions(self, user_id: str) -> tuple[Optional[float], int, str]:
        try:
            from app.core.db.queries import get_transactions_for_user
            import polars as pl

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return None, 0, "Sem transações disponíveis para análise de IRRF."

            desc_col = next(
                (c for c in ("description", "memo", "name") if c in df.columns), None
            )
            if not desc_col:
                return None, 0, "Descrições de transações não disponíveis para análise de IRRF."

            date_col = "transaction_date" if "transaction_date" in df.columns else "date"
            cutoff = date.today() - timedelta(days=365)
            df_year = df.filter(pl.col(date_col) >= cutoff)

            ir_rows = df_year.filter(
                pl.col(desc_col).str.contains(r"(?i)(ir retido|irrf|imposto renda|ret ir|ret fonte)")
            )

            if ir_rows.is_empty():
                return None, 0, "Nenhum IRRF retido detectado nas transações do último ano."

            total = abs(float(ir_rows["amount"].sum()))
            count = ir_rows.height
            return round(total, 2), count, (
                f"Detectados {count} lançamento(s) de IRRF nas transações "
                f"(total R$ {total:,.2f} no último ano)."
            )

        except Exception as exc:
            logger.warning("[IrRestituicaoChecker] user=%s: %s", user_id, exc)
            return None, 0, "Consulte o app Meu Imposto de Renda para verificar restituições pendentes."

    def _estimate_annual_income(self, user_id: str) -> tuple[Optional[float], str]:
        try:
            from app.core.db.queries import get_transactions_for_user
            import polars as pl

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return None, "Sem dados."

            date_col = "transaction_date" if "transaction_date" in df.columns else "date"
            cutoff = date.today() - timedelta(days=365)
            income = (
                df.filter(pl.col(date_col) >= cutoff)
                .filter(pl.col("amount") > 0)
            )
            if income.is_empty():
                return None, "Sem créditos no último ano."

            total = float(income["amount"].sum())
            return round(total, 2), f"Renda bruta anual estimada: R$ {total:,.2f}."

        except Exception:
            return None, "Não foi possível estimar renda anual."
