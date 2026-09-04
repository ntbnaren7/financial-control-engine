import structlog
import json
from typing import Protocol, Dict, Any, Optional
from datetime import datetime, timezone

from src.domain.core.models import RecoveryIntent, RecoveryAction, ActuationOutcome
from src.domain.actuation.models import ActuationRecord, ActuationState
from src.engine.actuation_key import generate_canonical_payload, generate_idempotency_key
from src.storage.postgres_substrate import PostgresActiveIncidentRepository, PostgresActuationRepository
from src.domain.investigation.lifecycle import IncidentState
from src.engine.external_simulator import simulator

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Backward-compatible shim used by worker.py and all legacy tests.
# The worker still calls self.actuator.execute(intent) — until the worker is
# updated to call ActuationEngine.execute_intent() this keeps tests green.
# ---------------------------------------------------------------------------
class SimulatedActuator:
    """
    Thin shim over the external simulator, retained for backward compatibility
    with the existing worker and unit tests while Phase 9 engine is wired in.
    """
    async def execute(self, intent: RecoveryIntent) -> ActuationOutcome:
        logger.info(f"SimulatedActuator: Executing {intent.action.value} on {intent.target_id}")

        if intent.action == RecoveryAction.REPAIR_MERCHANT_STATE:
            result = simulator.update_merchant_order(intent.target_id, "PAID", intent.expected_provider_state)
            return ActuationOutcome(result)

        elif intent.action == RecoveryAction.REFUND_PAYMENT:
            result = simulator.refund_provider_payment(intent.target_id)
            return ActuationOutcome(result)

        elif intent.action == RecoveryAction.ESCALATE:
            logger.info("SimulatedActuator: Escalate intent, no external mutation.")
            return ActuationOutcome.SUCCESS

        logger.error(f"SimulatedActuator: Unsupported action {intent.action}")
        return ActuationOutcome.REJECTED


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------
class ProviderActuator(Protocol):
    async def execute(self, target_id: str, idempotency_key: str, payload: Dict[str, Any]) -> ActuationState:
        """Executes the provider API call idempotently."""
        ...


_SIMULATOR_RESULT_MAP: Dict[str, ActuationState] = {
    "SUCCESS": ActuationState.SUCCESS,
    "REJECTED": ActuationState.REJECTED,
    "TIMEOUT_UNKNOWN": ActuationState.TIMEOUT_UNKNOWN,
}


def _map_simulator_result(raw: str) -> ActuationState:
    """Converts a simulator string result to ActuationState. Unknown values are TIMEOUT_UNKNOWN (safe ambiguity)."""
    return _SIMULATOR_RESULT_MAP.get(raw, ActuationState.TIMEOUT_UNKNOWN)


from src.integrations.razorpay.provider import RazorpayProvider

class RazorpayRefundActuator:
    """Issues POST /v1/payments/{id}/refund with X-Refund-Idempotency header."""

    def __init__(self, provider: RazorpayProvider):
        self.provider = provider

    async def execute(self, target_id: str, idempotency_key: str, payload: Dict[str, Any]) -> ActuationState:
        logger.info(
            "Razorpay API POST /v1/payments/{target_id}/refund",
            target_id=target_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        try:
            amount = payload.get("amount", 0)
            receipt = payload.get("receipt", f"fce_{target_id}")
            await self.provider.create_refund(
                payment_id=target_id, 
                amount=amount, 
                receipt=receipt, 
                idempotency_key=idempotency_key
            )
            return ActuationState.SUCCESS
        except Exception as e:
            logger.error(f"RazorpayRefundActuator error: {e}")
            return ActuationState.TIMEOUT_UNKNOWN


class MerchantRepairActuator:
    """Issues an internal order-state-transition request to the Merchant API."""

    async def execute(self, target_id: str, idempotency_key: str, payload: Dict[str, Any]) -> ActuationState:
        logger.info(
            "Merchant Internal API repair order",
            target_id=target_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        expected_state = payload.get("expected_provider_state")
        raw = simulator.update_merchant_order(target_id, "PAID", expected_state)
        return _map_simulator_result(raw)


# ---------------------------------------------------------------------------
# Actuation Engine
# ---------------------------------------------------------------------------
class ActuationEngine:
    """
    Implements the two-transaction, idempotent actuation sequence:
      Tx1 (OCC lock + PENDING persist) → Network call → Tx2 (record outcome).
    """

    def __init__(
        self,
        investigation_repo: PostgresActiveIncidentRepository,
        actuation_repo: PostgresActuationRepository,
        razorpay_provider: RazorpayProvider,
    ):
        self.investigation_repo = investigation_repo
        self.actuation_repo = actuation_repo
        self.providers: Dict[RecoveryAction, ProviderActuator] = {
            RecoveryAction.REFUND_PAYMENT: RazorpayRefundActuator(razorpay_provider),
            RecoveryAction.REPAIR_MERCHANT_STATE: MerchantRepairActuator(),
        }

    async def execute_intent(
        self,
        intent: RecoveryIntent,
        execution_identity: str,
        discrepancy_reason: str,
        incident_version: int,
    ) -> ActuationState:
        """
        Executes the authorization → OCC → Network → Persist sequence.

        Parameters
        ----------
        intent:               The policy-authorized recovery intent.
        execution_identity:   The active_subject / incident correlation key.
        discrepancy_reason:   The DiscrepancyReason string stored on the incident.
        incident_version:     The OCC version read from ActiveIncidentIdempotencyRecord.
        """
        if intent.action == RecoveryAction.ESCALATE:
            logger.info("ActuationEngine: Escalate intent, no external mutation.")
            return ActuationState.ESCALATED

        if intent.action not in self.providers:
            logger.error("ActuationEngine: Unsupported action", action=intent.action)
            return ActuationState.REJECTED

        provider = self.providers[intent.action]

        # 1. Build canonical mutation payload -----------------------------------
        payload: Dict[str, Any] = {}
        if intent.action == RecoveryAction.REFUND_PAYMENT:
            if intent.amount is not None:
                payload["amount"] = intent.amount
            if intent.currency is not None:
                payload["currency"] = intent.currency
        elif intent.action == RecoveryAction.REPAIR_MERCHANT_STATE:
            payload["expected_provider_state"] = intent.expected_provider_state

        canonical_str = generate_canonical_payload(payload)

        # 2. Deterministic idempotency key --------------------------------------
        idempotency_key = generate_idempotency_key(
            execution_identity=execution_identity,
            intent_action=intent.action.value,
            target_id=intent.target_id,
            canonical_payload=canonical_str,
        )

        # 3. Transaction 1: OCC claim + PENDING persist -------------------------
        provider_name = "razorpay" if intent.action == RecoveryAction.REFUND_PAYMENT else "merchant"
        record = ActuationRecord(
            execution_identity=execution_identity,
            intent_action=intent.action.value,
            target_id=intent.target_id,
            mutation_parameters_canonical=canonical_str,
            idempotency_key=idempotency_key,
            provider=provider_name,
            state=ActuationState.PENDING,
        )

        claimed = self.investigation_repo.update_incident_state_occ(
            active_subject=execution_identity,
            discrepancy_reason=discrepancy_reason,
            current_version=incident_version,
            new_state=IncidentState.ACTUATION_PENDING,
        )

        if not claimed:
            logger.warning(
                "ActuationEngine: OCC claim failed — incident modified concurrently.",
                execution_identity=execution_identity,
            )
            return ActuationState.ESCALATED

        # Tx1: Save PENDING record as an immutable snapshot before touching the network.
        # A crash anywhere after this point leaves a recoverable PENDING record in the DB.
        self.actuation_repo.save(record)

        # 4. Network call (outside any transaction) -----------------------------
        # This is intentionally outside any DB transaction — we must never hold
        # a DB lock across an external API call.
        try:
            outcome = await provider.execute(intent.target_id, idempotency_key, payload)
        except Exception as exc:
            logger.error("ActuationEngine: Network error during execution", error=str(exc))
            outcome = ActuationState.TIMEOUT_UNKNOWN

        # Tx2: Record outcome by saving an updated copy of the record.
        # We update the mutable fields on the existing object so the record_id
        # (and therefore idempotency_key) remain stable across both transactions.
        record.state = outcome
        record.updated_at = datetime.now(timezone.utc)
        self.actuation_repo.save(record)

        return outcome

    async def execute_claimed_intent(
        self,
        intent: RecoveryIntent,
        record: ActuationRecord,
    ) -> ActuationState:
        """
        Executes the network call and outcome persistence for an intent that has
        ALREADY been claimed by the Governance Gate (Tx1 complete).
        """
        if intent.action not in self.providers:
            logger.error("ActuationEngine: Unsupported action", action=intent.action)
            return ActuationState.REJECTED
            
        provider = self.providers[intent.action]
        
        # Build payload (deterministic)
        payload: Dict[str, Any] = {}
        if intent.action == RecoveryAction.REFUND_PAYMENT:
            if intent.amount is not None:
                payload["amount"] = intent.amount
            if intent.currency is not None:
                payload["currency"] = intent.currency
        elif intent.action == RecoveryAction.REPAIR_MERCHANT_STATE:
            payload["expected_provider_state"] = intent.expected_provider_state

        # Network call (outside any transaction)
        try:
            outcome = await provider.execute(record.target_id, record.idempotency_key, payload)
        except Exception as exc:
            logger.error("ActuationEngine: Network error during execution", error=str(exc))
            outcome = ActuationState.TIMEOUT_UNKNOWN

        # Tx2: Record outcome
        record.state = outcome
        record.updated_at = datetime.now(timezone.utc)
        self.actuation_repo.save(record)

        return outcome
