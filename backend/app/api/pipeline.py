from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models import (
    StartPipelineRequest,
    PipelineRun,
    PipelineRunStatus,
    PipelineStageResult,
    CrisisQuery,
)
from app.stages import sense, understand, validate, world_state, health_monitor, healing_loop

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

_runs: dict[str, PipelineRun] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _update_stage(run: PipelineRun, stage: str, status: str, count: int = 0, detail: str = "") -> None:
    for s in run.stages:
        if s.stage == stage:
            s.status = status
            s.count = count
            s.detail = detail
            if status == "running":
                s.started_at = _now()
            elif status in ("done", "failed"):
                s.completed_at = _now()
            return
    run.stages.append(
        PipelineStageResult(
            stage=stage,
            status=status,
            count=count,
            detail=detail,
            started_at=_now() if status == "running" else None,
            completed_at=_now() if status in ("done", "failed") else None,
        )
    )


async def _run_pipeline(run_id: str, query: CrisisQuery) -> None:
    run = _runs[run_id]
    run.status = PipelineRunStatus.running
    crisis_context = f"{query.event_type.value} in {query.location}"

    try:
        # Stage 1 — Sense
        _update_stage(run, "sense", "running")
        documents = await sense.run(query)
        _update_stage(run, "sense", "done", count=len(documents))

        if not documents:
            run.status = PipelineRunStatus.completed
            run.completed_at = _now()
            return

        # Stage 2 — Understand
        _update_stage(run, "understand", "running")
        claims = await understand.run(documents, crisis_context)
        _update_stage(run, "understand", "done", count=len(claims))

        # Stage 3 — Validate
        _update_stage(run, "validate", "running")
        validated, rejected = validate.run(claims)
        _update_stage(
            run, "validate", "done",
            count=len(validated),
            detail=f"{len(rejected)} rejected",
        )

        # Stage 4 — World State
        _update_stage(run, "world_state", "running")
        entries = await world_state.ingest_claims(validated)
        _update_stage(run, "world_state", "done", count=len(entries))

        # Stage 5 — Health Monitor
        _update_stage(run, "health_monitor", "running")
        all_entries = await world_state.get_dashboard()
        health_events = await health_monitor.run(all_entries, query.event_type.value)
        _update_stage(run, "health_monitor", "done", count=len(health_events))

        # Stage 6 — Healing Loop
        if health_events:
            _update_stage(run, "healing_loop", "running")
            records = await healing_loop.run(health_events)
            committed = sum(1 for r in records if r.committed)
            _update_stage(run, "healing_loop", "done", count=committed, detail=f"{len(records)} events processed")
        else:
            _update_stage(run, "healing_loop", "done", count=0, detail="no health events")

        run.status = PipelineRunStatus.completed
        run.completed_at = _now()

    except Exception as e:
        run.status = PipelineRunStatus.failed
        run.error = str(e)
        run.completed_at = _now()


@router.post("/run")
async def start_pipeline(request: StartPipelineRequest, background_tasks: BackgroundTasks):
    query = CrisisQuery(
        event_type=request.event_type,
        location=request.location,
        radius_km=request.radius_km,
        time_window_hours=request.time_window_hours,
        keywords=request.keywords,
    )
    run = PipelineRun(query=query)
    _runs[run.id] = run
    background_tasks.add_task(_run_pipeline, run.id, query)
    return {"run_id": run.id, "status": run.status}


@router.get("/run/{run_id}")
async def get_run(run_id: str):
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs")
async def list_runs():
    return list(_runs.values())
