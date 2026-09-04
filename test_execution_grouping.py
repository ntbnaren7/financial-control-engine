from src.engine.execution_identity import group_by_execution
from src.domain.core.models import Observation, CorrelationKeys, CanonicalStatus

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

groups = group_by_execution([obs_merchant, obs_provider])
print(f"Groups length: {len(groups)}")
for g in groups:
    print(f"Group ID: {g.execution_identity}")
    for obs in g.observations:
        print(f"  Obs: {obs.provider}")
