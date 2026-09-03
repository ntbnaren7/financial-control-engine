from typing import List
from src.domain.actions.models import Action, ActionStatus, ActionType
from src.engine.outbox import ActionOutbox
from src.engine.runtime import ControlRuntime, ObservationReceived
from src.integrations.razorpay.client import RazorpayClient
from src.evidence.models import ProviderObservation, EntityType
import uuid
from datetime import datetime, timezone

class ActionExecutor:
    def __init__(self, outbox: ActionOutbox, runtime: ControlRuntime, razorpay_client: RazorpayClient):
        self._outbox = outbox
        self._runtime = runtime
        self._client = razorpay_client

    async def execute_pending(self):
        pending_actions = self._outbox.get_pending()
        for action in pending_actions:
            if action.action_type == ActionType.CONTROLLED_REFUND:
                try:
                    payload = action.payload
                    intent_id = payload.get("intent_id")
                    if not intent_id:
                        continue
                    
                    # Hack: getting amount from expectations. In a real system, payload should have amount.
                    expectation = self._runtime._repo._expectations.get(intent_id)
                    amount = int(getattr(expectation, "amount", 0)) if expectation else 0
                    payment_id = str(getattr(expectation, "provider_payment_id", "")) if expectation else ""
                    
                    # Execute mutation
                    refund = await self._client.create_refund(
                        payment_id=payment_id,
                        amount=amount,
                        receipt=intent_id,
                        idempotency_key=action.idempotency_key
                    )
                    
                    self._outbox.update_status(action.idempotency_key, ActionStatus.SUCCESS)
                    
                    # Post-action Verification: Closing the loop
                    # Synthesize an ObservationReceived event representing the provider's acceptance
                    obs_time = datetime.fromtimestamp(refund.created_at, tz=timezone.utc)
                    observation = ProviderObservation(
                        provider="razorpay",
                        event_id=refund.id,
                        entity_type=EntityType.REFUND_INTENT.value,
                        entity_id=intent_id,
                        event_type="refund.processed",
                        payload={
                            "status": refund.status,
                            "amount": refund.amount,
                            "currency": refund.currency,
                        },
                        created_at=obs_time,
                        id=uuid.uuid4()
                    )
                    await self._runtime.ingest_event(ObservationReceived(observation))
                except Exception as e:
                    print(f"Action {action.action_id} failed: {e}")
                    self._outbox.update_status(action.idempotency_key, ActionStatus.FAILED)
