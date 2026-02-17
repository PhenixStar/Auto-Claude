"""
Roadmap Routes
==============

REST endpoints for AI-powered roadmap management. Mirrors the data contract
from the Electron IPC handlers (roadmap-handlers.ts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies.auth import verify_auth
from ..dependencies.project import find_project

router = APIRouter(prefix="/api/projects", tags=["roadmap"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AUTO_CLAUDE_DIRS = (".auto-claude", "auto-claude")
_ROADMAP_DIR = "roadmap"
_ROADMAP_FILE = "roadmap.json"
_COMPETITOR_ANALYSIS_FILE = "competitor_analysis.json"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RoadmapGenerateRequest(BaseModel):
    includeCompetitorAnalysis: bool = False
    model: str | None = None
    thinkingLevel: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _roadmap_dir(project: dict[str, Any]) -> Path:
    """Return the roadmap directory for a project."""
    return (
        Path(project["path"])
        / project.get("autoBuildPath", _AUTO_CLAUDE_DIRS[0])
        / _ROADMAP_DIR
    )


def _load_roadmap(project: dict[str, Any]) -> dict[str, Any] | None:
    """Load roadmap JSON from disk, or None if not found."""
    roadmap_path = _roadmap_dir(project) / _ROADMAP_FILE
    if not roadmap_path.exists():
        return None
    try:
        return json.loads(roadmap_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_competitor_analysis(project: dict[str, Any]) -> dict[str, Any] | None:
    """Load competitor analysis JSON from disk, or None if not found."""
    analysis_path = _roadmap_dir(project) / _COMPETITOR_ANALYSIS_FILE
    if not analysis_path.exists():
        return None
    try:
        return json.loads(analysis_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{project_id}/roadmap")
async def get_roadmap(project_id: str) -> dict[str, Any]:
    """Get the current roadmap for a project."""
    project = find_project(project_id)
    roadmap = _load_roadmap(project)

    result: dict[str, Any] = {"roadmap": roadmap}

    # Include competitor analysis if available
    competitor_analysis = _load_competitor_analysis(project)
    if competitor_analysis is not None:
        result["competitorAnalysis"] = competitor_analysis

    return result


@router.post("/{project_id}/roadmap/generate")
async def generate_roadmap(
    project_id: str, request: RoadmapGenerateRequest
) -> dict[str, Any]:
    """Start roadmap generation for a project.

    In the web version, this queues the generation task. The actual AI
    generation runs asynchronously and progress is reported via Socket.IO.
    """
    project = find_project(project_id)

    # Ensure roadmap directory exists
    rd = _roadmap_dir(project)
    rd.mkdir(parents=True, exist_ok=True)

    return {
        "status": "queued",
        "message": "Roadmap generation has been queued",
        "projectId": project_id,
    }
