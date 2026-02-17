"""
Environment Routes
===================

REST endpoints for per-project environment configuration (.env files).
Mirrors the data contract from the Electron IPC handlers (env-handlers.ts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies.auth import verify_auth
from ..dependencies.project import find_project

router = APIRouter(prefix="/api/projects", tags=["environment"], dependencies=[Depends(verify_auth)])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUTO_CLAUDE_DIRS = (".auto-claude", "auto-claude")


def _env_path(project: dict[str, Any]) -> Path:
    """Resolve the .env file path for a project."""
    project_path = project["path"]
    auto_build = project.get("autoBuildPath", "")
    if auto_build:
        return Path(project_path) / auto_build / ".env"
    # Fallback: check known auto-claude directories
    for dirname in _AUTO_CLAUDE_DIRS:
        candidate = Path(project_path) / dirname
        if candidate.is_dir():
            return candidate / ".env"
    # Default to .auto-claude
    return Path(project_path) / ".auto-claude" / ".env"


def _parse_env_file(content: str) -> dict[str, str]:
    """Parse a .env file into a key-value dict (ignores comments/blanks)."""
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


_SENSITIVE_SUBSTRINGS = ("TOKEN", "SECRET", "KEY", "PASSWORD", "AUTH")


def _mask_value(value: str) -> str:
    """Mask a sensitive value, showing only the last 4 characters."""
    if len(value) <= 4:
        return "****"
    return f"****{value[-4:]}"


def _is_sensitive_key(key: str) -> bool:
    """Check if an env key name looks like it holds a secret."""
    upper = key.upper()
    return any(s in upper for s in _SENSITIVE_SUBSTRINGS)


def _env_to_config(
    env_vars: dict[str, str],
    *,
    mask_secrets: bool = False,
) -> dict[str, Any]:
    """Map .env variables to a ProjectEnvConfig-style dict.

    When *mask_secrets* is True, values whose env key contains TOKEN,
    SECRET, KEY, PASSWORD, or AUTH are replaced with ``****<last4>``.
    """
    config: dict[str, Any] = {}
    _map = {
        "CLAUDE_CODE_OAUTH_TOKEN": "claudeOAuthToken",
        "AUTO_BUILD_MODEL": "autoBuildModel",
        "LINEAR_API_KEY": "linearApiKey",
        "LINEAR_TEAM_ID": "linearTeamId",
        "LINEAR_PROJECT_ID": "linearProjectId",
        "GITHUB_TOKEN": "githubToken",
        "GITHUB_REPO": "githubRepo",
        "DEFAULT_BRANCH": "defaultBranch",
        "OPENAI_API_KEY": "openaiApiKey",
        "GITLAB_TOKEN": "gitlabToken",
        "GITLAB_INSTANCE_URL": "gitlabInstanceUrl",
        "GITLAB_PROJECT": "gitlabProject",
    }
    for env_key, config_key in _map.items():
        if env_key in env_vars:
            value = env_vars[env_key]
            if mask_secrets and _is_sensitive_key(env_key):
                value = _mask_value(value)
            config[config_key] = value

    # Boolean fields (never masked — they are true/false)
    _bool_map = {
        "LINEAR_REALTIME_SYNC": "linearRealtimeSync",
        "GITHUB_AUTO_SYNC": "githubAutoSync",
        "GRAPHITI_ENABLED": "graphitiEnabled",
        "GITLAB_ENABLED": "gitlabEnabled",
        "GITLAB_AUTO_SYNC": "gitlabAutoSync",
        "ENABLE_FANCY_UI": "enableFancyUi",
    }
    for env_key, config_key in _bool_map.items():
        if env_key in env_vars:
            config[config_key] = env_vars[env_key].lower() == "true"

    return config


def _config_to_env_lines(config: dict[str, Any]) -> dict[str, str]:
    """Map a ProjectEnvConfig-style dict back to env key-value pairs."""
    env_vars: dict[str, str] = {}
    _map = {
        "claudeOAuthToken": "CLAUDE_CODE_OAUTH_TOKEN",
        "autoBuildModel": "AUTO_BUILD_MODEL",
        "linearApiKey": "LINEAR_API_KEY",
        "linearTeamId": "LINEAR_TEAM_ID",
        "linearProjectId": "LINEAR_PROJECT_ID",
        "githubToken": "GITHUB_TOKEN",
        "githubRepo": "GITHUB_REPO",
        "defaultBranch": "DEFAULT_BRANCH",
        "openaiApiKey": "OPENAI_API_KEY",
        "gitlabToken": "GITLAB_TOKEN",
        "gitlabInstanceUrl": "GITLAB_INSTANCE_URL",
        "gitlabProject": "GITLAB_PROJECT",
    }
    _bool_map = {
        "linearRealtimeSync": "LINEAR_REALTIME_SYNC",
        "githubAutoSync": "GITHUB_AUTO_SYNC",
        "graphitiEnabled": "GRAPHITI_ENABLED",
        "gitlabEnabled": "GITLAB_ENABLED",
        "gitlabAutoSync": "GITLAB_AUTO_SYNC",
        "enableFancyUi": "ENABLE_FANCY_UI",
    }
    for config_key, env_key in _map.items():
        if config_key in config and config[config_key] is not None:
            env_vars[env_key] = str(config[config_key])
    for config_key, env_key in _bool_map.items():
        if config_key in config and config[config_key] is not None:
            env_vars[env_key] = "true" if config[config_key] else "false"
    return env_vars


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class EnvConfigUpdate(BaseModel):
    """Partial env config update — all fields optional."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{project_id}/env")
async def get_env(project_id: str) -> dict[str, Any]:
    """Read a project's environment configuration from its .env file."""
    project = find_project(project_id)
    env_file = _env_path(project)

    if not env_file.exists():
        return {"success": True, "data": {}}

    try:
        content = env_file.read_text(encoding="utf-8")
        env_vars = _parse_env_file(content)
        config = _env_to_config(env_vars, mask_secrets=True)
        return {"success": True, "data": config}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read .env: {exc}")


@router.put("/{project_id}/env")
async def update_env(project_id: str, body: EnvConfigUpdate) -> dict[str, Any]:
    """Save a project's environment configuration to its .env file."""
    project = find_project(project_id)
    env_file = _env_path(project)

    # Load existing env vars
    existing_vars: dict[str, str] = {}
    if env_file.exists():
        try:
            existing_vars = _parse_env_file(env_file.read_text(encoding="utf-8"))
        except OSError:
            pass

    # Merge new values
    new_vars = _config_to_env_lines(body.model_dump(exclude_unset=True))
    existing_vars.update(new_vars)

    # Write back
    try:
        env_file.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{k}={v}" for k, v in sorted(existing_vars.items())]
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write .env: {exc}")

    config = _env_to_config(existing_vars)
    return {"success": True, "data": config}
