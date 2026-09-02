import uuid
from datetime import datetime, timezone
import pytest
from typing import Optional
from decimal import Decimal

from src.domain.actions.models import Action, ActionType
from src.domain.refunds.models import Refund
from src.evidence.models import EntityType, ProviderObservation
from src.integrations.provider import ProviderQueryConfidence
from src.recovery.outbox import TransactionalOutbox, OutboxDispatcher, OutboxStatus, OutboxMessage, ConcurrencyError
from src.recovery.uncertainty import (
    ResolutionStatus,
    RetryPolicy,
    resolve_refund_uncertainty,
    RefundQueryAdapter,
)
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.state.models import KnowledgeState, ExecutionState

from tests.doubles.provider_double import (
    ProviderDouble,
    E2EProviderAdapter,
    ProviderTransportResult,
    ProviderQueryResult,
)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)



def make_refund() -> Refund:
    intent_id = f"ref_{uuid.uuid4().hex[:8]}"
    return Refund(
        refund_intent_id=intent_id,
        provider_payment_id=f"pay_{uuid.uuid4().hex[:8]}",
        amount=Decimal('100'),
        currency="USD"
    )

def default_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        max_attempts=3,
        provider_key_valid=True
    )

def run_workflow_and_verify(
    refund: Refund, 
    adapter: E2EProviderAdapter, 
    expected_fce_status: ResolutionStatus,
    expected_fce_knowledge: KnowledgeState,
    expected_fce_execution: Optional[ExecutionState],
    expected_oracle_effect_count: int
):
    # Execute the Uncertainty Workflow
    # In reality, this runs asynchronously via a recovery worker when it detects an AMBIGUOUS outbox message.
    outcome, observation = resolve_refund_uncertainty(
        refund=refund,
        existing_observations=adapter.observations,
        query_adapter=adapter,
        retry_policy=default_retry_policy()
    )

    if observation:
        adapter.observations.append(observation)

    # INDEPENDENT ASSERTION 1: FCE Truth (What it is justified in knowing)
    assert outcome.status == expected_fce_status
    assert outcome.reconstructed_state.knowledge_state == expected_fce_knowledge
    assert outcome.reconstructed_state.execution == expected_fce_execution

    # INDEPENDENT ASSERTION 2: Provider Oracle Truth (What actually happened)
    adapter.double.assert_at_most_one_effect(refund.refund_intent_id)
    assert adapter.double.get_financial_effect_count(refund.refund_intent_id) == expected_oracle_effect_count
    
    return outcome


class TestRefundUncertaintyE2E:
    
    def test_e2e_1_execute_and_response_lost(self):
        """
        Provider effect = 1
        FCE initially = UNKNOWN
        Authoritative query = EXECUTED
        Final FCE = VERIFIED + EXECUTED
        No second effect.
        """
        double = ProviderDouble()
        adapter = E2EProviderAdapter(double)
        outbox = TransactionalOutbox()
        dispatcher = OutboxDispatcher(outbox, adapter)

        refund = make_refund()
        action = Action(
            action_type=ActionType.CONTROLLED_REFUND,
            idempotency_key=refund.get_provider_idempotency_key(),
            incident_id="inc_123"
        )
        action.payload = {"intent_id": refund.refund_intent_id}  # type: ignore

        # 1. Oracle drops the response but executes the financial effect
        double.configure_drop(refund.get_provider_idempotency_key())
        
        # 2. Control plane publishes to outbox
        outbox.publish_action(action)
        
        # 3. Outbox dispatcher attempts execution
        dispatcher.process_pending()
        
        # 4. Outbox state should be AMBIGUOUS because transport failed
        messages = list(outbox._messages.values())
        assert len(messages) == 1
        assert messages[0].status == OutboxStatus.AMBIGUOUS
        
        # Provider effect is actually 1
        assert double.get_financial_effect_count(refund.refund_intent_id) == 1

        # 5. Uncertainty Workflow runs
        run_workflow_and_verify(
            refund=refund,
            adapter=adapter,
            expected_fce_status=ResolutionStatus.VERIFIED_EXECUTED,
            expected_fce_knowledge=KnowledgeState.VERIFIED,
            expected_fce_execution=ExecutionState.EXECUTED,
            expected_oracle_effect_count=1
        )

    def test_e2e_2_no_execution_and_ambiguous_response(self):
        """
        Provider effect = 0
        FCE initially = UNKNOWN
        Authoritative query = NOT_EXECUTED
        Final FCE = VERIFIED + NOT_EXECUTED
        Financial state remains None.
        """
        double = ProviderDouble()
        adapter = E2EProviderAdapter(double)
        outbox = TransactionalOutbox()
        dispatcher = OutboxDispatcher(outbox, adapter)

        refund = make_refund()
        action = Action(
            action_type=ActionType.CONTROLLED_REFUND,
            idempotency_key=refund.get_provider_idempotency_key(),
            incident_id="inc_123"
        )
        action.payload = {"intent_id": refund.refund_intent_id}  # type: ignore

        # 1. Oracle timeout / fails entirely
        double.configure_ambiguous(refund.get_provider_idempotency_key())
        
        outbox.publish_action(action)
        dispatcher.process_pending()
        
        # 2. Uncertainty Workflow runs
        outcome = run_workflow_and_verify(
            refund=refund,
            adapter=adapter,
            expected_fce_status=ResolutionStatus.AUTHORIZED_RETRY,
            expected_fce_knowledge=KnowledgeState.VERIFIED,
            expected_fce_execution=ExecutionState.NOT_EXECUTED,
            expected_oracle_effect_count=0
        )
        assert outcome.reconstructed_state.observed_financial_state is None

    def test_e2e_3_still_unknowable(self):
        """
        Provider effect = 0 or 1
        Query = non-authoritative/failed
        Final FCE = UNKNOWN
        No retry / no consequential action.
        """
        double = ProviderDouble()
        adapter = E2EProviderAdapter(double)
        outbox = TransactionalOutbox()
        dispatcher = OutboxDispatcher(outbox, adapter)

        refund = make_refund()
        action = Action(
            action_type=ActionType.CONTROLLED_REFUND,
            idempotency_key=refund.get_provider_idempotency_key(),
            incident_id="inc_123"
        )
        action.payload = {"intent_id": refund.refund_intent_id}  # type: ignore

        # 1. Oracle drops the response but executes the financial effect
        double.configure_drop(refund.get_provider_idempotency_key())
        
        # 2. Oracle queries also fail
        double.configure_query_failure(refund.get_provider_idempotency_key())
        
        outbox.publish_action(action)
        dispatcher.process_pending()
        
        # 3. Uncertainty Workflow runs
        run_workflow_and_verify(
            refund=refund,
            adapter=adapter,
            expected_fce_status=ResolutionStatus.ESCALATE,
            expected_fce_knowledge=KnowledgeState.UNKNOWN,
            expected_fce_execution=None,
            expected_oracle_effect_count=1  # Still exactly 1 effect from the drop!
        )

    def test_e2e_4_crash_recovery_race(self):
        """
        Test that crash recovery respects the at-most-one effect invariant by enforcing
        FCE transactional concurrency before the provider is even called.
        """
        double = ProviderDouble()
        adapter = E2EProviderAdapter(double)
        outbox = TransactionalOutbox()
        dispatcher = OutboxDispatcher(outbox, adapter)

        refund = make_refund()
        initial_action = Action(
            action_type=ActionType.CONTROLLED_REFUND,
            idempotency_key=refund.get_provider_idempotency_key(),
            incident_id="inc_initial"
        )
        initial_action.payload = {"intent_id": refund.refund_intent_id}  # type: ignore

        # Provider simulates a timeout for the initial dispatch
        double.configure_ambiguous(refund.get_provider_idempotency_key())
        outbox.publish_action(initial_action)
        dispatcher.process_pending()

        # Worker 1 recovers
        outcome1 = run_workflow_and_verify(
            refund=refund, adapter=adapter,
            expected_fce_status=ResolutionStatus.AUTHORIZED_RETRY,
            expected_fce_knowledge=KnowledgeState.VERIFIED,
            expected_fce_execution=ExecutionState.NOT_EXECUTED,
            expected_oracle_effect_count=0
        )
        
        # Worker 2 also simultaneously read the ambiguous outbox state and recovers
        outcome2 = run_workflow_and_verify(
            refund=refund, adapter=adapter,
            expected_fce_status=ResolutionStatus.AUTHORIZED_RETRY,
            expected_fce_knowledge=KnowledgeState.VERIFIED,
            expected_fce_execution=ExecutionState.NOT_EXECUTED,
            expected_oracle_effect_count=0
        )
        
        # Both workers independently construct new retry actions
        # Both must use the same refund_intent_id, same immutable payload, same provider idempotency key
        retry_action_1 = Action(
            action_type=ActionType.CONTROLLED_REFUND,
            idempotency_key=refund.get_provider_idempotency_key(),
            incident_id="inc_retry_w1"
        )
        retry_action_1.payload = {"intent_id": refund.refund_intent_id}  # type: ignore

        retry_action_2 = Action(
            action_type=ActionType.CONTROLLED_REFUND,
            idempotency_key=refund.get_provider_idempotency_key(),
            incident_id="inc_retry_w2"
        )
        retry_action_2.payload = {"intent_id": refund.refund_intent_id}  # type: ignore
        
        # Worker 1 commits to the outbox successfully
        outbox.publish_action(retry_action_1)
        
        # Worker 2 attempts to commit to the outbox, but the UNIQUE constraint rejects it
        with pytest.raises(ConcurrencyError) as exc_info:
            outbox.publish_action(retry_action_2)
            
        assert "Concurrent authorization prevented" in str(exc_info.value)
        
        # Prove EXACTLY 1 executable action is in the outbox (plus the 1 initial ambiguous action)
        all_messages = list(outbox._messages.values())
        assert len(all_messages) == 2
        pending_messages = outbox.get_pending_messages()
        assert len(pending_messages) == 1
        assert pending_messages[0].action.incident_id == "inc_retry_w1"
        
        # Clear the ambiguous override so the retry goes through
        double._force_ambiguous_keys.remove(refund.get_provider_idempotency_key())
        
        # Dispatcher processes the one committed retry
        # Prove exactly 1 dispatch happens for the retry
        dispatcher.process_pending()
        
        # Verify the Oracle effect count is exactly 1
        assert double.get_financial_effect_count(refund.refund_intent_id) == 1
        double.assert_at_most_one_effect(refund.refund_intent_id)
