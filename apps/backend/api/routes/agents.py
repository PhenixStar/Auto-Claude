"""
Agent Routes
============

REST endpoints for agent execution management. Mirrors the data contract
from the Electron IPC handlers (agent-events-handlers.ts).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies.auth import verify_auth
from ..dependencies.project import find_project
from .tasks import _read_json, _specs_dir

router = APIRouter(prefix="/api", tags=["agents"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IMPLEMENTATION_PLAN = "implementation_plan.json"
_BUILD_PROGRESS = "build-progress.txt"

# NOTE: In-memory state for REST API. Real agent state managed by Electron main process.
_agent_state: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StartAgentRequest(BaseModel):
    project_id: str
    phase: str | None = None
    resume: bool = False


class AgentStatus(BaseModel):
    task_id: str
    status: str  # "idle" | "running" | "completed" | "failed" | "stopped"
    phase: str | None = None
    progress: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/tasks/{task_id}/start")
async def start_agent(task_id: str, body: StartAgentRequest) -> dict[str, Any]:
    """Start agent execution for a task.

    This is a placeholder that records intent; real agent spawning will be
    integrated when the agent manager is ported to the web backend.
    """
    project = find_project(body.project_id)
    specs_path = _specs_dir(project)
    spec_folder = specs_path / task_id

    if not spec_folder.exists() or not spec_folder.is_dir():
        raise HTTPException(status_code=404, detail="Task not found")

    if task_id in _agent_state and _agent_state[task_id]["status"] == "running":
        raise HTTPException(
            status_code=409, detail="Agent is already running for this task"
        )

    _agent_state[task_id] = {
        "task_id": task_id,
        "project_id": body.project_id,
        "status": "running",
        "phase": body.phase or "building",
        "progress": None,
    }

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "status": "running",
            "phase": body.phase or "building",
        },
    }


@router.post("/tasks/{task_id}/stop")
async def stop_agent(task_id: str) -> dict[str, Any]:
    """Stop agent execution for a task."""
    state = _agent_state.get(task_id)
    if not state or state["status"] != "running":
        raise HTTPException(
            status_code=404, detail="No running agent found for this task"
        )

    _agent_state[task_id]["status"] = "stopped"

    return {
        "success": True,
        "data": {"task_id": task_id, "status": "stopped"},
    }


@router.get("/tasks/{task_id}/status")
async def get_agent_status(task_id: str, project_id: str) -> dict[str, Any]:
    """Get agent execution status for a task.

    Requires project_id as a query parameter to read plan progress.
    """
    # Check in-memory state first
    state = _agent_state.get(task_id)
    if state:
        return {"success": True, "data": state}

    # Fall back to reading plan file for historical status
    project = find_project(project_id)
    specs_path = _specs_dir(project)
    spec_folder = specs_path / task_id

    if not spec_folder.exists() or not spec_folder.is_dir():
        raise HTTPException(status_code=404, detail="Task not found")

    plan = _read_json(spec_folder / _IMPLEMENTATION_PLAN)
    plan_status = (plan or {}).get("status", "pending")

    status_map = {
        "pending": "idle",
        "in_progress": "running",
        "review": "completed",
        "completed": "completed",
    }

    # Count subtask progress
    completed = 0
    total = 0
    if plan:
        for phase in plan.get("phases", []):
            for st in phase.get("subtasks", []):
                total += 1
                if st.get("status") == "completed":
                    completed += 1

    return {
        "success": True,
        "data": {
            "task_id": task_id,
            "status": status_map.get(plan_status, "idle"),
            "phase": (plan or {}).get("lastEvent", {}).get("type"),
            "progress": f"{completed}/{total}",
        },
    }


@router.get("/tasks/{task_id}/logs")
async def get_agent_logs(task_id: str, project_id: str) -> dict[str, Any]:
    """Get execution logs for a task.

    Requires project_id as a query parameter. Reads from build-progress.txt.
    """
    project = find_project(project_id)
    specs_path = _specs_dir(project)
    spec_folder = specs_path / task_id

    if not spec_folder.exists() or not spec_folder.is_dir():
        raise HTTPException(status_code=404, detail="Task not found")

    progress_file = spec_folder / _BUILD_PROGRESS
    logs: list[str] = []
    if progress_file.exists():
        try:
            content = progress_file.read_text(encoding="utf-8")
            logs = [line for line in content.splitlines() if line.strip()]
        except OSError:
            pass

    return {"success": True, "data": {"task_id": task_id, "logs": logs}}
