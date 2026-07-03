import pytest
from app.fiscal.services.tax_radar import TaxRadarService, MockAsset

def test_tax_radar_detects_inefficient_cdb():
    radar = TaxRadarService()
    
    # CDB rendendo 11% ao ano, imposto de 22.5% (6 meses) -> Líquido = 8.525%
    # Mercado tem LCI a 10.5%. Então CDB perde pra caramba.
    portfolio = [
        MockAsset(
            asset_name="CDB Banco X",
            asset_type="CDB",
            amount=50000.0,
            gross_rate_pct=11.0,
            holding_months=6
        )
    ]
    
    report = radar.scan_portfolio(user_id="user_test", portfolio=portfolio)
    
    assert len(report.alerts) == 1
    alert = report.alerts[0]
    assert alert.alert_type == "CDB_INEFFICIENT"
    assert alert.priority == "HIGH"
    assert alert.estimated_impact_brl > 0

def test_tax_radar_detects_poupanca():
    radar = TaxRadarService()
    
    portfolio = [
        MockAsset(
            asset_name="Poupança Caixa",
            asset_type="POUPANCA",
            amount=20000.0,
            gross_rate_pct=6.17,
            holding_months=12
        )
    ]
    
    report = radar.scan_portfolio(user_id="user_test", portfolio=portfolio)
    
    assert len(report.alerts) == 1
    alert = report.alerts[0]
    assert alert.alert_type == "POUPANCA_INEFFICIENT"
    assert "Tesouro SELIC" in alert.description

def test_tax_radar_detects_come_cotas():
    radar = TaxRadarService()
    
    portfolio = [
        MockAsset(
            asset_name="Fundo Multimercado Y",
            asset_type="FUND",
            amount=100000.0,
            gross_rate_pct=10.0,
            holding_months=12
        )
    ]
    
    report = radar.scan_portfolio(user_id="user_test", portfolio=portfolio)
    
    assert len(report.alerts) == 1
    alert = report.alerts[0]
    assert alert.alert_type == "COME_COTAS_IMPACT"
    assert alert.estimated_impact_brl == 1500.0  # 15% sobre 10k de rendimento

def test_tax_radar_efficient_portfolio():
    radar = TaxRadarService()
    
    # CDB a 14% -> Lci breakeven ~ 11.2%. Melhor que LCI de mercado (10.5%).
    portfolio = [
        MockAsset(
            asset_name="CDB Banco Y",
            asset_type="CDB",
            amount=50000.0,
            gross_rate_pct=14.0,
            holding_months=24
        ),
        MockAsset(
            asset_name="LCI Banco Z",
            asset_type="LCI",
            amount=20000.0,
            gross_rate_pct=10.5,
            holding_months=12
        )
    ]
    
    report = radar.scan_portfolio(user_id="user_test", portfolio=portfolio)
    
    assert len(report.alerts) == 0
    assert report.total_estimated_savings_brl == 0.0
