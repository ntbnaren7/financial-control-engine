import hashlib
from typing import Optional
from dataclasses import replace

from src.reconciliation.models import ReconciliationResult, DiscrepancyType, ExpectedRefund
from src.domain.incidents.models import Incident, IncidentState

def project_incident(
    reconciliation_result: ReconciliationResult,
    expectation: ExpectedRefund,
    existing_incident: Optional[Incident] = None
) -> Optional[Incident]:
    """
    Pure deterministic projection of a ReconciliationResult into an Incident.
    
    Returns None for MATCH and IN_FLIGHT_PENDING.
    Does not transform EPISTEMIC_STALEMATE into ABSENT_EXECUTION.
    Maintains strict deterministic identity.
    """
    if reconciliation_result.discrepancy_type in (DiscrepancyType.MATCH, DiscrepancyType.IN_FLIGHT_PENDING):
        return None

    discrepancy = reconciliation_result.discrepancy_type

    intent_id = reconciliation_result.intent_id
    hash_hex = hashlib.sha256(intent_id.encode("utf-8")).hexdigest()
    incident_id = f"inc_{hash_hex[:16]}"
    
    disc_instance_hash = hashlib.sha256(f"{intent_id}:{discrepancy.value}".encode("utf-8")).hexdigest()
    discrepancy_instance_id = f"disc_{disc_instance_hash[:16]}"
    
    provider_payment_id = expectation.provider_payment_id
    evidence_refs = reconciliation_result.details.get("evidence_references", [])
    
    severity = "HIGH" if discrepancy == DiscrepancyType.EXCESS_EFFECT else "MEDIUM"
    
    if existing_incident:
        history = list(existing_incident.discrepancy_history)
        if existing_incident.discrepancy_type:
            history.append(existing_incident.discrepancy_type.value)
        
        return replace(
            existing_incident,
            discrepancy_type=discrepancy,
            discrepancy_instance_id=discrepancy_instance_id,
            discrepancy_history=history,
            reconciliation_timestamp=reconciliation_result.reconciliation_timestamp,
            reconstructed_state_ids=list(reconciliation_result.reconstructed_state_ids),
            evidence_references=evidence_refs,
            severity=severity,
            provenance={"source": "project_incident_update", "version": "1.1"}
        )

    return Incident(
        incident_id=incident_id,
        lifecycle_state=IncidentState.OPEN,
        expectation_id=reconciliation_result.expectation_id,
        refund_intent_id=intent_id,
        provider_payment_id=provider_payment_id,
        discrepancy_type=discrepancy,
        discrepancy_instance_id=discrepancy_instance_id,
        reconciliation_timestamp=reconciliation_result.reconciliation_timestamp,
        reconstructed_state_ids=list(reconciliation_result.reconstructed_state_ids),
        evidence_references=evidence_refs,
        severity=severity,
        provenance={"source": "project_incident", "version": "1.1"}
    )
