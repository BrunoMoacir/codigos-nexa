"""
app/negotiator/opportunity_detector.py — F13: Detector de Oportunidades de Negociação

Detecta quando o usuário tem poder de barganha para negociar taxas ou anuidades,
cruzando 3 fontes de dados:

  1. FeeDetector (F5)     → tarifas pagas nos últimos meses (JUROS_ROTATIVO, ANUIDADE_CARTAO)
  2. BacenConnector       → taxa SELIC como base para estimar custo de mercado
  3. UserProfileAnalyzer  → health score como proxy de poder de barganha

Limitação conhecida:
  O sistema não tem acesso a dados de crédito (Serasa/SCR/BACEN). O proxy de
  "bom pagador" é a ausência de JUROS_ROTATIVO nos últimos N meses — válido
  como sinal de comportamento, mas não substitui score de crédito real.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Optional

import polars as pl

from app.costs.fee_detector import FeeDetector
from app.costs.models import FeeEntry, FeeType
from app.negotiator.models import NegotiationOpportunity, NegotiationTrigger

logger = logging.getLogger(__name__)

# Thresholds de detecção
_MIN_HEALTH_SCORE_FOR_BARGAIN = 60     # score mínimo para ter poder de barganha
_JUROS_WINDOW_MONTHS          = 3      # janela de detecção de juros rotativos
_GOOD_PAYER_WINDOW_MONTHS     = 6      # janela para calcular meses sem juros
_ANUIDADE_MARKET_MONTHLY_AVG  = 30.0  # referência de mercado: R$ 30/mês ≈ R$ 360/ano
_MIN_JUROS_TO_FLAG            = 20.0  # R$ — ignora cobranças simbólicas (IOF de centavos)


def _month_offset(ref: date, months_back: int) -> tuple[int, int]:
    """Retorna (year, month) correspondente a `months_back` meses antes de `ref`."""
    month = ref.month - months_back
    year = ref.year
    while month <= 0:
        month += 12
        year -= 1
    return (year, month)


def _date_months_ago(ref: date, months_back: int) -> date:
    """Retorna a data de início do mês que fica `months_back` meses antes de `ref`."""
    year, month = _month_offset(ref, months_back)
    return date(year, month, 1)


class NegotiationOpportunityDetector:
    """
    Detecta oportunidades de negociação a partir das transações do usuário.

    Usage:
        detector = NegotiationOpportunityDetector()
        opportunities = detector.detect(transactions_df, health_score=75)
    """

    def __init__(self, fee_detector: FeeDetector | None = None) -> None:
        self._fee_detector = fee_detector or FeeDetector()

    def detect(
        self,
        transactions_df: pl.DataFrame,
        health_score: int,
        reference_date: Optional[date] = None,
    ) -> list[NegotiationOpportunity]:
        """
        Varre as transações e retorna oportunidades de negociação detectadas.

        Args:
            transactions_df: Histórico de transações limpas do usuário.
            health_score:    Score atual do usuário (0-100).
            reference_date:  Data de referência (padrão: hoje). Útil para testes.

        Returns:
            Lista de NegotiationOpportunity ordenada por economia potencial decrescente.
        """
        ref = reference_date or date.today()
        opportunities: list[NegotiationOpportunity] = []

        if transactions_df.is_empty():
            logger.info("NegotiationOpportunityDetector | DataFrame vazio, nenhuma oportunidade")
            return opportunities

        # Detectar todas as tarifas do histórico
        all_fees = self._fee_detector.detect(transactions_df)

        # Taxas de mercado resolvidas uma única vez — evita múltiplas chamadas HTTP ao BACEN
        from app.architect.connectors.bacen_credit import BacenCreditConnector
        credit_rates = BacenCreditConnector().get_rates()
        market_rate = credit_rates["rotativo_monthly"]

        # ── Trigger 1: Juros rotativos acima do mercado ───────────────
        juros_opps = self._detect_juros_rotativo(all_fees, health_score, ref, market_rate)
        opportunities.extend(juros_opps)

        # ── Trigger 2: Anuidade acima da média de mercado ─────────────
        anuidade_opps = self._detect_anuidade_alta(all_fees, health_score, ref)
        opportunities.extend(anuidade_opps)

        # ── Trigger 3: Cheque especial ────────────────────────────────
        cheque_opps = self._detect_cheque_especial(
            all_fees, health_score, ref, credit_rates["cheque_especial_monthly"]
        )
        opportunities.extend(cheque_opps)

        # ── Trigger 4: Health score alto sem outros triggers ──────────
        if health_score >= _MIN_HEALTH_SCORE_FOR_BARGAIN and not opportunities:
            opp = self._detect_score_only(all_fees, health_score, ref, market_rate)
            if opp:
                opportunities.append(opp)

        # Ordena por economia potencial (maior primeiro)
        opportunities.sort(key=lambda o: o.potential_saving_monthly, reverse=True)
        logger.info(
            "NegotiationOpportunityDetector | %d oportunidade(s) detectada(s) | health_score=%d",
            len(opportunities), health_score,
        )
        return opportunities

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DETECTORES POR TRIGGER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _detect_juros_rotativo(
        self,
        fees: list[FeeEntry],
        health_score: int,
        ref: date,
        market_rate: float,
    ) -> list[NegotiationOpportunity]:
        """
        Detecta juros rotativos pagos na janela de 3 meses.
        Gera uma oportunidade por banco com juros detectados.
        """
        cutoff = _date_months_ago(ref, _JUROS_WINDOW_MONTHS)

        # Filtra juros na janela e acima do limiar mínimo
        juros_fees = [
            f for f in fees
            if f.fee_type == FeeType.JUROS_ROTATIVO
            and f.transaction_date >= cutoff
            and f.amount >= _MIN_JUROS_TO_FLAG
        ]

        if not juros_fees:
            return []

        # Agrupa por banco
        by_bank: dict[str, list[FeeEntry]] = defaultdict(list)
        for fee in juros_fees:
            by_bank[fee.bank_name].append(fee)

        # Meses sem juros (proxy de bom pagador) — olha janela maior
        good_payer_months = self._count_good_payer_months(fees, ref)

        opportunities = []
        for bank_name, entries in by_bank.items():
            total_juros = sum(e.amount for e in entries)
            monthly_avg = round(total_juros / _JUROS_WINDOW_MONTHS, 2)

            # Economia potencial = o que paga de juros (não há como saber a taxa exata
            # sem o saldo devedor — usamos o valor pago como proxy direto)
            saving = round(monthly_avg, 2)

            opportunities.append(
                NegotiationOpportunity(
                    trigger=NegotiationTrigger.JUROS_ROTATIVO_ALTO,
                    bank_name=bank_name,
                    product="Crédito Rotativo / Parcelado com Juros",
                    user_fee_monthly=monthly_avg,
                    market_rate_monthly=market_rate,
                    potential_saving_monthly=saving,
                    health_score=health_score,
                    months_as_good_payer=good_payer_months,
                    description=(
                        f"Você pagou em média R$ {monthly_avg:.2f}/mês em juros rotativos "
                        f"para {bank_name} nos últimos {_JUROS_WINDOW_MONTHS} meses. "
                        f"A taxa média CDC de mercado é {market_rate * 100:.1f}% a.m."
                    ),
                )
            )

        return opportunities

    def _detect_anuidade_alta(
        self,
        fees: list[FeeEntry],
        health_score: int,
        ref: date,
    ) -> list[NegotiationOpportunity]:
        """
        Detecta anuidades pagas acima da referência de mercado.
        Janela: últimos 12 meses (anuidade é anual).
        """
        cutoff = _date_months_ago(ref, 12)

        anuidade_fees = [
            f for f in fees
            if f.fee_type == FeeType.ANUIDADE_CARTAO
            and f.transaction_date >= cutoff
        ]

        if not anuidade_fees:
            return []

        by_bank: dict[str, list[FeeEntry]] = defaultdict(list)
        for fee in anuidade_fees:
            by_bank[fee.bank_name].append(fee)

        good_payer_months = self._count_good_payer_months(fees, ref)
        opportunities = []

        for bank_name, entries in by_bank.items():
            total_anuidade = sum(e.amount for e in entries)
            monthly_equiv = round(total_anuidade / 12, 2)

            if monthly_equiv <= _ANUIDADE_MARKET_MONTHLY_AVG:
                continue  # já está na média ou abaixo

            saving = round(monthly_equiv - _ANUIDADE_MARKET_MONTHLY_AVG, 2)

            opportunities.append(
                NegotiationOpportunity(
                    trigger=NegotiationTrigger.ANUIDADE_ALTA,
                    bank_name=bank_name,
                    product="Anuidade do Cartão de Crédito",
                    user_fee_monthly=monthly_equiv,
                    market_rate_monthly=None,
                    potential_saving_monthly=saving,
                    health_score=health_score,
                    months_as_good_payer=good_payer_months,
                    description=(
                        f"Sua anuidade com {bank_name} equivale a "
                        f"R$ {monthly_equiv:.2f}/mês (R$ {total_anuidade:.2f}/ano). "
                        f"A média de mercado é R$ {_ANUIDADE_MARKET_MONTHLY_AVG:.0f}/mês. "
                        f"Você pode pedir isenção ou redução."
                    ),
                )
            )

        return opportunities

    def _detect_score_only(
        self,
        fees: list[FeeEntry],
        health_score: int,
        ref: date,
        market_rate: float,
    ) -> Optional[NegotiationOpportunity]:
        """
        Quando o health score é alto mas não há tarifas excessivas detectadas,
        gera oportunidade genérica de renegociação de limites/taxas futuras.
        Só ativado se score >= 70 (threshold mais alto que o mínimo geral).
        """
        if health_score < 70:
            return None

        good_payer_months = self._count_good_payer_months(fees, ref)

        # Identifica o banco mais frequente nas tarifas ou usa genérico
        bank_name = "seu banco principal"
        if fees:
            counts: dict[str, int] = defaultdict(int)
            for f in fees:
                counts[f.bank_name] += 1
            bank_name = max(counts, key=lambda k: counts[k])

        return NegotiationOpportunity(
            trigger=NegotiationTrigger.HEALTH_SCORE_ALTO,
            bank_name=bank_name,
            product="Taxa de Crédito / Limite",
            user_fee_monthly=None,
            market_rate_monthly=market_rate,
            potential_saving_monthly=0.0,
            health_score=health_score,
            months_as_good_payer=good_payer_months,
            description=(
                f"Seu Score Nexa é {health_score}/100 — perfil de baixo risco. "
                f"Você tem bom histórico ({good_payer_months} meses sem juros rotativos) "
                "e pode usar isso para negociar melhores condições proativamente."
            ),
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _detect_cheque_especial(
        self,
        fees: list[FeeEntry],
        health_score: int,
        ref: date,
        cheque_market_rate: float,
    ) -> list[NegotiationOpportunity]:
        """
        Detecta cobranças relacionadas a cheque especial na janela de 3 meses.
        Usa SGS 20706 como benchmark de mercado.

        Nota: a existência de qualquer cobrança de cheque especial já justifica
        a oportunidade, pois trata-se de uma das modalidades mais caras do Brasil.
        Validação de teto legal (eventual Lei 14.905/2024) deve ser feita com
        jurídico antes de ser codificada aqui.
        """
        import unicodedata

        def _norm(s: str) -> str:
            n = unicodedata.normalize("NFKD", s)
            return "".join(c for c in n if not unicodedata.combining(c)).lower()

        _CHEQUE_KEYWORDS = ("cheque especial", "limite especial", "juros cheque", "esp especial")

        cutoff = _date_months_ago(ref, _JUROS_WINDOW_MONTHS)
        cheque_fees = [
            f for f in fees
            if f.transaction_date >= cutoff
            and any(kw in _norm(f.description) for kw in _CHEQUE_KEYWORDS)
        ]

        if not cheque_fees:
            return []

        by_bank: dict[str, list[FeeEntry]] = defaultdict(list)
        for fee in cheque_fees:
            by_bank[fee.bank_name].append(fee)

        good_payer_months = self._count_good_payer_months(fees, ref)
        opportunities = []

        for bank_name, entries in by_bank.items():
            total = sum(e.amount for e in entries)
            monthly_avg = round(total / _JUROS_WINDOW_MONTHS, 2)

            opportunities.append(
                NegotiationOpportunity(
                    trigger=NegotiationTrigger.CHEQUE_ESPECIAL_ALTO,
                    bank_name=bank_name,
                    product="Cheque Especial",
                    user_fee_monthly=monthly_avg,
                    market_rate_monthly=cheque_market_rate,
                    potential_saving_monthly=round(monthly_avg, 2),
                    health_score=health_score,
                    months_as_good_payer=good_payer_months,
                    description=(
                        f"Você pagou em média R$ {monthly_avg:.2f}/mês em cheque especial "
                        f"para {bank_name}. A taxa média de mercado (BACEN SGS 20706) é "
                        f"{cheque_market_rate * 100:.1f}% a.m. Negocie uma linha de crédito "
                        "pessoal com taxa menor ou peça redução do spread."
                    ),
                )
            )

        return opportunities

    @staticmethod
    def _count_good_payer_months(fees: list[FeeEntry], ref: date) -> int:
        """
        Conta meses consecutivos (a partir do mais recente) sem JUROS_ROTATIVO.
        Proxy de bom pagador — ver limitação no docstring do módulo.
        """
        cutoff = _date_months_ago(ref, _GOOD_PAYER_WINDOW_MONTHS)
        juros_months: set[tuple[int, int]] = {
            (f.transaction_date.year, f.transaction_date.month)
            for f in fees
            if f.fee_type == FeeType.JUROS_ROTATIVO
            and f.transaction_date >= cutoff
        }

        count = 0
        for offset in range(_GOOD_PAYER_WINDOW_MONTHS):
            # Itera do mês mais recente para o mais antigo usando aritmética de ano/mês
            # (timedelta(days=30) não garante salto de mês correto)
            if _month_offset(ref, offset) in juros_months:
                break
            count += 1

        return min(count, _GOOD_PAYER_WINDOW_MONTHS)
