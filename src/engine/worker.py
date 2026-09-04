import asyncio
import uuid
import structlog
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from typing import Any


def _as_utc(dt: Any) -> datetime:
    """Coerce a naive (or SQLAlchemy-typed) datetime to UTC-aware.

    SQLite stores timestamps without tzinfo and SQLAlchemy exposes the
    column as Column[datetime], which the type checker flags. At runtime
    the value is always a plain datetime; we just ensure it carries tzinfo.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


from src.storage.postgres_substrate import (
    PostgresControlEventRepository,
    PostgresActiveIncidentRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresExpectationRepository,
    PostgresReconciliationResultRepository,
    PostgresActuationRepository,
    ControlEventType,
    ActiveIncidentIdempotencyRecord,
)
from src.domain.investigation.lifecycle import IncidentState
from src.domain.investigation.models import VerificationStatus, ValidationRejection, CausalHypothesis
from src.domain.core.models import RecoveryAction, ReconciliationOutcome, ReconciliationResult
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.policy import V2PolicyEvaluator
from src.investigation.verifier import DeterministicVerifier
from src.integrations.razorpay.provider import RazorpayProvider
from src.engine.actuator import ActuationEngine
from src.domain.actuation.models import ActuationState
from src.engine.observer import SimulatedObserver
from src.investigation.agent import Investigator, InvestigatorError
from src.investigation.validator import OutputValidator
from src.investigation.verifier import DeterministicVerifier
from src.investigation.input_formatter import format_context_for_investigation
from src.engine.reconciliation_v2 import V2ReconciliationEngine
from sqlalchemy.exc import OperationalError
from src.config.settings import ControlLoopSettings

from src.observability.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

class V2ControlWorker:
    def __init__(
        self,
        worker_id: str,
        event_repo: PostgresControlEventRepository,
        incident_repo: PostgresActiveIncidentRepository,
        observation_repo: PostgresObservationRepository,
        evidence_repo: PostgresEvidenceRepository,
        exp_repo: PostgresExpectationRepository,
        recon_result_repo: PostgresReconciliationResultRepository,
        actuation_repo: PostgresActuationRepository,
        reconciliation_engine: V2ReconciliationEngine,
        assembler: EvidenceAssembler,
        investigator: Investigator,
        validator: OutputValidator,
        verifier: DeterministicVerifier,
        razorpay_provider: Optional[RazorpayProvider] = None,
        settings: ControlLoopSettings = ControlLoopSettings(),
        test_hooks: Optional[Dict[str, Callable[[], None]]] = None
    ):
        self.worker_id = worker_id
        self.event_repo = event_repo
        self.incident_repo = incident_repo
        self.observation_repo = observation_repo
        self.evidence_repo = evidence_repo
        self.exp_repo = exp_repo
        self.recon_result_repo = recon_result_repo
        self.actuation_repo = actuation_repo
        self.reconciliation_engine = reconciliation_engine
        self.assembler = assembler
        self.investigator = investigator
        self.validator = validator
        self.verifier = verifier
        self.policy = V2PolicyEvaluator()
        self.actuator = ActuationEngine(self.incident_repo, self.actuation_repo, razorpay_provider=razorpay_provider)
        
        # Phase 10 Governance Gate (Optional for legacy tests)
        from src.engine.governance_gate import GovernanceGate
        self.governance_gate = GovernanceGate(self.incident_repo.session_maker) if hasattr(self.incident_repo, 'session_maker') else None
        
        self.observer = SimulatedObserver(razorpay_provider=razorpay_provider)
        self.settings = settings
        self.test_hooks = test_hooks or {}

    def _trigger_hook(self, name: str):
        if name in self.test_hooks:
            self.test_hooks[name]()

    async def poll_and_process(self, limit: int = 5) -> int:
        # Start Prometheus metrics server once (idempotent — OSError means already running)
        if not getattr(self, "_metrics_server_started", False):
            try:
                from prometheus_client import start_http_server
                start_http_server(9090)
                logger.info("Prometheus metrics server started on port 9090")
                self._metrics_server_started = True
            except OSError:
                self._metrics_server_started = True  # already running, mark done
            except Exception:
                pass  # non-fatal: metrics unavailable

        # 1. Recover stale events from crashed workers
        recovered_count = self.event_repo.recover_stale_events(self.settings.event_stale_threshold_seconds)
        if recovered_count > 0:
            logger.warning(f"Recovered {recovered_count} stale events that were stuck IN_PROGRESS")

        # 2. Poll for pending events
        events = self.event_repo.poll_pending_events(limit=limit)
        
        # Update gauges
        from src.observability.metrics import set_pending_events, set_active_incidents
        try:
            pending_count = self.event_repo.count_pending()
            set_pending_events(pending_count)
        except Exception:
            pass # count_pending might not exist, ignore for now

        try:
            active_count = self.incident_repo.count_active()
            set_active_incidents(active_count)
        except Exception:
            pass

        for event in events:
            import time
            start_time = time.monotonic()
            try:
                structlog.contextvars.bind_contextvars(
                    worker_id=self.worker_id,
                    event_id=str(event.event_id),
                    event_type=event.event_type.value
                )
                logger.info("Worker processing event")
                event_type: Any = event.event_type
                payload: Dict[str, Any] = dict(event.payload) if isinstance(event.payload, dict) else {}  # type: ignore
                if event_type == ControlEventType.OBSERVATION_INGESTED:
                    await self._handle_observation_ingested(payload)
                elif event_type == ControlEventType.DISCREPANCY_DETECTED:
                    await self._handle_discrepancy(payload)
                
                self.event_repo.mark_processed(str(event.event_id))
            except Exception as e:
                import traceback
                print(f"Exception in process_event: {e}\n{traceback.format_exc()}", flush=True)
                logger.error(f"Error processing event {event.event_id}: {str(e)}", exception=traceback.format_exc())
                self.event_repo.mark_failed(str(event.event_id))
            finally:
                elapsed = time.monotonic() - start_time
                from src.observability.metrics import inc_event_processed, observe_event_processing_latency
                inc_event_processed(event.event_type.value)
                observe_event_processing_latency(event.event_type.value, elapsed)

        # 3. Poll for matured retry incidents
        matured_retries = self.incident_repo.acquire_matured_retries(
            worker_id=self.worker_id,
            ttl_seconds=self.settings.worker_lease_ttl_seconds,
            limit=limit,
        )
        for incident_record in matured_retries:
            await self._handle_matured_retry(incident_record)

        return len(events) + len(matured_retries)

    async def _handle_observation_ingested(self, payload: Dict[str, Any]):
        """
        Targeted reconciliation: reconcile only the expectations that match the
        newly-ingested observation, not the entire open batch.
        This prevents O(N²) event fan-out when seeding or receiving bulk data.
        """
        observation_id = payload.get("observation_id")
        if not observation_id:
            # Fallback: full batch reconcile (legacy callers without payload)
            results = self.reconciliation_engine.reconcile_batch()
        else:
            obs = self.observation_repo.get(observation_id)
            if not obs:
                return
            # Find expectations whose correlation_keys match this observation
            matching_exps = self.exp_repo.find_open_by_correlation_keys(obs.correlation_keys)
            if not matching_exps:
                # Observation-centric path: no expectation found → unexpected execution
                from src.engine.reconciliation_controls import evaluate_observation_centric
                obs_result = evaluate_observation_centric(obs, [])
                results = [obs_result] if obs_result else []
            else:
                from src.engine.reconciliation_controls import evaluate_expectation_centric
                results = []
                for exp in matching_exps:
                    candidate_obs = self.observation_repo.find_by_correlation_keys(exp.correlation_keys)
                    res = evaluate_expectation_centric(exp, candidate_obs)
                    if res:
                        results.append(res)

        for res in results:
            self.recon_result_repo.save(res)
            if res.outcome == ReconciliationOutcome.DISCREPANCY:
                self.event_repo.publish(
                    ControlEventType.DISCREPANCY_DETECTED,
                    {"reconciliation_id": res.reconciliation_id}
                )

    async def _handle_discrepancy(self, payload: Dict[str, Any]):
        reconciliation_id = payload.get("reconciliation_id")
        if not reconciliation_id:
            return
            
        recon_result = self.recon_result_repo.get(reconciliation_id)
        if not recon_result or recon_result.outcome != ReconciliationOutcome.DISCREPANCY:
            return
            
        active_subject = recon_result.expectation_id or recon_result.observation_ids[0]
        discrepancy_reason = recon_result.discrepancy_reason.value if recon_result.discrepancy_reason else "UNKNOWN"
        
        # 1. Try to initialize the state machine
        self.incident_repo.try_claim_incident(active_subject, discrepancy_reason, f"inc_{uuid.uuid4()}")
        
        self._trigger_hook("before_lease_acquire")
        # 2. Acquire Lease (Locks for distributed safety)
        record = self.incident_repo.acquire_lease(
            active_subject, 
            discrepancy_reason, 
            self.worker_id, 
            ttl_seconds=self.settings.worker_lease_ttl_seconds
        )
        if not record:
            from src.observability.metrics import inc_lease_contention
            inc_lease_contention()
            logger.info(f"Could not acquire lease for {active_subject}")
            return # Someone else has the lease or it's not ready

        await self._process_investigation(record, recon_result)

    async def _handle_matured_retry(self, record: ActiveIncidentIdempotencyRecord):
        active_subject: str = str(record.active_subject)
        discrepancy_reason: str = str(record.discrepancy_reason)
        created_at: datetime = _as_utc(record.created_at) if record.created_at is not None else datetime.now(timezone.utc)
        logger.info(
            f"Processing matured retry for incident {record.incident_id} (subject={active_subject}, retry_count={record.retry_count})"
        )
        recon_result = self.recon_result_repo.find_latest_discrepancy(
            active_subject, discrepancy_reason
        )
        if not recon_result:
            from src.domain.core.models import DiscrepancyReason
            reason_enum = None
            if discrepancy_reason and hasattr(DiscrepancyReason, discrepancy_reason):
                reason_enum = DiscrepancyReason[discrepancy_reason]
            recon_result = ReconciliationResult(
                reconciliation_id=f"rec_retry_{record.incident_id}",
                expectation_id=active_subject if not active_subject.startswith("obs") else None,
                observation_ids=[active_subject] if active_subject.startswith("obs") else [],
                outcome=ReconciliationOutcome.DISCREPANCY,
                discrepancy_reason=reason_enum,
                reconciliation_reason="Retried discrepancy",
                created_at=created_at,
            )
        await self._process_investigation(record, recon_result)

    async def _process_investigation(
        self,
        record: ActiveIncidentIdempotencyRecord,
        recon_result: ReconciliationResult,
    ):
        active_subject: str = str(record.active_subject)
        discrepancy_reason: str = str(record.discrepancy_reason)
        reconciliation_id: str = recon_result.reconciliation_id

        structlog.contextvars.bind_contextvars(
            reconciliation_id=reconciliation_id,
            active_subject=active_subject,
            incident_id=record.incident_id
        )
        logger.info("Lease acquired, starting investigation")
        self._trigger_hook("after_lease_acquire")

        # 3. Stale-event guard: re-evaluate current state before committing to investigation.
        # If a concurrent worker already resolved this discrepancy (e.g., the observation
        # now matches the expectation), drop this event and resolve the incident.
        if recon_result.expectation_id:
            exp = self.exp_repo.get(recon_result.expectation_id)
            if exp:
                current_obs = self.observation_repo.find_by_correlation_keys(exp.correlation_keys)
                if current_obs:
                    from src.engine.reconciliation_controls import evaluate_expectation_centric
                    fresh_result = evaluate_expectation_centric(exp, current_obs)
                    if fresh_result.outcome == ReconciliationOutcome.MATCH:
                        from src.observability.metrics import (
                            inc_stale_event_dropped,
                            observe_cycle_resolution_latency,
                            observe_incident_lifetime
                        )
                        inc_stale_event_dropped()
                        elapsed = (datetime.now(timezone.utc) - _as_utc(recon_result.created_at)).total_seconds()
                        observe_cycle_resolution_latency(elapsed)
                        observe_incident_lifetime((datetime.now(timezone.utc) - _as_utc(record.created_at)).total_seconds())
                        logger.info(f"Stale DISCREPANCY event for {active_subject} — current state is MATCH. Resolving incident.")
                        self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.RESOLVED)
                        return

        import time
        from src.observability.metrics import (
            observe_investigation_latency,
            observe_incident_lifetime,
            inc_control_loop_outcome
        )
        try:
            investigation_start_time = time.monotonic()

            # A2: Assemble Evidence (Always fresh to capture latest observations)
            context = self.assembler.assemble(recon_result)
            formatted_input = format_context_for_investigation(context)

            hypothesis = None
            
            # A3: AI Investigation (Skip if already have a validated hypothesis from a previous retry)
            self._trigger_hook("before_a3")
            if record.state == IncidentState.VERIFYING and record.hypothesis_payload is not None:  # type: ignore
                logger.info(f"Reusing existing hypothesis for {active_subject}")
                hypothesis = CausalHypothesis.model_validate(record.hypothesis_payload)
            else:
                import inspect
                logger.info(f"Running A3 AI Investigation for {active_subject}")
                self._trigger_hook("during_a3")
                if inspect.iscoroutinefunction(self.investigator.investigate):
                    hypothesis = await self.investigator.investigate(formatted_input)
                else:
                    hypothesis = await asyncio.to_thread(self.investigator.investigate, formatted_input)
                    
                validation_result = self.validator.validate(hypothesis.model_dump(mode="json"), formatted_input)
                if isinstance(validation_result, ValidationRejection):
                    logger.warning(
                        f"Hypothesis rejected: {validation_result.reason}. Detail: {validation_result.detail}",
                        incident_id=record.incident_id,
                    )
                    self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_UNKNOWN)
                    observe_incident_lifetime((datetime.now(timezone.utc) - _as_utc(record.created_at)).total_seconds())
                    inc_control_loop_outcome("escalated")
                    return
                
                hypothesis = validation_result
                # Save hypothesis and move state to VERIFYING
                self.incident_repo.update_hypothesis(active_subject, discrepancy_reason, self.worker_id, hypothesis)

            # A4: Deterministic Verification
            logger.info(f"Running A4 Deterministic Verification for {active_subject}")
            self._trigger_hook("before_a4")
            verification_results = await self.verifier.verify(hypothesis, context)
            self._trigger_hook("after_a4")
            
            # Process Results
            all_new_evidence = []
            all_new_observations = []
            
            for v_res in verification_results:
                if v_res.status == VerificationStatus.FAILED:
                    logger.warning(f"Verification FAILED for {active_subject}: {v_res.failure_reason}. Scheduling retry.")
                    # Retry policy: 30s * (2 ^ retry_count), max 5 retries
                    r_count = int(record.retry_count) # type: ignore
                    if r_count >= 5:
                        logger.error(f"Exhausted retries for {active_subject}. Escalating.")
                        self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_MISSING_EVIDENCE)
                        observe_incident_lifetime((datetime.now(timezone.utc) - _as_utc(record.created_at)).total_seconds())
                        inc_control_loop_outcome("escalated")
                    else:
                        delay = 30 * (2 ** r_count)
                        self._trigger_hook("before_retry")
                        self.incident_repo.schedule_retry(active_subject, discrepancy_reason, self.worker_id, delay)
                        inc_control_loop_outcome("retry_pending")
                    return # Stop processing further intents on this pass

                elif v_res.status == VerificationStatus.REJECTED:
                    logger.error(f"Verification REJECTED for {active_subject}: {v_res.failure_reason}. Escalating.")
                    self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_MISSING_EVIDENCE)
                    observe_incident_lifetime((datetime.now(timezone.utc) - _as_utc(record.created_at)).total_seconds())
                    inc_control_loop_outcome("escalated")
                    return
                    
                elif v_res.status == VerificationStatus.SUCCEEDED:
                    logger.info(f"Verification SUCCEEDED for {active_subject}. Staging new evidence for atomic commit.")
                    all_new_evidence.extend(v_res.new_evidence)
                    all_new_observations.extend(v_res.new_observations)
                        
            # VERIFY VERIFICATION OUTCOME
            from src.engine.reconciliation_controls import evaluate_expectation_centric, evaluate_observation_centric
            if context.expectation:
                mid_reconciliation = evaluate_expectation_centric(context.expectation, context.observations + all_new_observations)
            else:
                mid_reconciliation = evaluate_observation_centric((context.observations + all_new_observations)[0], [])
                
            if mid_reconciliation and mid_reconciliation.outcome == ReconciliationOutcome.MATCH:
                logger.info(f"Verification resolved the discrepancy. Committing and resolving incident {active_subject}.")
                self._trigger_hook("before_commit")
                self.incident_repo.commit_verification_success(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason,
                    new_evidence=all_new_evidence,
                    new_observations=all_new_observations
                )
                self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.RESOLVED)
                from src.observability.metrics import inc_control_loop_outcome
                inc_control_loop_outcome("resolved")
                return

            # DECIDE: Evaluate Policy
            logger.info("Evaluating Policy to derive RecoveryIntent")
            combined_observations = context.observations + all_new_observations
            combined_evidence = context.evidence_records + all_new_evidence
            
            intent = self.policy.evaluate(active_subject, discrepancy_reason, combined_observations, combined_evidence, context)
            
            if intent is None or intent.action == RecoveryAction.ESCALATE:
                logger.info(f"Policy derived ESCALATE for {active_subject}: {intent.reason if intent else 'No safe intent could be derived'}. Triggering re-observation guard.")
                
                # J. Re-observation / Convergence Guard
                reobserved = False
                for obs in combined_observations:
                    try:
                        new_obs = None
                        if obs.provider.lower() == "razorpay":
                            # Use domain from correlation_keys (set by normalizer) or fall back
                            # to observation_type prefix. Normalizer emits "API_REFUND"/"API_PAYMENT".
                            obs_domain = (
                                (obs.correlation_keys.domain if obs.correlation_keys else None)
                                or obs.observation_type
                            ).upper()
                            if "REFUND" in obs_domain:
                                new_obs = await self.observer.observe_provider_refund(obs.provider_reference)
                            else:
                                new_obs = await self.observer.observe_provider_payment(obs.provider_reference)
                        elif obs.provider.lower() == "merchant":
                            new_obs = await self.observer.observe_merchant_order(obs.provider_reference)
                        
                        if new_obs and new_obs.canonical_status != obs.canonical_status:
                            logger.info(f"Re-observation guard caught state change for {obs.provider_reference}: {obs.canonical_status} -> {new_obs.canonical_status}")
                            all_new_observations.append(new_obs)
                            reobserved = True
                    except Exception as fetch_ex:
                        logger.error(f"Re-observation fetch failed: {fetch_ex}")
                        
                if reobserved:
                    # Re-evaluate reconciliation to see if it's now resolved
                    from src.engine.reconciliation_controls import evaluate_expectation_centric, evaluate_observation_centric
                    if context.expectation:
                        mid_reconciliation = evaluate_expectation_centric(context.expectation, context.observations + all_new_observations)
                    else:
                        mid_reconciliation = evaluate_observation_centric((context.observations + all_new_observations)[0], [])
                        
                    if mid_reconciliation and mid_reconciliation.outcome == ReconciliationOutcome.MATCH:
                        logger.info(f"Re-observation resolved the discrepancy. Committing and resolving incident {active_subject}.")
                        self.incident_repo.commit_verification_success(
                            active_subject=active_subject,
                            discrepancy_reason=discrepancy_reason,
                            new_evidence=all_new_evidence,
                            new_observations=all_new_observations
                        )
                        self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.RESOLVED)
                        from src.observability.metrics import inc_control_loop_outcome
                        inc_control_loop_outcome("resolved")
                        return
                    else:
                        # Re-evaluate policy with new facts
                        combined_observations = context.observations + all_new_observations
                        intent = self.policy.evaluate(active_subject, discrepancy_reason, combined_observations, combined_evidence, context)
                        if intent and intent.action != RecoveryAction.ESCALATE:
                            logger.info(f"Re-observation averted escalation. New intent: {intent.action}")
                        else:
                            logger.info(f"Re-observation did not avert escalation. Final intent: {intent.action if intent else 'None'}")
                            
            # Commit verification success (transitions to ACTIONABLE)
            self.incident_repo.commit_verification_success(
                active_subject=active_subject,
                discrepancy_reason=discrepancy_reason,
                new_evidence=all_new_evidence,
                new_observations=all_new_observations
            )

            if intent is None or intent.action == RecoveryAction.ESCALATE:
                logger.info(f"Proceeding with ESCALATE for {active_subject}")
                self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_POLICY_BLOCKED)
                from src.observability.metrics import inc_control_loop_outcome
                inc_control_loop_outcome("escalated")
                return
                
            # ACT: Governance Gate (Phase 10)
            logger.info(f"Executing ACT: {intent.action.value} on {intent.target_id} via Governance Gate")
            
            if self.governance_gate:
                budget_id = f"budget_{intent.action.value.lower()}"
                budget_amount = intent.amount or 0
                
                decision = self.governance_gate.evaluate_and_claim(
                    intent=intent,
                    execution_identity=active_subject,
                    discrepancy_reason=discrepancy_reason,
                    incident_version=int(record.version), # type: ignore
                    budget_id=budget_id,
                    budget_amount=budget_amount
                )
                
                from src.domain.governance.gate import GovernanceGateDecision
                if decision.status != GovernanceGateDecision.ALLOWED:
                    if decision.status == GovernanceGateDecision.BLOCKED_BY_KILL_SWITCH:
                        escalation_state = IncidentState.ESCALATED_PAUSED_BY_KILL_SWITCH
                    elif decision.status == GovernanceGateDecision.BLOCKED_BY_BUDGET:
                        escalation_state = IncidentState.ESCALATED_BUDGET_EXHAUSTED
                    else:
                        escalation_state = IncidentState.ESCALATED_UNKNOWN
                    logger.error(f"Actuation blocked by Governance Gate: {decision.status.value} - {decision.reason}")
                    self.incident_repo.terminate_incident(active_subject, discrepancy_reason, escalation_state)
                    from src.observability.metrics import inc_control_loop_outcome
                    inc_control_loop_outcome("escalated")
                    return
                
                # Gate is ALLOWED, and the claim has been atomically established in Tx1.
                # Now Phase 9 ActuationEngine performs the external mutation (Tx2).
                assert decision.actuation_record is not None, "Governance Gate ALLOWED but did not return ActuationRecord"
                self.incident_repo.transition_to_actuating(active_subject, discrepancy_reason)
                actuation_state = await self.actuator.execute_claimed_intent(
                    intent=intent,
                    record=decision.actuation_record
                )
            else:
                # Fallback for legacy tests: mirror the GovernanceGate sequence.
                # execute_intent() performs Tx1 internally (ACTIONABLE → ACTUATION_PENDING via OCC).
                # We must NOT call transition_to_actuating() before Tx1, or the OCC inside
                # execute_intent() will overwrite ACTUATING → ACTUATION_PENDING, causing the
                # subsequent ACTUATING → REOBSERVING transition to fail.
                actuation_state = await self.actuator.execute_intent(
                    intent=intent,
                    execution_identity=active_subject,
                    discrepancy_reason=discrepancy_reason,
                    incident_version=int(record.version)  # type: ignore
                )
                # Tx1 is complete: incident is now ACTUATION_PENDING. Advance to ACTUATING
                # (matching the GovernanceGate path) before the post-network transitions.
                self.incident_repo.transition_to_actuating(active_subject, discrepancy_reason)
            
            if actuation_state == ActuationState.REJECTED or actuation_state == ActuationState.ESCALATED:
                logger.error(f"Actuation {actuation_state.value} for {active_subject}. Escalating.")
                self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_MUTATION_FAILED)
                from src.observability.metrics import inc_control_loop_outcome
                inc_control_loop_outcome("escalated")
                return
                
            if actuation_state == ActuationState.TIMEOUT_UNKNOWN:
                logger.warning(f"Actuation TIMEOUT_UNKNOWN for {active_subject}. Will observe independently.")
                
            # ENTER REOBSERVING: mutation was dispatched, now verify external convergence.
            # This state is durably written before the observation fetch — a crash here
            # leaves a recoverable REOBSERVING incident that re-attempts observation on next lease.
            self.incident_repo.transition_to_reobserving(active_subject, discrepancy_reason)

            # OBSERVE AGAIN: Re-read state from external systems
            logger.info(f"OBSERVE AGAIN: Reading final state from simulated external systems")
            
            if intent.action == RecoveryAction.REPAIR_MERCHANT_STATE:
                final_obs = await self.observer.observe_merchant_order(intent.target_id)
                if final_obs:
                    all_new_observations.append(final_obs)
            elif intent.action == RecoveryAction.REFUND_PAYMENT:
                final_obs = await self.observer.observe_provider_payment(intent.target_id)
                if final_obs:
                    all_new_observations.append(final_obs)
                    
            # VERIFY OUTCOME
            logger.info(f"VERIFY OUTCOME: Re-evaluating reconciliation with final state")
            from src.engine.reconciliation_controls import evaluate_expectation_centric, evaluate_observation_centric
            if context.expectation:
                final_reconciliation = evaluate_expectation_centric(context.expectation, context.observations + all_new_observations)
            else:
                final_reconciliation = evaluate_observation_centric((context.observations + all_new_observations)[0], [])

            if final_reconciliation and final_reconciliation.outcome == ReconciliationOutcome.MATCH:
                logger.info(f"Final Outcome is MATCH. Resolving incident {active_subject} via REOBSERVING→RESOLVED.")
                # Atomic: persist evidence + observations, then REOBSERVING → RESOLVED.
                # This is the ONLY autonomous path to RESOLVED.
                self._trigger_hook("before_commit")
                self.incident_repo.persist_reobservation_and_resolve(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason,
                    new_evidence=all_new_evidence,
                    new_observations=all_new_observations
                )
                inc_control_loop_outcome("resolved")
            else:
                if actuation_state == ActuationState.TIMEOUT_UNKNOWN:
                    # Mutation outcome was ambiguous and re-observation did not confirm convergence.
                    # REOBSERVING has no legal autonomous path back to INVESTIGATING — that
                    # transition is reserved for operator-driven recovery from an escalated state.
                    # Escalate so an operator can confirm the external mutation and re-enqueue.
                    logger.error(f"Outcome UNKNOWN and state did not reconcile for {active_subject}. ESCALATED_CONVERGENCE_FAILED.")
                    self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_CONVERGENCE_FAILED)
                    inc_control_loop_outcome("escalated")
                else:
                    logger.error(f"Actuation succeeded but convergence not established for {active_subject}. ESCALATED_CONVERGENCE_FAILED.")
                    self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_CONVERGENCE_FAILED)
                    inc_control_loop_outcome("escalated")
            
        except (InvestigatorError, OperationalError) as e:
            logger.warning(f"Transient infrastructure error for {active_subject}: {e}. Scheduling retry.")
            r_count = int(record.retry_count) # type: ignore
            if r_count >= 5:
                logger.error(f"Exhausted retries for {active_subject} due to infrastructure errors. Escalating.")
                self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_UNKNOWN)
                observe_incident_lifetime((datetime.now(timezone.utc) - _as_utc(record.created_at)).total_seconds())
                inc_control_loop_outcome("escalated")
            else:
                delay = 30 * (2 ** r_count)
                self.incident_repo.schedule_retry(active_subject, discrepancy_reason, self.worker_id, delay)
                inc_control_loop_outcome("retry_pending")
                
        except Exception as e:
            logger.exception(f"Unexpected programming or deterministic error in _handle_discrepancy for {active_subject}: {e}. Escalating.")
            self.incident_repo.terminate_incident(active_subject, discrepancy_reason, IncidentState.ESCALATED_UNKNOWN)
            observe_incident_lifetime((datetime.now(timezone.utc) - _as_utc(record.created_at)).total_seconds())
            inc_control_loop_outcome("unresolved")
