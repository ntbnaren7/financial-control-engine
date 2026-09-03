from src.reconciliation.models import ReconciliationResult, DiscrepancyType

class DiscrepancyRouter:
    @staticmethod
    def is_actionable_discrepancy(result: ReconciliationResult) -> bool:
        """
        Explicit business policy defining which reconciliation results 
        should be routed as actionable discrepancies.
        """
        # MATCH and IN_FLIGHT_PENDING are ignored (normal operation)
        if result.discrepancy_type in (DiscrepancyType.MATCH, DiscrepancyType.IN_FLIGHT_PENDING):
            return False
            
        # Everything else is a discrepancy (VALUE_MISMATCH, ABSENT_EXECUTION, 
        # ORPHANED_EXECUTION, EXCESS_EFFECT, EPISTEMIC_STALEMATE, etc.)
        return True
