import asyncio
import uuid
import structlog
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone

from src.storage.postgres_substrate import (
    PostgresControlEventRepository,
    PostgresActiveIncidentRepository,
    PostgresObservationRepository,
    PostgresEvidenceRepository,
    PostgresExpectationRepository,
    PostgresReconciliationResultRepository,
    ControlEventType,
    InvestigationState
)
from src.domain.investigation.models import VerificationStatus, ValidationRejection, CausalHypothesis
from src.domain.core.models import RecoveryAction, ReconciliationOutcome
from src.engine.evidence_assembler import EvidenceAssembler
from src.engine.policy import V2PolicyEvaluator
from src.engine.actuator import SimulatedActuator
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
        reconciliation_engine: V2ReconciliationEngine,
        assembler: EvidenceAssembler,
        investigator: Investigator,
        validator: OutputValidator,
        verifier: DeterministicVerifier,
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
        self.reconciliation_engine = reconciliation_engine
        self.assembler = assembler
        self.investigator = investigator
        self.validator = validator
        self.verifier = verifier
        self.policy = V2PolicyEvaluator()
        self.actuator = SimulatedActuator()
        self.observer = SimulatedObserver()
        self.settings = settings
        self.test_hooks = test_hooks or {}

    def _trigger_hook(self, name: str):
        if name in self.test_hooks:
            self.test_hooks[name]()

    async def poll_and_process(self, limit: int = 5):
        # Start Prometheus metrics server once (idempotent — OSError means already running)
        if not getattr(self, "_metrics_server_started", False):
            try:
                from prometheus_client import start_http_server
                start_http_server(8000)
                logger.info("Prometheus metrics server started on port 8000")
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
                if event.event_type == ControlEventType.OBSERVATION_INGESTED:
                    await self._handle_observation_ingested()
                elif event.event_type == ControlEventType.DISCREPANCY_DETECTED:
                    await self._handle_discrepancy(event.payload)
                
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

    async def _handle_observation_ingested(self):
        # A1: Detect
        results = self.reconciliation_engine.reconcile_batch()
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

        structlog.contextvars.bind_contextvars(
            reconciliation_id=reconciliation_id,
            active_subject=active_subject,
            incident_id=record.incident_id
        )
        logger.info("Lease acquired, starting investigation")
        self._trigger_hook("after_lease_acquire")

        # 3. Stale-event guard: re-evaluate current state before committing to investigation.
        # If a concurrent worker already resolved this discrepancy (e.g., the observation
        # now matches the expectation), this event is stale and should be dropped.
        if recon_result.expectation_id:
            from src.engine.reconciliation_controls import evaluate_expectation_centric
            current_obs = self.observation_repo.find_by_correlation_keys(recon_result.expectation.correlation_keys) if hasattr(recon_result, "expectation") else []
            if not current_obs and recon_result.expectation_id:
                exp = self.exp_repo.get(recon_result.expectation_id)
                if exp:
                    current_obs = self.observation_repo.find_by_correlation_keys(exp.correlation_keys)
                    fresh_result = evaluate_expectation_centric(exp, current_obs)
                    if fresh_result.outcome == ReconciliationOutcome.MATCH:
                        from src.observability.metrics import (
                            inc_stale_event_dropped,
                            observe_cycle_resolution_latency,
                            observe_incident_lifetime
                        )
                        inc_stale_event_dropped()
                        elapsed = (datetime.now(timezone.utc) - recon_result.created_at).total_seconds()
                        observe_cycle_resolution_latency(elapsed)
                        observe_incident_lifetime((datetime.now(timezone.utc) - record.created_at).total_seconds())

                        logger.info(f"Stale DISCREPANCY event for {active_subject} — current state is MATCH. Releasing incident.")
                        self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=False)
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
            if record.state == InvestigationState.VERIFYING and record.hypothesis_payload:
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
                    logger.warning(f"Hypothesis rejected: {validation_result.reason}")
                    self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
                    observe_incident_lifetime((datetime.now(timezone.utc) - record.created_at).total_seconds())
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
                        self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
                        observe_incident_lifetime((datetime.now(timezone.utc) - record.created_at).total_seconds())
                        inc_control_loop_outcome("escalated")
                    else:
                        delay = 30 * (2 ** r_count)
                        self._trigger_hook("before_retry")
                        self.incident_repo.schedule_retry(active_subject, discrepancy_reason, self.worker_id, delay)
                        inc_control_loop_outcome("retry_pending")
                    return # Stop processing further intents on this pass

                elif v_res.status == VerificationStatus.REJECTED:
                    logger.error(f"Verification REJECTED for {active_subject}: {v_res.failure_reason}. Escalating.")
                    self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
                    observe_incident_lifetime((datetime.now(timezone.utc) - record.created_at).total_seconds())
                    inc_control_loop_outcome("escalated")
                    return
                    
                elif v_res.status == VerificationStatus.SUCCEEDED:
                    logger.info(f"Verification SUCCEEDED for {active_subject}. Staging new evidence for atomic commit.")
                    all_new_evidence.extend(v_res.new_evidence)
                    all_new_observations.extend(v_res.new_observations)
                        
            # DECIDE: Evaluate Policy
            logger.info("Evaluating Policy to derive RecoveryIntent")
            combined_observations = context.observations + all_new_observations
            combined_evidence = context.evidence_records + all_new_evidence
            
            intent = self.policy.evaluate(active_subject, discrepancy_reason, combined_observations, combined_evidence)
            
            if intent is None or intent.action == RecoveryAction.ESCALATE:
                logger.info(f"Policy derived ESCALATE for {active_subject}: {intent.reason if intent else 'No safe intent could be derived'}")
                self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
                inc_control_loop_outcome("escalated")
                return
                
            # ACT: Simulated Actuator
            logger.info(f"Executing ACT: {intent.action.value} on {intent.target_id}")
            from src.domain.core.models import ActuationOutcome
            actuation_outcome = self.actuator.execute(intent)
            
            if actuation_outcome == ActuationOutcome.REJECTED:
                logger.error(f"Actuation REJECTED for {active_subject}. Escalating.")
                self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
                inc_control_loop_outcome("escalated")
                return
                
            if actuation_outcome == ActuationOutcome.TIMEOUT_UNKNOWN:
                logger.warning(f"Actuation TIMEOUT_UNKNOWN for {active_subject}. Will observe independently.")
                
            # OBSERVE AGAIN: Re-read state
            logger.info(f"OBSERVE AGAIN: Reading final state from simulated external systems")
            
            if intent.action == RecoveryAction.REPAIR_MERCHANT_STATE:
                final_obs = self.observer.observe_merchant_order(intent.target_id)
                if final_obs:
                    all_new_observations.append(final_obs)
            elif intent.action == RecoveryAction.REFUND_PAYMENT:
                final_obs = self.observer.observe_provider_payment(intent.target_id)
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
                logger.info(f"Final Outcome is MATCH. Resolving incident {active_subject}.")
                # Atomic Persistence: Save Evidence, Upsert Observations, Release Incident
                self._trigger_hook("before_commit")
                self.incident_repo.commit_verification_success(
                    active_subject=active_subject,
                    discrepancy_reason=discrepancy_reason,
                    new_evidence=all_new_evidence,
                    new_observations=all_new_observations
                )
                inc_control_loop_outcome("resolved")
            else:
                if actuation_outcome == ActuationOutcome.TIMEOUT_UNKNOWN:
                    logger.warning(f"Outcome UNKNOWN and state did not reconcile for {active_subject}. Scheduling retry.")
                    r_count = int(record.retry_count) # type: ignore
                    delay = 30 * (2 ** r_count)
                    self.incident_repo.schedule_retry(active_subject, discrepancy_reason, self.worker_id, delay)
                    inc_control_loop_outcome("retry_pending")
                else:
                    logger.error(f"Actuation {actuation_outcome.value} but final state is DISCREPANCY for {active_subject}. Escalating.")
                    self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
                    inc_control_loop_outcome("escalated")
            
            observe_investigation_latency(time.monotonic() - investigation_start_time)
            observe_incident_lifetime((datetime.now(timezone.utc) - record.created_at).total_seconds())
            inc_control_loop_outcome("resolved")
            
        except (InvestigatorError, OperationalError) as e:
            logger.warning(f"Transient infrastructure error for {active_subject}: {e}. Scheduling retry.")
            r_count = int(record.retry_count) # type: ignore
            if r_count >= 5:
                logger.error(f"Exhausted retries for {active_subject} due to infrastructure errors. Escalating.")
                self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
                observe_incident_lifetime((datetime.now(timezone.utc) - record.created_at).total_seconds())
                inc_control_loop_outcome("escalated")
            else:
                delay = 30 * (2 ** r_count)
                self.incident_repo.schedule_retry(active_subject, discrepancy_reason, self.worker_id, delay)
                inc_control_loop_outcome("retry_pending")
                
        except Exception as e:
            logger.exception(f"Unexpected programming or deterministic error in _handle_discrepancy for {active_subject}: {e}. Escalating.")
            self.incident_repo.release_incident(active_subject, discrepancy_reason, escalate=True)
            observe_incident_lifetime((datetime.now(timezone.utc) - record.created_at).total_seconds())
            inc_control_loop_outcome("unresolved")
