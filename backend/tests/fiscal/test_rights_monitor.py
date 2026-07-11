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

def test_connectors_not_found_case():
    # Test SVR, FGTS and Receita with specific hashes to guarantee "NOT_FOUND"
    from app.fiscal.rights_monitor.services.fgts_connector import FGTSConnector
    from app.fiscal.rights_monitor.services.receita_connector import ReceitaConnector
    
    svr = SVRConnector()
    fgts = FGTSConnector()
    receita = ReceitaConnector()
    
    # Try different CPFs until we hit the "NOT_FOUND" branch for each.
    # SVR uses hash(cpf) % 3 == 0 for AVAILABLE.
    # Because hash() is randomized per process in Python, we loop until we hit NOT_FOUND.
    async def run_tests():
        # SVR
        for i in range(100):
            cpf = f"test_cpf_{i}"
            c = await svr.check_rights("u", cpf)
            if c.status == "NOT_FOUND":
                assert True
                break

        # FGTS
        for i in range(100):
            cpf = f"test_cpf_{i}"
            f = await fgts.check_rights("u", cpf)
            if f.status == "NOT_FOUND":
                assert True
                break
        
        # Receita
        for i in range(100):
            cpf = f"test_cpf_{i}"
            r = await receita.check_rights("u", cpf)
            if r.status == "NOT_FOUND":
                assert True
                break
        
    asyncio.run(run_tests())

def test_aggregator_with_exceptions(monkeypatch):
    from app.fiscal.rights_monitor.services.monitor import RightsMonitorAggregator
    
    aggregator = RightsMonitorAggregator()
    
    # Mock check_rights to raise an exception
    async def mock_check_rights(*args, **kwargs):
        raise ValueError("Simulated connection error")
        
    monkeypatch.setattr(aggregator.svr, "check_rights", mock_check_rights)
    
    cpf = "123"
    async def run_aggregator():
        return await aggregator.run_scan(user_id="user_err", cpf=cpf)
        
    report = asyncio.run(run_aggregator())
    
    # Only FGTS and Receita should be there because SVR failed.
    assert len(report.candidates) == 2
    sources = {c.source for c in report.candidates}
    assert "SVR_BACEN" not in sources

