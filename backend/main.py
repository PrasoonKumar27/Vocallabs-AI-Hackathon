"""
Part 05 — FastAPI App + WebSocket

The integration point: exposes REST endpoints and WebSocket streaming,
kicks off the orchestrator loop, and wires event callbacks so that
resilience events flow from Parts 03/04 through to connected clients.
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.chaos_middleware import router as chaos_router
from backend.model_router import set_failover_callback
from backend.resilience_core import (
    get_aggregate_state,
    get_all_states,
    set_event_callback,
)
from backend.orchestrator import run_task

logger = logging.getLogger("toolfall.main")

# ---------------------------------------------------------------------------
# In-memory registries
# ---------------------------------------------------------------------------

# task_id → list[WebSocket]  (active connections)
_ws_connections: dict[str, list[WebSocket]] = {}

# task_id → list[dict]  (full event history for late-joining clients / eval)
_task_events: dict[str, list[dict]] = {}

# task_id → asyncio.Task  (background task handle)
_task_handles: dict[str, asyncio.Task] = {}

# Currently active task_id (for routing resilience/failover events)
_active_task_id: str | None = None


# ---------------------------------------------------------------------------
# Event broadcasting
# ---------------------------------------------------------------------------

async def _broadcast(task_id: str, event: dict):
    """Send an event to all WebSocket clients for a given task_id and store it."""
    # Store in history
    if task_id not in _task_events:
        _task_events[task_id] = []
    _task_events[task_id].append(event)

    # Broadcast to all connected sockets
    sockets = _ws_connections.get(task_id, [])
    dead: list[WebSocket] = []
    data = json.dumps(event, default=str)
    for ws in sockets:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    # Clean up dead connections
    for ws in dead:
        if ws in sockets:
            sockets.remove(ws)


async def _global_event_callback(event: dict):
    """
    Callback registered with resilience_core (Part 03).
    Routes events to the currently active task's WebSocket broadcast.
    """
    if _active_task_id:
        await _broadcast(_active_task_id, event)


async def _global_failover_callback(event: dict):
    """
    Callback registered with model_router (Part 04).
    Routes model_failover events to the currently active task's WS broadcast.
    """
    if _active_task_id:
        await _broadcast(_active_task_id, event)


# ---------------------------------------------------------------------------
# Lifespan — wire callbacks on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register event callbacks so Parts 03/04 push events through our WS bus
    set_event_callback(_global_event_callback)
    set_failover_callback(_global_failover_callback)
    logger.info("ToolFall backend started — event callbacks registered")
    yield
    logger.info("ToolFall backend shutting down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ToolFall",
    description="Resilience layer for AI agents that use external tools",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server and any origin for hackathon demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount chaos middleware routes (Part 02)
app.include_router(chaos_router)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

class TaskStartRequest(BaseModel):
    request: str


@app.post("/api/task/start")
async def start_task(body: TaskStartRequest):
    """
    Kick off the orchestrator loop as a background async task.
    Returns the task_id immediately (non-blocking).
    """
    global _active_task_id

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    _task_events[task_id] = []
    _ws_connections[task_id] = []
    _active_task_id = task_id

    async def _emit(event: dict):
        await _broadcast(task_id, event)

    async def _run_wrapper():
        try:
            await run_task(task_id, body.request, _emit)
        except Exception as e:
            logger.exception("[%s] Unhandled error in orchestrator", task_id)
            await _broadcast(task_id, {
                "event": "task_completed",
                "success": False,
                "degraded": True,
                "error": str(e),
                "ts": datetime.now(tz=datetime.now().astimezone().tzinfo).isoformat(),
            })

    bg_task = asyncio.create_task(_run_wrapper())
    _task_handles[task_id] = bg_task

    return {"task_id": task_id}


@app.get("/api/task/{task_id}/events")
async def get_task_events(task_id: str):
    """
    Fetch the full event history for a task.
    Useful for late-joining clients or the eval harness.
    """
    events = _task_events.get(task_id)
    if events is None:
        return {"error": "Task not found", "events": []}
    return {"task_id": task_id, "events": events}


@app.get("/api/state")
async def get_state():
    """Return current resilience states for all tools + aggregate."""
    return get_aggregate_state()


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "ToolFall Resilience Backend",
        "endpoints": ["/api/health", "/api/state", "/api/task/start", "/ws/task/{task_id}"]
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "active_task": _active_task_id}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/task/{task_id}")
async def ws_task(websocket: WebSocket, task_id: str):
    """
    Stream events for a task in real time.
    Supports multiple simultaneous clients on the same task_id.
    On connect, replays all past events (for late-joining clients).
    """
    await websocket.accept()

    # Register this socket
    if task_id not in _ws_connections:
        _ws_connections[task_id] = []
    _ws_connections[task_id].append(websocket)

    logger.info("[WS] Client connected to task %s (total: %d)", task_id, len(_ws_connections[task_id]))

    # Replay past events for late joiners
    past_events = _task_events.get(task_id, [])
    for event in past_events:
        try:
            await websocket.send_text(json.dumps(event, default=str))
        except Exception:
            break

    # Keep connection alive, listening for incoming messages (e.g. pings)
    try:
        while True:
            # We don't expect client messages, but we must read to detect disconnect
            data = await websocket.receive_text()
            # Optionally handle client pings or chaos commands via WS
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected from task %s", task_id)
    except Exception as e:
        logger.warning("[WS] Connection error on task %s: %s", task_id, e)
    finally:
        if websocket in _ws_connections.get(task_id, []):
            _ws_connections[task_id].remove(websocket)


# ---------------------------------------------------------------------------
# Eval harness mount point (Part 06)
# ---------------------------------------------------------------------------

from backend.eval.run_eval import router as eval_router
app.include_router(eval_router)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
