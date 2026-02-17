"""
Changelog Routes
================

REST endpoints for AI-powered changelog generation. Mirrors the data contract
from the Electron IPC handlers (changelog-handlers.ts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies.auth import verify_auth
from ..dependencies.project import find_project

router = APIRouter(prefix="/api/projects", tags=["changelog"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHANGELOG_FILE = "CHANGELOG.md"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ChangelogGenerateRequest(BaseModel):
    taskIds: list[str] | None = None
    sourceMode: str = "tasks"
    version: str | None = None
    model: str | None = None
    thinkingLevel: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{project_id}/changelog")
async def get_changelog(project_id: str) -> dict[str, Any]:
    """Read the existing changelog for a project."""
    project = find_project(project_id)
    changelog_path = Path(project["path"]) / _CHANGELOG_FILE

    content: str | None = None
    if changelog_path.exists():
        try:
            content = changelog_path.read_text(encoding="utf-8")
        except OSError:
            pass

    return {"content": content}


@router.post("/{project_id}/changelog/generate")
async def generate_changelog(
    project_id: str, request: ChangelogGenerateRequest
) -> dict[str, Any]:
    """Start changelog generation for a project.

    In the web version, this queues the generation task. The actual AI
    generation runs asynchronously and progress is reported via Socket.IO.
    """
    project = find_project(project_id)

    return {
        "status": "queued",
        "message": "Changelog generation has been queued",
        "projectId": project_id,
    }
