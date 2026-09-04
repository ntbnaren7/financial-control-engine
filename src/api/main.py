from fastapi import FastAPI
from src.api.webhooks import router as webhooks_router

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.storage.postgres_ingestion import PostgresIngestionRepository
from src.api.webhooks import set_ingestion_repository

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required for production durability")
        
    engine = create_engine(db_url)
    session_factory = sessionmaker(bind=engine, autoflush=True, expire_on_commit=True)
    set_ingestion_repository(PostgresIngestionRepository(session_factory))
    yield

app = FastAPI(title="Financial Control Engine API", version="2.0.0", lifespan=lifespan)

app.include_router(webhooks_router)


@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "version": "2.0.0"}
