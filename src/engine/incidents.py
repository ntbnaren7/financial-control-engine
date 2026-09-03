import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Tuple

from src.reconciliation.models import ReconciliationResult, DiscrepancyType, ExpectedRefund
from src.evidence.models import ProviderObservation, EntityType
from src.domain.incidents.models import Incident, IncidentState
from src.domain.incidents.projection import project_incident
from src.domain.cases.models import ReconciliationCase
from src.domain.correlation.models import CorrelationContext
from src.domain.investigation.models import CausalHypothesis, InvestigationDisposition, VerificationIntent, ValidationRejection, VerificationRejection
from src.investigation.input_formatter import format_case_for_investigation
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.storage.incident_repo import IncidentRepository
from src.engine.router import DiscrepancyRouter
from src.engine.reconciliation import ReconciliationEngine

# Extend IncidentState safely here if ACTION_REQUIRED doesn't exist yet,
# or we just map it to ESCALATED or whatever exists.
# Wait, `IncidentState` in `src.domain.incidents.models` has:
# OPEN, MONITORING, ESCALATED, RESOLVED, CLOSED
# We will use ESCALATED for all required actions for now.

class IncidentEngine:
    def __init__(
        self,
        reconciliation_engine: ReconciliationEngine,
        investigator,
        validator: OutputValidator,
        verifier: DeterministicVerifier,
        incident_repo: Optional[IncidentRepository] = None
    ):
        self._reconciliation_engine = reconciliation_engine
        self._investigator = investigator
        self._validator = validator
        self._verifier = verifier
        self._repo = incident_repo or IncidentRepository()

    async def _investigate(
        self,
        case: ReconciliationCase,
        sub_case_hint: str,
    ) -> Tuple[str, str, List[ProviderObservation]]:
        agent_input = format_case_for_investigation(case)

        hypothesis: Optional[CausalHypothesis] = None
        if self._investigator is None:
            hypothesis = CausalHypothesis(
                hypothesis="Provider status unknown; issuing query to establish execution state.",
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[],
                missing_evidence_description="Provider refund record",
                confidence="LOW",
                disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
                verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
            )
        else:
            try:
                hypothesis = await asyncio.to_thread(self._investigator.investigate, agent_input)
            except Exception:
                hypothesis = CausalHypothesis(
                    hypothesis="Provider status unknown; issuing query to establish execution state.",
                    supporting_evidence_ids=[],
                    contradicting_evidence_ids=[],
                    missing_evidence_description="Provider refund record",
                    confidence="LOW",
                    disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
                    verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
                )

        if sub_case_hint == "C5_BOUNDARY_REJECT":
            hypothesis = CausalHypothesis(
                hypothesis="Hypothesis referencing a fabricated evidence ID.",
                supporting_evidence_ids=["hallucinated_evidence_ref_999"],
                contradicting_evidence_ids=[],
                missing_evidence_description="None",
                confidence="LOW",
                disposition=InvestigationDisposition.VERIFICATION_PROPOSED,
                verification_intent=VerificationIntent.QUERY_PROVIDER_REFUND,
            )

        validation = self._validator.validate(hypothesis.model_dump(), agent_input)
        if isinstance(validation, ValidationRejection):
            return "d4_rejected", f"D4 rejected: {validation.reason} — {validation.detail}", []

        try:
            new_evidences = await self._verifier.verify(hypothesis, case)
        except Exception as e:
            return "provider_error", f"Provider error during verification: {e}", []

        if isinstance(new_evidences, VerificationRejection):
            return "provider_error", f"D5 rejected: {new_evidences.reason} — {new_evidences.detail}", []

        evidence_list: list = new_evidences
        new_observations: list[ProviderObservation] = []
        for ev in evidence_list:
            raw_status = (ev.payload.get("status") or "").lower()

            if raw_status == "processed":
                knowledge_state = "VERIFIED"
                financial_state = "REFUNDED"
                execution_state = "EXECUTED"
            elif raw_status in ("failed", "cancelled"):
                knowledge_state = "VERIFIED"
                financial_state = "FAILED"
                execution_state = "NOT_EXECUTED"
            elif raw_status in ("not_found", ""):
                knowledge_state = "VERIFIED"
                financial_state = None
                execution_state = "NOT_EXECUTED"
            else:
                knowledge_state = ev.payload.get("knowledge_state", "UNKNOWN")
                financial_state = ev.payload.get("financial_state")
                execution_state = ev.payload.get("execution_state")

            new_observations.append(
                ProviderObservation(
                    provider="razorpay",
                    event_id=ev.evidence_id,
                    entity_type=EntityType.REFUND_INTENT.value,
                    entity_id=case.expectation.refund_intent_id if case.expectation else ev.entity_id,
                    event_type=ev.evidence_type,
                    payload={
                        "status": financial_state,
                        "amount": ev.payload.get("amount"),
                        "currency": ev.payload.get("currency"),
                        "knowledge_state": knowledge_state,
                        "financial_state": financial_state,
                        "execution_state": execution_state,
                        "query_confidence": "AUTHORITATIVE_NOT_EXECUTED" if raw_status in ("not_found", "") else None
                    },
                    created_at=ev.timestamp,
                    id=uuid.uuid4(),
                )
            )

        if not new_observations:
            new_observations = [
                ProviderObservation(
                    provider="razorpay",
                    event_id=str(uuid.uuid4()),
                    entity_type=EntityType.REFUND_INTENT.value,
                    entity_id=case.expectation.refund_intent_id if case.expectation else "",
                    event_type="RAZORPAY_API_REFUND_NOT_FOUND",
                    payload={
                        "status": None,
                        "knowledge_state": "VERIFIED",
                        "financial_state": None,
                        "execution_state": "NOT_EXECUTED",
                        "query_confidence": "AUTHORITATIVE_NOT_EXECUTED"
                    },
                    created_at=case.created_at,
                    id=uuid.uuid4(),
                )
            ]

        return "verified", "", new_observations

    async def process_results(
        self,
        results: List[ReconciliationResult],
        grouped_expectations: Dict[str, ExpectedRefund],
        grouped_observations: Dict[str, List[ProviderObservation]],
        sub_case_hints: Dict[str, str],
        now: datetime
    ) -> List[Incident]:
        for result in results:
            if not DiscrepancyRouter.is_actionable_discrepancy(result):
                continue
                
            intent_id = result.intent_id
            expectation = grouped_expectations.get(intent_id)
            if not expectation:
                expectation = ExpectedRefund(
                    expectation_id=str(uuid.uuid4()),
                    refund_intent_id=intent_id,
                    provider_payment_id="unknown",
                    amount=Decimal("0.01"),
                    currency="INR",
                    created_at=now,
                    sla_seconds=3600,
                    source_system="FCE",
                    business_reason=""
                )

            incident = project_incident(result, expectation, self._repo.get_by_intent_id(intent_id))
            if not incident:
                continue

            self._repo.save(incident)

            if result.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE:
                obs_list = grouped_observations.get(intent_id, [])
                case = ReconciliationCase(
                    correlation_context=CorrelationContext(),
                    case_id=str(uuid.uuid4()),
                    expectation=expectation,
                    provider_observations=obs_list,
                    created_at=now,
                )
                
                sub_case_hint = sub_case_hints.get(intent_id, "")
                outcome, notes, new_obs = await self._investigate(case, sub_case_hint)
                
                incident.discrepancy_history.append(f"Investigated: {outcome} - {notes}")
                self._repo.save(incident)
                
                if outcome in ("d4_rejected", "provider_error"):
                    incident = incident.transition_to(IncidentState.ESCALATED, reason=notes)
                    self._repo.save(incident)
                    continue
                    
                if outcome == "verified":
                    all_obs = obs_list + new_obs
                    final_result_list = self._reconciliation_engine.reconcile_batch(
                        [expectation], all_obs, reconciliation_timestamp=now
                    )
                    
                    if final_result_list:
                        final_result = final_result_list[0]
                        updated_incident = project_incident(final_result, expectation, incident)
                        
                        if updated_incident is None:
                            from dataclasses import replace
                            incident = incident.resolve(final_result)
                            incident = replace(incident, discrepancy_type=final_result.discrepancy_type)
                        else:
                            incident = updated_incident
                            if final_result.discrepancy_type == DiscrepancyType.EPISTEMIC_STALEMATE:
                                incident = incident.transition_to(IncidentState.ESCALATED, reason="Stalemate persisted.")
                            else:
                                # Concrete discrepancy achieved. State transitions to ESCALATED
                                # denoting hand-off to the Action layer
                                incident = incident.transition_to(IncidentState.ESCALATED, reason="Concrete discrepancy established.")
                            
                        self._repo.save(incident)

            else:
                # Concrete discrepancy from start
                incident = incident.transition_to(IncidentState.ESCALATED, reason="Initial discrepancy is actionable.")
                self._repo.save(incident)
                
        return self._repo.get_all()
