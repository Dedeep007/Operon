"""FastAPI Web Application and Live Streaming Server for Operon."""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from operon.agent import OperonAgent
from operon.tools.registry import registry
from operon.environment.erp_system import default_erp
from operon.llm import llm_provider
from operon.config import settings

app = FastAPI(title="Operon Autonomous AI Worker", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class TaskRequest(BaseModel):
    task: str

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<h1>Operon Dashboard</h1>"

@app.get("/api/info")
def get_info():
    return {
        "model_name": settings.model_name,
        "is_live_groq": llm_provider.is_live,
        "max_retries": settings.max_retries,
        "tools_count": len(registry.list_definitions())
    }

@app.get("/api/tools")
def get_tools():
    return [t.model_dump() for t in registry.list_definitions()]

@app.get("/api/erp/state")
def get_erp_state():
    return default_erp.get_state_snapshot()

@app.post("/api/erp/reset")
def reset_erp():
    default_erp._seed_initial_data()
    default_erp._initial_snapshot = default_erp.get_state_snapshot()
    return {"message": "ERP datastore successfully reset to initial state.", "state": default_erp.get_state_snapshot()}

@app.post("/api/run")
def run_task_sync(req: TaskRequest):
    agent = OperonAgent()
    packet = agent.run(req.task)
    return packet.model_dump() if packet else {"status": "error", "message": "Failed to complete task"}

@app.get("/api/stream")
async def stream_task_events(task: str):
    """Server-Sent Events endpoint streaming execution progress in real time."""
    agent = OperonAgent()

    async def event_generator():
        # Yield start event
        yield f"data: {json.dumps({'event': 'start', 'task': task})}\n\n"
        
        # Execute stream in executor thread to not block asyncio
        loop = asyncio.get_event_loop()
        
        def run_stream():
            return list(agent.stream(task))
            
        events = await loop.run_in_executor(None, run_stream)
        
        for ev in events:
            for node_name, node_data in ev.items():
                payload = {
                    "event": "node_update",
                    "node": node_name,
                    "status": node_data.get("status"),
                    "current_step_index": node_data.get("current_step_index"),
                }
                
                if node_name == "planner":
                    payload["plan"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in node_data.get("plan", [])]
                elif node_name == "executor":
                    history = node_data.get("action_history", [])
                    if history:
                        last = history[-1]
                        payload["action"] = last.model_dump() if hasattr(last, "model_dump") else last
                elif node_name == "observer":
                    payload["scratchpad"] = node_data.get("scratchpad", {})
                    payload["errors"] = [e.model_dump() if hasattr(e, "model_dump") else e for e in node_data.get("errors", [])]
                elif node_name == "verifier":
                    v = node_data.get("verification_result")
                    payload["verification"] = v.model_dump() if hasattr(v, "model_dump") else v
                elif node_name == "summarizer":
                    packet = node_data.get("evidence_packet")
                    payload["evidence_packet"] = packet.model_dump() if hasattr(packet, "model_dump") else packet
                    
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0.05)
                
        yield f"data: {json.dumps({'event': 'end'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ui.app:app", host="0.0.0.0", port=8000, reload=True)
