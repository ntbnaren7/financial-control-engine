import asyncio
import structlog
import pytest
from src.observability.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

async def worker_task(worker_id: str, incident_id: str, sleep_time: float, output_list: list):
    # Bind context for this task
    structlog.contextvars.bind_contextvars(worker_id=worker_id, incident_id=incident_id)
    
    # Simulate some async work
    await asyncio.sleep(sleep_time)
    
    # Get the current context variables
    context = structlog.contextvars.get_contextvars()
    output_list.append(context)

@pytest.mark.asyncio
async def test_contextvars_isolation_between_async_tasks():
    """
    Proves that when multiple async tasks are running concurrently,
    the context variables bound in one task do not leak into another.
    """
    structlog.contextvars.clear_contextvars()
    
    results = []
    
    # Create two tasks that sleep for different amounts of time.
    # If contextvars are not isolated, task 2 might overwrite task 1's context.
    task1 = asyncio.create_task(worker_task("worker_1", "inc_1", 0.2, results))
    task2 = asyncio.create_task(worker_task("worker_2", "inc_2", 0.1, results))
    
    await asyncio.gather(task1, task2)
    
    # Results should contain two dicts with the specific bound values for each task
    # Task 2 finishes first because it sleeps for 0.1s
    assert len(results) == 2
    
    assert results[0]["worker_id"] == "worker_2"
    assert results[0]["incident_id"] == "inc_2"
    
    assert results[1]["worker_id"] == "worker_1"
    assert results[1]["incident_id"] == "inc_1"
    
    # The parent task context should remain empty/unaffected
    parent_context = structlog.contextvars.get_contextvars()
    assert "worker_id" not in parent_context
    assert "incident_id" not in parent_context
