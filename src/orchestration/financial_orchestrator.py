from typing import List, Dict, Any, Tuple
from datetime import datetime, timezone
from decimal import Decimal

from src.domain.evidence.models import Evidence
from src.domain.evidence.normalization import InternalRefundIntentNormalizer, RazorpayWebhookNormalizer, RazorpayApiNormalizer
from src.storage.repository import EvidenceRepository, CorrelationRepository, CaseRepository
from src.domain.correlation.engine import DeterministicCorrelationEngine
from src.domain.cases.models import ReconciliationCase
from src.domain.cases.derivation import derive_expectation, derive_observations
from src.state.engine import StateEngine, TemporalOrderingPolicy
from src.reconciliation.engine import reconcile
from src.evidence.models import EntityType

class FinancialControlOrchestrator:
    def __init__(
        self,
        evidence_repo: EvidenceRepository,
        state_engine: StateEngine
    ):
        self.evidence_repo = evidence_repo
        self.state_engine = state_engine
        self.correlation_engine = DeterministicCorrelationEngine()
        
        self.normalizers = {
            "internal_oms": InternalRefundIntentNormalizer(),
            "razorpay_webhook": RazorpayWebhookNormalizer(),
            "razorpay_api": RazorpayApiNormalizer(),
        }

    def ingest_and_generate_cases(
        self, 
        raw_records: List[Tuple[str, Dict[str, Any]]] # (source, payload)
    ) -> List[ReconciliationCase]:
        """
        Takes raw heterogeneous records and produces fully classified ReconciliationCases.
        """
        # 1. Normalize & Persist Evidence
        evidences = []
        for source, payload in raw_records:
            normalizer = self.normalizers.get(source)
            if not normalizer:
                continue
                
            evidence = normalizer.normalize(payload, provenance={"batch_ingestion": True})
            self.evidence_repo.save(evidence)
            evidences.append(evidence)
            
        # Separate internal intents from provider records
        internal_intents = [e for e in evidences if e.evidence_type == "REFUND_INTENT"]
        provider_records = [e for e in evidences if "RAZORPAY" in e.evidence_type]
        
        # 2. Deterministic Correlation
        contexts = self.correlation_engine.correlate_refund(internal_intents, provider_records)
        
        cases = []
        
        # 3. Case Generation & V1 Classification
        for ctx in contexts:
            # Derive Expectation & Observations
            expectation = derive_expectation(ctx)
            observations = derive_observations(ctx)
            
            # Base Case (Inputs only)
            case = ReconciliationCase(
                correlation_context=ctx,
                expectation=expectation,
                provider_observations=observations,
                provenance={"generated_by": "FinancialControlOrchestrator"}
            )
            
            reconciliation_timestamp = datetime.now(timezone.utc)
            
            # Reconstruct State (Even for orphans, state engine can handle it if we fallback the entity_id)
            entity_id = expectation.refund_intent_id if expectation else (observations[0].entity_id if observations else "UNKNOWN")
            
            ordering_policy_val = getattr(self.state_engine, 'ordering_policy', None)
            ordering_policy: TemporalOrderingPolicy = ordering_policy_val if ordering_policy_val is not None else TemporalOrderingPolicy()

            reconstructed_state = self.state_engine.reconstruct_state(
                entity_type=EntityType.REFUND_INTENT,
                entity_id=entity_id,
                observations=observations,
                reconstructed_at=reconciliation_timestamp,
                ordering_policy=ordering_policy
            )
            
            # Derive observed metrics for V1
            observed_amount = None
            observed_currency = None
            
            correlated_provider_results = [r for r in ctx.results if r.is_correlated() and r.provider_evidence]
            if correlated_provider_results:
                # Use the latest correlated evidence payload
                latest_ev = sorted(correlated_provider_results, key=lambda x: x.provider_evidence.timestamp if x.provider_evidence else datetime.min.replace(tzinfo=timezone.utc))[-1].provider_evidence
                
                if latest_ev and latest_ev.source == "razorpay_webhook":
                    entity = latest_ev.payload.get("payload", {}).get("refund", {}).get("entity", {})
                    amount_paise = entity.get("amount")
                    if amount_paise is not None:
                        observed_amount = Decimal(str(amount_paise)) / Decimal("100")
                    observed_currency = entity.get("currency")
                elif latest_ev and latest_ev.source == "razorpay_api":
                    amount_paise = latest_ev.payload.get("amount")
                    if amount_paise is not None:
                        observed_amount = Decimal(str(amount_paise)) / Decimal("100")
                    observed_currency = latest_ev.payload.get("currency")
            elif not expectation and observations:
                # Orphaned scenario: pull from the first observation
                payload = observations[0].payload if observations[0].payload else {}
                if "payload" in payload and "refund" in payload["payload"]: # Webhook
                    entity = payload["payload"]["refund"]["entity"]
                    amount_paise = entity.get("amount")
                    if amount_paise is not None:
                        observed_amount = Decimal(str(amount_paise)) / Decimal("100")
                    observed_currency = entity.get("currency")
                else: # API
                    amount_paise = payload.get("amount")
                    if amount_paise is not None:
                        observed_amount = Decimal(str(amount_paise)) / Decimal("100")
                    observed_currency = payload.get("currency")

            # Determine executions count
            # Here we count unique provider payments/refunds if they correspond to execution.
            # In our simple model, we assume each record is a distinct effect unless they share the same provider ID.
            # Let's count unique provider IDs among the correlated provider records that are EXECUTED
            executions = set()
            for rec in ctx.provider_records:
                # Simplified check for execution
                if "PROCESSED" in rec.evidence_type or "CREATED" in rec.evidence_type:
                    executions.add(rec.entity_id)
            matching_executions_count = len(executions) if executions else 1 # Default to 1 to avoid EXCESS_EFFECT if not applicable

            # If expectation is None, V1 reconcile natively supports it now and yields ORPHANED_EXECUTION!
            result = reconcile(
                expectation=expectation,
                reconstructed_state=reconstructed_state,
                reconciliation_timestamp=reconciliation_timestamp,
                observed_amount=observed_amount,
                observed_currency=observed_currency,
                matching_executions_count=matching_executions_count
            )
            
            final_case = case.attach_derivatives(state=reconstructed_state, result=result)
            cases.append(final_case)
            
        return cases
