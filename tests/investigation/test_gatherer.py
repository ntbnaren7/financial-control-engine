from src.evidence.models import EntityType
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.evidence.models import ProviderObservation
from src.merchant.models import MerchantOrder
from src.investigation.models import (
    EvidenceType,
    EvidenceCoverage,
    ProviderPaymentContent,
    MerchantOrderStateContent,
    WebhookCapturedContent,
    WebhookCoverageContent,
    ProcessingCoverageContent,
    MerchantProcessingContent,
    MerchantStateTransitionContent,
    StateTransitionCoverageContent,
)
from src.reconciliation.models import VerifiedDiscrepancy

@pytest.mark.asyncio
async def test_gatherer_transformations():
    # Setup mock session and sessionmaker
    mock_session = AsyncMock()
    mock_session_maker = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    
    # Fake database rows
    fake_obs_pay = ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        provider="razorpay",
        event_id="evt_pay_1",
        event_type="payment",
        payload={"order_id": "ord_123", "payment_id": "pay_1", "amount": 5000, "currency": "INR", "status": "captured", "captured": True}
    )
    fake_obs_wh = ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        provider="razorpay",
        event_id="evt_wh_1",
        event_type="webhook",
        payload={"order_id": "ord_123"}
    )
    fake_obs_proc = ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        provider="razorpay",
        event_id="evt_proc_1",
        event_type="processing",
        payload={"order_id": "ord_123", "status": "PROCESSED"}
    )
    fake_obs_st = ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        provider="razorpay",
        event_id="evt_st_1",
        event_type="state_transition",
        payload={"order_id": "ord_123", "from_status": "CREATED", "to_status": "UNPAID"}
    )
    fake_obs_irrelevant = ProviderObservation(
        entity_type=EntityType.PAYMENT.value,
        entity_id="pay_123",
        provider="razorpay",
        event_id="evt_other",
        event_type="webhook",
        payload={"order_id": "ord_999"} # Irrelevant order
    )
    
    fake_merchant_order = MerchantOrder(
        merchant_order_id="mo_123",
        razorpay_order_id="ord_123",
        expected_amount=5000,
        currency="INR",
        status="UNPAID"
    )
    
    # Configure mock returns for the two execute calls:
    # 1. select(ProviderObservation)
    mock_res_obs = MagicMock()
    mock_res_obs.scalars.return_value.all.return_value = [
        fake_obs_pay, fake_obs_wh, fake_obs_proc, fake_obs_st, fake_obs_irrelevant
    ]
    
    # 2. select(MerchantOrder)
    mock_res_order = MagicMock()
    mock_res_order.scalars.return_value.first.return_value = fake_merchant_order
    
    mock_session.execute.side_effect = [mock_res_obs, mock_res_order]
    
    discrepancy = VerifiedDiscrepancy(
        discrepancy_id="disc_1",
        payment_id="pay_1",
        order_id="ord_123",
        description="Captured payment with stale order",
        provider_status="captured",
        merchant_status="UNPAID",
        amount_match=True,
        currency_match=True,
        identity_verified=True
    )
    
    gatherer = DatabaseEvidenceGatherer(mock_session_maker)
    packet = await gatherer.gather(discrepancy)
    
    # Verify the bounded packet contains all expected observational items
    item_types = [ev.type for ev in packet.items]
    assert EvidenceType.E_PROVIDER_PAYMENT in item_types
    assert EvidenceType.E_MERCHANT_ORDER_STATE in item_types
    assert EvidenceType.E_WEBHOOK_CAPTURED in item_types
    assert EvidenceType.E_WEBHOOK_COVERAGE in item_types
    assert EvidenceType.E_MERCHANT_PROCESSING in item_types
    assert EvidenceType.E_PROCESSING_COVERAGE in item_types
    assert EvidenceType.E_MERCHANT_STATE_TRANSITION in item_types
    assert EvidenceType.E_STATE_TRANSITION_COVERAGE in item_types
    
    # Verify strict typing and values
    pay_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_PROVIDER_PAYMENT)
    assert isinstance(pay_ev.content, ProviderPaymentContent)
    assert pay_ev.content.payment_id == "pay_1"
    assert pay_ev.content.captured is True
    assert pay_ev.id == "EV-PAY-01"
    
    mo_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_MERCHANT_ORDER_STATE)
    assert isinstance(mo_ev.content, MerchantOrderStateContent)
    assert mo_ev.content.status == "UNPAID"
    assert mo_ev.id == "EV-MO-01"
    
    wh_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_WEBHOOK_CAPTURED)
    assert isinstance(wh_ev.content, WebhookCapturedContent)
    assert wh_ev.content.present is True
    assert wh_ev.id == "EV-WH-01"
    
    whcov_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_WEBHOOK_COVERAGE)
    assert isinstance(whcov_ev.content, WebhookCoverageContent)
    assert whcov_ev.content.coverage == EvidenceCoverage.COMPLETE
    assert whcov_ev.content.webhook_count == 1
    
    proc_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_MERCHANT_PROCESSING)
    assert isinstance(proc_ev.content, MerchantProcessingContent)
    assert proc_ev.content.status == "PROCESSED"
    assert proc_ev.id == "EV-PROC-01"
    
    pccov_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_PROCESSING_COVERAGE)
    assert isinstance(pccov_ev.content, ProcessingCoverageContent)
    assert pccov_ev.content.coverage == EvidenceCoverage.COMPLETE
    assert pccov_ev.content.processing_count == 1
    assert pccov_ev.id == "EV-PC-01"

@pytest.mark.asyncio
async def test_gatherer_no_pseudo_evidence_when_db_empty():
    """Verify that if no payment or merchant order rows exist in DB, no pseudo-evidence is synthesized."""
    mock_session = AsyncMock()
    mock_session_maker = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    
    mock_res_obs = MagicMock()
    mock_res_obs.scalars.return_value.all.return_value = []
    
    mock_res_order = MagicMock()
    mock_res_order.scalars.return_value.first.return_value = None
    
    mock_session.execute.side_effect = [mock_res_obs, mock_res_order]
    
    discrepancy = VerifiedDiscrepancy(
        discrepancy_id="disc_empty",
        payment_id="pay_missing",
        order_id="ord_missing",
        description="Missing all DB records",
        provider_status="captured",
        merchant_status="UNPAID",
        amount_match=True,
        currency_match=True,
        identity_verified=True
    )
    
    gatherer = DatabaseEvidenceGatherer(mock_session_maker)
    packet = await gatherer.gather(discrepancy)
    
    item_types = [ev.type for ev in packet.items]
    # No payment or merchant order or webhook captured evidence synthesized
    assert EvidenceType.E_PROVIDER_PAYMENT not in item_types
    assert EvidenceType.E_MERCHANT_ORDER_STATE not in item_types
    assert EvidenceType.E_WEBHOOK_CAPTURED not in item_types
    
    # Ingestion coverage should be emitted with count 0
    whcov_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_WEBHOOK_COVERAGE)
    assert whcov_ev.content.webhook_count == 0
    assert whcov_ev.content.coverage == EvidenceCoverage.COMPLETE
