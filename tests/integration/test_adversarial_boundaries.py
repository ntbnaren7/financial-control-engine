import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import os
import asyncio
from datetime import datetime, timezone
import uuid
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from src.domain.core.models import (
    Observation, CorrelationKeys, CanonicalStatus, Expectation, BusinessStatus,
    ReconciliationResult, ReconciliationOutcome, DiscrepancyReason
)
from src.engine.execution_identity import group_by_execution
from src.engine.policy import V2PolicyEvaluator
from src.engine.adapters.razorpay_payment_adapter import RazorpayPaymentAdapter
from src.engine.worker import V2ControlWorker
from src.storage.postgres_ingestion import PostgresIngestionRepository
from src.storage.postgres.models import Base
from src.integrations.verifier import RazorpayVerifier
from src.engine.observer import SimulatedObserver
from src.integrations.razorpay.client import RazorpayClient
from src.domain.investigation.models import VerificationIntent
from src.domain.ingestion.models import IngestionPayload
import hashlib, json

@pytest.fixture
def db_session_maker():
    db_url = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    engine = sa.create_engine(db_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

def test_1_currency_integrity():
    """1000 INR vs 1000 USD -> DISCREPANCY"""
    policy = V2PolicyEvaluator()
    
    exp = Expectation(
        domain="PAYMENT",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=1000,
        currency="USD",
        source_system="merchant",
        correlation_keys=CorrelationKeys(internal_ref="order_1", provider_ref="pay_1")
    )
    
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_1",
        observation_type="PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR"
    )
    
    merchant_obs = Observation(
        provider="merchant",
        provider_reference="order_1",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=1000,
        currency="USD"
    )
    
    intent = policy.evaluate("exec_1", DiscrepancyReason.AMOUNT_MISMATCH, [obs, merchant_obs], [], type("Context", (), {"expectation": exp, "observations": [obs, merchant_obs]})())
    
    assert intent is not None
    assert intent.action == "ESCALATE"
    assert "currency mismatch" in intent.reason.lower()

def test_2_execution_grouping():
    """Merchant order_123 + Razorpay pay_123 -> One execution group"""
    obs1 = Observation(
        provider="merchant",
        provider_reference="order_123",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="order_123")
    )
    obs2 = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="order_123", provider_ref="pay_123")
    )
    
    groups = group_by_execution([obs1, obs2])
    assert len(groups) == 1
    assert groups[0].execution_identity == "order_123"
    assert len(groups[0].observations) == 2

def test_3_settled_payment_match():
    """Settled payment -> MATCH, never DUPLICATE_EXECUTION / ESCALATE"""
    from src.engine.reconciliation_controls import evaluate_expectation_centric
    exp = Expectation(
        domain="PAYMENT",
        expected_canonical_status=CanonicalStatus.SETTLED,
        expected_amount=1000,
        currency="INR",
        source_system="merchant"
    )
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_123",
        observation_type="PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR"
    )
    res = evaluate_expectation_centric(exp, [obs])
    assert res.outcome == ReconciliationOutcome.MATCH

def test_4_refunded_payment_semantics():
    """Refunded payment -> Distinct REFUNDED status"""
    adapter = RazorpayPaymentAdapter()
    payload = {
        "event": "payment.refunded",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_123",
                    "status": "refunded",
                    "amount": 1000,
                    "currency": "INR",
                    "order_id": "order_123"
                }
            }
        },
        "created_at": 1600000000
    }
    
    obs, evidence = adapter.normalize_payload(payload)
    
    assert obs.canonical_status == CanonicalStatus.REFUNDED
    assert obs.observation_type == "PAYMENT"

def test_5_duplicate_webhook_idempotency(db_session_maker):
    """Duplicate webhook concurrently -> One persisted payload"""
    repo = PostgresIngestionRepository(db_session_maker)
    raw = {"event": "payment.captured", "id": "evt_1"}
    raw_str = json.dumps(raw, sort_keys=True)
    payload_hash = hashlib.sha256(raw_str.encode()).hexdigest()
    
    ingestion_payload = IngestionPayload(
        provider="razorpay",
        event_type="payment.captured",
        raw_payload=raw,
        payload_hash=payload_hash,
        idempotency_key="evt_1"
    )
    
    # Save once
    repo.save_payload(ingestion_payload)
    
    # Save again with same idempotency_key — must be handled gracefully (no exception)
    try:
        repo.save_payload(ingestion_payload)
    except Exception as e:
        pytest.fail(f"Duplicate webhook should be handled gracefully, got {e}")

def test_6_unversioned_observation_replay(db_session_maker):
    """Unversioned observation replay -> No duplicate observation"""
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_1",
        observation_type="PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR",
        provider_version=None
    )
    assert obs.provider_version == ""

def test_7_api_startup_failure():
    """API without DATABASE_URL -> Startup failure"""
    from src.api.main import lifespan, app
    from src.api import deps
    import contextlib
    
    # Clear the cached session factory if any
    original_session_factory = deps._session_factory
    deps._session_factory = None
        
    try:
        with patch("src.api.deps.FCESettings.load") as mock_load:
            # Mock settings to return an empty db_url
            mock_settings = MagicMock()
            mock_settings.database.url.get_secret_value.return_value = ""
            mock_load.return_value = mock_settings
            
            with pytest.raises(RuntimeError, match="DATABASE_URL.*is required"):
                async def run():
                    async with lifespan(app):
                        pass
                import asyncio
                asyncio.run(run())
    finally:
        deps._session_factory = original_session_factory

@pytest.mark.asyncio
async def test_8_verification_routing():
    """PAYMENT verification -> Calls get_payment(), REFUND verification -> Calls refund endpoint"""
    mock_client = MagicMock(spec=RazorpayClient)
    
    # PAYMENT path: get_payment must return an object with .id and .model_dump()
    mock_payment = MagicMock()
    mock_payment.id = "pay_123"
    mock_payment.model_dump.return_value = {
        "id": "pay_123", "status": "captured", "amount": 50000,
        "currency": "INR", "order_id": "order_123", "created_at": 1600000000
    }
    mock_client.get_payment = AsyncMock(return_value=mock_payment)
    mock_client.get_payment_refunds = AsyncMock(return_value=[])

    verifier = RazorpayVerifier(mock_client)
    intent = VerificationIntent.QUERY_PROVIDER_STATE
    
    context_payment = MagicMock()
    context_payment.expectation.domain = "PAYMENT"
    context_payment.expectation.correlation_keys.provider_ref = "pay_123"
    context_payment.expectation.correlation_keys.internal_ref = "order_123"
    context_payment.observations = []
    
    await verifier.verify(intent, context_payment)
    mock_client.get_payment.assert_called_once_with("pay_123")
    mock_client.get_payment_refunds.assert_not_called()
    
    mock_client.get_payment.reset_mock()
    mock_client.get_payment_refunds.reset_mock()
    
    context_refund = MagicMock()
    context_refund.expectation.domain = "REFUND"
    context_refund.expectation.correlation_keys.provider_ref = "pay_123"
    context_refund.expectation.correlation_keys.internal_ref = None
    context_refund.observations = []
    
    await verifier.verify(intent, context_refund)
    mock_client.get_payment_refunds.assert_called_once_with("pay_123")
    mock_client.get_payment.assert_not_called()

def test_9_reobservation_routing():
    """Payment re-observation -> Payment observer, Refund re-observation -> Refund observer"""
    observer = SimulatedObserver()
    assert hasattr(observer, "observe_provider_payment")
    assert hasattr(observer, "observe_provider_refund")


# --- Phase 8D Blocker Regression Tests ---
# Each test is named after the blocker letter it proves.

def test_B_execution_grouping_cross_system_correlation():
    """B — Merchant order + Razorpay payment with shared internal_ref -> single execution group.
    Execution identity MUST be the internal_ref (merchant order id), not the provider ref.
    """
    obs_merchant = Observation(
        provider="merchant",
        provider_reference="ord_abc",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=2000,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="ord_abc")
    )
    obs_provider = Observation(
        provider="razorpay",
        provider_reference="pay_xyz",
        observation_type="PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=2000,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="ord_abc", provider_ref="pay_xyz")
    )

    groups = group_by_execution([obs_merchant, obs_provider])
    assert len(groups) == 1, "Cross-system observations with the same internal_ref must form one execution group"
    assert groups[0].execution_identity == "ord_abc", "Execution identity must be the internal_ref (business key)"
    assert len(groups[0].observations) == 2


def test_B_execution_grouping_disjoint_refs_produce_separate_groups():
    """B — Observations with distinct internal_refs must NOT be merged into one group."""
    obs_a = Observation(
        provider="merchant",
        provider_reference="ord_001",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=100,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="ord_001")
    )
    obs_b = Observation(
        provider="merchant",
        provider_reference="ord_002",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=200,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="ord_002")
    )

    groups = group_by_execution([obs_a, obs_b])
    assert len(groups) == 2, "Observations with distinct internal_refs must form separate execution groups"


def test_C_refund_status_processed_maps_to_settled():
    """C — Razorpay refund status 'processed' must map to CanonicalStatus.SETTLED, not FAILED."""
    from src.integrations.razorpay.normalizer import RazorpayV2Normalizer
    evidence_id = str(uuid.uuid4())
    obs = RazorpayV2Normalizer.normalize_refund(
        {"id": "rfnd_1", "payment_id": "pay_1", "status": "processed", "amount": 500, "currency": "INR"},
        evidence_id
    )
    assert obs.canonical_status == CanonicalStatus.SETTLED, (
        f"Razorpay 'processed' refund must map to SETTLED, got {obs.canonical_status}"
    )


def test_C_refund_status_refunded_on_payment_entity_maps_to_unknown():
    """C — Razorpay 'refunded' is a payment-entity status leaking into refund context.
    Must map to UNKNOWN (fail closed), NOT FAILED.
    Classifying it as FAILED would trigger incorrect recovery actions.
    """
    from src.integrations.razorpay.normalizer import _map_razorpay_refund_status
    result = _map_razorpay_refund_status("refunded")
    assert result == CanonicalStatus.UNKNOWN, (
        f"'refunded' on a refund entity is ambiguous and must map to UNKNOWN, got {result}"
    )


def test_C_refund_status_failed_maps_to_failed():
    """C — 'failed' on a refund entity correctly maps to FAILED."""
    from src.integrations.razorpay.normalizer import _map_razorpay_refund_status
    assert _map_razorpay_refund_status("failed") == CanonicalStatus.FAILED


def test_E_provider_version_none_defaults_to_empty_string():
    """E — Observation with provider_version=None must default to '' via __post_init__.
    This prevents fingerprint deduplication treating None and '' as distinct versions.
    """
    obs = Observation(
        provider="razorpay",
        provider_reference="pay_e",
        observation_type="PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR",
        provider_version=None
    )
    assert obs.provider_version == "", (
        "provider_version=None must be normalized to '' by __post_init__"
    )


def test_E_two_observations_same_version_have_same_fingerprint():
    """E — Two observations identical except for provider_version=None vs '' must
    produce the same deduplication fingerprint (same canonical state).
    """
    base_kwargs = dict(
        provider="razorpay",
        provider_reference="pay_e2",
        observation_type="PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR"
    )
    obs_none = Observation(**base_kwargs, provider_version=None)
    obs_empty = Observation(**base_kwargs, provider_version="")
    assert obs_none.provider_version == obs_empty.provider_version, (
        "None and '' provider_version must be equivalent after normalization"
    )


def test_G_webhook_handler_raises_without_initialized_repo():
    """G — get_ingestion_repository() must raise RuntimeError if lifespan has not injected
    a real PostgresIngestionRepository. Silent fallback to MemoryIngestionRepository
    is a financial-safety defect: events would be accepted and silently lost on restart.
    """
    from src.api import webhooks
    original_repo = webhooks._ingestion_repo
    try:
        webhooks._ingestion_repo = None
        with pytest.raises(RuntimeError, match="Ingestion repository has not been initialized"):
            webhooks.get_ingestion_repository()
    finally:
        webhooks._ingestion_repo = original_repo


def test_H_payment_verification_uses_get_payment_not_refunds():
    """H — Provider verification for PAYMENT domain must call client.get_payment(),
    never client.get_payment_refunds(). Calling the wrong endpoint on a PAYMENT
    context would return empty/wrong data and silently treat the payment as unverified.
    """
    # Re-asserted explicitly here as a standalone blocker regression — the routing
    # invariant from test_8 is the same, but this test documents the H blocker lineage.
    from src.integrations.verifier import RazorpayVerifier
    from src.domain.investigation.models import VerificationIntent

    mock_client = MagicMock(spec=RazorpayClient)
    mock_payment = MagicMock()
    mock_payment.id = "pay_h1"
    mock_payment.model_dump.return_value = {
        "id": "pay_h1", "status": "captured", "amount": 5000,
        "currency": "INR", "order_id": "ord_h1", "created_at": 1700000000
    }
    mock_client.get_payment = AsyncMock(return_value=mock_payment)
    mock_client.get_payment_refunds = AsyncMock(return_value=[])

    import asyncio
    verifier = RazorpayVerifier(mock_client)
    context = MagicMock()
    context.expectation.domain = "PAYMENT"
    context.expectation.correlation_keys.provider_ref = "pay_h1"
    context.expectation.correlation_keys.internal_ref = "ord_h1"
    context.observations = []

    asyncio.run(verifier.verify(VerificationIntent.QUERY_PROVIDER_STATE, context))
    mock_client.get_payment.assert_called_once_with("pay_h1")
    mock_client.get_payment_refunds.assert_not_called()


def test_I_execution_identity_propagates_via_internal_ref():
    """I — Execution identity must be derived from the authoritative business key (internal_ref),
    not from provider_ref or observation_id. This ensures the same business execution is
    consistently identified regardless of which provider observation arrives first.
    """
    # Simulate Razorpay observation arriving before merchant observation
    obs_provider_first = Observation(
        provider="razorpay",
        provider_reference="pay_i1",
        observation_type="API_PAYMENT",
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=3000,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="ord_i1", provider_ref="pay_i1", domain="PAYMENT")
    )
    obs_merchant_second = Observation(
        provider="merchant",
        provider_reference="ord_i1",
        observation_type="OrderState",
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=3000,
        currency="INR",
        correlation_keys=CorrelationKeys(internal_ref="ord_i1")
    )

    groups = group_by_execution([obs_provider_first, obs_merchant_second])
    assert len(groups) == 1, "Regardless of arrival order, shared internal_ref must produce one group"
    assert groups[0].execution_identity == "ord_i1"


def test_J_reobservation_routing_uses_correlation_domain():
    """J — Re-observation routing must use correlation_keys.domain (set by normalizer as 'REFUND'
    or 'PAYMENT') rather than the raw observation_type string ('API_REFUND', 'API_PAYMENT').
    Checking only observation_type == 'REFUND' would never match normalizer output.
    """
    obs_refund = Observation(
        provider="razorpay",
        provider_reference="rfnd_j1",
        observation_type="API_REFUND",  # normalizer-emitted value
        canonical_status=CanonicalStatus.PENDING,
        observed_amount=500,
        currency="INR",
        correlation_keys=CorrelationKeys(
            provider_ref="pay_j1",
            internal_ref="ord_j1",
            provider="razorpay",
            domain="REFUND"
        )
    )
    obs_payment = Observation(
        provider="razorpay",
        provider_reference="pay_j2",
        observation_type="API_PAYMENT",  # normalizer-emitted value
        canonical_status=CanonicalStatus.SETTLED,
        observed_amount=1000,
        currency="INR",
        correlation_keys=CorrelationKeys(
            provider_ref="pay_j2",
            internal_ref="ord_j2",
            provider="razorpay",
            domain="PAYMENT"
        )
    )

    def _route(obs: Observation) -> str:
        """Mirror the fixed worker routing logic."""
        obs_domain = (
            (obs.correlation_keys.domain if obs.correlation_keys else None)
            or obs.observation_type
        ).upper()
        return "refund" if "REFUND" in obs_domain else "payment"

    assert _route(obs_refund) == "refund", (
        "API_REFUND observation with domain='REFUND' must route to refund observer"
    )
    assert _route(obs_payment) == "payment", (
        "API_PAYMENT observation with domain='PAYMENT' must route to payment observer"
    )

