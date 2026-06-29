"""
app/rights/services/fgts_checker.py — FGTS Esquecido

Não existe API pública para consultar saldo FGTS por CPF sem autenticação
via GOV.BR / app FGTS (CEF).

Esta implementação:
  - analisa transações para detectar padrões de renda CLT (salário regular);
  - estima a contribuição FGTS teórica (8% do salário bruto × meses) como
    indicativo de relevância — NÃO é o saldo real, que só a CEF tem;
  - orienta o usuário ao app FGTS ou agência CEF.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Optional

from app.rights.models import ForgottenRight

logger = logging.getLogger(__name__)

_CLT_KEYWORDS = re.compile(
    r"\b(salario|salário|folha|pagamento|holerite|vencimento|remuneracao|remuneração|clt)\b",
    re.IGNORECASE,
)

_FGTS_RATE = 0.08  # 8% do salário bruto — alíquota padrão CLT


class FgtsChecker:
    """
    Detecta se o usuário provavelmente tem vínculo CLT e estima contribuição FGTS.
    """

    def check(self, user_id: str) -> ForgottenRight:
        monthly_salary, months_detected, reason = self._detect_salary(user_id)

        if monthly_salary and monthly_salary > 0:
            estimated = round(monthly_salary * _FGTS_RATE * months_detected, 2)
            confidence = "medium" if months_detected >= 3 else "low"
        else:
            estimated = None
            confidence = "unknown"

        return ForgottenRight(
            category="fgts",
            title="FGTS — Fundo de Garantia por Tempo de Serviço",
            description=(
                "Saldo de contas FGTS de empregos anteriores (inclusive empresas extintas ou falidas). "
                "O FGTS pode ser sacado em demissão sem justa causa, aposentadoria, compra do imóvel "
                "ou doenças graves. Contas de empregos anteriores ficam ativas indefinidamente."
            ),
            estimated_amount=estimated,
            estimated_confidence=confidence,
            relevance_reason=reason,
            official_channel="App FGTS (CEF) ou agência Caixa Econômica Federal",
            official_url="https://www.fgts.gov.br",
            action_steps=[
                "Baixe o app 'FGTS' da Caixa Econômica Federal (iOS/Android).",
                "Faça login com CPF e senha Caixa ou GOV.BR.",
                "Consulte 'Meus contratos' para ver contas ativas de empregos antigos.",
                "Para empresas extintas: vá presencialmente à agência CEF com CTPS e documentos.",
                "Saque-aniversário: avalie se a modalidade atual ainda é vantajosa para seu perfil.",
            ],
            warning=(
                f"Estimativa Nexa (R$ {estimated:,.2f}) baseada em {months_detected} meses de salário detectado × 8%. "
                "O saldo real inclui correção TR + 3% a.a. e só a Caixa tem o extrato completo."
            ) if estimated else None,
        )

    def _detect_salary(self, user_id: str) -> tuple[Optional[float], int, str]:
        try:
            from app.core.db.queries import get_transactions_for_user
            import polars as pl

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return None, 0, "Sem transações disponíveis. Verifique o app FGTS para histórico de empregos."

            date_col = "transaction_date" if "transaction_date" in df.columns else "date"
            desc_col = "description" if "description" in df.columns else None

            # Últimos 6 meses
            cutoff = date.today() - timedelta(days=180)
            df_recent = df.filter(pl.col(date_col) >= cutoff)

            income = df_recent.filter(pl.col("amount") > 0)

            # Filtra por descrição CLT se disponível
            if desc_col and desc_col in df_recent.columns:
                salary_rows = income.filter(
                    pl.col(desc_col).str.contains(r"(?i)(salario|salário|folha|pagamento|clt|vencimento)")
                )
                if salary_rows.height > 0:
                    avg_salary = round(float(salary_rows["amount"].mean()), 2)
                    months = salary_rows.height
                    return avg_salary, min(months, 6), (
                        f"Detectados {months} crédito(s) com padrão salarial CLT "
                        f"(média R$ {avg_salary:,.2f}/mês nos últimos 6 meses)."
                    )

            # Heurística: depósitos regulares mensais de valor similar
            monthly = (
                income
                .with_columns(
                    pl.col(date_col).dt.strftime("%Y-%m").alias("month")
                )
                .group_by("month")
                .agg(pl.col("amount").max().alias("max_deposit"))
                .sort("month")
            )
            if monthly.height >= 3:
                deposits = monthly["max_deposit"].to_list()
                avg = sum(deposits) / len(deposits)
                variability = max(abs(d - avg) / avg for d in deposits if avg > 0)
                if variability < 0.15 and avg > 800:
                    return round(avg, 2), monthly.height, (
                        f"Detectados depósitos mensais regulares com pouca variação "
                        f"(média R$ {avg:,.2f}/mês) — possível vínculo CLT."
                    )

            return None, 0, (
                "Padrão CLT não identificado nas transações recentes. "
                "Se teve empregos anteriores, consulte o app FGTS mesmo assim."
            )

        except Exception as exc:
            logger.warning("[FgtsChecker] user=%s: %s", user_id, exc)
            return None, 0, "Verifique o app FGTS (CEF) para confirmar saldos de empregos anteriores."
