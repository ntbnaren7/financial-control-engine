from src.engine.reconciliation_controls import evaluate_expectation_centric
from src.engine.policy import V2PolicyEvaluator
from src.domain.core.models import Observation, CorrelationKeys, CanonicalStatus, Expectation
from src.domain.investigation.context import InvestigationContext

exp = Expectation(
    domain="PAYMENT",
    expected_canonical_status=CanonicalStatus.SETTLED,
    expected_amount=1000,
    currency="INR",
    source_system="ledger",
    correlation_keys=CorrelationKeys(internal_ref="order_123", provider_ref="pay_123")
)

obs_merchant = Observation(
    provider="Merchant",
    provider_reference="order_123",
    observation_type="OrderState",
    canonical_status=CanonicalStatus.SETTLED,
    observed_amount=1000,
    currency="INR",
    correlation_keys=CorrelationKeys(internal_ref="order_123")
)

obs_provider = Observation(
    provider="Razorpay",
    provider_reference="pay_123",
    observation_type="PAYMENT",
    canonical_status=CanonicalStatus.SETTLED,
    observed_amount=1000,
    currency="INR",
    correlation_keys=CorrelationKeys(internal_ref="order_123", provider_ref="pay_123")
)

ctx = InvestigationContext(
    expectation=exp,
    observations=[obs_merchant, obs_provider],
    evidence_records=[]
)

policy = V2PolicyEvaluator()
intent = policy.evaluate("sub", "DUPLICATE_EXECUTION", [obs_merchant, obs_provider], [], ctx)
print(f"Policy intent: {intent.action} - {intent.reason}")
