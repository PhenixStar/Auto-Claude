"""
Terminal Routes
===============

REST endpoints for terminal session management. Mirrors the data contract
from the Electron IPC handlers (terminal-handlers.ts).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies.auth import verify_auth

router = APIRouter(prefix="/api", tags=["terminals"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# In-memory terminal session store (will be replaced by real PTY integration)
# NOTE: In-memory state for REST API. Real terminal state managed by WebSocket/PTY daemon.
# ---------------------------------------------------------------------------

_terminals: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CreateTerminalRequest(BaseModel):
    name: str | None = None
    cwd: str | None = None
    project_id: str | None = None
    cols: int = 80
    rows: int = 24


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/terminals")
async def create_terminal(body: CreateTerminalRequest) -> dict[str, Any]:
    """Create a new terminal session.

    This is a placeholder that records the session; real PTY integration
    will be added when the terminal system is ported to the web backend.
    """
    terminal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    terminal = {
        "id": terminal_id,
        "name": body.name or f"Terminal {len(_terminals) + 1}",
        "cwd": body.cwd,
        "projectId": body.project_id,
        "cols": body.cols,
        "rows": body.rows,
        "status": "active",
        "createdAt": now,
    }

    _terminals[terminal_id] = terminal

    return {"success": True, "data": terminal}


@router.get("/terminals")
async def list_terminals() -> dict[str, Any]:
    """List all active terminal sessions."""
    active = [t for t in _terminals.values() if t["status"] == "active"]
    return {"success": True, "data": active}


@router.delete("/terminals/{terminal_id}")
async def close_terminal(terminal_id: str) -> dict[str, Any]:
    """Close a terminal session."""
    terminal = _terminals.get(terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail="Terminal not found")

    if terminal["status"] != "active":
        raise HTTPException(status_code=409, detail="Terminal is already closed")

    terminal["status"] = "closed"

    return {"success": True, "data": {"id": terminal_id, "status": "closed"}}
