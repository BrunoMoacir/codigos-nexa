"""
app/opportunities/services/savings_vs_cdi.py

Ticket OPP4-C (docs/OPP4_POUPANCA_CDI_PLANO.md) — comparação genérica
poupança vs. CDI, sem depender de saldo real do usuário (Opção A do OPP.4).
A comparação personalizada (Opção B) fica para o Ticket OPP4-E (spike).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.opportunities.models import SavingsVsCdiResult
from app.opportunities.services.savings_rate import calculate_savings_rate

logger = logging.getLogger(__name__)

_DEFAULT_AMOUNT_REFERENCE_BRL = 10_000.0

# Singleton de módulo (Ticket OPP4-D): o cache do BaseConnector é por
# instância — consumidores fora do router (tool do agente, engine de
# notificações) devem usar este acessor em vez de instanciar o serviço,
# senão o TTL de cache das taxas nunca é reaproveitado.
_shared_service: "SavingsVsCdiService | None" = None


def get_savings_vs_cdi_service() -> "SavingsVsCdiService":
    global _shared_service
    if _shared_service is None:
        _shared_service = SavingsVsCdiService()
    return _shared_service

# Seção 5.5 do plano — thresholds de severidade/elegibilidade. Produto, não
# lei: se mudarem, mudar só aqui (constantes testadas em test_savings_vs_cdi.py).
_NEAR_CDI_THRESHOLD_ANNUAL_BRL = 30.0
_HIGH_SEVERITY_THRESHOLD_ANNUAL_BRL = 150.0


class SavingsVsCdiService:
    """
    Compara a remuneração oficial da poupança (savings_rate.py) com o CDI
    atual, para um valor de referência — não personalizado.

    As instâncias de conector (`AnbimaConnector`, `BacenConnector`) são
    criadas uma vez no __init__ e reaproveitadas entre chamadas de analyze():
    o cache de BaseConnector é por instância, então recriar o conector a cada
    chamada anularia o TTL de cache. Para o cache funcionar de fato entre
    requisições, o serviço deve ser instanciado uma única vez (nível de
    módulo), como o router de opportunities já faz com OpportunityEngine.
    """

    def __init__(self) -> None:
        from app.architect.connectors.anbima import AnbimaConnector
        from app.architect.connectors.bacen import BacenConnector

        self._anbima = AnbimaConnector()
        self._bacen = BacenConnector()

    def analyze_for_user(self, user_id: str) -> SavingsVsCdiResult:
        """OPP4-E — comparação PERSONALIZADA com o saldo real de poupança do
        usuário (account_balances, persistido no sync do Pluggy).

        Sem saldo fresco (< 7 dias) ou saldo zero → cai no modo genérico
        (analyze), que nunca afirma saldo do usuário. O texto personalizado
        só afirma "você tem R$ X na poupança" quando o dado existe de fato —
        regra do plano OPP.4 ("não inventar saldo")."""
        try:
            from app.core.db.balances import get_latest_balance
            snapshot = get_latest_balance(user_id, "SAVINGS")
        except Exception as exc:
            logger.warning("[SavingsVsCdiService] balance user=%s: %s", user_id, exc)
            snapshot = None

        if snapshot is None or snapshot.balance <= 0:
            return self.analyze()

        result = self.analyze(amount_reference_brl=snapshot.balance)
        if result.status == "DATA_UNAVAILABLE":
            return result

        personalized_reason = (
            f"Você tem R$ {snapshot.balance:,.2f} na poupança"
            + (f" ({snapshot.bank_name})" if snapshot.bank_name else "")
            + f". Ao CDI de hoje, isso significa cerca de "
            f"R$ {result.estimated_loss_annual_brl:,.2f}/ano rendendo a menos."
        ) if result.status == "BELOW_CDI" else result.reason

        return result.model_copy(update={
            "is_personalized": True,
            "savings_balance_brl": snapshot.balance,
            "balance_captured_at": snapshot.captured_at,
            "reason": personalized_reason,
        })

    def analyze(
        self, amount_reference_brl: float = _DEFAULT_AMOUNT_REFERENCE_BRL
    ) -> SavingsVsCdiResult:
        now = datetime.now(timezone.utc)

        try:
            cdi_annual = self._anbima.get_cdi()
            selic_annual = self._bacen.get_selic()
            tr_monthly = self._bacen.get_tr_monthly()
        except Exception as exc:
            logger.error("[SavingsVsCdiService] falha ao buscar taxas: %s", exc)
            return self._data_unavailable(amount_reference_brl, now)

        savings = calculate_savings_rate(selic_annual, tr_monthly)

        cdi_annual_pct = round(cdi_annual * 100, 4)
        cdi_reference_annual_pct = cdi_annual_pct  # CDI bruto — ver docstring de SavingsVsCdiResult
        savings_annual_pct = round(savings.savings_annual * 100, 4)
        spread_pct_points = round(cdi_reference_annual_pct - savings_annual_pct, 4)

        cdi_gain_annual = amount_reference_brl * cdi_annual
        savings_gain_annual = amount_reference_brl * savings.savings_annual
        estimated_loss_annual_brl = round(cdi_gain_annual - savings_gain_annual, 2)
        estimated_loss_monthly_brl = round(estimated_loss_annual_brl / 12, 2)

        status, severity = self._classify(estimated_loss_annual_brl)
        reason = self._build_reason(status, amount_reference_brl, estimated_loss_annual_brl)

        return SavingsVsCdiResult(
            amount_reference_brl=amount_reference_brl,
            savings_annual_pct=savings_annual_pct,
            cdi_annual_pct=cdi_annual_pct,
            cdi_reference_annual_pct=cdi_reference_annual_pct,
            spread_pct_points=spread_pct_points,
            estimated_loss_monthly_brl=estimated_loss_monthly_brl,
            estimated_loss_annual_brl=estimated_loss_annual_brl,
            status=status,
            severity=severity,
            reason=reason,
            generated_at=now,
        )

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _classify(estimated_loss_annual_brl: float) -> tuple[str, str]:
        """Seção 5.5 do plano. `<= 0` cobre o caso "incoerente" (poupança
        empatando ou superando o CDI na referência) — não é DATA_UNAVAILABLE,
        é um resultado válido só que sem desvantagem para reportar."""
        if estimated_loss_annual_brl <= 0:
            return "NO_ADVANTAGE", "LOW"
        if estimated_loss_annual_brl < _NEAR_CDI_THRESHOLD_ANNUAL_BRL:
            return "NEAR_CDI", "LOW"
        if estimated_loss_annual_brl < _HIGH_SEVERITY_THRESHOLD_ANNUAL_BRL:
            return "BELOW_CDI", "MEDIUM"
        return "BELOW_CDI", "HIGH"

    @staticmethod
    def _build_reason(
        status: str, amount_reference_brl: float, estimated_loss_annual_brl: float
    ) -> str:
        if status == "NO_ADVANTAGE":
            return (
                "Com as taxas atuais, a poupança não está perdendo para o CDI de forma "
                "relevante nesta referência — situação incomum; vale reconferir as taxas."
            )
        if status == "NEAR_CDI":
            return (
                f"A diferença estimada entre poupança e CDI é pequena hoje: cerca de "
                f"R$ {estimated_loss_annual_brl:,.2f}/ano para cada "
                f"R$ {amount_reference_brl:,.2f} na poupança."
            )
        return (
            f"Hoje a poupança tende a render menos que o CDI. Para cada "
            f"R$ {amount_reference_brl:,.2f} na poupança, a diferença estimada é de "
            f"R$ {estimated_loss_annual_brl:,.2f}/ano."
        )

    @staticmethod
    def _data_unavailable(amount_reference_brl: float, now: datetime) -> SavingsVsCdiResult:
        return SavingsVsCdiResult(
            amount_reference_brl=amount_reference_brl,
            savings_annual_pct=0.0,
            cdi_annual_pct=0.0,
            cdi_reference_annual_pct=0.0,
            spread_pct_points=0.0,
            estimated_loss_monthly_brl=0.0,
            estimated_loss_annual_brl=0.0,
            status="DATA_UNAVAILABLE",
            severity="LOW",
            reason="Não foi possível calcular a comparação agora — tente novamente em instantes.",
            generated_at=now,
        )
