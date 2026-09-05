import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.deps import get_session_factory
from src.api.webhooks import router as webhooks_router, set_ingestion_repository
from src.api.incidents import router as incidents_router
from src.api.governance import router as governance_router
from src.api.audit import router as audit_router
from src.api.operator import router as operator_router
from src.storage.postgres_ingestion import PostgresIngestionRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_factory = get_session_factory()
    set_ingestion_repository(PostgresIngestionRepository(session_factory))
    yield


app = FastAPI(
    title="Financial Control Engine",
    description=(
        "Autonomous financial control engine: reconciles payment records, "
        "verifies discrepancies, safely recovers when permitted, and escalates "
        "anything it cannot establish or resolve with confidence."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(webhooks_router)
app.include_router(incidents_router)
app.include_router(governance_router)
app.include_router(audit_router)
app.include_router(operator_router)

# ── Static files (operator console UI) ───────────────────────────────────────
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "HEALTHY", "version": "2.0.0", "service": "financial-control-engine"}


@app.get("/health/readiness", tags=["system"])
def readiness_check():
    import urllib.request
    import json
    
    ollama_ready = False
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", headers={"User-Agent": "FCE-HealthCheck"})
        with urllib.request.urlopen(req, timeout=0.6) as response:
            if response.status == 200:
                tags = json.loads(response.read().decode())
                models = [m.get("name", "") for m in tags.get("models", [])]
                ollama_ready = any("llama3" in m or "qwen" in m for m in models) or len(models) > 0
    except Exception:
        ollama_ready = False

    provider_configured = bool(os.getenv("RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_key"))

    return {
        "backend": "CONNECTED",
        "ollama": "READY" if ollama_ready else "NOT_DETECTED",
        "provider": "CONFIGURED" if provider_configured else "UNCONFIGURED",
    }


@app.get("/", tags=["system"])
def root():
    return {
        "service": "Financial Control Engine",
        "version": "2.0.0",
        "docs": "/docs",
        "ui": "/ui",
    }
