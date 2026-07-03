import pytest
import asyncio
from app.fiscal.rights_monitor.services.svr_connector import SVRConnector

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
