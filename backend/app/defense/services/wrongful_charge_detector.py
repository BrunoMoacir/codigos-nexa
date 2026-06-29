"""
app/defense/services/wrongful_charge_detector.py — D2: Cobranças Indevidas

Detecta:
  - Tarifas duplicadas no mesmo mês (mesmo banco + fee_type)
  - Cobranças de bancos sem transações recentes (conta não encerrada)
  - Tarifas novas sem histórico anterior

Base legal: Resolução BACEN 3.919/2010 — vedada cobrança não prevista em contrato.
            CDC art. 42 — vedada cobrança de dívida já paga ou indevida.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

_LEGAL_BASIS = (
    "Resolução BACEN 3.919/2010 — tarifa não prevista em contrato é vedada. "
    "CDC art. 42 — consumidor não pode ser cobrado indevidamente. "
    "Prazo de contestação: até 5 dias úteis após o lançamento."
)

_ACTION = (
    "1. Reúna extrato bancário com os lançamentos duplicados ou indevidos.\n"
    "2. Abra reclamação formal no banco (guarde número de protocolo).\n"
    "3. Se não resolvido em 5 dias úteis: Banco Central (bcb.gov.br/meubc) ou PROCON.\n"
    "4. Para valores acima de R$ 20: Juizado Especial Cível (gratuito, sem advogado)."
)


class WrongfulChargeDetector:
    """D2 — Detecta cobranças indevidas: duplicatas, pós-cancelamento, sem contrato."""

    _STALE_DAYS = 60   # banco considerado inativo se sem transação por N dias

    def detect(self, user_id: str) -> list[DefenseFinding]:
        findings: list[DefenseFinding] = []
        findings.extend(self._check_duplicates(user_id))
        findings.extend(self._check_stale_banks(user_id))
        findings.extend(self._check_new_fees(user_id))
        logger.info("[D2] user=%s → %d achados", user_id, len(findings))
        return findings

    # ── D2a: Duplicatas ───────────────────────────────────────────────

    def _check_duplicates(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            current_month = date.today().strftime("%Y-%m")
            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, fee_type, COUNT(*) as cnt, SUM(amount) as total"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid AND month = :month"
                        " GROUP BY bank_name, fee_type"
                        " HAVING COUNT(*) > 1"
                        " ORDER BY total DESC"
                    ),
                    {"uid": user_id, "month": current_month},
                ).fetchall()

            findings = []
            for bank, ftype, cnt, total in rows:
                findings.append(DefenseFinding(
                    detector="D2",
                    severity="high",
                    bank_name=bank,
                    title=f"Tarifa duplicada — {ftype.replace('_', ' ')} ({cnt}x)",
                    description=(
                        f"{bank} cobrou {ftype.replace('_', ' ').lower()} "
                        f"{cnt} vezes no mesmo mês, total R$ {float(total):.2f}. "
                        "Apenas uma cobrança deveria ocorrer por período."
                    ),
                    amount_disputed=round(float(total) * (cnt - 1) / cnt, 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Mês: {current_month}",
                        f"Banco: {bank}",
                        f"Tipo: {ftype}",
                        f"Ocorrências: {cnt}x",
                        f"Total cobrado: R$ {float(total):.2f}",
                        f"Valor contestável (excedente): R$ {float(total) * (cnt-1)/cnt:.2f}",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D2] _check_duplicates: %s", exc)
            return []

    # ── D2b: Bancos sem transações recentes ainda cobrando ────────────

    def _check_stale_banks(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.core.database import SessionLocal
            from sqlalchemy import text
            import polars as pl

            df = get_transactions_for_user(user_id)
            cutoff = date.today() - timedelta(days=self._STALE_DAYS)

            if df.is_empty() or "bank_name" not in df.columns:
                return []

            date_col = "transaction_date" if "transaction_date" in df.columns else "date"
            active_banks: set[str] = set(
                df.filter(pl.col(date_col) >= cutoff)
                  .select("bank_name")
                  .unique()["bank_name"]
                  .to_list()
            )

            current_month = date.today().strftime("%Y-%m")
            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, SUM(amount) as total"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid AND month = :month"
                        " GROUP BY bank_name"
                    ),
                    {"uid": user_id, "month": current_month},
                ).fetchall()

            stale = [(b, float(t)) for b, t in rows if b not in active_banks]

            findings = []
            for bank, total in stale:
                findings.append(DefenseFinding(
                    detector="D2",
                    severity="high",
                    bank_name=bank,
                    title=f"Cobrança pós-inatividade — {bank}",
                    description=(
                        f"{bank} cobrou R$ {total:.2f} este mês sem nenhuma "
                        f"transação nos últimos {self._STALE_DAYS} dias. "
                        "Pode indicar conta não encerrada ou cobrança indevida."
                    ),
                    amount_disputed=round(total, 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=(
                        "1. Verifique se a conta foi de fato encerrada.\n"
                        "2. Solicite certidão de quitação e encerramento por escrito.\n"
                        "3. Exija estorno de todas as cobranças após a data de encerramento."
                    ),
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Total cobrado no mês: R$ {total:.2f}",
                        f"Última transação: mais de {self._STALE_DAYS} dias atrás",
                        "Ausência de transações = possível conta encerrada ou cancelada",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D2] _check_stale_banks: %s", exc)
            return []

    # ── D2c: Tarifas novas sem histórico ──────────────────────────────

    def _check_new_fees(self, user_id: str) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.costs.bank_fee_analyzer import BankFeeAnalyzer

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            report = BankFeeAnalyzer().analyze(df, user_id=user_id)
            new_fees = BankFeeAnalyzer.detect_new_fees(user_id, report.entries)

            # Filtra apenas tipos não classificados como D1 (seguro embutido)
            d1_types = {"SEGURO_EMBUTIDO", "SEGURO_PRESTAMISTA", "TARIFA_CADASTRO"}
            new_fees = [f for f in new_fees if f.fee_type.value not in d1_types]

            findings = []
            for fee in new_fees:
                findings.append(DefenseFinding(
                    detector="D2",
                    severity="medium",
                    bank_name=fee.bank_name,
                    title=f"Tarifa nova sem histórico — {fee.fee_type.value.replace('_', ' ')}",
                    description=(
                        f"{fee.bank_name} cobrou {fee.fee_type.value.replace('_', ' ').lower()} "
                        f"(R$ {fee.amount:.2f}) pela primeira vez — sem registros anteriores. "
                        "Tarifas novas exigem notificação prévia de 30 dias."
                    ),
                    amount_disputed=float(fee.amount),
                    legal_basis=(
                        "Resolução BACEN 3.919/2010, art. 3º — alterações de tarifas devem "
                        "ser comunicadas ao cliente com 30 dias de antecedência."
                    ),
                    recommended_action=(
                        "1. Solicite ao banco o contrato ou aditivo que prevê essa tarifa.\n"
                        "2. Exija comprovante da notificação prévia de 30 dias.\n"
                        "3. Se não houver notificação, solicite estorno e registre no BACEN."
                    ),
                    evidence_points=[
                        f"Banco: {fee.bank_name}",
                        f"Tipo: {fee.fee_type.value}",
                        f"Valor: R$ {fee.amount:.2f}",
                        "Sem ocorrências anteriores no histórico bank_fee_history",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D2] _check_new_fees: %s", exc)
            return []
