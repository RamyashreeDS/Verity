import asyncio
import time
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models import DashboardResponse, WorldStateStatus
from app.stages import world_state

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _sync_generate_image(prompt: str, api_key: str) -> str:
    from black_forest_labs import Client
    from black_forest_labs.client import Status

    client = Client(api_key=api_key)
    task = client.generate("flux-pro-1.1", prompt=prompt, width=1024, height=768)

    deadline = time.time() + 90
    while time.time() < deadline:
        task = client.get_result(task)
        if task.is_done:
            break
        time.sleep(2)

    if task.status != Status.READY or not task.result:
        raise ValueError(f"Image generation failed with status: {task.status}")

    return task.result.sample


@router.get("")
async def get_dashboard():
    entries = await world_state.get_dashboard()
    last_updated = max((e.last_updated for e in entries), default=None)
    return DashboardResponse(entries=entries, last_updated=last_updated)


@router.get("/entity/{entity}")
async def get_entity(entity: str):
    entries = await world_state.get_dashboard()
    matched = [e for e in entries if e.entity.lower() == entity.lower()]
    if not matched:
        raise HTTPException(status_code=404, detail=f"Entity '{entity}' not found")
    return matched


@router.get("/entity/{entity}/history")
async def get_entity_history(entity: str):
    history = await world_state.get_entity_history(entity)
    return {"entity": entity, "claims": history}


@router.get("/conflicted")
async def get_conflicted():
    entries = await world_state.get_conflicted_entries()
    return {"entries": entries, "count": len(entries)}


@router.get("/by-status/{status}")
async def get_by_status(status: WorldStateStatus):
    entries = await world_state.get_dashboard()
    matched = [e for e in entries if e.status == status]
    return {"entries": matched, "count": len(matched)}


@router.get("/visual")
async def generate_visual(crisis_query_id: str = ""):
    if not settings.bfl_api_key:
        raise HTTPException(status_code=503, detail="BFL_API_KEY not configured")

    entries = await world_state.get_dashboard()
    state_summary = "; ".join(
        f"{e.entity} {e.claim_type}: {e.current_value} ({e.status.value})"
        for e in entries[:15]
    )

    prompt = (
        "A real-time crisis monitoring map visualization. "
        f"Current situation: {state_summary}. "
        "Style: clean data visualization, dark background, color-coded status indicators, "
        "emergency response aesthetic, satellite map overlay."
    )

    try:
        image_url = await asyncio.to_thread(_sync_generate_image, prompt, settings.bfl_api_key)
        return {"image_url": image_url, "prompt": prompt}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image generation failed: {str(e)}")
