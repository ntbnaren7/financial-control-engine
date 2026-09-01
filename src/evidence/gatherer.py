import uuid
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.evidence.models import ProviderObservation
from src.investigation.evidence import EvidenceGatherer, EvidencePacket
from src.investigation.models import (
    EvidenceItem,
    EvidenceType,
    EvidenceCoverage,
    WebhookCapturedContent,
    ProcessingCoverageContent
)
from src.reconciliation.models import VerifiedDiscrepancy

class DatabaseEvidenceGatherer(EvidenceGatherer):
    """
    Acquires read-only evidence from the database without inferring causality.
    """
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker
        
    async def gather(self, discrepancy: VerifiedDiscrepancy) -> EvidencePacket:
        items: List[EvidenceItem] = []
        
        async with self.session_maker() as session:
            # Query all observations that might belong to this order or payment
            # Using Python-side filtering to avoid SQLite vs PostgreSQL JSON dialect issues 
            # for this simple prototype, but in production we'd use index-backed JSONB queries.
            stmt = select(ProviderObservation)
            result = await session.execute(stmt)
            observations = result.scalars().all()
            
            # Filter for this discrepancy
            relevant_obs = []
            for obs in observations:
                order_id = obs.payload.get("order_id")
                payment_id = obs.payload.get("payment_id")
                
                if order_id == discrepancy.order_id or payment_id == discrepancy.payment_id:
                    relevant_obs.append(obs)
                    
            webhook_present = any(obs.event_type == "webhook" for obs in relevant_obs)
            processing_count = sum(1 for obs in relevant_obs if obs.event_type == "processing")
            
            # 1. Webhook Captured Evidence
            items.append(
                EvidenceItem(
                    id=f"EV-WH-{uuid.uuid4().hex[:8]}",
                    type=EvidenceType.E_WEBHOOK_CAPTURED,
                    content=WebhookCapturedContent(present=webhook_present)
                )
            )
            
            # 2. Processing Coverage Evidence
            # We explicitly define COMPLETE coverage as: 
            # "The database contains the authoritative processing-event stream for this order 
            # and the query covers the complete applicable investigation window."
            # Since we are querying the source of truth table directly for this order, 
            # we assert coverage is COMPLETE.
            items.append(
                EvidenceItem(
                    id=f"EV-PC-{uuid.uuid4().hex[:8]}",
                    type=EvidenceType.E_PROCESSING_COVERAGE,
                    content=ProcessingCoverageContent(
                        coverage=EvidenceCoverage.COMPLETE,
                        processing_count=processing_count
                    )
                )
            )
            
        return EvidencePacket(items=items)
