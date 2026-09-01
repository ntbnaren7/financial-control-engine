import pytest
from unittest.mock import AsyncMock, MagicMock
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.evidence.models import ProviderObservation
from src.investigation.models import EvidenceType, WebhookCapturedContent, ProcessingCoverageContent
from src.reconciliation.models import VerifiedDiscrepancy

@pytest.mark.asyncio
async def test_gatherer_transformations():
    # Setup mock session and sessionmaker
    mock_session = AsyncMock()
    mock_session_maker = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    
    # Fake database rows
    fake_obs_1 = ProviderObservation(
        provider="razorpay",
        event_id="evt_1",
        event_type="webhook",
        payload={"order_id": "ord_123"}
    )
    fake_obs_2 = ProviderObservation(
        provider="razorpay",
        event_id="evt_2",
        event_type="processing",
        payload={"order_id": "ord_123"}
    )
    fake_obs_3 = ProviderObservation(
        provider="razorpay",
        event_id="evt_3",
        event_type="webhook",
        payload={"order_id": "ord_999"} # Irrelevant order
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_obs_1, fake_obs_2, fake_obs_3]
    mock_session.execute.return_value = mock_result
    
    discrepancy = VerifiedDiscrepancy(
        discrepancy_id="disc_1",
        payment_id="pay_1",
        order_id="ord_123",
        description="test",
        provider_status="captured",
        merchant_status="UNPAID",
        amount_match=True,
        currency_match=True,
        identity_verified=True
    )
    
    gatherer = DatabaseEvidenceGatherer(mock_session_maker)
    packet = await gatherer.gather(discrepancy)
    
    # Verify the bounded packet
    assert len(packet.items) == 2
    
    webhook_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_WEBHOOK_CAPTURED)
    processing_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_PROCESSING_COVERAGE)
    
    # Verify strict typing and semantic extraction
    assert isinstance(webhook_ev.content, WebhookCapturedContent)
    assert webhook_ev.content.present is True
    
    assert isinstance(processing_ev.content, ProcessingCoverageContent)
    assert processing_ev.content.coverage == "COMPLETE"
    assert processing_ev.content.processing_count == 1
