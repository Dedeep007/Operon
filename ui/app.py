"""Local operations dashboard with durable reports and reconnectable event streams."""

import asyncio
import json
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, field_validator
from operon.config import settings
from operon.environment.erp_system import default_erp
from operon.llm import llm_provider
from operon.runs import RunManager, RunBusyError, TERMINAL
from operon.tools.registry import registry
from operon.workflows import SUPPORTED_TOOLS
from operon.conversation import chat_reply


@asynccontextmanager
async def lifespan(app):
    app.state.runs = RunManager(settings.storage_dir / "runs.sqlite3")
    yield
    await asyncio.to_thread(app.state.runs.close)


app = FastAPI(title="Operon Task Workspace", version="0.2.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)
    mode: Literal["execute", "preview"] = "execute"

    @field_validator("task")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Please enter a task.")
        return value.strip()


class ApprovalRequest(BaseModel):
    approval_id: str = Field(min_length=1)
    approved: StrictBool


class ChatRequest(TaskRequest):
    context_run_id: str | None = Field(default=None, max_length=200)


def manager(request):
    return request.app.state.runs


def find_run(request, run_id):
    try:
        return manager(request).store.get(run_id)
    except KeyError:
        raise HTTPException(404, "Run not found.")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "style.css"):
        revision = hashlib.sha256((STATIC_DIR / name).read_bytes()).hexdigest()[:12]
        page = page.replace(f"/static/{name}", f"/static/{name}?v={revision}")
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


@app.get("/api/info")
def info():
    return {"model_name": llm_provider.model_name, "is_live_groq": llm_provider.is_live,
            "max_retries": settings.max_retries, "tools_count": len(SUPPORTED_TOOLS),
            "approval_threshold": 25000, "environment": "Simulated company ERP"}


@app.get("/api/tools")
def tools():
    return [t.model_dump() for t in registry.list_definitions() if t.name in SUPPORTED_TOOLS]


@app.get("/api/erp/state")
def erp_state():
    return default_erp.get_state_snapshot()


@app.post("/api/erp/reset")
def reset(request: Request):
    try:
        return {"state": manager(request).reset_erp()}
    except RunBusyError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/runs", status_code=202)
def create_run(req: TaskRequest, request: Request):
    try:
        return manager(request).start(req.task, req.mode)
    except RunBusyError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    previous = find_run(request, req.context_run_id) if req.context_run_id else None
    response = chat_reply(req.task, previous)
    if response["kind"] == "reply":
        return response
    if response["kind"] == "decision":
        if req.mode == "preview":
            return {"kind": "reply", "reply": "This action is waiting in an actual run. Use Send or the approval buttons to approve or decline it; preview does not authorize execution."}
        try:
            run = manager(request).decide(previous["id"], previous["approval"]["approval_id"], response["approved"])
        except ValueError as exc:
            raise HTTPException(409, str(exc))
    else:
        mode = "preview" if req.mode == "preview" else response.get("mode", req.mode)
        run = create_run(TaskRequest(task=response["task"], mode=mode), request)
    return {"kind": "run", "run": run}


@app.get("/api/runs")
def list_runs(request: Request, limit: int = Query(30, ge=1, le=100)):
    return manager(request).store.list(limit)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, request: Request):
    return find_run(request, run_id)


@app.post("/api/runs/{run_id}/approval", status_code=202)
def approve(run_id: str, req: ApprovalRequest, request: Request):
    find_run(request, run_id)
    try:
        return manager(request).decide(run_id, req.approval_id, req.approved)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/runs/{run_id}/evidence")
def download_evidence(run_id: str, request: Request):
    packet = find_run(request, run_id)["packet"]
    if not packet:
        raise HTTPException(409, "Evidence is available after the run finishes.")
    return JSONResponse(packet, headers={"Content-Disposition": f'attachment; filename="{run_id}-evidence.json"'})


@app.get("/api/runs/{run_id}/sources/{source_index}")
def view_source(run_id: str, source_index: int, request: Request):
    packet = find_run(request, run_id)["packet"]
    sources = (packet or {}).get("source_documents", [])
    if source_index < 0 or source_index >= len(sources):
        raise HTTPException(404, "This task has no source at that position.")
    source = sources[source_index]
    path = Path(source["file_path"]).resolve()
    if not path.is_relative_to(settings.sample_data_dir.resolve()):
        raise HTTPException(403, "Only company sandbox sources can be opened here.")
    try:
        content = path.read_bytes()
    except OSError:
        raise HTTPException(404, "The captured source is no longer available. Check its location before retrying.")
    if hashlib.sha256(content).hexdigest() != source["sha256"]:
        raise HTTPException(409, "This source changed after the task. Run the task again to capture and verify its current version.")
    return Response(content, media_type="text/plain", headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request, after: int = Query(0, ge=0)):
    find_run(request, run_id)
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(400, "Invalid event cursor.")

    async def generate():
        nonlocal cursor
        heartbeat = 0
        while not await request.is_disconnected():
            batch = await asyncio.to_thread(manager(request).store.events, run_id, cursor)
            for payload in batch:
                cursor = payload["seq"]
                yield f"id: {cursor}\ndata: {json.dumps(payload)}\n\n"
            if len(batch) < 100 and manager(request).store.get(run_id)["status"] in TERMINAL:
                # Re-read once: terminal status can be written just before its final event.
                if not manager(request).store.events(run_id, cursor):
                    return
                continue
            heartbeat += 1
            if heartbeat % 50 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/run")
def run_sync(req: TaskRequest, request: Request):
    run = create_run(req, request)
    manager(request).wait_segment()
    result = find_run(request, run["id"])
    return JSONResponse(result["packet"] or result, status_code=202 if result["status"] == "waiting_approval" else 200)
