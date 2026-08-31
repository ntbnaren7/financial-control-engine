import os
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from alembic import command
from alembic.config import Config

# 1. Override the database URL to point to an isolated test database BEFORE app imports
original_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/fce_test")
if not original_url.endswith("_pytest"):
    test_db_url = original_url + "_pytest"
    os.environ["DATABASE_URL"] = test_db_url
else:
    test_db_url = original_url
    original_url = test_db_url.replace("_pytest", "")

# Now we can safely import our app modules which will bind to the test_db_url


import subprocess

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create the test database and run migrations before tests."""
    db_name = test_db_url.split("/")[-1]
    
    # Create database using psql (or ignoring if it exists)
    psql_sys_url = original_url.replace("+asyncpg", "")
    subprocess.run(["psql", psql_sys_url, "-c", f"CREATE DATABASE {db_name}"], capture_output=True)
    
    # Run Alembic migrations via subprocess to avoid asyncio loop conflicts
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db_url
    env["PYTHONPATH"] = "src"
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], env=env, check=True)
    
    yield

@pytest.fixture(autouse=True)
def cleanup_db_per_test():
    """Clean tables before each test for test isolation, instead of deleting the DB."""
    tables = ["provider_observations", "merchant_orders"]
    psql_url = test_db_url.replace("+asyncpg", "")
    for table in tables:
        subprocess.run(["psql", psql_url, "-c", f"TRUNCATE TABLE {table} CASCADE"], check=True, capture_output=True)
    yield
