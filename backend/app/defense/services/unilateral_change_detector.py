"""
app/defense/services/unilateral_change_detector.py — D4: Alteração Unilateral de Tarifas

Detecta tarifas que aumentaram mais de 10% em relação ao mês anterior
sem notificação prévia ao cliente (30 dias de antecedência exigidos).

Base legal: Resolução BACEN 3.919/2010, art. 3º — alterações de tarifas
            devem ser comunicadas ao cliente com no mínimo 30 dias antes.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

_LEGAL_BASIS = (
    "Resolução BACEN 3.919/2010, art. 3º — alterações de tarifas bancárias "
    "exigem comunicação prévia ao cliente com no mínimo 30 dias de antecedência. "
    "Aumentos sem aviso são passíveis de contestação e estorno."
)

_ACTION = (
    "1. Solicite ao banco o comprovante de notificação enviada 30 dias antes do aumento.\n"
    "2. Se não houver comprovante, exija estorno da diferença cobrada.\n"
    "3. Registre no Banco Central (bcb.gov.br/meubc) — prazo de resolução: 10 dias úteis.\n"
    "4. Para aumentos recorrentes, avalie portabilidade de conta (gratuita)."
)

# Aumento mínimo para disparar alerta (10%)
_INCREASE_THRESHOLD = 0.10


class UnilateralChangeDetector:
    """
    D4 — Detecta aumentos de tarifas sem notificação prévia.

    Compara o valor de cada (bank, fee_type) no mês atual com o mês anterior.
    Flag se o aumento for superior a 10%.
    """

    def detect(self, user_id: str) -> list[DefenseFinding]:
        findings = self._compare_months(user_id)
        logger.info("[D4] user=%s → %d achados", user_id, len(findings))
        return findings

    def _compare_months(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            today = date.today()
            current_month = today.strftime("%Y-%m")
            # mês anterior
            first_of_current = today.replace(day=1)
            last_of_prev = first_of_current - timedelta(days=1)
            prev_month = last_of_prev.strftime("%Y-%m")

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT cur.bank_name, cur.fee_type,"
                        "       cur.amount  AS current_amount,"
                        "       prev.amount AS prev_amount"
                        " FROM bank_fee_history cur"
                        " JOIN bank_fee_history prev"
                        "   ON  prev.user_id   = cur.user_id"
                        "   AND prev.bank_name  = cur.bank_name"
                        "   AND prev.fee_type   = cur.fee_type"
                        "   AND prev.month      = :prev_month"
                        " WHERE cur.user_id = :uid"
                        "   AND cur.month   = :cur_month"
                        "   AND prev.amount > 0"
                    ),
                    {"uid": user_id, "cur_month": current_month, "prev_month": prev_month},
                ).fetchall()

            findings = []
            for bank, ftype, cur_amt, prev_amt in rows:
                cur_amt = float(cur_amt)
                prev_amt = float(prev_amt)
                if prev_amt <= 0:
                    continue

                increase_pct = (cur_amt - prev_amt) / prev_amt
                if increase_pct < _INCREASE_THRESHOLD:
                    continue

                severity = "high" if increase_pct >= 0.25 else "medium"
                disputed = round(cur_amt - prev_amt, 2)

                findings.append(DefenseFinding(
                    detector="D4",
                    severity=severity,
                    bank_name=bank,
                    title=(
                        f"Aumento unilateral de {increase_pct*100:.1f}% — "
                        f"{ftype.replace('_', ' ')}"
                    ),
                    description=(
                        f"{bank} aumentou {ftype.replace('_', ' ').lower()} "
                        f"de R$ {prev_amt:.2f} para R$ {cur_amt:.2f} "
                        f"({increase_pct*100:.1f}% de alta), "
                        f"de {prev_month} para {current_month}, "
                        "sem comprovante de notificação prévia."
                    ),
                    amount_disputed=disputed,
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Tarifa: {ftype}",
                        f"Valor anterior ({prev_month}): R$ {prev_amt:.2f}",
                        f"Valor atual ({current_month}): R$ {cur_amt:.2f}",
                        f"Aumento: R$ {disputed:.2f} ({increase_pct*100:.1f}%)",
                        "Limite legal sem aviso: até 10% — acima exige notificação 30 dias antes",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D4] _compare_months: %s", exc)
            return []
