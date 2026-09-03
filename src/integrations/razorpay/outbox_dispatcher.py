import asyncio
import logging
import uuid
import inspect
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from src.recovery.outbox import TransactionalOutbox, OutboxStatus
from src.domain.actions.models import ActionType
from src.domain.refunds.models import Refund
from src.integrations.provider import ProviderQueryConfidence, ProviderMutationOutcome
from src.evidence.models import ProviderObservation, EntityType

logger = logging.getLogger(__name__)

class AsyncOutboxDispatcher:
    """
    Consumes messages from TransactionalOutbox and dispatches them to the provider.
    Converts provider outcomes into ProviderObservations.
    """
    def __init__(self, outbox: TransactionalOutbox, provider_adapter, observation_store):
        self.outbox = outbox
        self.provider_adapter = provider_adapter
        self.observation_store = observation_store
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self):
        while self._running:
            try:
                await self._process_pending_messages()
            except Exception as e:
                logger.error(f"Error in outbox dispatcher loop: {e}")
            
            # Polling delay
            await asyncio.sleep(1.0)

    async def _process_pending_messages(self):
        messages = self.outbox.get_pending_messages()
        for msg in messages:
            if not self._running:
                break
                
            if msg.action.action_type != ActionType.CONTROLLED_REFUND:
                # Dispatcher only knows about CONTROLLED_REFUND for now
                continue
                
            try:
                # Mark as processing
                self.outbox.update_status(msg.message_id, OutboxStatus.PROCESSING)
                
                payload = msg.action.payload
                refund = Refund(
                    refund_intent_id=payload["refund_intent_id"],
                    provider_payment_id=payload["provider_payment_id"],
                    amount=Decimal(payload["amount"]),
                    currency=payload["currency"]
                )
                
                # Perform the dispatch
                dispatch_func = self.provider_adapter.dispatch_refund
                if inspect.iscoroutinefunction(dispatch_func):
                    outcome = await dispatch_func(msg.action, refund)
                else:
                    outcome = dispatch_func(msg.action, refund)
                
                now = datetime.now(timezone.utc).isoformat()
                
                if outcome == ProviderMutationOutcome.ACCEPTED_EXECUTED:
                    obs = ProviderObservation(
                        provider="razorpay",
                        event_id=str(uuid.uuid4()),
                        entity_type=EntityType.REFUND_INTENT.value,
                        entity_id=refund.refund_intent_id,
                        event_type="DISPATCH_RESULT",
                        payload={"status": "REFUNDED", "provider_timestamp": now}
                    )
                    self.observation_store.add(obs)
                    self.outbox.update_status(msg.message_id, OutboxStatus.DISPATCHED)
                    
                elif outcome == ProviderMutationOutcome.ACCEPTED_PENDING:
                    self.outbox.update_status(msg.message_id, OutboxStatus.DISPATCHED)
                    
                elif outcome == ProviderMutationOutcome.EXPLICITLY_REJECTED:
                    obs = ProviderObservation(
                        provider="razorpay",
                        event_id=str(uuid.uuid4()),
                        entity_type=EntityType.REFUND_INTENT.value,
                        entity_id=refund.refund_intent_id,
                        event_type="DISPATCH_RESULT",
                        payload={"status": "FAILED", "provider_timestamp": now}
                    )
                    self.observation_store.add(obs)
                    self.outbox.update_status(msg.message_id, OutboxStatus.RETRYABLE)
                    
                elif outcome == ProviderMutationOutcome.AMBIGUOUS_OUTCOME:
                    # Let outbox retry on timeout / ambiguity
                    self.outbox.update_status(msg.message_id, OutboxStatus.AMBIGUOUS)
                    
                elif outcome == ProviderMutationOutcome.TRANSIENT_CONFLICT:
                    self.outbox.update_status(msg.message_id, OutboxStatus.RETRYABLE)
                    
                elif outcome == ProviderMutationOutcome.IDEMPOTENCY_MISMATCH:
                    self.outbox.update_status(msg.message_id, OutboxStatus.RETRYABLE)
                    
            except Exception as e:
                logger.error(f"Failed to process message {msg.message_id}: {e}")
                try:
                    self.outbox.update_status(msg.message_id, OutboxStatus.RETRYABLE)
                except Exception:
                    pass
