"""
Terminal WebSocket Namespace
============================

Socket.IO ``/terminal`` namespace handling real-time terminal I/O.

Events (client → server):
    create  — Create a new PTY session
    input   — Write data to a PTY
    resize  — Resize a PTY window
    kill    — Kill a PTY session

Events (server → client):
    output  — PTY output data
    exit    — PTY process exited
    error   — Error notification
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import socketio

from ..dependencies.auth import verify_websocket_token
from ..services.terminal_service import TerminalService

logger = logging.getLogger(__name__)

# Singleton terminal service shared across all connections
_terminal_service = TerminalService()


def get_terminal_service() -> TerminalService:
    """Return the global TerminalService instance."""
    return _terminal_service


class TerminalNamespace(socketio.AsyncNamespace):
    """Socket.IO namespace for /terminal."""

    def __init__(self) -> None:
        super().__init__("/terminal")
        self.service = _terminal_service

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def on_connect(self, sid: str, environ: dict[str, Any]) -> bool | None:
        """Authenticate and accept/reject the WebSocket connection.

        The client may supply the token as:
        - query parameter ``?token=<value>``
        - ``Authorization: Bearer <value>`` HTTP header on the upgrade request
        """
        token: str | None = None

        # Try query string first
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        if "token" in qs:
            token = qs["token"][0]

        # Fallback to Authorization header
        if not token:
            headers = environ.get("HTTP_AUTHORIZATION", "")
            if headers.startswith("Bearer "):
                token = headers[7:]

        if not verify_websocket_token(token):
            logger.warning("[TerminalNS] Rejected unauthenticated client: %s", sid)
            return False

        logger.info("[TerminalNS] Client connected: %s", sid)

    async def on_disconnect(self, sid: str) -> None:
        logger.info("[TerminalNS] Client disconnected: %s", sid)

    # ------------------------------------------------------------------
    # CWD validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_cwd(cwd: str | None) -> str | None:
        """Validate that *cwd* is inside a registered project directory.

        Returns the resolved cwd if valid, or ``None`` to fall back to HOME.
        """
        if not cwd:
            return None

        resolved = os.path.realpath(os.path.abspath(cwd))

        # Must be an existing directory
        if not os.path.isdir(resolved):
            logger.warning("[TerminalNS] cwd does not exist: %s", resolved)
            return None

        # Load registered project paths from the store
        store_path = Path.home() / ".auto-claude-web" / "projects.json"
        project_paths: list[str] = []
        try:
            if store_path.exists():
                data = json.loads(store_path.read_text(encoding="utf-8"))
                for project in data.get("projects", []):
                    p = project.get("path")
                    if p:
                        project_paths.append(os.path.realpath(os.path.abspath(p)))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[TerminalNS] Could not read project store: %s", exc)

        # If no projects registered, allow any existing directory
        if not project_paths:
            return resolved

        # Check if resolved cwd is within any registered project
        for proj_path in project_paths:
            # Ensure trailing separator for prefix check to avoid
            # /home/user/project-extra matching /home/user/project
            proj_prefix = proj_path.rstrip(os.sep) + os.sep
            if resolved == proj_path or resolved.startswith(proj_prefix):
                return resolved

        # Also allow HOME itself
        home = os.path.realpath(os.path.expanduser("~"))
        if resolved == home:
            return resolved

        logger.warning(
            "[TerminalNS] cwd %s is not inside any registered project; falling back to HOME",
            resolved,
        )
        return None

    # ------------------------------------------------------------------
    # Terminal events
    # ------------------------------------------------------------------

    async def on_create(
        self, sid: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Create a new PTY session.

        Expected *data*::

            {
                "sessionId": str,
                "cwd": str | None,
                "cols": int,   # default 80
                "rows": int,   # default 24
            }
        """
        session_id: str = data.get("sessionId", "")
        if not session_id:
            await self.emit(
                "error", {"error": "sessionId is required"}, to=sid
            )
            return {"ok": False, "error": "sessionId is required"}

        cwd = self._validate_cwd(data.get("cwd"))
        cols = int(data.get("cols", 80))
        rows = int(data.get("rows", 24))

        try:

            async def _on_output(sess_id: str, raw: bytes) -> None:
                if raw:
                    await self.emit(
                        "output",
                        {
                            "sessionId": sess_id,
                            "data": raw.decode("utf-8", errors="replace"),
                        },
                        to=sid,
                    )

            await self.service.spawn(session_id, cwd, cols, rows, on_output=_on_output)
            logger.info(
                "[TerminalNS] Created session %s for client %s", session_id, sid
            )
            return {"ok": True, "sessionId": session_id}
        except Exception as exc:
            logger.exception("[TerminalNS] Failed to create session %s", session_id)
            await self.emit(
                "error", {"sessionId": session_id, "error": str(exc)}, to=sid
            )
            return {"ok": False, "error": str(exc)}

    async def on_input(self, sid: str, data: dict[str, Any]) -> None:
        """
        Write input to a PTY session.

        Expected *data*::

            {"sessionId": str, "data": str}
        """
        session_id = data.get("sessionId", "")
        input_data = data.get("data", "")
        if not session_id:
            return

        try:
            await self.service.write(session_id, input_data)
        except KeyError:
            await self.emit(
                "error",
                {"sessionId": session_id, "error": "Session not found"},
                to=sid,
            )

    async def on_resize(self, sid: str, data: dict[str, Any]) -> None:
        """
        Resize a PTY session.

        Expected *data*::

            {"sessionId": str, "cols": int, "rows": int}
        """
        session_id = data.get("sessionId", "")
        if not session_id:
            return

        cols = int(data.get("cols", 80))
        rows = int(data.get("rows", 24))

        try:
            await self.service.resize(session_id, cols, rows)
        except KeyError:
            await self.emit(
                "error",
                {"sessionId": session_id, "error": "Session not found"},
                to=sid,
            )

    async def on_kill(self, sid: str, data: dict[str, Any]) -> None:
        """
        Close (kill) a PTY session.

        Expected *data*::

            {"sessionId": str}
        """
        session_id = data.get("sessionId", "")
        if not session_id:
            return

        await self.service.kill(session_id)
        await self.emit("exit", {"sessionId": session_id}, to=sid)
        logger.info("[TerminalNS] Closed session %s for client %s", session_id, sid)


def register_terminal_namespace(sio_server: socketio.AsyncServer) -> None:
    """Register the /terminal namespace on the given Socket.IO server."""
    sio_server.register_namespace(TerminalNamespace())
    logger.info("[TerminalNS] Registered /terminal namespace")
