from fastapi import FastAPI
from src.api.webhooks import router as webhooks_router

app = FastAPI(title="Financial Control Engine")

app.include_router(webhooks_router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
