"""
Project Dependency
==================

Shared project-lookup logic used across all route modules.

Centralises the ``_find_project()`` pattern that was previously duplicated
in every route file, providing a single ``find_project()`` function and a
FastAPI-compatible dependency ``get_project()``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..routes.projects import _load_store


def find_project(project_id: str) -> dict[str, Any]:
    """Look up a project by ID from the store.

    Raises ``HTTPException(404)`` when the project cannot be found.
    """
    store = _load_store()
    for project in store.get("projects", []):
        if project["id"] == project_id:
            return project
    raise HTTPException(status_code=404, detail="Project not found")
