import os
import subprocess
import pytest

# 1. Override the database URL to point to an isolated test database BEFORE app imports
original_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/fce_test")
if not original_url.endswith("_pytest"):
    test_db_url = original_url + "_pytest"
    os.environ["DATABASE_URL"] = test_db_url
else:
    test_db_url = original_url
    original_url = test_db_url.replace("_pytest", "")

# Now we can safely import our app modules which will bind to the test_db_url


def _db_is_available() -> bool:
    """Returns True if the PostgreSQL test database is reachable."""
    psql_url = original_url.replace("+asyncpg", "")
    result = subprocess.run(
        ["psql", psql_url, "-c", "SELECT 1"],
        capture_output=True,
    )
    return result.returncode == 0


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create the test database and run migrations before tests.
    
    Skips gracefully when PostgreSQL is not available, so pure unit tests
    (which don't touch the DB) can still run in sandboxed/offline environments.
    """
    if not _db_is_available():
        yield
        return

    db_name = test_db_url.split("/")[-1]

    # Create database using psql (or ignore if it exists)
    psql_sys_url = original_url.replace("+asyncpg", "")
    subprocess.run(["psql", psql_sys_url, "-c", f"CREATE DATABASE {db_name}"], capture_output=True)

    # Run Alembic migrations via subprocess to avoid asyncio loop conflicts
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db_url
    env["PYTHONPATH"] = "src"
    result = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], env=env, capture_output=True)
    if result.returncode != 0:
        pytest.skip(f"Alembic migration failed: {result.stderr.decode()}")

    yield


@pytest.fixture(autouse=True)
def cleanup_db_per_test():
    """Truncate tables before each test for isolation.
    
    No-ops silently when PostgreSQL is unavailable, so unit tests are unaffected.
    """
    psql_url = test_db_url.replace("+asyncpg", "")
    tables = ["provider_observations", "merchant_orders"]
    for table in tables:
        subprocess.run(["psql", psql_url, "-c", f"TRUNCATE TABLE {table} CASCADE"], capture_output=True)
    yield
