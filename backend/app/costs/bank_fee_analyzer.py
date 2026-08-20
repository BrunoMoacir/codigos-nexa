"""
app/costs/bank_fee_analyzer.py — F5: Agregador de Custos Bancários

Responsabilidades:
  1. Delegar detecção de tarifas ao FeeDetector
  2. Agregar FeeEntry por banco e por tipo de tarifa
  3. Calcular média mensal e projeção anual (CBT — Custo Bancário Total)
  4. Comparar com benchmarks de mercado via MarketFeesDB
  5. Calcular economia potencial e retornar BankCostReport

Usage:
    analyzer = BankFeeAnalyzer()
    report   = analyzer.analyze(transactions_df, user_id="user_123")
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import date

import polars as pl

from app.costs.fee_detector import FeeDetector
from app.costs.models import (
    BankCostReport,
    BankFeeSummary,
    FeeEntry,
    FeeType,
    MarketBenchmark,
)

logger = logging.getLogger(__name__)

# Meses mínimos de histórico para calcular média confiável
_MIN_MONTHS_FOR_AVG = 1


class BankFeeAnalyzer:
    """
    Orquestra a análise completa de custos bancários.

    Usage:
        report = BankFeeAnalyzer().analyze(transactions_df, user_id)
    """

    def __init__(self, detector: FeeDetector | None = None) -> None:
        self._detector = detector or FeeDetector()

    def analyze(
        self,
        transactions_df: pl.DataFrame,
        user_id: str,
    ) -> BankCostReport:
        logger.info("BankFeeAnalyzer | user=%s rows=%d", user_id, len(transactions_df))

        warnings: list[str] = []
        data_sources: list[str] = []

        # ── 0. Normalizar UMA vez, para todo o resto ──────────────────
        # O detector normalizava na cópia local dele e o _calc_period recebia o
        # DataFrame cru: sem a coluna `transaction_date`, devolvia 1 mês para
        # qualquer histórico e a projeção anual saía inflada exatamente pelo
        # número de meses de dados. Normalizar aqui é o que mantém detecção e
        # período falando do mesmo extrato.
        from app.costs.fee_detector import normalizar_extrato

        transactions_df = normalizar_extrato(transactions_df, user_id=user_id)

        # ── 1. Detectar tarifas ───────────────────────────────────────
        fees = self._detector.detect(transactions_df)
        if not fees:
            warnings.append("Nenhuma tarifa bancária detectada no histórico disponível.")

        # ── 2. Calcular período analisado ─────────────────────────────
        period_start, period_end, analysis_months = self._calc_period(transactions_df)
        data_sources.append("transactions_db")

        # ── 3. Agregar por banco ──────────────────────────────────────
        by_bank = self._aggregate_by_bank(fees, analysis_months)

        # ── 4. Agregar por tipo de tarifa ─────────────────────────────
        by_fee_type = self._aggregate_by_type(fees)

        # ── 5. Totais ─────────────────────────────────────────────────
        total_paid   = round(sum(f.amount for f in fees), 2)
        monthly_avg  = round(total_paid / max(analysis_months, 1), 2)
        annual_proj  = round(monthly_avg * 12, 2)

        # ── 6. Benchmarks de mercado ──────────────────────────────────
        from app.costs.market_fees_db import MarketFeesDB
        market_db = MarketFeesDB()
        benchmarks = market_db.get_benchmarks(by_bank)
        data_sources.append("market_fees_db")

        savings = self._calc_savings_opportunity(by_bank, benchmarks)

        # ── 7. Confidence ─────────────────────────────────────────────
        confidence = self._compute_confidence(
            analysis_months=analysis_months,
            fee_count=len(fees),
            has_institution_id=self._has_institution_id(transactions_df),
        )

        if analysis_months < 3:
            warnings.append(
                f"Histórico de apenas {analysis_months} mês(es) — "
                "médias podem não refletir o custo real anual."
            )

        # Transparência sobre o que NÃO foi possível concluir. O relatório
        # sempre teve o campo de economia; o que faltava era dizer quando ele
        # é zero por falta de dado, e não por o usuário já estar bem.
        from app.costs.fee_detector import banco_identificado

        nao_identificados = [b for b in by_bank if not banco_identificado(b.bank_name)]
        if nao_identificados:
            valor = round(sum(b.total_paid for b in nao_identificados), 2)
            warnings.append(
                f"R$ {valor:.2f} em tarifas não puderam ser atribuídas a um banco "
                "específico — sem isso não há comparação de mercado possível para "
                "esse valor. Reconecte a conta pelo Open Finance para identificar "
                "a instituição."
            )

        return BankCostReport(
            user_id=user_id,
            analysis_months=analysis_months,
            period_start=period_start,
            period_end=period_end,
            total_paid=total_paid,
            monthly_avg=monthly_avg,
            annual_projection=annual_proj,
            by_bank=by_bank,
            by_fee_type=by_fee_type,
            market_benchmarks=benchmarks,
            savings_opportunity=savings,
            fees_detected=fees,
            confidence_score=round(confidence, 2),
            warnings=warnings,
            data_sources=data_sources,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # MÉTODOS DE HISTÓRICO (usam bank_fee_history / bank_fee_trends)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def persist_snapshot(self, report: BankCostReport) -> None:
        """
        Persiste o snapshot de tarifas do report em bank_fee_history.

        Agrega por (month, bank_name, fee_type) antes de inserir para respeitar
        a constraint UNIQUE. Chame APÓS detect_new_fees() — o detector lê o
        histórico *antes* de este snapshot ser salvo.

        Falha silenciosamente: se a tabela ainda não existir (migration pendente)
        ou a DB estiver inacessível, apenas loga WARNING e retorna.
        """
        if not report.fees_detected:
            return

        agg: dict[tuple[str, str, str], dict] = defaultdict(
            lambda: {"amount": 0.0, "description": ""}
        )
        for fee in report.fees_detected:
            key = (fee.transaction_date.strftime("%Y-%m"), fee.bank_name, fee.fee_type.value)
            agg[key]["amount"] += fee.amount
            agg[key]["description"] = fee.description

        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                for (month, bank_name, fee_type), data in agg.items():
                    db.execute(
                        text(
                            "INSERT INTO bank_fee_history"
                            " (id, user_id, month, bank_name, fee_type, amount, description)"
                            " VALUES (:id, :uid, :month, :bank, :ftype, :amount, :desc)"
                            " ON CONFLICT ON CONSTRAINT uq_bank_fee_history DO NOTHING"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "uid": report.user_id,
                            "month": month,
                            "bank": bank_name,
                            "ftype": fee_type,
                            "amount": round(data["amount"], 2),
                            "desc": data["description"],
                        },
                    )
                db.commit()
            logger.info(
                "BankFeeAnalyzer | persisted %d fee-type rows for user=%s",
                len(agg),
                report.user_id,
            )
        except Exception as exc:
            logger.warning("BankFeeAnalyzer | persist_snapshot falhou: %s", exc)

    @staticmethod
    def detect_new_fees(user_id: str, current_fees: list[FeeEntry]) -> list[FeeEntry]:
        """
        Retorna as tarifas em current_fees cujo (bank_name, fee_type) nunca
        apareceu antes no histórico desse usuário.

        Deve ser chamado ANTES de persist_snapshot() para que o histórico
        consultado ainda não contenha o período atual.

        Retorna lista vazia em caso de erro (falha graciosamente).
        """
        if not current_fees:
            return []

        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                rows = db.execute(
                    text(
                        "SELECT DISTINCT bank_name, fee_type"
                        " FROM bank_fee_history"
                        " WHERE user_id = :uid"
                    ),
                    {"uid": user_id},
                ).fetchall()

            known = {(r[0], r[1]) for r in rows}
            return [
                fee for fee in current_fees
                if (fee.bank_name, fee.fee_type.value) not in known
            ]

        except Exception as exc:
            logger.warning("BankFeeAnalyzer | detect_new_fees falhou: %s", exc)
            return []

    @staticmethod
    def compare_to_market_baseline(user_id: str, bank_name: str) -> dict:
        """
        Compara o custo médio mensal do usuário neste banco com o benchmark de mercado.

        Prioridade de fonte do benchmark:
          1. bank_fee_trends (dinâmico, baseado em dados anônimos Nexa)
          2. MarketFeesDB estático (fallback sempre disponível)

        Returns:
            {
                "bank_name": str,
                "user_monthly_avg": float | None,  # média dos últimos 3 meses
                "market_avg": float | None,
                "excess_brl": float | None,        # quanto acima do mercado (0 se abaixo)
                "data_source": "bank_fee_trends" | "static",
            }
        """
        result: dict = {
            "bank_name": bank_name,
            "user_monthly_avg": None,
            "market_avg": None,
            "excess_brl": None,
            "data_source": "static",
        }

        try:
            from app.core.database import SessionLocal
            from sqlalchemy import text

            with SessionLocal() as db:
                user_row = db.execute(
                    text(
                        "SELECT AVG(amount) FROM bank_fee_history"
                        " WHERE user_id = :uid AND bank_name = :bank"
                        " AND month >= to_char(NOW() - INTERVAL '3 months', 'YYYY-MM')"
                    ),
                    {"uid": user_id, "bank": bank_name},
                ).fetchone()
                if user_row and user_row[0] is not None:
                    result["user_monthly_avg"] = round(float(user_row[0]), 2)

                trend_row = db.execute(
                    text(
                        "SELECT market_avg FROM bank_fee_trends"
                        " WHERE bank_name = :bank"
                        " ORDER BY month DESC LIMIT 1"
                    ),
                    {"bank": bank_name},
                ).fetchone()
                if trend_row and trend_row[0] is not None:
                    result["market_avg"] = round(float(trend_row[0]), 2)
                    result["data_source"] = "bank_fee_trends"

        except Exception as exc:
            logger.warning("BankFeeAnalyzer | compare_to_market_baseline db falhou: %s", exc)

        if result["market_avg"] is None:
            from app.costs.market_fees_db import MarketFeesDB
            result["market_avg"] = MarketFeesDB().get_avg_for_bank(bank_name)

        if result["user_monthly_avg"] is not None:
            excess = result["user_monthly_avg"] - result["market_avg"]
            result["excess_brl"] = round(max(excess, 0.0), 2)

        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # HELPERS PRIVADOS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _calc_period(
        df: pl.DataFrame,
    ) -> tuple[date | None, date | None, int]:
        """Retorna (data_início, data_fim, meses_analisados)."""
        if df.is_empty() or "transaction_date" not in df.columns:
            return None, None, _MIN_MONTHS_FOR_AVG

        dates = df["transaction_date"].drop_nulls()
        if dates.is_empty():
            return None, None, _MIN_MONTHS_FOR_AVG

        start = dates.min()
        end   = dates.max()

        # Converte para date se vier como datetime
        if hasattr(start, "date"):
            start = start.date()
        if hasattr(end, "date"):
            end = end.date()

        months = max(
            (end.year - start.year) * 12 + (end.month - start.month) + 1,
            _MIN_MONTHS_FOR_AVG,
        )
        return start, end, months

    @staticmethod
    def _aggregate_by_bank(
        fees: list[FeeEntry], analysis_months: int
    ) -> list[BankFeeSummary]:
        """Agrupa FeeEntry por institution_id e calcula totais."""
        buckets: dict[str, list[FeeEntry]] = defaultdict(list)
        for fee in fees:
            buckets[fee.institution_id].append(fee)

        summaries: list[BankFeeSummary] = []
        for institution_id, entries in buckets.items():
            total = round(sum(e.amount for e in entries), 2)
            monthly = round(total / max(analysis_months, 1), 2)

            fees_by_type: dict[str, float] = defaultdict(float)
            for e in entries:
                fees_by_type[e.fee_type.value] += e.amount
            fees_by_type = {k: round(v, 2) for k, v in fees_by_type.items()}

            summaries.append(
                BankFeeSummary(
                    bank_name=entries[0].bank_name,
                    institution_id=institution_id,
                    total_paid=total,
                    monthly_avg=monthly,
                    fees_by_type=fees_by_type,
                    transaction_count=len(entries),
                )
            )

        # Ordena do banco mais caro para o mais barato
        summaries.sort(key=lambda s: s.monthly_avg, reverse=True)
        return summaries

    @staticmethod
    def _aggregate_by_type(fees: list[FeeEntry]) -> dict[str, float]:
        """Soma total pago por FeeType."""
        totals: dict[str, float] = defaultdict(float)
        for fee in fees:
            totals[fee.fee_type.value] += fee.amount
        return {k: round(v, 2) for k, v in sorted(totals.items(), key=lambda x: -x[1])}

    @staticmethod
    def _calc_savings_opportunity(
        by_bank: list[BankFeeSummary],
        benchmarks: list[MarketBenchmark],
    ) -> float:
        """
        Economia potencial = soma dos excessos por banco.

        Para cada banco que o usuário usa, compara seu custo mensal com o
        benchmark daquele banco. Soma apenas as diferenças positivas
        (bancos onde o usuário paga acima do mercado).

        Exemplo:
            Nubank:  usuário R$45/mês, mercado R$30/mês → excesso R$15
            Itaú:    usuário R$80/mês, mercado R$90/mês → excesso R$0 (já ok)
            Total savings_opportunity = R$15
        """
        if not benchmarks or not by_bank:
            return 0.0

        from app.costs.fee_detector import banco_identificado

        benchmark_map = {b.bank_name: b.monthly_avg_market for b in benchmarks}
        total_savings = 0.0

        for bank in by_bank:
            # Só compara quando SABEMOS de que banco é a tarifa. O balde de
            # sobra recebia o benchmark médio dos tradicionais e produzia
            # economia em reais para um banco que ninguém identificou — dizendo
            # a um usuário de banco digital que ele economizaria migrando.
            if not banco_identificado(bank.bank_name):
                continue
            market_avg = benchmark_map.get(bank.bank_name)
            if market_avg is None:
                continue
            excess = bank.monthly_avg - market_avg
            if excess > 0:
                total_savings += excess

        return round(total_savings, 2)

    @staticmethod
    def _has_institution_id(df: pl.DataFrame) -> bool:
        if "institution_id" not in df.columns:
            return False
        return df["institution_id"].drop_nulls().len() > 0

    @staticmethod
    def _compute_confidence(
        analysis_months: int,
        fee_count: int,
        has_institution_id: bool,
    ) -> float:
        score = 0.0
        # Qualidade do histórico
        if analysis_months >= 6:
            score += 0.40
        elif analysis_months >= 3:
            score += 0.25
        else:
            score += 0.10
        # Tarifas encontradas
        if fee_count >= 5:
            score += 0.35
        elif fee_count >= 1:
            score += 0.20
        # institution_id disponível (permite agregar por banco corretamente)
        if has_institution_id:
            score += 0.25
        return max(0.10, min(1.00, score))
