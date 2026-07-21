import pytest
import asyncio
from app.jobs.win_back import WinBackService, run_win_back_job

def test_win_back_service():
    service = WinBackService()
    
    users = service.get_inactive_users(14)
    assert len(users) == 2
    assert "user_inativo_1" in users
    
    async def run_trigger():
        return await service.trigger_win_back_for_user(users[0])
        
    res = asyncio.run(run_trigger())
    assert res is True

def test_win_back_job_execution(monkeypatch):
    from unittest.mock import MagicMock, AsyncMock
    import app.jobs.win_back as module
    
    service_mock = MagicMock()
    service_mock.get_inactive_users.return_value = ["u1", "u2"]
    service_mock.trigger_win_back_for_user = AsyncMock()
    
    monkeypatch.setattr(module, "WinBackService", lambda: service_mock)
    
    asyncio.run(module.run_win_back_job.__wrapped__())
    
    service_mock.get_inactive_users.assert_called_once_with(days_inactive=14)
    assert service_mock.trigger_win_back_for_user.call_count == 2
