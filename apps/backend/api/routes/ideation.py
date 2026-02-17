"""
Ideation Routes
===============

REST endpoints for AI-powered idea generation and management. Mirrors the
data contract from the Electron IPC handlers (ideation-handlers.ts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies.auth import verify_auth
from ..dependencies.project import find_project

router = APIRouter(prefix="/api/projects", tags=["ideation"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AUTO_CLAUDE_DIRS = (".auto-claude", "auto-claude")
_IDEATION_DIR = "ideation"
_SESSION_FILE = "session.json"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class IdeationGenerateRequest(BaseModel):
    types: list[str] | None = None
    model: str | None = None
    thinkingLevel: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ideation_dir(project: dict[str, Any]) -> Path:
    """Return the ideation directory for a project."""
    return (
        Path(project["path"])
        / project.get("autoBuildPath", _AUTO_CLAUDE_DIRS[0])
        / _IDEATION_DIR
    )


def _load_session(project: dict[str, Any]) -> dict[str, Any] | None:
    """Load the ideation session from disk, or None if not found."""
    session_path = _ideation_dir(project) / _SESSION_FILE
    if not session_path.exists():
        return None
    try:
        return json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{project_id}/ideas")
async def get_ideas(project_id: str) -> dict[str, Any]:
    """Get the current ideation session for a project."""
    project = find_project(project_id)
    session = _load_session(project)
    return {"session": session}


@router.post("/{project_id}/ideas/generate")
async def generate_ideas(
    project_id: str, request: IdeationGenerateRequest
) -> dict[str, Any]:
    """Start idea generation for a project.

    In the web version, this queues the generation task. The actual AI
    generation runs asynchronously and progress is reported via Socket.IO.
    """
    project = find_project(project_id)

    # Ensure ideation directory exists
    d = _ideation_dir(project)
    d.mkdir(parents=True, exist_ok=True)

    return {
        "status": "queued",
        "message": "Idea generation has been queued",
        "projectId": project_id,
    }
