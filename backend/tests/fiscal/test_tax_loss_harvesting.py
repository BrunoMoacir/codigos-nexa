import pytest
from app.fiscal.services.tax_loss_harvesting import TaxLossHarvestingService, OpenPosition

def test_no_realized_gain_returns_empty():
    service = TaxLossHarvestingService()
    
    positions = [
        OpenPosition(ticker="PETR4", quantity=100, average_price=30.0, current_price=25.0)
    ]
    
    report = service.scan_opportunities(user_id="user1", realized_gain_month=0.0, open_positions=positions)
    
    assert len(report.opportunities) == 0
    assert report.total_tax_savings_possible == 0.0
    assert report.darf_estimated == 0.0

def test_realized_gain_with_losing_position():
    service = TaxLossHarvestingService()
    
    # Ganho de R$ 1000 no mês. IR devido = R$ 150.
    # Tem posição MGLU3 com perda de R$ -600.
    positions = [
        OpenPosition(ticker="MGLU3", quantity=1000, average_price=2.0, current_price=1.4) # Prejuízo de -600
    ]
    
    report = service.scan_opportunities(user_id="user1", realized_gain_month=1000.0, open_positions=positions)
    
    assert report.darf_estimated == 150.0
    assert len(report.opportunities) == 1
    
    opp = report.opportunities[0]
    assert opp.ticker_to_sell == "MGLU3"
    assert opp.unrealized_loss == 600.0
    assert opp.tax_saved == 90.0  # 15% de 600
    assert report.total_tax_savings_possible == 90.0

def test_realized_gain_with_multiple_losing_positions_exceeding_gain():
    service = TaxLossHarvestingService()
    
    # Ganho de R$ 500. IR devido = R$ 75.
    positions = [
        OpenPosition(ticker="POS1", quantity=100, average_price=10.0, current_price=5.0), # Perda de -500
        OpenPosition(ticker="POS2", quantity=100, average_price=10.0, current_price=5.0)  # Perda de -500
    ]
    
    report = service.scan_opportunities(user_id="user1", realized_gain_month=500.0, open_positions=positions)
    
    assert report.darf_estimated == 75.0
    assert len(report.opportunities) == 1  # Só precisou/usou uma para zerar o ganho (embora o loop possa adicionar a segunda com tax_saved=0 se não tivesse o break, mas o break impede)
    
    assert report.total_tax_savings_possible == 75.0

def test_realized_gain_with_winning_position_ignored():
    service = TaxLossHarvestingService()
    
    # Ganho de R$ 1000.
    # Posição VALE3 está com LUCRO não realizado. Não deve sugerir venda.
    positions = [
        OpenPosition(ticker="VALE3", quantity=100, average_price=60.0, current_price=70.0) # Lucro de +1000
    ]
    
    report = service.scan_opportunities(user_id="user1", realized_gain_month=1000.0, open_positions=positions)
    
    assert len(report.opportunities) == 0
    assert report.total_tax_savings_possible == 0.0

def test_loss_harvesting_ignores_small_losses():
    service = TaxLossHarvestingService()
    
    # Prejuízos menores que 10.0 reais devem ser ignorados pela regra < -10.0
    positions = [
        OpenPosition(ticker="POS1", quantity=1, average_price=20.0, current_price=15.0), # Perda de -5.0
        OpenPosition(ticker="POS2", quantity=1, average_price=10.0, current_price=1.0)   # Perda de -9.0
    ]
    
    report = service.scan_opportunities(user_id="user1", realized_gain_month=500.0, open_positions=positions)
    
    assert len(report.opportunities) == 0

def test_loss_harvesting_ordering_largest_losses_first():
    service = TaxLossHarvestingService()
    
    # O ganho é de R$ 500.
    # Temos 3 posições com perdas. A maior é a POS3 (-600), depois POS2 (-400), depois POS1 (-50)
    # A lógica deve pegar a POS3 primeiro. Como ela é suficiente para abater os R$ 500, só ela será sugerida.
    positions = [
        OpenPosition(ticker="POS1", quantity=1, average_price=100.0, current_price=50.0),   # -50.0
        OpenPosition(ticker="POS2", quantity=1, average_price=500.0, current_price=100.0),  # -400.0
        OpenPosition(ticker="POS3", quantity=1, average_price=1000.0, current_price=400.0)  # -600.0
    ]
    
    report = service.scan_opportunities(user_id="user1", realized_gain_month=500.0, open_positions=positions)
    
    assert len(report.opportunities) == 1
    assert report.opportunities[0].ticker_to_sell == "POS3"
    assert report.opportunities[0].unrealized_loss == 600.0
    # O tax saved max vai ser 15% de 500, pois usou 500 da perda de 600
    assert report.opportunities[0].tax_saved == 75.0
