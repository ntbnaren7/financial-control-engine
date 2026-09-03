import structlog
from typing import List, Optional
from src.domain.core.models import Observation, Evidence, RecoveryIntent, RecoveryAction

logger = structlog.get_logger()

class V2PolicyEvaluator:
    """
    Evaluates verified facts (observations and evidence) to derive an authorized RecoveryIntent.
    Ensures safety by explicitly blocking unsafe combinations (e.g. uncertain provider state -> refund).
    """
    def evaluate(self, active_subject: str, discrepancy_reason: str, observations: List[Observation], evidence: List[Evidence]) -> Optional[RecoveryIntent]:
        # Identify merchant and provider states
        merchant_obs = next((obs for obs in observations if obs.provider == "Merchant"), None)
        provider_obs = next((obs for obs in observations if obs.provider == "Razorpay"), None)
        
        if not merchant_obs or not provider_obs:
            logger.warning("Policy evaluation failed: Missing required observations", 
                          has_merchant=bool(merchant_obs), 
                          has_provider=bool(provider_obs))
            return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Missing observations")
            
        merchant_state = merchant_obs.observed_state
        provider_state = provider_obs.observed_state
        
        # Policy: Hero Incident (CAPTURED + UNPAID)
        if provider_state == "CAPTURED" and merchant_state == "UNPAID":
            # Safety Check: Verify amounts match (we don't repair if there is an amount mismatch)
            if provider_obs.observed_amount != merchant_obs.observed_amount:
                logger.info("Policy derived ESCALATE: amount mismatch", 
                            provider_amt=provider_obs.observed_amount, 
                            merchant_amt=merchant_obs.observed_amount)
                return RecoveryIntent(action=RecoveryAction.ESCALATE, target_id=active_subject, reason="Amount mismatch")
                
            # If everything checks out, repair the merchant state
            logger.info("Policy derived REPAIR_MERCHANT_STATE", target_id=merchant_obs.provider_reference)
            return RecoveryIntent(
                action=RecoveryAction.REPAIR_MERCHANT_STATE,
                target_id=merchant_obs.provider_reference,
                amount=provider_obs.observed_amount,
                currency=provider_obs.currency,
                reason="Provider captured payment but merchant is UNPAID."
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
