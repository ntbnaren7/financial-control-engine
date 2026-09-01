import asyncio
import os
import sys

# Add project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.evidence.models import Base, ProviderObservation
from src.evidence.db import engine as db_engine, AsyncSessionLocal as session_maker
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.reconciliation.engine import M3Engine
from src.reconciliation.models import ProviderPayment, MerchantOrderState
from src.investigation.config import LLMConfig
from src.investigation.ai import InvestigationEngine
from src.investigation.orchestrator import InvestigationOrchestrator
import uuid

async def main():
    print("Connecting to PostgreSQL DB for pipeline run...")
    
    # We will use a unique order_id for this run so it doesn't conflict with other test data
    test_order_id = f"order_stale_{uuid.uuid4().hex[:8]}"
    
    # 1. Insert some evidence into the DB (simulating real production observations)
    async with session_maker() as session:
        obs1 = ProviderObservation(
            provider="razorpay",
            event_id=f"evt_hook_{uuid.uuid4().hex[:8]}",
            event_type="webhook",
            payload={"order_id": test_order_id}
        )
        # Note: No processing event inserted. This means webhook received, but not processed.
        session.add(obs1)
        await session.commit()
    
    # 2. Receive raw payment and order (The Trigger)
    payment = ProviderPayment(
        payment_id="pay_123",
        order_id=test_order_id,
        amount=5000,
        currency="INR",
        status="captured",
        captured=True,
        observed_at=datetime.now(timezone.utc)
    )
    order = MerchantOrderState(
        merchant_order_id="mo_123",
        razorpay_order_id=test_order_id,
        expected_amount=5000,
        currency="INR",
        status="UNPAID" # Stale order!
    )
    
    print("Running M3 Deterministic Gate...")
    m3 = M3Engine()
    discrepancy = m3.evaluate_reconciliation(payment, order)
    
    if not discrepancy:
        print("No discrepancy found. Pipeline stopped.")
        return
        
    print(f"M3 Discrepancy Found: {discrepancy.description}")
    
    # 3. M4 Investigation Initialization
    config = LLMConfig(
        model_name="phi4-mini:3.8b-q4_K_M",  # Our selected default
        base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434/v1"),
        api_key="ollama",
        temperature=0.0
    )
    
    print("Initializing M4 Investigation Orchestrator...")
    engine = InvestigationEngine(config)
    gatherer = DatabaseEvidenceGatherer(session_maker)
    orchestrator = InvestigationOrchestrator(engine, gatherer)
    
    # 4. Run the full orchestrator
    print("Executing async investigation (Gather -> LLM -> Semantic Check)...")
    result = await orchestrator.investigate(discrepancy)
    
    print("\n" + "="*50)
    print("INVESTIGATION RESULT")
    print("="*50)
    print(f"Status: {result.status.value}")
    
    if result.proposal:
        top = next((s for s in result.proposal.selections if s.rank == 1), None)
        if top:
            print(f"Top Hypothesis: {top.hypothesis_id.value}")
            print(f"Rationale: {top.rationale}")
            
    if result.failure_reason:
        print(f"\nFailure Reason: {result.failure_reason}")
    if result.validation_errors:
        print(f"Validation Errors: {result.validation_errors}")
        
    # Optional cleanup if required by your application context
    await engine.client.close()

if __name__ == "__main__":
    asyncio.run(main())
