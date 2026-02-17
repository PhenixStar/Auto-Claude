"""
Context Routes
==============

REST endpoints for project context, memories, and project index. Mirrors
the data contract from the Electron IPC handlers (context-handlers.ts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies.auth import verify_auth
from ..dependencies.project import find_project

router = APIRouter(prefix="/api/projects", tags=["context"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AUTO_CLAUDE_DIRS = (".auto-claude", "auto-claude")
_CONTEXT_DIR = "context"
_MEMORIES_FILE = "memories.json"
_PROJECT_INDEX_FILE = "project_index.json"
_ENV_FILE = ".env"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auto_claude_dir(project: dict[str, Any]) -> Path:
    """Return the .auto-claude directory for a project."""
    return Path(project["path"]) / project.get("autoBuildPath", _AUTO_CLAUDE_DIRS[0])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{project_id}/context")
async def get_context(project_id: str) -> dict[str, Any]:
    """Get project context information including environment config."""
    project = find_project(project_id)
    ac_dir = _auto_claude_dir(project)

    # Read .env file if present
    env_config: dict[str, str] = {}
    env_path = ac_dir / _ENV_FILE
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_config[key.strip()] = value.strip()
        except OSError:
            pass

    # Check for Graphiti/memory configuration
    graphiti_enabled = env_config.get("GRAPHITI_ENABLED", "").lower() == "true"
    graphiti_url = env_config.get("GRAPHITI_URL", "")

    return {
        "projectId": project_id,
        "graphitiEnabled": graphiti_enabled,
        "graphitiUrl": graphiti_url,
    }


@router.get("/{project_id}/memories")
async def get_memories(project_id: str) -> dict[str, Any]:
    """Get stored memories for a project."""
    project = find_project(project_id)
    ac_dir = _auto_claude_dir(project)

    memories_path = ac_dir / _CONTEXT_DIR / _MEMORIES_FILE
    memories: list[dict[str, Any]] = []

    if memories_path.exists():
        try:
            memories = json.loads(memories_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {"memories": memories}


@router.get("/{project_id}/project-index")
async def get_project_index(project_id: str) -> dict[str, Any]:
    """Get the project index (file structure, technologies, etc.)."""
    project = find_project(project_id)
    ac_dir = _auto_claude_dir(project)

    index_path = ac_dir / _CONTEXT_DIR / _PROJECT_INDEX_FILE
    index_data: dict[str, Any] | None = None

    if index_path.exists():
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {"index": index_data}
