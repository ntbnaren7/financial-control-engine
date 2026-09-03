from fastapi import FastAPI
from src.api.webhooks import router as webhooks_router

app = FastAPI(title="Financial Control Engine API", version="2.0.0")

app.include_router(webhooks_router)


@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "version": "2.0.0"}
