import pytest
import asyncio
import httpx
from decimal import Decimal
from datetime import datetime, timezone

from src.integrations.razorpay.client import RazorpayClient
from src.integrations.razorpay.adapter import RazorpayProviderAdapter
from src.domain.refunds.models import Refund
from src.domain.actions.models import Action, ActionType
from src.recovery.outbox import TransactionalOutbox, OutboxDispatcher, OutboxStatus

from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.evidence.models import ProviderObservation, EntityType
from src.integrations.provider import ProviderMutationOutcome, ProviderQueryConfidence
from tests.doubles.razorpay_mock_transport import RazorpayMockTransport

@pytest.fixture
def mock_transport():
    return RazorpayMockTransport()

@pytest.fixture
def razorpay_client(mock_transport):
    http_client = httpx.AsyncClient(transport=mock_transport, base_url="https://api.razorpay.com/v1")
    return RazorpayClient(client=http_client)

@pytest.fixture
def adapter(razorpay_client):
    return RazorpayProviderAdapter(client=razorpay_client)

@pytest.fixture
def refund_intent():
    return Refund.create_new(
        provider_payment_id="pay_123",
        amount=Decimal("100.00"),
        currency="INR",
        business_reason="Customer request"
    )

@pytest.mark.asyncio
async def test_razorpay_vertical_slice_case_A_ambiguous_executed(mock_transport, adapter, refund_intent):
    """
    Case A: POST /refund drops connection but executes on Razorpay.
    Query confirms execution.
    """
    mock_transport.simulate_timeout_on_create = True
    
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key=refund_intent.get_provider_idempotency_key(),
        incident_id=refund_intent.refund_intent_id
    )
    
    # 1. Dispatch fails with AMBIGUOUS
    outcome = await adapter.dispatch_refund(action, refund_intent)
    assert outcome == ProviderMutationOutcome.AMBIGUOUS_OUTCOME
    
    # 2. Query confirms it executed
    confidence = await adapter.query_refund_status(
        payment_id="pay_123", 
        idempotency_key=action.idempotency_key, 
        receipt=refund_intent.refund_intent_id
    )
    
    assert confidence == ProviderQueryConfidence.AUTHORITATIVE_EXECUTED

@pytest.mark.asyncio
async def test_razorpay_adapter_outcomes(mock_transport, adapter, refund_intent):
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key=refund_intent.get_provider_idempotency_key(),
        incident_id=refund_intent.refund_intent_id
    )
    
    # Normal execution
    outcome = await adapter.dispatch_refund(action, refund_intent)
    assert outcome == ProviderMutationOutcome.ACCEPTED_EXECUTED
    assert len(mock_transport.refunds) == 1
    
    # Query confirms it
    confidence = await adapter.query_refund_status(
        payment_id="pay_123", 
        idempotency_key=action.idempotency_key, 
        receipt=refund_intent.refund_intent_id
    )
    assert confidence == ProviderQueryConfidence.AUTHORITATIVE_EXECUTED

@pytest.mark.asyncio
async def test_razorpay_adapter_case_B_ambiguous_not_executed(mock_transport, adapter, refund_intent):
    mock_transport.simulate_504_on_create = True
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key=refund_intent.get_provider_idempotency_key(),
        incident_id=refund_intent.refund_intent_id
    )
    
    # Dispatch fails with AMBIGUOUS (504)
    outcome = await adapter.dispatch_refund(action, refund_intent)
    assert outcome == ProviderMutationOutcome.AMBIGUOUS_OUTCOME
    assert len(mock_transport.refunds) == 0
    
    # Query confirms NOT EXECUTED
    confidence = await adapter.query_refund_status(
        payment_id="pay_123", 
        idempotency_key=action.idempotency_key, 
        receipt=refund_intent.refund_intent_id
    )
    assert confidence == ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED

@pytest.mark.asyncio
async def test_razorpay_adapter_case_C_query_fails(mock_transport, adapter, refund_intent):
    mock_transport.simulate_500_on_query = True
    action = Action(
        action_type=ActionType.CONTROLLED_REFUND,
        idempotency_key=refund_intent.get_provider_idempotency_key(),
        incident_id=refund_intent.refund_intent_id
    )
    
    confidence = await adapter.query_refund_status(
        payment_id="pay_123", 
        idempotency_key=action.idempotency_key, 
        receipt=refund_intent.refund_intent_id
    )
    assert confidence == ProviderQueryConfidence.QUERY_FAILED
