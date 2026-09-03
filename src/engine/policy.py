import structlog
from typing import List, Optional
from src.domain.core.models import Observation, Evidence, RecoveryIntent, RecoveryAction, CanonicalStatus

logger = structlog.get_logger()

class ContradictoryEvidenceError(Exception):
    pass

class V2PolicyEvaluator:
    """
    Evaluates verified facts (observations and evidence) to derive an authorized RecoveryIntent.
    Ensures safety by explicitly blocking unsafe combinations (e.g. uncertain provider state -> refund)
    and strictly enforcing subject identity, precedence, and contradiction semantics.
    """
    
    def _select_authoritative_observation(self, observations: List[Observation], provider: str) -> Optional[Observation]:
        """
        Explicit Observation Selection Policy.
        Establishes authoritative freshness based on temporal precedence and detects contradictions.
        """
        provider_obs = [obs for obs in observations if obs.provider == provider]
        if not provider_obs:
            return None
            
        # Temporal Precedence: sort by observed_at descending
        provider_obs.sort(key=lambda o: o.observed_at, reverse=True)
        
        newest = provider_obs[0]
        
        # Contradiction Semantics: If we cannot establish a single, unambiguous current state, fail closed.
        # Here we define ambiguity as multiple observations having the exact same authoritative timestamp
        # but asserting different states.
        for obs in provider_obs[1:]:
            if obs.observed_at == newest.observed_at and obs.canonical_status != newest.canonical_status:
                s1 = newest.canonical_status.value if hasattr(newest.canonical_status, "value") else str(newest.canonical_status)
                s2 = obs.canonical_status.value if hasattr(obs.canonical_status, "value") else str(obs.canonical_status)
                logger.error("Contradictory evidence detected", 
                             provider=provider, 
                             timestamp=newest.observed_at.isoformat(), 
                             state1=s1, 
                             state2=s2)
                raise ContradictoryEvidenceError(f"Simultaneous contradictory claims for {provider} at {newest.observed_at}")
                
        return newest

    def evaluate(self, active_subject: str, discrepancy_reason: str, observations: List[Observation], evidence: List[Evidence], context=None) -> Optional[RecoveryIntent]:
        try:
            merchant_obs = self._select_authoritative_observation(observations, "Merchant")
            provider_obs = self._select_authoritative_observation(observations, "Razorpay")
        except ContradictoryEvidenceError as e:
            return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason=str(e))
            
        if not merchant_obs or not provider_obs:
            logger.warning("Policy evaluation failed: Missing required observations", 
                          has_merchant=bool(merchant_obs), 
                          has_provider=bool(provider_obs))
            return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Missing observations")
            
        # Cross-Subject Binding Validation
        if not merchant_obs.provider_reference or not provider_obs.provider_reference:
            logger.warning("Policy evaluation failed: Missing subject identity (provider_reference)")
            return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Missing subject identity")
            
        # Establish expected references from context
        expected_merchant_ref = None
        expected_provider_ref = None
        
        if context:
            if context.expectation and context.expectation.correlation_keys:
                expected_merchant_ref = context.expectation.correlation_keys.internal_ref
                expected_provider_ref = context.expectation.correlation_keys.provider_ref
                
            # Fallback if expectation didn't provide them
            if not expected_merchant_ref:
                orig_merchant_obs = next((obs for obs in context.observations if obs.provider == "Merchant"), None)
                if orig_merchant_obs:
                    expected_merchant_ref = orig_merchant_obs.provider_reference
            
            if not expected_provider_ref:
                orig_provider_obs = next((obs for obs in context.observations if obs.provider == "Razorpay"), None)
                if orig_provider_obs:
                    expected_provider_ref = orig_provider_obs.provider_reference
        
        # If we STILL don't have expected references, we must fail closed
        if not expected_merchant_ref or not expected_provider_ref:
            logger.warning("Policy evaluation failed: Cannot determine expected subject identity from context")
            return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Cannot establish subject identity from context")
        
        if expected_merchant_ref and merchant_obs.provider_reference != expected_merchant_ref:
            logger.warning("Policy evaluation failed: Merchant evidence contamination",
                           expected=expected_merchant_ref, actual=merchant_obs.provider_reference)
            return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Cross-subject evidence binding failure")

        if expected_provider_ref and provider_obs.provider_reference != expected_provider_ref:
            logger.warning("Policy evaluation failed: Provider evidence contamination",
                           expected=expected_provider_ref, actual=provider_obs.provider_reference)
            return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Cross-subject evidence binding failure")
            
        merchant_status = merchant_obs.canonical_status
        provider_status = provider_obs.canonical_status
        
        is_provider_settled = (provider_status == CanonicalStatus.SETTLED or provider_status == "CAPTURED")
        is_merchant_pending = (merchant_status == CanonicalStatus.PENDING or merchant_status == "UNPAID")

        # Policy: Hero Incident (SETTLED provider + PENDING merchant)
        if is_provider_settled and is_merchant_pending:
            # Safety Check: Verify amounts match
            if provider_obs.observed_amount != merchant_obs.observed_amount:
                logger.info("Policy derived ESCALATE: amount mismatch", 
                            provider_amt=provider_obs.observed_amount, 
                            merchant_amt=merchant_obs.observed_amount)
                return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Amount mismatch")
                
            # If everything checks out, repair the merchant state
            # Set expected_provider_state to enforce atomic Actuator TOCTOU safety
            provider_state_str = provider_status.value if hasattr(provider_status, "value") else str(provider_status)
            logger.info("Policy derived REPAIR_MERCHANT_STATE", target_id=merchant_obs.provider_reference)
            return RecoveryIntent(
                action=RecoveryAction.REPAIR_MERCHANT_STATE,
                target_id=merchant_obs.provider_reference,
                amount=provider_obs.observed_amount,
                currency=provider_obs.currency,
                reason="Provider captured payment but merchant is UNPAID.",
                expected_provider_state=provider_state_str
            )
            
        # Policy: Unknown provider outcome -> ESCALATE
        if provider_status in (CanonicalStatus.UNKNOWN, "UNKNOWN", "TIMEOUT"):
            logger.info("Policy derived ESCALATE: UNKNOWN provider state")
            return RecoveryIntent(
                action=RecoveryAction.ESCALATE,
                target_id=active_subject,
                reason="Cannot act on UNKNOWN provider state."
            )
            
        # Default: ESCALATE (Safe fallback for unhandled discrepancy combinations)
        m_str = merchant_status.value if hasattr(merchant_status, "value") else str(merchant_status)
        p_str = provider_status.value if hasattr(provider_status, "value") else str(provider_status)
        logger.info("Policy derived ESCALATE: Unhandled state combination", 
                    merchant=m_str, 
                    provider=p_str)
        return RecoveryIntent(
            action=RecoveryAction.ESCALATE,
            target_id=active_subject,
            reason=f"Unhandled state combination: Merchant={m_str}, Provider={p_str}"
        )
