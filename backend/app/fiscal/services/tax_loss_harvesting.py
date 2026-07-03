import logging
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class OpenPosition(BaseModel):
    ticker: str
    quantity: int
    average_price: float
    current_price: float
    type: str = "Ação" # Ação, FII, etc.

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.average_price) * self.quantity

class TaxLossHarvestingOpportunity(BaseModel):
    ticker_to_sell: str
    unrealized_loss: float
    tax_saved: float
    description: str

class TaxLossHarvestingReport(BaseModel):
    user_id: str
    realized_gain_month: float
    darf_estimated: float
    opportunities: List[TaxLossHarvestingOpportunity]
    total_tax_savings_possible: float
    generated_at: datetime

class TaxLossHarvestingService:
    """
    T1 - Otimizador de IR (Tax Loss Harvesting).
    Verifica se o usuário tem lucro realizado no mês (terá que pagar DARF)
    e sugere realizar prejuízos de posições em aberto para compensar o lucro
    e evitar/reduzir o pagamento de impostos.
    """
    
    def __init__(self):
        # Simplificação: 15% para Swing Trade de Ações
        self._swing_trade_tax_rate = 0.15

    def scan_opportunities(
        self, 
        user_id: str, 
        realized_gain_month: float, 
        open_positions: List[OpenPosition]
    ) -> TaxLossHarvestingReport:
        
        logger.info(f"TaxLossHarvestingService: Escaneando oportunidades para {user_id}")
        
        # Se não teve lucro tributável (acima da isenção de 20k no mês real, mas simplificamos aqui)
        # ou se o lucro é menor ou igual a 0, não há o que compensar para pagar menos IR.
        if realized_gain_month <= 0:
            return TaxLossHarvestingReport(
                user_id=user_id,
                realized_gain_month=realized_gain_month,
                darf_estimated=0.0,
                opportunities=[],
                total_tax_savings_possible=0.0,
                generated_at=datetime.now(timezone.utc)
            )

        darf_estimated = realized_gain_month * self._swing_trade_tax_rate
        
        opportunities: List[TaxLossHarvestingOpportunity] = []
        
        # Filtra apenas posições que estão com prejuízo não realizado (unrealized_pnl < 0)
        losing_positions = [p for p in open_positions if p.unrealized_pnl < -10.0]
        
        # Ordena para sugerir os maiores prejuízos primeiro
        losing_positions.sort(key=lambda x: x.unrealized_pnl)
        
        gain_to_offset = realized_gain_month
        total_tax_saved = 0.0
        
        for pos in losing_positions:
            if gain_to_offset <= 0:
                break
                
            loss = round(abs(pos.unrealized_pnl), 2)
            
            # O quanto dessa perda pode ser usada para abater o ganho atual
            offset_used = min(loss, gain_to_offset)
            tax_saved = offset_used * self._swing_trade_tax_rate
            
            opportunities.append(
                TaxLossHarvestingOpportunity(
                    ticker_to_sell=pos.ticker,
                    unrealized_loss=loss,
                    tax_saved=round(tax_saved, 2),
                    description=f"Venda {pos.quantity} ações de {pos.ticker} para realizar prejuízo de R$ {loss:.2f}. Isso abaterá R$ {offset_used:.2f} do seu lucro mensal, economizando R$ {tax_saved:.2f} em IR."
                )
            )
            
            gain_to_offset -= offset_used
            total_tax_saved += tax_saved

        return TaxLossHarvestingReport(
            user_id=user_id,
            realized_gain_month=realized_gain_month,
            darf_estimated=round(darf_estimated, 2),
            opportunities=opportunities,
            total_tax_savings_possible=round(total_tax_saved, 2),
            generated_at=datetime.now(timezone.utc)
        )
