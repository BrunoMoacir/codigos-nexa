import logging
from typing import List, Literal, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
from app.fiscal.ir_pf_calculator import IRPFCalculator

logger = logging.getLogger(__name__)

AlertType = Literal["CDB_INEFFICIENT", "COME_COTAS_IMPACT", "POUPANCA_INEFFICIENT"]
AlertPriority = Literal["HIGH", "MEDIUM", "LOW"]

class TaxRadarAlert(BaseModel):
    alert_type: AlertType
    priority: AlertPriority
    title: str
    description: str
    asset_name: str
    estimated_impact_brl: float
    action_hint: str

class TaxRadarReport(BaseModel):
    user_id: str
    total_estimated_savings_brl: float
    alerts: List[TaxRadarAlert]
    generated_at: datetime

class MockAsset(BaseModel):
    asset_name: str
    asset_type: Literal["CDB", "FUND", "POUPANCA", "LCI", "LCA", "STOCK"]
    amount: float
    gross_rate_pct: float
    holding_months: int

class TaxRadarService:
    """
    T2 - Radar Proativo Modo Imposto Zero.
    Escaneia a carteira de investimentos (aqui simulada) e dispara
    alertas de ineficiências fiscais.
    """

    def __init__(self):
        self._ir_calc = IRPFCalculator()

        # Simulação de LCI de mercado — fora do escopo do OPP4-B, não vem de conector.
        self._market_lci_rate_pct = 10.5

        # SELIC/TR reais via BACEN (Ticket OPP4-B) — antes eram hardcoded
        # (11.25 aqui, 6.17 em _check_poupanca_inefficiency). Não reintroduzir
        # número fixo: calculate_savings_rate() é a única fonte de verdade
        # para a taxa da poupança no repositório.
        from app.architect.connectors.bacen import BacenConnector

        bacen = BacenConnector()
        self._selic_annual = bacen.get_selic()
        self._tr_monthly = bacen.get_tr_monthly()
        self._selic_rate_pct = round(self._selic_annual * 100, 4)

    def scan_portfolio(self, user_id: str, portfolio: List[MockAsset]) -> TaxRadarReport:
        logger.info(f"TaxRadarService: Escaneando portfolio para user {user_id}")
        
        alerts: List[TaxRadarAlert] = []
        
        for asset in portfolio:
            if asset.asset_type == "CDB":
                self._check_cdb_inefficiency(asset, alerts)
            elif asset.asset_type == "FUND":
                self._check_come_cotas_impact(asset, alerts)
            elif asset.asset_type == "POUPANCA":
                self._check_poupanca_inefficiency(asset, alerts)

        total_savings = sum(a.estimated_impact_brl for a in alerts)
        
        return TaxRadarReport(
            user_id=user_id,
            total_estimated_savings_brl=total_savings,
            alerts=alerts,
            generated_at=datetime.now(timezone.utc)
        )

    def _check_cdb_inefficiency(self, asset: MockAsset, alerts: List[TaxRadarAlert]):
        # Usa a calculadora para ver o breakeven
        bk = self._ir_calc.calc_breakeven_lci(
            cdb_gross_rate_pct=asset.gross_rate_pct,
            holding_months=asset.holding_months,
            lci_offered_rate_pct=self._market_lci_rate_pct
        )
        
        # Se a LCI oferecida for melhor que o Breakeven do CDB
        if bk.lci_advantage_pct and bk.lci_advantage_pct > 0:
            # Impacto bruto estimado num ano: diferenca percentual sobre o montante
            estimated_impact = (bk.lci_advantage_pct / 100.0) * asset.amount
            
            # Só avisa se o impacto for maior que R$ 50
            if estimated_impact >= 50.0:
                alerts.append(TaxRadarAlert(
                    alert_type="CDB_INEFFICIENT",
                    priority="HIGH" if estimated_impact > 300 else "MEDIUM",
                    title="Seu CDB está rendendo menos que uma LCI isenta de IR",
                    description=f"O {asset.asset_name} paga {asset.gross_rate_pct}% a.a., mas devido ao IR, rende apenas {bk.cdb_net_rate_pct}% a.a. líquidos.",
                    asset_name=asset.asset_name,
                    estimated_impact_brl=round(estimated_impact, 2),
                    action_hint=f"Resgate se tiver liquidez diária e aplique em uma LCI que pague pelo menos {bk.lci_breakeven_pct}% a.a."
                ))

    def _check_come_cotas_impact(self, asset: MockAsset, alerts: List[TaxRadarAlert]):
        # Come-cotas incide em maio e novembro sobre o rendimento.
        # Estimativa simples: 15% sobre a rentabilidade passada.
        estimated_yield = asset.amount * (asset.gross_rate_pct / 100.0)
        estimated_come_cotas = estimated_yield * 0.15
        
        if estimated_come_cotas >= 100.0:
            alerts.append(TaxRadarAlert(
                alert_type="COME_COTAS_IMPACT",
                priority="MEDIUM",
                title="Alto impacto do Come-Cotas no seu fundo de investimento",
                description=f"O {asset.asset_name} sofre antecipação de IR que corrói o efeito dos juros compostos.",
                asset_name=asset.asset_name,
                estimated_impact_brl=round(estimated_come_cotas, 2),
                action_hint="Considere fundos isentos (FIIs, FIAGRO, Debêntures Incentivadas) ou títulos de renda fixa direto se a estratégia permitir."
            ))

    def _check_poupanca_inefficiency(self, asset: MockAsset, alerts: List[TaxRadarAlert]):
        # Taxa oficial da poupança via SELIC + TR reais (Ticket OPP4-B) —
        # antes era um número fixo (6.17). Ver savings_rate.py para a regra.
        from app.opportunities.services.savings_rate import calculate_savings_rate

        savings = calculate_savings_rate(self._selic_annual, self._tr_monthly)
        poupanca_rate = round(savings.savings_annual * 100, 4)

        if asset.amount >= 1000.0:
            # Tesouro Selic liquido ~ (Selic - IR) -> (11.25 - 20%) ~ 9.0%
            tesouro_net_rate = self._selic_rate_pct * 0.80
            advantage_pct = tesouro_net_rate - poupanca_rate
            
            estimated_impact = (advantage_pct / 100.0) * asset.amount
            
            if estimated_impact >= 30.0:
                alerts.append(TaxRadarAlert(
                    alert_type="POUPANCA_INEFFICIENT",
                    priority="HIGH",
                    title="Dinheiro perdendo para a inflação na Poupança",
                    description=f"O {asset.asset_name} rende apenas {poupanca_rate}% ao ano. O Tesouro SELIC rende cerca de {tesouro_net_rate}% a.a. já livre de IR.",
                    asset_name=asset.asset_name,
                    estimated_impact_brl=round(estimated_impact, 2),
                    action_hint="Migre o valor para o Tesouro SELIC ou um CDB 100% CDI com liquidez diária."
                ))
