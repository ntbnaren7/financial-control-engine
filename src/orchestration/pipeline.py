from src.evidence.models import EntityType
import logging
from datetime import datetime, timezone
from typing import cast, Any, Dict
from src.evidence.db import AsyncSessionLocal
from src.evidence.models import ProviderObservation
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.reconciliation.engine import M3Engine
from src.reconciliation.models import ProviderPayment, MerchantOrderState
from src.investigation.orchestrator import InvestigationOrchestrator
from src.investigation.ai import InvestigationEngine
from src.investigation.config import LLMConfig
from src.control.policy import evaluate_repair_eligibility, ActionDecision
from src.recovery.action import execute_repair_action, ActionStatus
from src.recovery.verifier import verify_resolution, VerificationStatus
from src.merchant.models import MerchantOrder
from src.control.audit import emit_audit_event, Actor
import os

logger = logging.getLogger(__name__)

async def run_investigation_pipeline(observation_id: str) -> dict | None:
    """
    Integration Spike: Triggered asynchronously by a webhook ingestion.
    Fetches the persisted observation, simulates a merchant order state,
    runs M3 deterministic reconciliation, and if a discrepancy is found,
    triggers an M4 LLM investigation.
    """
    logger.info(f"Pipeline started for observation_id: {observation_id}")
    
    async with AsyncSessionLocal() as session:
        # Fetch the observation that just came in
        observation = await session.get(ProviderObservation, observation_id)
        if not observation:
            logger.error(f"Observation {observation_id} not found.")
            return

        payload = observation.payload
        if not payload:
            logger.warning("Observation has no payload.")
            return

        # Simple integration spike assumptions:
        # 1. We assume the webhook is a payment webhook with order_id, payment_id etc.
        #    Real razorpay payloads are nested, e.g., payload['payload']['payment']['entity'].
        #    For this spike, we'll try to extract fields safely.
        payload_dict = cast(Dict[str, Any], payload) if payload else {}
        payment_entity = payload_dict.get("payload", {}).get("payment", {}).get("entity", payload_dict)
        
        order_id = payment_entity.get("order_id")
        payment_id = payment_entity.get("id") or payment_entity.get("payment_id")
        amount = payment_entity.get("amount", 0)
        currency = payment_entity.get("currency", "INR")
        status = payment_entity.get("status", "unknown")
        
        if not order_id or not payment_id:
            logger.info("Observation missing order_id or payment_id. Skipping pipeline.")
            return

        logger.info(f"Reconciling Payment: {payment_id} | Order: {order_id}")

        # 1. Fetch real MerchantOrder using the order_id
        # We need this to get the PK (id) for atomic updates later
        from sqlalchemy import select
        result = await session.execute(
            select(MerchantOrder).where(MerchantOrder.razorpay_order_id == order_id)
        )
        order_state = result.scalar_one_or_none()
        
        incident_id = f"disc_{payment_id}" # Preliminary ID before M3 creates it
        
        emit_audit_event(
            incident_id=incident_id,
            state="WEBHOOK_INGESTED",
            actor=Actor.SYSTEM,
            reason=f"Pipeline triggered for observation_id: {observation_id}"
        )
        
        if not order_state:
            logger.info(f"Merchant order {order_id} not found in DB. Skipping pipeline.")
            return

        # 2. Construct ProviderPayment from the observation payload
        payment = ProviderPayment(
            payment_id=payment_id,
            order_id=order_id,
            amount=amount,
            currency=currency,
            status=status,
            captured=(status == "captured"),
            observed_at=datetime.now(timezone.utc)
        )

    # 3. M3 Deterministic Verification
    m3 = M3Engine()
    try:
        # We need to map MerchantOrder (SQLAlchemy) to MerchantOrderState (Pydantic)
        merchant_state = None
        if order_state:
            merchant_state = MerchantOrderState(
                merchant_order_id=order_state.merchant_order_id,
                razorpay_order_id=order_state.razorpay_order_id,
                expected_amount=order_state.expected_amount,
                currency=order_state.currency,
                status=order_state.status
            )
            
        discrepancy = m3.evaluate_reconciliation(
            payment=payment,
            order=merchant_state
        )
    except ValueError as e:
        logger.error(f"M3 evaluation failed: {e}")
        return

    if not discrepancy:
        logger.info("M3 found no discrepancy. Pipeline complete.")
        emit_audit_event(
            incident_id=incident_id,
            state="NO_DISCREPANCY",
            actor=Actor.M3,
            reason="M3 found no discrepancy."
        )
        return {"pipeline_status": "NO_ACTION", "reason": "No discrepancy"}

    # Update incident_id to the formal one created by M3
    incident_id = str(discrepancy.id) if hasattr(discrepancy, 'id') else incident_id

    logger.warning(f"M3 Discrepancy Detected! [{discrepancy.discrepancy_id}] {discrepancy.description}")
    emit_audit_event(
        incident_id=incident_id,
        state="DISCREPANCY_DETECTED",
        actor=Actor.M3,
        reason=discrepancy.description
    )

    # 4. M4 LLM Investigation
    config = LLMConfig(
        model_name="qwen3:8b",
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1"),
        api_key="ollama",
        temperature=0.0
    )
    engine = InvestigationEngine(config)
    gatherer = DatabaseEvidenceGatherer(AsyncSessionLocal)
    orchestrator = InvestigationOrchestrator(engine, gatherer)

    logger.info("Starting M4 Investigation...")
    result = await orchestrator.investigate(discrepancy)

    logger.info(f"Investigation Complete. Status: {result.status.value}")
    if result.proposal:
        top_sel = next((s for s in result.proposal.selections if s.rank == 1), None)
        if top_sel:
            logger.info(f"Top Hypothesis: {top_sel.hypothesis_id.value}")
            logger.info(f"Rationale: {top_sel.rationale}")

    if result.failure_reason:
        logger.error(f"Safety Gate Rejection: {result.failure_reason}")
        emit_audit_event(
            incident_id=incident_id,
            state="INVESTIGATION_REJECTED",
            actor=Actor.M4,
            reason=result.failure_reason
        )
        await engine.client.close()
        return {"pipeline_status": "NO_ACTION", "investigation": result, "reason": result.failure_reason}
        
    emit_audit_event(
        incident_id=incident_id,
        state="INVESTIGATION_COMPLETED",
        actor=Actor.M4,
        reason="M4 returned an accepted semantic proposal"
    )

    # 5. Deterministic Control Plane
    logger.info("Evaluating Repair Eligibility...")
    # We need the raw evidence packet that was used by M4. M4 orchestrator doesn't currently return it,
    # but we can re-gather or modify the gatherer call. Let's just re-gather for the spike to keep it clean.
    evidence_packet = await gatherer.gather(discrepancy)
    
    # We need the real MerchantOrder object, not just the M3 state snapshot
    async with AsyncSessionLocal() as session:
        db_res = await session.execute(select(MerchantOrder).where(MerchantOrder.razorpay_order_id == order_id))
        real_merchant_order = db_res.scalar_one()
    
    control_decision = evaluate_repair_eligibility(
        discrepancy=discrepancy,
        investigation_result=result,
        evidence=evidence_packet.items,
        merchant_order=real_merchant_order
    )
    logger.info(f"Control Decision: {control_decision.decision.value} - {control_decision.reason}")
    
    emit_audit_event(
        incident_id=incident_id,
        state="AUTHORIZATION_GRANTED" if control_decision.decision == ActionDecision.ALLOW_REPAIR else "AUTHORIZATION_DENIED",
        actor=Actor.CONTROL,
        reason=control_decision.reason,
        extra_context={"provenance": control_decision.provenance}
    )

    if control_decision.decision != ActionDecision.ALLOW_REPAIR:
        await engine.client.close()
        return {"pipeline_status": "NO_ACTION", "investigation": result, "reason": control_decision.reason}

    # 6. Recovery Action
    logger.info(f"Executing Conditional Idempotent Repair for Order {real_merchant_order.id}...")
    async with AsyncSessionLocal() as session:
        action_res = await execute_repair_action(
            session=session,
            merchant_order_id_pk=str(real_merchant_order.id),
            expected_precondition_status="UNPAID",
            target_status="PAID"
        )
    logger.info(f"Action Status: {action_res.status.value} - {action_res.message}")

    if action_res.status != ActionStatus.SUCCESS:
        emit_audit_event(
            incident_id=incident_id,
            state="MUTATION_FAILED",
            actor=Actor.RECOVERY,
            reason=action_res.message
        )
        await engine.client.close()
        return {"pipeline_status": "CONFLICT", "investigation": result, "reason": action_res.message}

    emit_audit_event(
        incident_id=incident_id,
        state="MUTATION_COMMITTED",
        actor=Actor.RECOVERY,
        reason=action_res.message
    )

    # 7. Independent Verification
    logger.info("Executing Independent Verification...")
    async with AsyncSessionLocal() as session:
        verify_res = await verify_resolution(
            session=session,
            merchant_order_id_pk=str(real_merchant_order.id),
            payment_id=payment_id
        )
    
    logger.info(f"Final Verification Status: {verify_res.status.value} - {verify_res.message}")
    
    emit_audit_event(
        incident_id=incident_id,
        state="VERIFICATION_SUCCESS" if verify_res.status == VerificationStatus.RESOLVED else "VERIFICATION_FAILED",
        actor=Actor.VERIFIER,
        reason=verify_res.message
    )

    await engine.client.close()
    return {"pipeline_status": verify_res.status.value, "investigation": result, "reason": verify_res.message}
