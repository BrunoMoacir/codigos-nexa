"""
app/defense/services/tied_sale_detector.py — D1: Venda Casada

Detecta seguros embutidos e outros produtos vinculados ilegalmente a crédito.
Base legal: Resolução BACEN 3.919/2010, art. 2º — proíbe condicionamento de crédito
            à contratação de seguro ou outros produtos/serviços.
"""

from __future__ import annotations

import logging
from datetime import date

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

_TIED_FEE_TYPES = {
    "SEGURO_EMBUTIDO":    "Seguro embutido em produto de crédito (venda casada)",
    "SEGURO_PRESTAMISTA": "Seguro prestamista vinculado a crédito",
    "TARIFA_CADASTRO":    "Tarifa de cadastro sem contratação explícita",
}

_LEGAL_BASIS = (
    "Resolução BACEN 3.919/2010, art. 2º — vedada a exigência ou vinculação de "
    "qualquer produto ou serviço como condição para concessão de crédito."
)

_ACTION = (
    "1. Solicite ao banco o cancelamento imediato e reembolso retroativo.\n"
    "2. Se o banco negar, registre reclamação no Banco Central: bcb.gov.br/meubc.\n"
    "3. Para valores acumulados, acione o PROCON ou Juizado Especial Cível (gratuito até 20 SM)."
)


class TiedSaleDetector:
    """D1 — Detecta venda casada: seguros embutidos em operações de crédito."""

    def detect(self, user_id: str) -> list[DefenseFinding]:
        findings: list[DefenseFinding] = []

        # ── 1. Análise via BankFeeAnalyzer (snapshot atual) ──────────
        findings.extend(self._check_fee_analyzer(user_id))

        # ── 2. Histórico em bank_fee_history ─────────────────────────
        findings.extend(self._check_fee_history(user_id))

        # Deduplica por banco + título
        seen: set[tuple[str, str]] = set()
        unique: list[DefenseFinding] = []
        for f in findings:
            key = (f.bank_name, f.title)
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("[D1] user=%s → %d achados", user_id, len(unique))
        return unique

    def _check_fee_analyzer(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.costs.bank_fee_analyzer import BankFeeAnalyzer

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            report = BankFeeAnalyzer().analyze(df, user_id=user_id)
            findings = []
            for entry in report.entries:
                fee_key = entry.fee_type.value
                if fee_key in _TIED_FEE_TYPES:
                    findings.append(DefenseFinding(
                        detector="D1",
                        severity="high",
                        bank_name=entry.bank_name,
                        title=_TIED_FEE_TYPES[fee_key],
                        description=(
                            f"{entry.bank_name} cobrou R$ {entry.amount:.2f} "
                            f"em {fee_key.replace('_', ' ').lower()} "
                            f"detectado na análise de tarifas atual."
                        ),
                        amount_disputed=float(entry.amount),
                        legal_basis=_LEGAL_BASIS,
                        recommended_action=_ACTION,
                        evidence_points=[
                            f"Tipo de tarifa: {fee_key}",
                            f"Valor: R$ {entry.amount:.2f}",
                            f"Banco: {entry.bank_name}",
                            entry.description or "",
                        ],
                    ))
            return findings
        except Exception as exc:
            logger.debug("[D1] _check_fee_analyzer: %s", exc)
            return []

    def _check_fee_history(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, fee_type, SUM(amount) as total, COUNT(*) as months"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid"
                        f"  AND fee_type IN ({', '.join(repr(k) for k in _TIED_FEE_TYPES)})"
                        " GROUP BY bank_name, fee_type"
                        " ORDER BY total DESC"
                    ),
                    {"uid": user_id},
                ).fetchall()

            findings = []
            for bank, ftype, total, months in rows:
                label = _TIED_FEE_TYPES.get(ftype, ftype)
                findings.append(DefenseFinding(
                    detector="D1",
                    severity="high",
                    bank_name=bank,
                    title=f"{label} — histórico {months} mês(es)",
                    description=(
                        f"{bank} cobrou {ftype.replace('_', ' ').lower()} "
                        f"por {months} mês(es), totalizando R$ {float(total):.2f}."
                    ),
                    amount_disputed=round(float(total), 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Tipo: {ftype}",
                        f"Meses cobrados: {months}",
                        f"Total acumulado: R$ {float(total):.2f}",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D1] _check_fee_history: %s", exc)
            return []
