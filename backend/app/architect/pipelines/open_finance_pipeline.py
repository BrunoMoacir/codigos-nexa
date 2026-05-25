"""
app/architect/pipelines/open_finance_pipeline.py
Transforma dados normalizados do Open Finance em OpenFinanceFeatures.

Responsabilidade:
    Camada pura de transformação (sem I/O, sem dependências externas).
    O conector institucional (por banco / agregador) normaliza o JSON bruto
    da API antes de passar aqui. Esta classe faz a extração de features.

Filosofia:
    Fail-silent por campo: se um endpoint não retorna dado ou o valor está
    malformado, o campo correspondente fica None. A simulação degrada
    graciosamente usando valores de mercado como fallback.

Formato de entrada (já normalizado):

    investments (list[dict]):
        type         : "FIXED_INCOME" | "VARIABLE_INCOME" | "HYBRID"
        amount_brl   : float   — valor total investido neste produto (R$)
        rate_annual  : float?  — retorno anual (decimal). Ex: 0.12 = 12% a.a.
        indexer      : str?    — "CDI" | "SELIC" | "IPCA+" | None
        indexer_pct  : float?  — fração do indexer. Ex: 1.005 = 100,5% CDI
        duration_years: float? — duration do ativo (anos)

    loans (list[dict]):
        cet_annual       : float — CET do contrato (decimal anual)
        monthly_payment  : float — parcela mensal (R$)
        paid_instalments : int   — parcelas pagas em dia
        missed_payments  : int   — parcelas em atraso (default 0)

    accounts (list[dict]):
        year          : int   — ano do período
        month         : int   — mês do período (1–12)
        income_total  : float — total de créditos no mês (R$)
        balance_delta : float — saldo final - saldo inicial (>0 = poupou)

    financings (list[dict]):
        product_type     : "HOME_LOAN" | "VEHICLE_LOAN" | "OTHER"
        cet_annual       : float — CET do contrato (decimal anual)
        paid_instalments : int
        missed_payments  : int   (default 0)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MONTH_LABELS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                 "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


class OpenFinancePipeline:
    """
    Extrai OpenFinanceFeatures a partir de dados normalizados do Open Finance.

    Uso:
        features = OpenFinancePipeline().extract(
            investments=inv_data,
            loans=loan_data,
            accounts=acc_data,
            financings=fin_data,
            cdi_annual=0.1465,
            monthly_income=8000.0,
        )
    """

    def extract(
        self,
        investments: Optional[list[dict]] = None,
        loans: Optional[list[dict]] = None,
        accounts: Optional[list[dict]] = None,
        financings: Optional[list[dict]] = None,
        cdi_annual: float = 0.1465,
        monthly_income: Optional[float] = None,
    ) -> "OpenFinanceFeatures":
        """
        Extrai e agrega features de todos os endpoints disponíveis.

        Args:
            investments:    Dados de /investments (carteira de investimentos).
            loans:          Dados de /loans (contratos de crédito ativos).
            accounts:       Dados de /accounts (movimentação por mês).
            financings:     Dados de /financings (financiamentos históricos).
            cdi_annual:     CDI atual (para converter indexer_pct → taxa efetiva).
            monthly_income: Renda mensal bruta do usuário (para comprometimento_renda_pct).

        Returns:
            OpenFinanceFeatures com os campos preenchidos a partir dos dados disponíveis.
            Campos sem dado ficam None.
        """
        # Importação local para evitar circular import (models → pipeline → models)
        from app.architect.models import OpenFinanceFeatures

        features: dict = {}

        if investments:
            try:
                features.update(self._from_investments(investments, cdi_annual))
            except Exception as exc:
                logger.warning("OpenFinancePipeline | /investments falhou: %s", exc)

        if loans:
            try:
                features.update(self._from_loans(loans, monthly_income))
            except Exception as exc:
                logger.warning("OpenFinancePipeline | /loans falhou: %s", exc)

        if accounts:
            try:
                features.update(self._from_accounts(accounts))
            except Exception as exc:
                logger.warning("OpenFinancePipeline | /accounts falhou: %s", exc)

        if financings:
            try:
                features.update(self._from_financings(financings))
            except Exception as exc:
                logger.warning("OpenFinancePipeline | /financings falhou: %s", exc)

        return OpenFinanceFeatures(**features)

    # ─── Extratores por endpoint ───────────────────────────────────────────────

    @staticmethod
    def _from_investments(data: list[dict], cdi_annual: float) -> dict:
        """
        Extrai rendimento real, composição de carteira e duration.

        Lógica de retorno:
          1. Se rate_annual informado → usa diretamente.
          2. Se indexer=CDI + indexer_pct → rate = cdi_annual × indexer_pct.
          3. Retorno ponderado pelo valor (amount_brl) investido por produto.

        O retorno resultante já reflete o net IR de longo prazo (≥720 dias = 15%)
        quando o conector institucional aplica o ajuste fiscal antes de passar aqui.
        Caso contrário, aplica-se 0.85 como proxy de IR 15%.
        """
        total_brl = sum(float(d.get("amount_brl", 0) or 0) for d in data)
        if total_brl <= 0:
            return {}

        rf_brl = rv_brl = 0.0
        weighted_rate = 0.0
        weighted_duration = 0.0
        rate_weight_sum = 0.0
        dur_weight_sum = 0.0

        for item in data:
            amt = float(item.get("amount_brl", 0) or 0)
            w = amt / total_brl

            asset_type = (item.get("type") or "").upper()
            if "FIXED" in asset_type or "RENDA_FIXA" in asset_type:
                rf_brl += amt
            elif "VARIABLE" in asset_type or "RENDA_VARIAVEL" in asset_type:
                rv_brl += amt

            rate = item.get("rate_annual")
            if rate is None:
                indexer = (item.get("indexer") or "").upper()
                pct = item.get("indexer_pct")
                if pct is not None:
                    base = cdi_annual if "CDI" in indexer else (
                        cdi_annual if "SELIC" in indexer else None
                    )
                    if base is not None:
                        # Gross rate — apply 85% as IR 15% proxy (≥720-day fixed income)
                        rate = base * float(pct) * 0.85

            if rate is not None and amt > 0:
                weighted_rate += w * float(rate)
                rate_weight_sum += w

            dur = item.get("duration_years")
            if dur is not None and amt > 0:
                weighted_duration += w * float(dur)
                dur_weight_sum += w

        result: dict = {}
        if rate_weight_sum > 0:
            effective_rate = weighted_rate / rate_weight_sum
            result["rendimento_real_atual"] = round(min(max(effective_rate, 0.0), 1.0), 4)

        if total_brl > 0:
            result["composicao_rf_pct"] = round(rf_brl / total_brl, 4)
            result["composicao_rv_pct"] = round(rv_brl / total_brl, 4)

        if dur_weight_sum > 0:
            result["duration_media_anos"] = round(weighted_duration / dur_weight_sum, 2)

        return result

    @staticmethod
    def _from_loans(data: list[dict], monthly_income: Optional[float]) -> dict:
        """
        Extrai CET médio histórico, adimplência e comprometimento de renda.

        Adimplência: parcelas pagas / (pagas + atrasadas) — acumulado de todos os contratos.
        CET médio: média ponderada pelo valor da parcela mensal.
        Comprometimento: soma das parcelas / renda mensal (requer monthly_income).
        """
        result: dict = {}
        cet_values: list[tuple[float, float]] = []
        total_paid = total_missed = 0
        total_monthly = 0.0

        for item in data:
            cet = item.get("cet_annual")
            pmt = float(item.get("monthly_payment", 0) or 0)
            paid = int(item.get("paid_instalments", 0) or 0)
            missed = int(item.get("missed_payments", 0) or 0)

            if cet is not None and pmt > 0:
                cet_values.append((float(cet), pmt))
            total_paid += paid
            total_missed += missed
            total_monthly += pmt

        if cet_values:
            total_w = sum(p for _, p in cet_values)
            result["cet_medio_historico"] = round(
                sum(c * p for c, p in cet_values) / total_w, 4
            )

        total_instalments = total_paid + total_missed
        if total_instalments > 0:
            result["adimplencia_pct"] = round(total_paid / total_instalments, 4)

        if total_monthly > 0 and monthly_income and monthly_income > 0:
            result["comprometimento_renda_pct"] = round(
                min(total_monthly / monthly_income, 1.0), 4
            )

        return result

    @staticmethod
    def _from_accounts(data: list[dict]) -> dict:
        """
        Extrai sazonalidade de receita e padrão de poupança.

        Sazonalidade: multiplicadores mensais relativos à média anual.
        Padrão de poupança: meses consecutivos com balance_delta > 0.
        Requer ao menos 6 meses de dados para calcular sazonalidade confiável.
        """
        result: dict = {}
        by_month: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        savings_streak = current_streak = 0

        sorted_data = sorted(
            data,
            key=lambda x: (x.get("year", 0), x.get("month", 0)),
        )
        for record in sorted_data:
            m = int(record.get("month", 0) or 0)
            if 1 <= m <= 12:
                income = float(record.get("income_total", 0) or 0)
                if income > 0:
                    by_month[m].append(income)

            delta = float(record.get("balance_delta", 0) or 0)
            if delta > 0:
                current_streak += 1
                savings_streak = max(savings_streak, current_streak)
            else:
                current_streak = 0

        monthly_avgs = {
            m: (sum(v) / len(v)) for m, v in by_month.items() if v
        }
        if len(monthly_avgs) >= 6:
            annual_avg = sum(monthly_avgs.values()) / len(monthly_avgs)
            if annual_avg > 0:
                sazon = [
                    round(monthly_avgs.get(m, annual_avg) / annual_avg, 3)
                    for m in range(1, 13)
                ]
                result["sazonalidade_receita"] = sazon

        if savings_streak > 0:
            result["meses_consecutivos_poupanca"] = savings_streak

        return result

    @staticmethod
    def _from_financings(data: list[dict]) -> dict:
        """
        Extrai experiência com financiamento e CET histórico real.

        CET histórico real: média simples dos contratos de financiamento.
        Difere do cet_medio_historico (de /loans, que inclui crédito pessoal e
        consignado) — representa exclusivamente o custo de financiamentos
        de bens, análogo ao que o usuário pagaria em um novo contrato.
        """
        if not data:
            return {}

        result: dict = {"experiencia_financiamento": True}
        cet_values = []

        for item in data:
            cet = item.get("cet_annual")
            if cet is not None:
                cet_values.append(float(cet))

        if cet_values:
            result["cet_historico_real"] = round(sum(cet_values) / len(cet_values), 4)

        return result


__all__ = ["OpenFinancePipeline"]
