import pytest
import asyncio
from unittest.mock import MagicMock
from app.jobs.promotion_alerts import PromotionAlertsService, run_promotion_alerts_job

def test_promotion_alerts_service(monkeypatch):
    from app.optimizer.promotion_tracker import TransferPromotion
    from datetime import date
    
    service = PromotionAlertsService()
    
    # Mock do tracker para retornar 1 promocao
    mock_promo = TransferPromotion(
        id="livelo-azul",
        loyalty_program="LIVELO",
        partner="TUDOAZUL",
        bonus_pct=100.0,
        normal_rate_per_1000=20.0,
        effective_rate_per_1000=40.0,
        start_date=date.today(),
        end_date=date.today(),
        min_points=1000,
        max_points=None,
        eligible_cards=["Qualquer"],
        description="Teste",
        source="manual",
        last_verified=date.today().isoformat()
    )
    
    tracker_mock = MagicMock()
    tracker_mock.get_active_promotions.return_value = [mock_promo]
    service.tracker = tracker_mock
    
    async def run_process():
        return await service.process_alerts_for_user("user_123")
        
    res = asyncio.run(run_process())
    assert res is True
    tracker_mock.get_active_promotions.assert_called_once()

def test_promotion_alerts_service_empty(monkeypatch):
    service = PromotionAlertsService()
    
    tracker_mock = MagicMock()
    tracker_mock.get_active_promotions.return_value = []
    service.tracker = tracker_mock
    
    async def run_process():
        return await service.process_alerts_for_user("user_456")
        
    res = asyncio.run(run_process())
    assert res is False

def test_run_promotion_alerts_job(monkeypatch):
    import app.jobs.promotion_alerts as module
    
    service_mock = MagicMock()
    service_mock.process_alerts_for_user = MagicMock()
    
    monkeypatch.setattr(module, "PromotionAlertsService", lambda: service_mock)
    monkeypatch.setattr(module, "get_active_user_ids", lambda: ["u1", "u2"])
    
    asyncio.run(module.run_promotion_alerts_job.__wrapped__())
    
    # get_active_user_ids retornou 2 usuarios, entao process deve ser chamado 2x
    assert service_mock.process_alerts_for_user.call_count == 2
