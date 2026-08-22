"""
app/defense/services/portability_detector.py — D6: Portabilidade Assistida

Detecta contratos de crédito com taxa acima do benchmark de mercado e
gera roteiro completo para solicitar portabilidade.

Base legal: Res. CMN 5.057/2022 (em vigor desde 01/03/2023 — revogou a 4.292/2013):
  - Portabilidade gratuita para o consumidor.
  - Banco cedente tem 5 dias úteis para contraproposta.
  - Novo contrato limitado ao saldo devedor e prazo remanescente.
  - Vedado cobrar qualquer custo da transferência ao consumidor.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from app.defense.models import DefenseFinding

logger = logging.getLogger(__name__)

_LEGAL_BASIS = (
    "Res. CMN 5.057/2022 (em vigor desde 01/03/2023) — portabilidade de crédito gratuita. "
    "Banco cedente tem 5 dias úteis para contraproposta. "
    "Novo contrato não pode exceder saldo devedor atual e prazo remanescente. "
    "Vedado cobrar qualquer custo de transferência do consumidor. "
    "CDC art. 6º, II — direito à livre escolha entre produtos e serviços equivalentes."
)

_ACTION_TEMPLATE = (
    "ROTEIRO DE PORTABILIDADE (Res. CMN 5.057/2022):\n"
    "1. Entre em contato com o banco DESTINO de sua preferência informando:\n"
    "   - Modalidade do crédito, saldo devedor atual e prazo remanescente.\n"
    "2. O banco destino enviará proposta ao banco de origem.\n"
    "3. O banco de origem tem 5 dias úteis para fazer contraproposta.\n"
    "4. Se a contraproposta for melhor que a proposta original, avalie aceitar.\n"
    "5. Se aceitar a portabilidade: a transferência é GRATUITA por lei.\n"
    "6. Monitore o Pix/TED do novo banco liquidando o saldo com o banco antigo.\n"
    "7. Se o banco cobrar qualquer taxa pela portabilidade, registre no BACEN."
)

# Gatilho: taxa do contrato > 1,2x a média do próprio banco para a modalidade
_THRESHOLD_INSTITUTION = 1.20
# Gatilho secundário: taxa do contrato > 1,15x a melhor taxa de mercado
_THRESHOLD_MARKET = 1.15


class PortabilityDetector:
    """
    D6 — Detecta contratos com taxa acima do benchmark e gera findings de portabilidade.

    Fontes de dados (em ordem de preferência):
      1. Pluggy loans/financings (taxa contratada explícita)
      2. Inferência de taxa implícita via encargos de fatura
      3. Histórico de negotiation_history com trigger de juros alto
    """

    def detect(self, user_id: str) -> list[DefenseFinding]:
        findings: list[DefenseFinding] = []
        findings.extend(self._check_from_loans(user_id))
        findings.extend(self._check_from_negotiation_history(user_id))

        seen: set[tuple[str, str]] = set()
        unique = []
        for f in findings:
            key = (f.bank_name, f.title)
            if key not in seen:
                seen.add(key)
                unique.append(f)

        logger.info("[D6] user=%s → %d achados", user_id, len(unique))
        return unique

    # ── D6a: via Pluggy loans/financings ─────────────────────────────

    def _check_from_loans(self, user_id: str) -> list[DefenseFinding]:
        """
        Tenta obter contratos de empréstimo/financiamento via Pluggy.
        Se taxa contratada disponível → compara com Olinda por IF e mercado.
        """
        try:
            from app.core.db.queries import get_transactions_for_user
            from app.core.database import SessionLocal
            from sqlalchemy import text

            # Tenta buscar dados de empréstimos no banco (se armazenados)
            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT bank_name, loan_type, contracted_rate, balance, "
                        "       remaining_months, contracted_at"
                        " FROM pluggy_loans"
                        " WHERE user_id = :uid"
                        " ORDER BY balance DESC"
                        " LIMIT 20"
                    ),
                    {"uid": user_id},
                ).fetchall()

            if not rows:
                return []

            market = self._get_market_rates()
            findings = []

            for bank, loan_type, rate, balance, rem_months, contracted_at in rows:
                rate_f = float(rate) if rate else None
                if not rate_f or rate_f <= 0:
                    continue

                modality = _infer_modality(loan_type or "")
                market_avg = market.get(modality, market.get("pessoal"))
                if not market_avg or market_avg <= 0:
                    continue

                multiple = rate_f / market_avg
                if multiple < _THRESHOLD_INSTITUTION:
                    continue

                best_rate = self._get_best_rate(modality)
                economy = _calc_economy(
                    rate_contracted=rate_f,
                    rate_target=best_rate or market_avg,
                    balance=float(balance or 0),
                    remaining_months=int(rem_months or 12),
                )

                severity = "high" if multiple >= 1.5 else "medium"

                findings.append(DefenseFinding(
                    detector="D6",
                    severity=severity,
                    bank_name=bank,
                    title=f"Portabilidade recomendada — {loan_type or modality} ({bank})",
                    description=(
                        f"Sua taxa contratada em {bank} ({rate_f*100:.2f}% a.m.) está "
                        f"{multiple:.1f}× acima da média de mercado "
                        f"({market_avg*100:.2f}% a.m.). "
                        f"Economia estimada com portabilidade: R$ {economy:.2f} no período. "
                        f"Portabilidade é GRATUITA (Res. CMN 5.057/2022)."
                    ),
                    amount_disputed=round(economy, 2),
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION_TEMPLATE,
                    evidence_points=[
                        f"Banco atual: {bank}",
                        f"Modalidade: {loan_type or modality}",
                        f"Taxa contratada: {rate_f*100:.2f}% a.m.",
                        f"Taxa média de mercado ({modality}): {market_avg*100:.2f}% a.m.",
                        f"Múltiplo: {multiple:.1f}×",
                        f"Saldo devedor: R$ {float(balance or 0):.2f}",
                        f"Prazo remanescente: {rem_months} meses",
                        f"Economia estimada: R$ {economy:.2f}",
                        "Portabilidade gratuita — Res. CMN 5.057/2022.",
                    ],
                    confidence=0.90,
                    evidence_source="transactions",
                    legal_review_level="auto",
                    estimated_vs_claimed="estimativa",
                ))
            return findings
        except Exception as exc:
            logger.debug("[D6] _check_from_loans: %s", exc)
            return []

    # ── D6b: via negotiation_history ──────────────────────────────────

    def _check_from_negotiation_history(self, user_id: str) -> list[DefenseFinding]:
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
                        "   AND trigger_type IN ("
                        "     'JUROS_ROTATIVO_ALTO', 'CHEQUE_ESPECIAL_ALTO',"
                        "     'CREDITO_PESSOAL_CARO', 'FINANCIAMENTO_CARO'"
                        "   )"
                        "   AND generated_at >= :cutoff"
                        " ORDER BY potential_gain DESC LIMIT 5"
                    ),
                    {"uid": user_id, "cutoff": cutoff},
                ).fetchall()

            if not rows:
                return []

            market = self._get_market_rates()
            findings = []

            for bank, trigger, gain in rows:
                gain_f = float(gain or 0)
                modality = _trigger_to_modality(trigger)
                market_avg = market.get(modality, 0.03)
                annual_economy = round(gain_f * 12, 2)

                findings.append(DefenseFinding(
                    detector="D6",
                    severity="medium",
                    bank_name=bank,
                    title=f"Portabilidade pode economizar R$ {annual_economy:.2f}/ano — {bank}",
                    description=(
                        f"Encargos de {trigger.replace('_', ' ').lower()} em {bank} "
                        f"indicam potencial de economia de R$ {gain_f:.2f}/mês "
                        f"(R$ {annual_economy:.2f}/ano) com portabilidade para IF "
                        f"com taxa próxima à média de mercado "
                        f"({market_avg*100:.2f}% a.m.). "
                        f"Portabilidade é gratuita (Res. CMN 5.057/2022). "
                        "Forneça a taxa contratada para análise mais precisa."
                    ),
                    amount_disputed=annual_economy,
                    legal_basis=_LEGAL_BASIS,
                    recommended_action=_ACTION_TEMPLATE,
                    evidence_points=[
                        f"Banco: {bank}",
                        f"Gatilho: {trigger}",
                        f"Economia mensal estimada: R$ {gain_f:.2f}",
                        f"Economia anual estimada: R$ {annual_economy:.2f}",
                        f"Taxa referência mercado: {market_avg*100:.2f}% a.m.",
                        "Portabilidade gratuita — Res. CMN 5.057/2022.",
                        "Estimativa baseada em histórico — forneça taxa contratada para precisão.",
                    ],
                    confidence=0.65,
                    evidence_source="negotiation_history",
                    legal_review_level="auto",
                    estimated_vs_claimed="estimativa",
                ))
            return findings
        except Exception as exc:
            logger.debug("[D6] _check_from_negotiation_history: %s", exc)
            return []

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _get_market_rates() -> dict[str, float]:
        """
        A mesma referência que o D3 usa, no vocabulário que `_infer_modality`
        produz (`rotativo`, `pessoal`, sem o sufixo `_monthly`).

        Havia aqui uma segunda cadeia de fontes com a própria tabela de
        fallback, e ela tinha dois problemas. O primeiro: `pessoal` estava
        fixado em 3,20% a.m., menos da metade da taxa real (7,08% a.m., SGS
        25464) — e `pessoal` é a modalidade DEFAULT de `_infer_modality`, ou
        seja, a referência da maioria dos empréstimos. Com o limiar de 1,20×,
        qualquer taxa acima de 3,84% a.m. virava "acima do mercado": quem
        pagava 5% a.m., abaixo do mercado, recebia ordem de portabilidade.

        O segundo: os níveis 2 e 3 eram inalcançáveis. `get_market_averages()`
        passa pelo `get_rates()` do BaseConnector, que já devolve fallback em
        vez de levantar — o `except` nunca rodava. Cadeia de três níveis em que
        o primeiro não falha é cadeia de um nível.
        """
        from app.defense.services.abusive_interest_detector import AbusiveInterestDetector

        return {
            chave.removesuffix("_monthly"): valor
            for chave, valor in AbusiveInterestDetector._get_market_rates().items()
        }

    @staticmethod
    def _get_best_rate(modality: str) -> Optional[float]:
        try:
            from app.architect.connectors.olinda_interest_rate import OlindaInterestRateConnector
            return OlindaInterestRateConnector().get_best_rate(modality)
        except Exception:
            return None


def _infer_modality(loan_type: str) -> str:
    lt = loan_type.lower()
    if "rotativo" in lt or "cartao" in lt or "cartão" in lt:
        return "rotativo"
    if "cheque" in lt or "especial" in lt:
        return "cheque_especial"
    if "consig" in lt or "inss" in lt:
        return "consignado"
    if "veiculo" in lt or "veículo" in lt or "auto" in lt:
        return "veiculo"
    if "imov" in lt or "imóv" in lt or "habita" in lt:
        return "imovel"
    return "pessoal"


def _trigger_to_modality(trigger: str) -> str:
    t = trigger.upper()
    if "ROTATIVO" in t:
        return "rotativo"
    if "CHEQUE" in t:
        return "cheque_especial"
    if "CONSIG" in t:
        return "consignado"
    return "pessoal"


def _calc_economy(
    rate_contracted: float,
    rate_target: float,
    balance: float,
    remaining_months: int,
) -> float:
    """
    Estima economia total (R$) com portabilidade usando diferença de juros simples.
    Fórmula conservadora: diferença mensal de juros × meses remanescentes.
    """
    if balance <= 0 or remaining_months <= 0 or rate_target >= rate_contracted:
        return 0.0
    monthly_diff = (rate_contracted - rate_target) * balance
    return round(monthly_diff * remaining_months, 2)
