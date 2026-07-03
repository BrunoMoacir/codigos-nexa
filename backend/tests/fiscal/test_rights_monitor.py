import pytest
import asyncio
from app.fiscal.rights_monitor.services.svr_connector import SVRConnector
from app.fiscal.rights_monitor.services.monitor import RightsMonitorAggregator

def test_svr_connector_returns_candidate():
    connector = SVRConnector()
    cpf_1 = "12345678900"
    
    async def run_test():
        return await connector.check_rights(user_id="user_1", cpf=cpf_1)
        
    candidate = asyncio.run(run_test())
    
    assert candidate.source == "SVR_BACEN"
    assert candidate.status in ["AVAILABLE", "NOT_FOUND"]
    assert candidate.estimated_amount >= 0.0
    assert candidate.action_url == "https://valoresareceber.bcb.gov.br/"

def test_rights_monitor_aggregator():
    aggregator = RightsMonitorAggregator()
    cpf = "00000000000"
    
    async def run_aggregator():
        return await aggregator.run_scan(user_id="user_2", cpf=cpf)
        
    report = asyncio.run(run_aggregator())
    
    assert report.user_id == "user_2"
    assert len(report.candidates) == 3
    sources = {c.source for c in report.candidates}
    assert sources == {"SVR_BACEN", "FGTS", "IR_RESTITUTION"}
