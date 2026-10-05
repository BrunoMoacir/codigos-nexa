"""
app/defense/services/abusive_interest_detector.py — D3: Juros Abusivos

Compara taxas de juros pagas pelo usuário com as taxas médias de mercado
publicadas pelo BACEN — SGS 25477 (cartão rotativo PF) e 25463 (cheque
especial PF), família "Taxa média MENSAL" — e com a distribuição por
instituição do Olinda taxaJuros v2.

Base legal:
  REsp 1.061.530/RS (Tema 27/STJ) — taxa média BACEN é o referencial de
  abusividade; análise do caso concreto é necessária.
  Res. CMN 4.765/2019, art. 2º — cheque especial de PF e MEI limitado a
  8% ao mês. É teto regulatório, não média: acima dele não se discute
  "quanto acima do mercado", discute-se descumprimento de norma do CMN.
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

from app.architect.connectors.bacen_credit import (
    TETO_CHEQUE_ESPECIAL_BASE_LEGAL,
    TETO_CHEQUE_ESPECIAL_MENSAL,
)
from app.defense.models import DefenseFinding
from app.core.formatacao import brl, numero

logger = logging.getLogger(__name__)

# Extrato bancário escreve no PLURAL: "JUROS", "ENCARGOS". O padrão só aceitava
# o singular (`\bjuro\b`, `\bencargo\b`), então "JUROS EMPRESTIMO", "ENCARGOS
# FATURA" e "JUROS SOBRE SALDO DEVEDOR" não casavam — e essas são as formas
# comuns. Só passava quando havia "rotativo" na mesma descrição.
#
# Este padrão é DELIBERADAMENTE mais largo que o `JUROS_ROTATIVO` do F5
# (app/costs/fee_detector.py), e os dois não devem ser unificados: lá o objetivo
# é classificar uma TARIFA de rotativo, e por isso exige contexto de cartão/
# fatura para não capturar juro de empréstimo — que é custo legítimo de crédito.
# Aqui o objetivo é o oposto: encontrar QUALQUER encargo de juros para comparar
# com a média de mercado, inclusive de empréstimo e cheque especial.
_INTEREST_PATTERN = re.compile(
    r"\b(juros?|encargos?|rotativo|cheque\s+especial|limite\s+especial"
    r"|financiamento|cet)\b",
    re.IGNORECASE,
)

# Base legal correta — Tema 27/STJ + STJ 2023
_LEGAL_BASIS = (
    "CDC art. 51, IV — cláusulas desproporcionais são abusivas e nulas de pleno direito. "
    "REsp 1.061.530/RS (Tema 27/STJ) — a taxa média BACEN é o referencial de abusividade. "
    "STJ 3ª Turma (2023) — abusividade exige análise do caso concreto, não apenas o múltiplo. "
    "Súmula 297/STJ + ADI 2.591/STF — CDC aplica-se integralmente às instituições financeiras. "
    + TETO_CHEQUE_ESPECIAL_BASE_LEGAL
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

# Fallback quando BACEN SGS e Olinda estiverem indisponíveis. Valores de
# jun/2026 (SGS, família "Taxa média mensal") e do corte do Olinda de
# 03/08/2026 para o máximo.
#
# O que havia aqui antes: rotativo 15,67% (perto do certo, por sorte) e cheque
# especial 10,80% a.m. — 43% acima da média real (7,56%) e, pior, ACIMA do teto
# de 8% a.m. da Res. CMN 4.765/2019. Com essa referência, o usuário que paga
# exatamente o teto legal saía com múltiplo 0,77× e o D3 não gerava achado.
# E como o Olinda estava consultando o endpoint errado, esse fallback era o
# que rodava em produção — não era fallback, era a fonte.
_FALLBACK_RATES = {
    "rotativo_monthly":        0.1513,  # 15,13% a.m. — SGS 25477, jun/2026
    "rotativo_max_monthly":    0.2499,  # 24,99% a.m. — maior IF, Olinda 03/08/2026
    "parcelado_monthly":       0.0932,  #  9,32% a.m. — SGS 25478
    "cheque_especial_monthly": 0.0756,  #  7,56% a.m. — SGS 25463
    "pessoal_monthly":         0.0708,  #  7,08% a.m. — SGS 25464
    "consignado_monthly":      0.0183,  #  1,83% a.m. — SGS 25468
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
                        f"economia de {brl(float(gain))}/mês se reduzidos à taxa média "
                        f"BACEN ({numero(ref_rate*100, 2)}% a.m.). "
                        f"Isso é um {threshold.label} — vale contestar/negociar. "
                        f"{_DISCLAIMER}"
                    ),
                    amount_disputed=estimated_annual,
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=threshold.action,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Modalidade: {ref_label}",
                        f"Economia mensal estimada se taxa = média BACEN: {brl(float(gain))}",
                        f"Taxa média BACEN de referência: {numero(ref_rate*100, 2)}% a.m.",
                        *([] if is_rotativo else [
                            f"Teto regulatório: {TETO_CHEQUE_ESPECIAL_MENSAL*100:.0f}% a.m. — "
                            f"{TETO_CHEQUE_ESPECIAL_BASE_LEGAL} Confira a taxa no seu extrato: "
                            f"acima disso não é 'caro', é fora da norma do CMN."
                        ]),
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
                        f"totalizando {brl(total)}. "
                        f"Taxa referência BACEN (rotativo PF): {numero(ref_rate*100, 2)}% a.m. "
                        f"Para comparação precisa, informe a taxa contratada. "
                        f"{_DISCLAIMER}"
                    ),
                    amount_disputed=round(total, 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=threshold.action,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Lançamentos detectados: {len(items)}",
                        f"Total cobrado: {brl(total)}",
                        f"Taxa referência BACEN (rotativo): {numero(ref_rate*100, 2)}% a.m.",
                        *[f"• {d}: {brl(a)}" for d, a in items[:5]],
                        "INDÍCIO — comparação precisa exige taxa contratada.",
                    ],
                ))
            return findings
        except Exception as exc:
            logger.debug("[D3] _check_from_transactions: %s", exc)
            return []

    @staticmethod
    def _get_market_rates() -> dict:
        """
        Monta a referência de mercado a partir das duas fontes, cada uma no
        papel em que é a autoridade — SEMPRE no mesmo vocabulário.

        1. SGS (`BacenCreditConnector`) dá as MÉDIAS. É a média ponderada pelo
           volume das concessões, que é justamente a "taxa média de mercado
           apurada pelo BACEN" a que o Tema 27/STJ se refere. O Olinda não
           publica volume, então a média dele é média simples entre IFs — bom
           para comparar bancos, fraco para citar num documento jurídico. Por
           isso a ordem inverteu: o Olinda vinha primeiro e o BACEN só era
           consultado quando o Olinda falhava.

        2. Olinda dá a DISTRIBUIÇÃO por instituição, e é de lá que sai a taxa
           máxima praticada. O SGS não publica máximo nenhum: a série que o
           projeto usava como `rotativo_max` era a média de pessoas JURÍDICAS,
           e por isso o "máximo" saía abaixo da "média".

        As fontes falam línguas diferentes — o Olinda devolve `rotativo`, o
        BacenCredit devolve `rotativo_monthly`, e os consumidores leem
        `market["rotativo_monthly"]`. `_normalizar_taxas` é o que impede a
        próxima fonte de reintroduzir o KeyError silencioso que já deixou o D3
        funcionando SÓ quando o dado de mercado falhava.
        """
        rates = dict(_FALLBACK_RATES)

        try:
            from app.architect.connectors.bacen_credit import BacenCreditConnector
            rates.update(_normalizar_taxas(BacenCreditConnector().get_rates()))
        except Exception as exc:
            logger.debug("[D3] BacenCreditConnector: %s", exc)

        try:
            from app.architect.connectors.olinda_interest_rate import OlindaInterestRateConnector
            olinda = OlindaInterestRateConnector()

            dist = olinda.get_rate_distribution("rotativo")
            if dist and dist["max"] >= rates["rotativo_monthly"]:
                rates["rotativo_max_monthly"] = dist["max"]

            # Veículo e imóvel não estão na família "Taxa média mensal … PF"
            # que o conector SGS usa; só o Olinda os cobre. Onde o SGS publica,
            # ele manda — a média ponderada por volume é a que o Tema 27
            # referencia.
            for chave, valor in olinda.get_market_averages().items():
                rates.setdefault(f"{chave}_monthly", valor)
        except Exception as exc:
            logger.debug("[D3] OlindaInterestRateConnector: %s", exc)

        return rates


def _normalizar_taxas(rates: dict) -> dict:
    """
    Põe as taxas no sufixo `_monthly`, aceitando as duas convenções, e completa
    o que faltar com o fallback — para o consumidor nunca cair em KeyError.
    """
    out = dict(_FALLBACK_RATES)
    for chave, valor in (rates or {}).items():
        if valor is None:
            continue
        canonica = chave if chave.endswith("_monthly") else f"{chave}_monthly"
        out[canonica] = float(valor)
    return out


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
