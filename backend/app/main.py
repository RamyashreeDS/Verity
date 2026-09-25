from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import pipeline, dashboard, health

app = FastAPI(title="Verity", description="Self-healing crisis information pipeline", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router)
app.include_router(dashboard.router)
app.include_router(health.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "Verity"}


@app.get("/api/status")
async def api_status():
    from app.config import settings
    return {
        "nimble": bool(settings.nimble_api_key),
        "liquid_ai": bool(settings.liquid_ai_api_key),
        "tinybird": bool(settings.tinybird_api_key),
        "bfl": bool(settings.bfl_api_key),
    }
