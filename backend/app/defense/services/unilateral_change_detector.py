"""
app/defense/services/unilateral_change_detector.py — D4: Alteração Unilateral de Tarifas

Detecta tarifas que aumentaram sem comprovante de notificação prévia ao cliente.

Base legal:
  Res. CMN 3.919/2010, art. 3º — qualquer alteração de tarifa exige comunicação
  prévia ao cliente com no mínimo 30 dias de antecedência.
  CDC art. 51 — cláusulas que permitem modificação unilateral sem previsão
  contratual são nulas de pleno direito.

IMPORTANTE: qualquer aumento, independentemente do percentual, pode ser
contestável se não houver comprovante de aviso prévio. O percentual define
apenas a SEVERIDADE do achado — não sua existência.
Nunca escrever "limite legal sem aviso: 10%" — isso está juridicamente errado.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.defense.models import DefenseFinding
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

_LEGAL_BASIS = (
    "Res. CMN 3.919/2010, art. 3º — qualquer alteração de tarifa bancária "
    "exige comunicação prévia ao cliente com no mínimo 30 dias de antecedência. "
    "CDC art. 51 — cláusulas que permitem modificação unilateral sem previsão contratual "
    "são nulas de pleno direito. Súmula 297/STJ — CDC aplica-se a bancos."
)

_ACTION = (
    "1. Solicite ao banco o comprovante de notificação enviada 30 dias antes do aumento.\n"
    "2. Se não houver comprovante, exija estorno da diferença cobrada indevidamente.\n"
    "3. Registre no Banco Central (bcb.gov.br/meubc) — prazo de resolução: 10 dias úteis.\n"
    "4. Para aumentos recorrentes, avalie portabilidade de conta (gratuita por lei)."
)


def _severity_from_pct(increase_pct: float) -> str:
    """
    O percentual decide SEVERIDADE, não existência do achado.
    Qualquer aumento sem aviso prévio é contestável.
    """
    if increase_pct >= 0.25:
        return "high"
    if increase_pct >= 0.10:
        return "medium"
    return "low"


class UnilateralChangeDetector:
    """
    D4 — Detecta aumentos de tarifas sem notificação prévia.

    CORREÇÃO JURÍDICA v2: qualquer aumento (> 0%) sem aviso prévio de 30 dias
    é contestável. O percentual determina severidade (low/medium/high),
    não a existência do achado.
    Integra Olinda Tarifas quando disponível para verificar teto oficial por IF.
    """

    def detect(self, user_id: str) -> list[DefenseFinding]:
        findings: list[DefenseFinding] = []
        findings.extend(self._compare_months(user_id))
        findings.extend(self._check_above_bacen_ceiling(user_id))
        # Deduplica por banco + tarifa
        seen: set[tuple[str, str]] = set()
        unique = []
        for f in findings:
            key = (f.bank_name, f.title)
            if key not in seen:
                seen.add(key)
                unique.append(f)
        logger.info("[D4] user=%s → %d achados", user_id, len(unique))
        return unique

    # ── D4a: Compara mês atual vs anterior ────────────────────────────

    def _compare_months(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            today = date.today()
            current_month = today.strftime("%Y-%m")
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
                cur_amt  = float(cur_amt)
                prev_amt = float(prev_amt)
                if prev_amt <= 0 or cur_amt <= prev_amt:
                    continue  # sem aumento — não é achado

                increase_pct = (cur_amt - prev_amt) / prev_amt
                severity  = _severity_from_pct(increase_pct)
                disputed  = round(cur_amt - prev_amt, 2)

                findings.append(DefenseFinding(
                    detector="D4",
                    severity=severity,
                    bank_name=bank,
                    title=(
                        f"Aumento de tarifa sem aviso verificado — "
                        f"{ftype.replace('_', ' ')} (+{numero(increase_pct*100, 1)}%)"
                    ),
                    description=(
                        f"{bank} aumentou '{ftype.replace('_', ' ').lower()}' "
                        f"de {brl(prev_amt)} para {brl(cur_amt)} "
                        f"(+{numero(increase_pct*100, 1)}%, {brl(disputed)} a mais) "
                        f"de {prev_month} para {current_month}. "
                        f"Qualquer aumento exige notificação prévia de 30 dias "
                        f"(Res. CMN 3.919/2010, art. 3º) — solicite o comprovante."
                    ),
                    amount_disputed=disputed,
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Tarifa: {ftype}",
                        f"Valor anterior ({prev_month}): {brl(prev_amt)}",
                        f"Valor atual ({current_month}): {brl(cur_amt)}",
                        f"Aumento: {brl(disputed)} (+{numero(increase_pct*100, 1)}%)",
                        "Qualquer aumento sem aviso prévio de 30 dias é contestável.",
                        "Solicite comprovante de notificação ao banco.",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D4] _compare_months: %s", exc)
            return []

    # ── D4b: Tarifa acima do teto BACEN/Olinda ─────────────────────────

    def _check_above_bacen_ceiling(self, user_id: str) -> list[DefenseFinding]:
        """
        Verifica se o valor cobrado excede o ValorMaximo registrado no BACEN
        para aquela IF e código de serviço (via OlindaBankFeeConnector).
        Alta severidade — evidência objetiva e direta.
        """
        try:
            from app.architect.connectors.olinda_bank_fee import OlindaBankFeeConnector
            from app.core.database import SessionLocal
            from sqlalchemy import text

            connector = OlindaBankFeeConnector()
            current_month = date.today().strftime("%Y-%m")

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, fee_type, amount"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid AND month = :month"
                    ),
                    {"uid": user_id, "month": current_month},
                ).fetchall()

            findings = []
            for bank, ftype, amount in rows:
                amount_f = float(amount)
                ceiling = connector.get_max_fee(bank_name=bank, fee_code=ftype)
                if ceiling is None or amount_f <= ceiling:
                    continue

                excedente = round(amount_f - ceiling, 2)
                findings.append(DefenseFinding(
                    detector="D4",
                    severity="high",
                    bank_name=bank,
                    title=f"Tarifa acima do teto BACEN — {ftype.replace('_', ' ')}",
                    description=(
                        f"{bank} cobrou {brl(amount_f)} por "
                        f"'{ftype.replace('_', ' ').lower()}', "
                        f"acima do valor máximo registrado no BACEN "
                        f"({brl(ceiling)}). "
                        f"Excedente: {brl(excedente)}. "
                        f"Evidência objetiva via Olinda BACEN Tarifas."
                    ),
                    amount_disputed=excedente,
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Tarifa: {ftype}",
                        f"Valor cobrado: {brl(amount_f)}",
                        f"Teto BACEN (Olinda): {brl(ceiling)}",
                        f"Excedente contestável: {brl(excedente)}",
                        "Fonte: BACEN Olinda ListaTarifasPorInstituicaoFinanceira",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D4] _check_above_bacen_ceiling: %s", exc)
            return []
