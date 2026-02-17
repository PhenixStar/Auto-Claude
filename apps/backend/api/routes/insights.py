"""
Insights Routes
===============

REST endpoints for the AI insights/chat interface. Mirrors the data contract
from the Electron IPC handlers (insights-handlers.ts).

The query endpoint returns a streaming SSE response for real-time AI output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..dependencies.auth import verify_auth
from ..dependencies.project import find_project

router = APIRouter(prefix="/api/projects", tags=["insights"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AUTO_CLAUDE_DIRS = (".auto-claude", "auto-claude")
_INSIGHTS_DIR = "insights"
_SESSION_FILE = "session.json"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class InsightsQueryRequest(BaseModel):
    message: str
    model: str | None = None
    thinkingLevel: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insights_dir(project: dict[str, Any]) -> Path:
    """Return the insights directory for a project."""
    return (
        Path(project["path"])
        / project.get("autoBuildPath", _AUTO_CLAUDE_DIRS[0])
        / _INSIGHTS_DIR
    )


def _load_session(project: dict[str, Any]) -> dict[str, Any] | None:
    """Load the insights session from disk, or None if not found."""
    session_path = _insights_dir(project) / _SESSION_FILE
    if not session_path.exists():
        return None
    try:
        return json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/{project_id}/insights/query")
async def query_insights(
    project_id: str, request: InsightsQueryRequest
) -> StreamingResponse:
    """Send a message to the insights AI and receive a streaming SSE response.

    In the web version, this starts the AI query and streams back results
    as Server-Sent Events for real-time display.
    """
    project = find_project(project_id)

    # Ensure insights directory exists
    d = _insights_dir(project)
    d.mkdir(parents=True, exist_ok=True)

    async def event_stream():
        """Generate SSE events. Placeholder for actual AI integration."""

        # Send initial acknowledgement
        yield f"data: {json.dumps({'type': 'start', 'projectId': project_id})}\n\n"

        # Placeholder: actual AI streaming will be wired in later
        yield f"data: {json.dumps({'type': 'message', 'content': 'Insights query received. AI integration pending.'})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
