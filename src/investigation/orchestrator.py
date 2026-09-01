from src.reconciliation.models import VerifiedDiscrepancy
from src.investigation.evidence import EvidenceGatherer
from src.investigation.ai import InvestigationEngine
from src.investigation.models import DiscrepancyContext
from src.investigation.result import InvestigationResult

class InvestigationOrchestrator:
    """
    Workflow coordinator for M4 investigations.
    Coordinates evidence gathering and LLM inference.
    Does not interpret results or perform state mutations.
    """
    def __init__(self, engine: InvestigationEngine, gatherer: EvidenceGatherer):
        self.engine = engine
        self.gatherer = gatherer
        
    async def investigate(self, discrepancy: VerifiedDiscrepancy) -> InvestigationResult:
        # 1. Gather bounded evidence
        evidence_packet = await self.gatherer.gather(discrepancy)
        
        # 2. Map verified discrepancy into M4 context
        context = DiscrepancyContext(
            case_id=discrepancy.discrepancy_id,
            description=discrepancy.description,
            provider_status=discrepancy.provider_status,
            merchant_status=discrepancy.merchant_status,
            amount_match=discrepancy.amount_match,
            currency_match=discrepancy.currency_match,
            identity_verified=discrepancy.identity_verified
        )
        
        # 3. Call InvestigationEngine
        result = await self.engine.investigate(context, evidence_packet.items)
        
        return result
