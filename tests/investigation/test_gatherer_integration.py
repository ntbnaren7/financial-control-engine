import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.evidence.models import Base, ProviderObservation
from src.evidence.gatherer import DatabaseEvidenceGatherer
from src.investigation.models import EvidenceType, WebhookCapturedContent, ProcessingCoverageContent
from src.reconciliation.models import VerifiedDiscrepancy

try:
    from testcontainers.postgres import PostgresContainer
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False

@pytest.fixture(scope="module")
def postgres_container():
    if not HAS_TESTCONTAINERS:
        pytest.skip("testcontainers not installed")
        
    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres.get_connection_url(driver="asyncpg")

@pytest.fixture
async def db_session_maker(postgres_container):
    engine = create_async_engine(postgres_container, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    yield session_maker
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_gatherer_with_postgresql(db_session_maker):
    discrepancy = VerifiedDiscrepancy(
        discrepancy_id="disc_1",
        payment_id="pay_123",
        order_id="ord_123",
        description="test",
        provider_status="captured",
        merchant_status="UNPAID",
        amount_match=True,
        currency_match=True,
        identity_verified=True
    )
    
    # Insert some data
    async with db_session_maker() as session:
        obs1 = ProviderObservation(
            provider="razorpay",
            event_id="evt_1",
            event_type="webhook",
            payload={"order_id": "ord_123"}
        )
        obs2 = ProviderObservation(
            provider="razorpay",
            event_id="evt_2",
            event_type="processing",
            payload={"order_id": "ord_123"}
        )
        
        session.add_all([obs1, obs2])
        await session.commit()
        
    gatherer = DatabaseEvidenceGatherer(db_session_maker)
    packet = await gatherer.gather(discrepancy)
    
    assert len(packet.items) == 2
    
    webhook_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_WEBHOOK_CAPTURED)
    processing_ev = next(ev for ev in packet.items if ev.type == EvidenceType.E_PROCESSING_COVERAGE)
    
    assert webhook_ev.content.present is True
    assert processing_ev.content.coverage == "COMPLETE"
    assert processing_ev.content.processing_count == 1
