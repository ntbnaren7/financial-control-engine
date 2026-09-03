import structlog
from src.domain.core.models import RecoveryIntent, RecoveryAction, ActuationOutcome
from src.engine.external_simulator import simulator

logger = structlog.get_logger()

class SimulatedActuator:
    """
    Simulates the execution of a RecoveryIntent against the SimulatedExternalSystem.
    Returns an ActuationOutcome.
    """
    def execute(self, intent: RecoveryIntent) -> ActuationOutcome:
        logger.info(f"SimulatedActuator: Executing {intent.action.value} on {intent.target_id}")
        
        if intent.action == RecoveryAction.REPAIR_MERCHANT_STATE:
            # In our hero incident, the merchant state is UNPAID, and we want to REPAIR it to PAID
            result = simulator.update_merchant_order(intent.target_id, "PAID")
            return ActuationOutcome(result)
            
        elif intent.action == RecoveryAction.REFUND_PAYMENT:
            result = simulator.refund_provider_payment(intent.target_id)
            return ActuationOutcome(result)
            
        elif intent.action == RecoveryAction.ESCALATE:
            logger.info("SimulatedActuator: Escalate intent, no external mutation.")
            return ActuationOutcome.SUCCESS
            
        logger.error(f"SimulatedActuator: Unsupported action {intent.action}")
        return ActuationOutcome.REJECTED
