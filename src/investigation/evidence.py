from typing import List, Protocol
from src.investigation.models import EvidenceItem
from src.reconciliation.models import VerifiedDiscrepancy

class EvidencePacket:
    """
    A read-only, bounded container of evidence explicitly gathered 
    for a single investigation.
    """
    def __init__(self, items: List[EvidenceItem]):
        self.items = items

class EvidenceGatherer(Protocol):
    """
    Protocol defining how M4 acquires evidence.
    Evidence acquisition is strictly isolated from causal reasoning.
    """
    async def gather(self, discrepancy: VerifiedDiscrepancy) -> EvidencePacket:
        ...

class MockEvidenceGatherer:
    """
    A mock implementation that returns pre-defined evidence.
    """
    def __init__(self, mock_evidence: List[EvidenceItem]):
        self.mock_evidence = mock_evidence
        
    async def gather(self, discrepancy: VerifiedDiscrepancy) -> EvidencePacket:
        return EvidencePacket(items=self.mock_evidence)
