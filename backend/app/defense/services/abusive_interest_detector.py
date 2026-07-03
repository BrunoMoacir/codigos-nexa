"""
app/defense/services/abusive_interest_detector.py — D3: Juros Abusivos

Compara taxas de juros pagas pelo usuário com as taxas médias de mercado
publicadas pelo BACEN (SGS séries 20714/20706) e Olinda taxaJuros v2 por IF.

Base legal:
  REsp 1.061.530/RS (Tema 27/STJ) — taxa média BACEN é o referencial de
  abusividade; análise do caso concreto é necessária.
  STJ Terceira Turma (2023) — ultrapassar 1,5x/3x a média, por si só, não
  configura abusividade automática; exige análise do caso concreto.
  CDC art. 51, IV — cláusulas desproporcionais são abusivas e nulas.

IMPORTANTE: este módulo gera INDÍCIOS, não afirma direito adquirido.
Linguagem obrigatória: "forte indício", "acima da média", "pode contestar".
Nunca usar: "você tem direito a R$ X", "é ilegal", "garantido".
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta
from typing import NamedTuple

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

_INTEREST_PATTERN = re.compile(
    r"\b(juro|encargo|rotativo|cheque especial|limite especial|financiamento|cet)\b",
    re.IGNORECASE,
)

# Base legal correta — Tema 27/STJ + STJ 2023
_LEGAL_BASIS = (
    "CDC art. 51, IV — cláusulas desproporcionais são abusivas e nulas de pleno direito. "
    "REsp 1.061.530/RS (Tema 27/STJ) — a taxa média BACEN é o referencial de abusividade. "
    "STJ 3ª Turma (2023) — abusividade exige análise do caso concreto, não apenas o múltiplo. "
    "Súmula 297/STJ + ADI 2.591/STF — CDC aplica-se integralmente às instituições financeiras."
)

_DISCLAIMER = (
    "⚠️ INDÍCIO EDUCACIONAL: este comparativo não constitui garantia de revisão judicial. "
    "A abusividade exige análise do caso concreto por advogado especializado."
)

_ACTION_HIGH = (
    "1. Solicite portabilidade de crédito — gratuita por lei (Res. CMN 5.057/2022).\n"
    "2. Use o Negociador Nexa para gerar roteiro de renegociação personalizado.\n"
    "3. Se o banco negar redução, registre reclamação no Banco Central (bcb.gov.br/meubc).\n"
    "4. Para crédito rotativo acumulado, avalie crédito pessoal com taxa menor.\n"
    "5. Consulte advogado especialista em direito bancário antes de acionar o JEC."
)

_ACTION_MEDIUM = (
    "1. Compare no Negociador Nexa: outras IFs cobram menos nesta modalidade.\n"
    "2. Solicite renegociação direta ao banco informando o benchmark BACEN.\n"
    "3. Avalie portabilidade de crédito se a taxa nova for ≥ 20% menor."
)

_ACTION_LOW = (
    "1. Acompanhe a evolução — taxa acima da média mas dentro da faixa usual.\n"
    "2. Na próxima renovação, negocie redução com base no benchmark BACEN."
)


class _RateThreshold(NamedTuple):
    multiple: float
    severity: str
    label: str
    action: str


# Faixas de múltiplo conforme PDF V2 seção 9
_THRESHOLDS = [
    _RateThreshold(3.0, "high",   "forte indício",     _ACTION_HIGH),
    _RateThreshold(1.5, "medium", "indício relevante", _ACTION_MEDIUM),
    _RateThreshold(1.0, "low",    "atenção",           _ACTION_LOW),
]

# Fallback quando BACEN SGS estiver indisponível (mai/2026)
# ATENÇÃO: validar unidade da série 20714 antes de usar em produção.
# O PDF V2 aponta que pode ser % a.a. — confirmar na documentação SGS.
_FALLBACK_RATES = {
    "rotativo_monthly":        0.1567,  # 15.67% a.m. — fallback mar/2026
    "rotativo_max_monthly":    0.1770,
    "cheque_especial_monthly": 0.1080,
    "consignado_monthly":      0.0175,
}


def _classify(rate_user: float, rate_market: float) -> _RateThreshold | None:
    """
    Retorna o threshold aplicável ou None se taxa <= média.
    Limites inclusivos (>=): 1,5x = medium, 3,0x = high conforme PDF V2 seção 9.
    """
    if rate_market <= 0:
        return None
    multiple = rate_user / rate_market
    for t in _THRESHOLDS:
        if multiple >= t.multiple:
            return t
    return None


class AbusiveInterestDetector:
    """
    D3 — Detecta indícios de juros acima da taxa média de mercado (BACEN/Olinda).

    Gera achados com linguagem de INDÍCIO, nunca de certeza jurídica.
    Thresholds: >3,0x = high | 1,5x-3,0x = medium | 1,0x-1,5x = low.
    """

    def detect(self, user_id: str) -> list[DefenseFinding]:
        market = self._get_market_rates()
        findings: list[DefenseFinding] = []
        findings.extend(self._check_from_negotiation_history(user_id, market))
        findings.extend(self._check_from_transactions(user_id, market))
        # Deduplica por banco + modalidade
        seen: set[tuple[str, str]] = set()
        unique = []
        for f in findings:
            key = (f.bank_name, f.title)
            if key not in seen:
                seen.add(key)
                unique.append(f)
        logger.info("[D3] user=%s → %d achados", user_id, len(unique))
        return unique

    # ── D3a: via negotiation_history ──────────────────────────────────

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
                ref_rate = (
                    market["rotativo_monthly"]
                    if is_rotativo
                    else market["cheque_especial_monthly"]
                )
                ref_label = "crédito rotativo PF" if is_rotativo else "cheque especial"

                # Sem taxa contratada explícita → usa finding como indício de valor alto
                estimated_annual = round(float(gain) * 12, 2)
                threshold = _THRESHOLDS[1]  # medium por default sem taxa contratada

                findings.append(DefenseFinding(
                    detector="D3",
                    severity=threshold.severity,
                    bank_name=bank,
                    title=f"Indício de juros elevados — {ref_label} em {bank}",
                    description=(
                        f"Detectamos encargos de {ref_label} em {bank} com potencial de "
                        f"economia de R$ {float(gain):.2f}/mês se reduzidos à taxa média "
                        f"BACEN ({ref_rate*100:.2f}% a.m.). "
                        f"Isso é um {threshold.label} — vale contestar/negociar. "
                        f"{_DISCLAIMER}"
                    ),
                    amount_disputed=estimated_annual,
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=threshold.action,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Modalidade: {ref_label}",
                        f"Economia mensal estimada se taxa = média BACEN: R$ {float(gain):.2f}",
                        f"Taxa média BACEN de referência: {ref_rate*100:.2f}% a.m.",
                        "Fonte: BACEN SGS + histórico de negociação Nexa",
                        "INDÍCIO — não garante revisão judicial; consulte advogado.",
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
            from collections import defaultdict

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

            by_bank: dict[str, list[tuple[str, float]]] = defaultdict(list)
            for bank, desc, amount in interest_rows[:20]:
                by_bank[bank].append((desc, amount))

            findings = []
            ref_rate = market["rotativo_monthly"]
            for bank, items in by_bank.items():
                total = sum(a for _, a in items)
                # Sem taxa contratada → indício low/medium por volume
                severity = "medium" if total > 100 else "low"
                threshold = next(t for t in _THRESHOLDS if t.severity == severity)

                findings.append(DefenseFinding(
                    detector="D3",
                    severity=severity,
                    bank_name=bank,
                    title=f"Encargos de juros detectados — {bank}",
                    description=(
                        f"{len(items)} lançamento(s) de juros/encargos em {bank}, "
                        f"totalizando R$ {total:.2f}. "
                        f"Taxa referência BACEN (rotativo PF): {ref_rate*100:.2f}% a.m. "
                        f"Para comparação precisa, informe a taxa contratada. "
                        f"{_DISCLAIMER}"
                    ),
                    amount_disputed=round(total, 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=threshold.action,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Lançamentos detectados: {len(items)}",
                        f"Total cobrado: R$ {total:.2f}",
                        f"Taxa referência BACEN (rotativo): {ref_rate*100:.2f}% a.m.",
                        *[f"• {d}: R$ {a:.2f}" for d, a in items[:5]],
                        "INDÍCIO — comparação precisa exige taxa contratada.",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D3] _check_from_transactions: %s", exc)
            return []

    @staticmethod
    def _get_market_rates() -> dict:
        """Tenta Olinda por IF, depois BacenCreditConnector, depois fallback."""
        try:
            from app.architect.connectors.olinda_interest_rate import OlindaInterestRateConnector
            connector = OlindaInterestRateConnector()
            rates = connector.get_market_averages()
            if rates:
                return rates
        except Exception as exc:
            logger.debug("[D3] OlindaInterestRateConnector: %s", exc)

        try:
            from app.architect.connectors.bacen_credit import BacenCreditConnector
            return BacenCreditConnector().get_rates()
        except Exception as exc:
            logger.debug("[D3] BacenCreditConnector fallback: %s", exc)

        return _FALLBACK_RATES


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
