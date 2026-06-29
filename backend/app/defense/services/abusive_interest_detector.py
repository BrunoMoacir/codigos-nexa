"""
app/defense/services/abusive_interest_detector.py — D3: Juros Abusivos

Compara taxas de juros pagas pelo usuário com as taxas médias de mercado
publicadas pelo BACEN (SGS séries 20714/20715/20706).

Base legal: CDC art. 51, IV — cláusulas abusivas são nulas de pleno direito.
            Resolução BACEN 3.401/2006 — portabilidade de crédito gratuita.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

_INTEREST_PATTERN = re.compile(
    r"\b(juro|encargo|rotativo|cheque especial|limite especial|financiamento)\b",
    re.IGNORECASE,
)

_LEGAL_BASIS = (
    "CDC art. 51, IV — cláusulas desproporcionais são abusivas e nulas. "
    "Resolução BACEN 3.401/2006 — portabilidade de crédito gratuita. "
    "Referência: BACEN SGS séries 20714 (rotativo PF) e 20706 (cheque especial)."
)

_ACTION = (
    "1. Solicite portabilidade de crédito — gratuita por lei (Res. BACEN 3.401/2006).\n"
    "2. Use o Negociador Nexa para gerar roteiro de negociação personalizado.\n"
    "3. Se o banco negar redução, registre no Banco Central (bcb.gov.br/meubc).\n"
    "4. Para rotativo acumulado, avalie parcelamento ou crédito pessoal com taxa menor."
)

# Fallback quando BACEN SGS estiver indisponível
_FALLBACK_RATES = {
    "rotativo_monthly": 0.1567,      # 15.67% a.m.
    "rotativo_max_monthly": 0.1770,  # 17.70% a.m.
    "cheque_especial_monthly": 0.1080,
}


class AbusiveInterestDetector:
    """D3 — Detecta juros acima da taxa média de mercado (BACEN SGS)."""

    def detect(self, user_id: str) -> list[DefenseFinding]:
        market = self._get_market_rates()
        findings: list[DefenseFinding] = []
        findings.extend(self._check_from_negotiation_history(user_id, market))
        findings.extend(self._check_from_transactions(user_id, market))
        logger.info("[D3] user=%s → %d achados", user_id, len(findings))
        return findings

    # ── D3a: via negotiation_history (triggers já detectados) ─────────

    def _check_from_negotiation_history(
        self, user_id: str, market: dict
    ) -> list[DefenseFinding]:
        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            cutoff = date.today() - timedelta(days=90)
            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, trigger_type, potential_gain"
                        " FROM negotiation_history"
                        " WHERE user_id = :uid"
                        "   AND trigger_type IN ('JUROS_ROTATIVO_ALTO', 'CHEQUE_ESPECIAL_ALTO')"
                        "   AND generated_at >= :cutoff"
                        " ORDER BY potential_gain DESC LIMIT 10"
                    ),
                    {"uid": user_id, "cutoff": cutoff},
                ).fetchall()

            findings = []
            for bank, trigger, gain in rows:
                is_rotativo = "ROTATIVO" in trigger
                ref_rate = market["rotativo_monthly"] if is_rotativo else market["cheque_especial_monthly"]
                ref_label = "crédito rotativo PF" if is_rotativo else "cheque especial"
                findings.append(DefenseFinding(
                    detector="D3",
                    severity="high",
                    bank_name=bank,
                    title=f"Juros acima da média BACEN — {ref_label}",
                    description=(
                        f"{bank} cobra {trigger.replace('_', ' ').lower()} "
                        f"com economia potencial de R$ {float(gain):.2f}/mês "
                        f"se reduzido à taxa média BACEN ({ref_rate*100:.2f}% a.m.)."
                    ),
                    amount_disputed=round(float(gain) * 12, 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Gatilho: {trigger}",
                        f"Economia mensal estimada: R$ {float(gain):.2f}",
                        f"Referência BACEN SGS: {ref_rate*100:.2f}% a.m. (média mercado)",
                        "Dados: negotiation_history + BACEN SGS",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D3] _check_from_negotiation_history: %s", exc)
            return []

    # ── D3b: via transações (palavras-chave de juros) ─────────────────

    def _check_from_transactions(
        self, user_id: str, market: dict
    ) -> list[DefenseFinding]:
        try:
            from app.core.db.queries import get_transactions_for_user
            import polars as pl

            df = get_transactions_for_user(user_id)
            if df.is_empty():
                return []

            desc_col = "description" if "description" in df.columns else None
            bank_col = "bank_name" if "bank_name" in df.columns else None
            if not desc_col:
                return []

            interest_rows = []
            for row in df.filter(pl.col("amount") < 0).iter_rows(named=True):
                desc = row.get(desc_col, "") or ""
                if _INTEREST_PATTERN.search(_normalize(desc)):
                    bank = row.get(bank_col, "Banco") if bank_col else "Banco"
                    amount = abs(row.get("amount", 0.0))
                    interest_rows.append((bank, desc[:80], amount))

            if not interest_rows:
                return []

            # Agrupa por banco
            from collections import defaultdict
            by_bank: dict[str, list[tuple[str, float]]] = defaultdict(list)
            for bank, desc, amount in interest_rows[:20]:
                by_bank[bank].append((desc, amount))

            findings = []
            ref_rate = market["rotativo_monthly"]
            for bank, items in by_bank.items():
                total = sum(a for _, a in items)
                findings.append(DefenseFinding(
                    detector="D3",
                    severity="medium",
                    bank_name=bank,
                    title=f"Cobrança de juros detectada — {bank}",
                    description=(
                        f"{len(items)} lançamento(s) de juros em {bank} "
                        f"totalizando R$ {total:.2f}. "
                        f"Taxa referência BACEN: {ref_rate*100:.2f}% a.m. (rotativo PF)."
                    ),
                    amount_disputed=round(total, 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Ocorrências: {len(items)}",
                        f"Total: R$ {total:.2f}",
                        *[f"• {d}: R$ {a:.2f}" for d, a in items[:5]],
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D3] _check_from_transactions: %s", exc)
            return []

    @staticmethod
    def _get_market_rates() -> dict:
        try:
            from app.architect.connectors.bacen_credit import BacenCreditConnector
            return BacenCreditConnector().get_rates()
        except Exception as exc:
            logger.debug("[D3] BacenCreditConnector fallback: %s", exc)
            return _FALLBACK_RATES


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
