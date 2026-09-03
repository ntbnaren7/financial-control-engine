"""
D6 — Investigation Loop

The deterministic orchestrator for the investigative agent.
Responsible strictly for sequencing components. It must never interpret
the LLM's hypothesis, nor resolve the financial state itself.
"""

from datetime import datetime
from typing import Optional

from src.domain.cases.models import ReconciliationCase
from src.domain.investigation.models import ValidationRejection, VerificationRejection
from src.evidence.models import EntityType, ProviderObservation
from src.investigation.agent import Investigator
from src.investigation.input_formatter import format_case_for_investigation
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.reconciliation.engine import reconcile
from src.reconciliation.models import DiscrepancyType, ReconciliationResult
from src.state.engine import StateEngine, TemporalOrderingPolicy


class InvestigationLoop:
    """
    Orchestrates a single investigation cycle.
    """

    def __init__(
        self,
        investigator: Investigator,
        validator: OutputValidator,
        verifier: DeterministicVerifier,
        state_engine: StateEngine,
        ordering_policy: TemporalOrderingPolicy,
    ) -> None:
        self._investigator = investigator
        self._validator = validator
        self._verifier = verifier
        self._state_engine = state_engine
        self._ordering_policy = ordering_policy

    async def investigate_stalemate(
        self,
        case: ReconciliationCase,
        current_time: datetime,
    ) -> Optional[ReconciliationResult]:
        """
        Run exactly one cycle of investigation for an EPISTEMIC_STALEMATE case.
        Returns the original result if investigation yields no new facts or is rejected.
        Returns the new ReconciliationResult if investigation produces evidence.
        """
        # 1. D6 only starts from EPISTEMIC_STALEMATE
        if (
            not case.reconciliation_result
            or case.reconciliation_result.discrepancy_type != DiscrepancyType.EPISTEMIC_STALEMATE
        ):
            return case.reconciliation_result

        # 2. Format input for LLM (D2)
        formatted_input = format_case_for_investigation(case)

        # 3. LLM Hypothesis Generation (D3)
        hypothesis = self._investigator.investigate(formatted_input)

        # 4. Gatekeeper Validation (D4)
        validation_result = self._validator.validate(
            hypothesis.model_dump(mode="json"), formatted_input
        )
        
        # Validation rejection is terminal for that investigation attempt
        if isinstance(validation_result, ValidationRejection):
            return case.reconciliation_result

        # 5. Deterministic Verification (D5)
        verification_result = await self._verifier.verify(validation_result, case)
        
        # Provider failure or exhaustion is not evidence, leaves state unchanged
        if isinstance(verification_result, VerificationRejection):
            return case.reconciliation_result

        evidences = verification_result
        if not evidences:
            return case.reconciliation_result

        # 6. Ingest Phase C Evidence -> ProviderObservation
        new_observations = []
        for ev in evidences:
            entity_type = (
                case.expectation.entity_type.value
                if case.expectation
                else EntityType.REFUND_INTENT.value
            )
            entity_id = (
                case.expectation.intent_id
                if case.expectation
                else ev.entity_id
            )

            new_observations.append(
                ProviderObservation(
                    provider=ev.source,
                    event_id=ev.evidence_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    event_type=ev.evidence_type,
                    payload=ev.payload,
                    created_at=current_time,
                )
            )

        all_observations = case.provider_observations + new_observations

        entity_type_enum = (
            case.expectation.entity_type if case.expectation else EntityType.REFUND_INTENT
        )
        entity_id_str = case.expectation.intent_id if case.expectation else "unknown"

        # 7. Reconstruct State with new observations
        new_state = self._state_engine.reconstruct_state(
            entity_type=entity_type_enum,
            entity_id=entity_id_str,
            observations=all_observations,
            reconstructed_at=current_time,
            ordering_policy=self._ordering_policy,
        )

        # 8. V1 Reconcile (D6 does not interpret the hypothesis, V1 determines truth)
        new_result = reconcile(
            expectation=case.expectation,
            reconstructed_state=new_state,
            reconciliation_timestamp=current_time,
        )

        return new_result
