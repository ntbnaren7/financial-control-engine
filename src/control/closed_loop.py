import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Protocol, Any
import inspect

from src.reconciliation.models import ExpectedRefund, DiscrepancyType
from src.reconciliation.engine import reconcile
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.domain.incidents.models import Incident, IncidentState, EscalationArtifact
from src.domain.incidents.projection import project_incident
from src.control.policy import evaluate_refund_eligibility, ActionDecision
from src.domain.actions.models import Action, ActionType
from src.recovery.outbox import TransactionalOutbox
from src.integrations.provider import ProviderQueryConfidence
from src.evidence.models import ProviderObservation, EntityType


class ObservationStore(Protocol):
    def get_for_entity(self, entity_type: EntityType, entity_id: str) -> List[ProviderObservation]: ...
    def add(self, observation: ProviderObservation) -> None: ...


class AsyncProviderAdapter(Protocol):
    async def query_refund_status(self, payment_id: str, idempotency_key: str, receipt: str) -> ProviderQueryConfidence: ...


class ClosedLoopCoordinator:
    """
    Integration Coordinator that sequences hand-offs across components.
    It has zero mutation authority, zero authorization authority, and never bypasses the outbox.
    """
    def __init__(
        self,
        state_engine: StateEngine,
        ordering_policy: TemporalOrderingPolicy,
        outbox: TransactionalOutbox,
        provider_adapter: Any,
        observation_store: ObservationStore
    ):
        self.state_engine = state_engine
        self.ordering_policy = ordering_policy
        self.outbox = outbox
        self.provider_adapter = provider_adapter
        self.observation_store = observation_store

    async def run_cycle(
        self,
        expectation: ExpectedRefund,
        reconciliation_timestamp: datetime,
        existing_incident: Optional[Incident] = None,
        probed: bool = False
    ) -> Tuple[Optional[Incident], Optional[EscalationArtifact]]:
        """
        Runs a single deterministic reconciliation and dispatch/probe cycle.
        """
        observations = self.observation_store.get_for_entity(
            EntityType.REFUND_INTENT, expectation.refund_intent_id
        )
        
        reconstructed_state = self.state_engine.reconstruct_state(
            entity_type=EntityType.REFUND_INTENT,
            entity_id=expectation.refund_intent_id,
            observations=observations,
            reconstructed_at=reconciliation_timestamp,
            ordering_policy=self.ordering_policy
        )
        
        # 1. Reconcile
        recon_result = reconcile(
            expectation=expectation,
            reconstructed_state=reconstructed_state,
            reconciliation_timestamp=reconciliation_timestamp
        )
        
        # 2. Project Incident
        incident = project_incident(recon_result, expectation, existing_incident)
        
        # Match Handling (Resolve Incident)
        if incident is None and existing_incident is not None:
            try:
                # Find the proving observation id (just use the latest for resolution proof)
                proving_obs_id = recon_result.reconstructed_state_ids[-1] if recon_result.reconstructed_state_ids else None
                incident = existing_incident.resolve(recon_result, proving_obs_id)
                return incident, None
            except ValueError:
                # If correlation constraints fail, incident remains as-is
                return existing_incident, None
                
        if incident is None:
            return None, None
            
        # 3. Path Routing
        # Check if already MONITORING and state hasn't changed.
        if incident.lifecycle_state == IncidentState.MONITORING and existing_incident is not None and incident.discrepancy_type == existing_incident.discrepancy_type:
            if not probed and incident.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION:
                # Already triggered recovery, wait for provider to acknowledge
                return incident, None

        if incident.discrepancy_type == DiscrepancyType.ABSENT_EXECUTION:
            # Path 1: Safe Recovery
            confidence = ProviderQueryConfidence.AUTHORITATIVE_NOT_EXECUTED
            refund = expectation.to_refund()
            decision = evaluate_refund_eligibility(
                reconstructed_state=reconstructed_state,
                provider_query_confidence=confidence,
                refund_intent=refund,
                incident_id=incident.incident_id
            )
            
            if decision.decision == ActionDecision.ALLOW_REFUND:
                action = Action(
                    action_type=ActionType.CONTROLLED_REFUND,
                    idempotency_key=expectation.get_provider_idempotency_key(),
                    incident_id=incident.incident_id,
                    payload={
                        "amount": str(expectation.amount),
                        "currency": expectation.currency,
                        "provider_payment_id": expectation.provider_payment_id,
                        "refund_intent_id": expectation.refund_intent_id
                    }
                )
                self.outbox.publish_action(action)
                incident = incident.transition_to(IncidentState.MONITORING, "Action published to outbox")
                return incident, None
            else:
                escalation = incident.escalate(f"Policy rejected recovery: {decision.reason}")
                incident = incident.transition_to(IncidentState.ESCALATED, "Policy rejection")
                return incident, escalation
                
        elif incident.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE:
            if probed:
                escalation = incident.escalate("Provider probe did not resolve uncertainty")
                incident = incident.transition_to(IncidentState.ESCALATED, "Unresolvable Epistemic Stalemate")
                return incident, escalation

            # Path 2: Uncertainty Probe
            incident = incident.transition_to(IncidentState.MONITORING, "Probing provider")
            
            confidence = ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY
            # Support both async and sync mock adapters for the probe
            if hasattr(self.provider_adapter, "query_refund_status"):
                query_func = self.provider_adapter.query_refund_status
                if inspect.iscoroutinefunction(query_func):
                    confidence = await query_func(
                        payment_id=expectation.provider_payment_id,
                        idempotency_key=expectation.get_provider_idempotency_key(),
                        receipt=expectation.refund_intent_id
                    )
                else:
                    # Synchronous fallback for basic mocks
                    confidence = query_func(
                        payment_id=expectation.provider_payment_id,
                        idempotency_key=expectation.get_provider_idempotency_key(),
                        receipt=expectation.refund_intent_id
                    )

            # Emit a new ProviderObservation
            probe_obs = ProviderObservation(
                provider="provider",
                event_id=str(uuid.uuid4()),
                entity_type=EntityType.REFUND_INTENT.value,
                entity_id=expectation.refund_intent_id,
                event_type="STATUS_PROBE",
                payload={
                    "query_confidence": confidence.value,
                    "provider_timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
            self.observation_store.add(probe_obs)
            
            if confidence in (ProviderQueryConfidence.QUERY_FAILED, ProviderQueryConfidence.NON_AUTHORITATIVE_QUERY):
                escalation = incident.escalate(f"Probe resulted in {confidence.value}")
                incident = incident.transition_to(IncidentState.ESCALATED, "Probe failed or ambiguous")
                return incident, escalation
            
            # Re-run cycle to act on new evidence
            return await self.run_cycle(expectation, reconciliation_timestamp, incident, probed=True)
            
        elif recon_result.requires_investigation:
            # Path 3: Unsafe / Anomalous
            escalation = incident.escalate(recon_result.details.get("reason", "Unsafe discrepancy detected"))
            incident = incident.transition_to(IncidentState.ESCALATED, "Requires investigation")
            return incident, escalation
            
        return incident, None
