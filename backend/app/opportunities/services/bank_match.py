"""
app/opportunities/services/bank_match.py

Bank Match — camada de inteligência "qual é o melhor banco PARA VOCÊ?".

O scorecard (bank_scorecard.py) responde "qual banco paga mais pelo
investimento?". O Bank Match generaliza: pondera QUATRO pilares por banco,
com pesos ajustados ao perfil financeiro do usuário (ConsumptionProfiler):

  1. Rendimento  — melhor retorno líquido ajustado a risco (reusa BankScorecardService)
  2. Tarifas     — custo mensal médio de mercado do banco (reusa MarketFeesDB do
                   módulo de custos F5) e, quando o usuário JÁ paga tarifa no banco,
                   o custo real detectado (BankFeeAnalyzer.by_bank via runner)
  3. Cartões     — força dos cartões emitidos pelo banco para o perfil de gasto
                   (reusa o catálogo do optimizer F2 — card_loader; sem refazer a
                   simulação completa do OptimizerService, que exige renda)
  4. Fit         — aderência ao perfil: tier de risco vs. FSS, liquidez diária
                   disponível, cobertura FGC, amplitude de portfólio

Pesos por perfil (somam 1.0):
  padrão                      → rendimento .40 | tarifas .30 | cartões .15 | fit .15
  fss ALERTA/CRITICO          → tarifas   .40 | rendimento .25 | fit .25 | cartões .10
  investidor ATIVO/DIVERSIF.  → rendimento .50 | tarifas .20 | cartões .15 | fit .15

Todos os pilares degradam graciosamente: fonte indisponível → nota neutra (50)
para todos os bancos naquele pilar, nunca derruba a análise.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.opportunities.calculators.issuer_risk import risk_penalty
from app.opportunities.models import (
    DATA_SOURCES,
    BankComparisonResponse,
    BankMatchComponents,
    BankMatchEntry,
    BankMatchResponse,
    BankScorecardEntry,
)
from app.opportunities.services.bank_scorecard import BankScorecardService
from app.core.formatacao import brl

logger = logging.getLogger(__name__)

_FRAGILE_FSS = {"ALERTA", "CRITICO"}
_ACTIVE_INVESTORS = {"ATIVO", "DIVERSIFICADO"}
_NEUTRAL_SCORE = 50.0

_WEIGHTS_DEFAULT = {"yield": 0.40, "fees": 0.30, "card": 0.15, "fit": 0.15}
_WEIGHTS_FRAGILE = {"yield": 0.25, "fees": 0.40, "card": 0.10, "fit": 0.25}
_WEIGHTS_INVESTOR = {"yield": 0.50, "fees": 0.20, "card": 0.15, "fit": 0.15}

# Diferença mínima de score para recomendar troca de banco — evita sugerir
# migração por diferença irrelevante (custo de troca não é zero na prática).
_MIN_SWITCH_SCORE_GAP = 5.0


class BankMatchService:
    """Ranking de bancos por match composto com o perfil do usuário."""

    def __init__(self, scorecard: BankScorecardService | None = None) -> None:
        self._scorecard = scorecard or BankScorecardService()

    def build(
        self,
        user_id: str,
        amount: float,
        holding_months: int,
        cdi_annual: float,
        selic_annual: float | None = None,
        user_profile=None,
        transactions_df=None,
        disclaimer: str = "",
    ) -> BankMatchResponse:
        scorecard = self._scorecard.build(
            user_id=user_id,
            amount=amount,
            holding_months=holding_months,
            cdi_annual=cdi_annual,
            selic_annual=selic_annual,
        )

        fss_level = getattr(user_profile, "fss_level", "SAUDAVEL")
        investor_type = getattr(user_profile, "investor_type", "NONE")
        weights = self._pick_weights(fss_level, investor_type)

        real_fees = self._detect_real_fees(user_id, transactions_df)
        fees_by_bank, real_fee_banks = self._project_fees(scorecard, real_fees)
        cards_by_bank = self._score_cards(scorecard, user_profile)

        entries = self._score_banks(
            scorecard, fees_by_bank, cards_by_bank, weights, fss_level, real_fee_banks
        )
        entries.sort(key=lambda e: -e.match_score)

        current = next((e for e in entries if e.is_user_current_bank), None)
        current_rank = entries.index(current) + 1 if current else None
        best = entries[0] if entries else None

        return BankMatchResponse(
            user_id=user_id,
            amount_simulated=amount,
            holding_months=holding_months,
            profile_used={
                "fss_level": fss_level,
                "investor_type": investor_type,
                "weights": weights,
            },
            ranking=entries,
            user_current_bank=current.bank_name if current else None,
            user_current_bank_rank=current_rank,
            best_bank=best.bank_name if best else None,
            switch_recommendation=self._build_recommendation(best, current, amount),
            disclaimer=disclaimer,
            data_sources=DATA_SOURCES + ["Tarifas: BACEN/curadoria (market_fees_db)", "Cartões: catálogo Nexa (optimizer)"],
            generated_at=datetime.now(timezone.utc),
        )

    # ── pesos ────────────────────────────────────────────────────────

    @staticmethod
    def _pick_weights(fss_level: str, investor_type: str) -> dict[str, float]:
        if fss_level in _FRAGILE_FSS:
            return dict(_WEIGHTS_FRAGILE)   # sobrevivência > rendimento
        if investor_type in _ACTIVE_INVESTORS:
            return dict(_WEIGHTS_INVESTOR)
        return dict(_WEIGHTS_DEFAULT)

    # ── pilar 2: tarifas ─────────────────────────────────────────────

    @staticmethod
    def _detect_real_fees(user_id: str, transactions_df) -> dict[str, float]:
        """OPP4-E — tarifa REAL que o usuário paga por banco (R$/mês), via
        BankFeeAnalyzer (F5) sobre o histórico de transações. Falha aberta →
        {} (só médias de mercado). Custo baixo: FeeDetector roda em memória
        sobre o DataFrame já buscado pelo chamador.

        Antes de detectar, enriquece o DataFrame com institution_id derivado
        do metadado Pluggy persistido (account_balances: conta → banco) —
        sem isso o FeeDetector cai em heurística por descrição, menos
        confiável para atribuir a tarifa ao banco certo."""
        if transactions_df is None or getattr(transactions_df, "is_empty", lambda: True)():
            return {}
        try:
            from app.costs.bank_fee_analyzer import BankFeeAnalyzer

            enriched = BankMatchService._enrich_institution_id(user_id, transactions_df)
            report = BankFeeAnalyzer().analyze(enriched, user_id)
            return {
                b.bank_name: float(b.monthly_avg)
                for b in report.by_bank
                if b.bank_name and b.monthly_avg is not None
            }
        except Exception as exc:
            logger.warning("[BankMatch] fee_analyzer user=%s: %s", user_id, exc)
            return {}

    @staticmethod
    def _enrich_institution_id(user_id: str, transactions_df):
        """Delega para o F5 — a implementação foi promovida para
        `app/costs/fee_detector.enriquecer_institution_id`, porque valia para os
        8 consumidores do BankFeeAnalyzer e era usada só aqui. Mantido como
        alias pelo nome já referenciado nos testes de Oportunidades."""
        from app.costs.fee_detector import enriquecer_institution_id

        return enriquecer_institution_id(user_id, transactions_df)

    @staticmethod
    def _project_fees(
        scorecard: BankComparisonResponse,
        real_fees: dict[str, float] | None = None,
    ) -> tuple[dict[str, float], set[str]]:
        """Custo mensal por banco (R$): tarifa REAL detectada no extrato do
        usuário quando existe (OPP4-E), média de mercado (MarketFeesDB do F5)
        caso contrário. Retorna também o conjunto de bancos com dado real,
        para o texto de transparência."""
        from app.opportunities.services.bank_names import find_matching

        fees: dict[str, float] = {}
        real_fee_banks: set[str] = set()
        real_fees = real_fees or {}
        try:
            from app.costs.market_fees_db import MarketFeesDB

            db = MarketFeesDB()
            for entry in scorecard.scorecard:
                matched = find_matching(entry.bank_name, real_fees)
                if matched is not None:
                    fees[entry.bank_name] = real_fees[matched]
                    real_fee_banks.add(entry.bank_name)
                elif entry.bank_name == "Tesouro Direto":
                    fees[entry.bank_name] = 0.0
                else:
                    fees[entry.bank_name] = float(db.get_avg_for_bank(entry.bank_name))
        except Exception as exc:
            logger.warning("[BankMatch] market_fees_db indisponível: %s", exc)
        return fees, real_fee_banks

    # ── pilar 3: cartões ─────────────────────────────────────────────

    @staticmethod
    def _score_cards(scorecard: BankComparisonResponse, user_profile) -> dict[str, dict]:
        """Por banco: quantos cartões o emissor tem no catálogo do optimizer
        (F2) e o nome do mais forte para o cluster do usuário. Integração
        leve de propósito: a simulação completa do OptimizerService exige
        renda e transações — aqui basta saber se o banco sustenta uma boa
        estratégia de cartão. Falha aberta → {} (nota neutra)."""
        try:
            from app.optimizer.card_loader import CardKnowledgeBase

            cards = CardKnowledgeBase().load()
        except Exception as exc:
            logger.warning("[BankMatch] card_loader indisponível: %s", exc)
            return {}

        from app.opportunities.services.bank_names import banks_match

        cluster = getattr(user_profile, "lifestyle_cluster", "NAO_CLASSIFICADO")

        result: dict[str, dict] = {}
        for entry in scorecard.scorecard:
            bank_cards = [c for c in cards if banks_match(getattr(c, "issuer", ""), entry.bank_name)]
            if not bank_cards:
                continue
            # heurística de força: sem anuidade > com anuidade; bônus se o
            # cartão tem tag alinhada ao cluster (ex: viagem p/ EXPLORADOR_GLOBAL)
            def _card_strength(c) -> float:
                strength = 1.0
                if not getattr(c, "base_annuity", 0.0):
                    strength += 0.5
                tags = {str(t).upper() for t in getattr(c, "benefit_tags", []) or []}
                if cluster == "EXPLORADOR_GLOBAL" and any("TRAVEL" in t or "LOUNGE" in t for t in tags):
                    strength += 0.5
                if cluster == "URBANO_FOODIE" and any("FOOD" in t or "CASHBACK" in t for t in tags):
                    strength += 0.5
                return strength

            best_card = max(bank_cards, key=_card_strength)
            result[entry.bank_name] = {
                "count": len(bank_cards),
                "top_card_name": best_card.name,
                "strength": _card_strength(best_card),
            }
        return result

    # ── composição ───────────────────────────────────────────────────

    def _score_banks(
        self,
        scorecard: BankComparisonResponse,
        fees_by_bank: dict[str, float],
        cards_by_bank: dict[str, dict],
        weights: dict[str, float],
        fss_level: str,
        real_fee_banks: set[str] | None = None,
    ) -> list[BankMatchEntry]:
        real_fee_banks = real_fee_banks or set()
        entries: list[BankMatchEntry] = []
        banks = scorecard.scorecard
        if not banks:
            return entries

        max_gain = max((b.best_risk_adjusted_brl for b in banks), default=0.0)
        max_fee = max(fees_by_bank.values(), default=0.0)
        max_card = max((c["strength"] for c in cards_by_bank.values()), default=0.0)

        for bank in banks:
            yield_score = (
                max(bank.best_risk_adjusted_brl, 0.0) / max_gain * 100 if max_gain > 0 else _NEUTRAL_SCORE
            )

            fee = fees_by_bank.get(bank.bank_name)
            if fee is None or max_fee <= 0:
                fees_score = _NEUTRAL_SCORE if fee is None else 100.0
            else:
                fees_score = (1 - fee / max_fee) * 100  # mais barato → nota maior

            card_info = cards_by_bank.get(bank.bank_name)
            if not cards_by_bank:
                card_score = _NEUTRAL_SCORE  # pilar inteiro indisponível
            elif card_info is None:
                card_score = 0.0             # banco sem cartão no catálogo
            else:
                card_score = card_info["strength"] / max_card * 100 if max_card > 0 else _NEUTRAL_SCORE

            fit_score, fit_reasons = self._fit_score(bank, fss_level)

            match = (
                weights["yield"] * yield_score
                + weights["fees"] * fees_score
                + weights["card"] * card_score
                + weights["fit"] * fit_score
            )

            reasons = [
                f"Rendimento: {brl(bank.best_net_return_brl)} líquidos no melhor produto "
                f"({bank.best_product_type} {bank.best_cdi_pct:.0f}% CDI)"
            ]
            if fee is not None:
                if bank.bank_name in real_fee_banks:
                    reasons.append(
                        "Você não paga tarifa neste banco hoje" if fee == 0
                        else f"Você paga {brl(fee)}/mês de tarifas neste banco hoje (detectado no seu extrato)"
                    )
                else:
                    reasons.append(
                        "Sem tarifa de manutenção típica" if fee == 0
                        else f"Tarifa média de mercado: {brl(fee)}/mês"
                    )
            if card_info:
                reasons.append(f"Cartão forte para seu perfil: {card_info['top_card_name']}")
            reasons.extend(fit_reasons)

            entries.append(BankMatchEntry(
                bank_name=bank.bank_name,
                match_score=round(match, 1),
                components=BankMatchComponents(
                    yield_score=round(yield_score, 1),
                    fees_score=round(fees_score, 1),
                    card_score=round(card_score, 1),
                    fit_score=round(fit_score, 1),
                ),
                reasons=reasons,
                risk_tier=bank.risk_tier,
                is_user_current_bank=bank.is_user_current_bank,
                projected_annual_gain_brl=bank.best_net_return_brl,
                projected_monthly_fee_brl=fee if fee is not None else 0.0,
                top_card_name=card_info["top_card_name"] if card_info else None,
            ))
        return entries

    @staticmethod
    def _fit_score(bank: BankScorecardEntry, fss_level: str) -> tuple[float, list[str]]:
        """Aderência ao perfil: solidez do emissor (pesa mais para perfil
        frágil), cobertura FGC e amplitude de portfólio."""
        reasons: list[str] = []

        solidity = {1: 100.0, 2: 70.0, 3: 40.0}.get(bank.risk_tier, 40.0)
        if fss_level in _FRAGILE_FSS and bank.risk_tier == 1:
            reasons.append("Emissor sólido — indicado para seu momento financeiro")

        guarantee = 100.0 if bank.fgc_covered or bank.bank_name == "Tesouro Direto" else 30.0
        breadth = min(bank.product_count / 3, 1.0) * 100

        fit = 0.5 * solidity + 0.3 * guarantee + 0.2 * breadth
        if bank.product_count >= 2:
            reasons.append(f"{bank.product_count} produtos disponíveis para diversificar")
        return fit, reasons

    @staticmethod
    def _build_recommendation(best, current, amount: float) -> str:
        if best is None:
            return "Sem bancos suficientes no catálogo para recomendar — tente novamente mais tarde."
        if current is None:
            return (
                f"Pelo seu perfil, o melhor banco hoje é o {best.bank_name} "
                f"(match {best.match_score:.0f}/100): "
                f"{brl(best.projected_annual_gain_brl)}/ano no melhor produto para "
                f"{brl(amount)}. Conecte suas contas para compararmos com o seu banco atual."
            )
        if current.bank_name == best.bank_name:
            return (
                f"Seu banco atual ({current.bank_name}) já é o melhor match para o seu perfil "
                f"({current.match_score:.0f}/100) — não há troca a recomendar hoje."
            )
        gap = best.match_score - current.match_score
        if gap < _MIN_SWITCH_SCORE_GAP:
            return (
                f"O {best.bank_name} lidera por pouco ({best.match_score:.0f} vs "
                f"{current.match_score:.0f} do seu {current.bank_name}) — a diferença não "
                "justifica o custo de trocar de banco agora."
            )
        gain_diff = best.projected_annual_gain_brl - current.projected_annual_gain_brl
        return (
            f"Vale avaliar o {best.bank_name}: match {best.match_score:.0f}/100 contra "
            f"{current.match_score:.0f} do seu {current.bank_name}"
            + (f", com {brl(gain_diff)}/ano a mais no melhor produto" if gain_diff > 0 else "")
            + f" para {brl(amount)}. Você não precisa fechar a conta atual para começar."
        )


__all__ = ["BankMatchService"]
