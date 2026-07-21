import pytest
from datetime import date
from app.jobs.quarterly_report import QuarterlyReportService, run_quarterly_report_job
import asyncio

def test_quarterly_report_logic():
    service = QuarterlyReportService()
    
    async def run_test():
        return await service.generate_for_user("user_123", date(2025, 4, 1))
        
    res = asyncio.run(run_test())
    assert res.quarter == 1
    assert res.year == 2025
    assert res.total_spent > 0
    assert res.total_fees_paid > 0
    assert res.total_saved > 0

def test_quarterly_report_q4_logic():
    service = QuarterlyReportService()
    
    async def run_test():
        return await service.generate_for_user("user_123", date(2026, 1, 1))
        
    res = asyncio.run(run_test())
    assert res.quarter == 4
    assert res.year == 2025

def test_job_ignores_wrong_day(monkeypatch):
    from unittest.mock import AsyncMock
    import app.jobs.quarterly_report as module
    
    service_mock = AsyncMock()
    monkeypatch.setattr(module, "QuarterlyReportService", lambda: service_mock)
    
    class MockDate:
        @classmethod
        def today(cls):
            return date(2025, 4, 2)
            
    monkeypatch.setattr(module, "date", MockDate)
    
    asyncio.run(module.run_quarterly_report_job.__wrapped__())
    
    service_mock.generate_for_user.assert_not_called()
