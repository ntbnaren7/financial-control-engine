import structlog
from typing import List, Optional
from src.domain.core.models import Observation, Evidence, RecoveryIntent, RecoveryAction

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
            if obs.observed_at == newest.observed_at and obs.observed_state != newest.observed_state:
                logger.error("Contradictory evidence detected", 
                             provider=provider, 
                             timestamp=newest.observed_at.isoformat(), 
                             state1=newest.observed_state, 
                             state2=obs.observed_state)
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
            
        merchant_state = merchant_obs.observed_state
        provider_state = provider_obs.observed_state
        
        # Policy: Hero Incident (CAPTURED + UNPAID)
        if provider_state == "CAPTURED" and merchant_state == "UNPAID":
            # Safety Check: Verify amounts match
            if provider_obs.observed_amount != merchant_obs.observed_amount:
                logger.info("Policy derived ESCALATE: amount mismatch", 
                            provider_amt=provider_obs.observed_amount, 
                            merchant_amt=merchant_obs.observed_amount)
                return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Amount mismatch")
                
            # If everything checks out, repair the merchant state
            # Set expected_provider_state to enforce atomic Actuator TOCTOU safety
            logger.info("Policy derived REPAIR_MERCHANT_STATE", target_id=merchant_obs.provider_reference)
            return RecoveryIntent(
                action=RecoveryAction.REPAIR_MERCHANT_STATE,
                target_id=merchant_obs.provider_reference,
                amount=provider_obs.observed_amount,
                currency=provider_obs.currency,
                reason="Provider captured payment but merchant is UNPAID.",
                expected_provider_state=provider_state
            )
            
        # Policy: Unknown provider outcome -> ESCALATE
        if provider_state == "UNKNOWN" or provider_state == "TIMEOUT":
            logger.info("Policy derived ESCALATE: UNKNOWN provider state")
            return RecoveryIntent(
                action=RecoveryAction.ESCALATE,
                target_id=active_subject,
                reason="Cannot act on UNKNOWN provider state."
            )
            
        # Default: ESCALATE (Safe fallback for unhandled discrepancy combinations)
        logger.info("Policy derived ESCALATE: Unhandled state combination", 
                    merchant=merchant_state, 
                    provider=provider_state)
        return RecoveryIntent(
            action=RecoveryAction.ESCALATE,
            target_id=active_subject,
            reason=f"Unhandled state combination: Merchant={merchant_state}, Provider={provider_state}"
        )
