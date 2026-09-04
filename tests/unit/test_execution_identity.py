import uuid
from src.engine.execution_identity import ExecutionIdentity

def test_execution_identity_deterministic():
    seed = "test-idempotency-key-123"
    id1 = ExecutionIdentity.generate(idempotency_seed=seed)
    id2 = ExecutionIdentity.generate(idempotency_seed=seed)
    assert id1 == id2
    assert uuid.UUID(id1).version == 5

def test_execution_identity_random():
    id1 = ExecutionIdentity.generate()
    id2 = ExecutionIdentity.generate()
    assert id1 != id2
    assert uuid.UUID(id1).version == 4
