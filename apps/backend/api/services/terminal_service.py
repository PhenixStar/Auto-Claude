"""
Terminal Service
================

Server-side PTY management: spawn, write, resize, and kill pseudo-terminal
processes. Each terminal session gets its own PTY subprocess with proper
lifecycle management and cleanup.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import select
import signal
import struct
import termios
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class _PtySession:
    """Represents a single PTY session with its master fd and child pid."""

    __slots__ = ("session_id", "pid", "fd", "cols", "rows", "cwd", "_reader_task")

    def __init__(
        self,
        session_id: str,
        pid: int,
        fd: int,
        cols: int,
        rows: int,
        cwd: str,
    ) -> None:
        self.session_id = session_id
        self.pid = pid
        self.fd = fd
        self.cols = cols
        self.rows = rows
        self.cwd = cwd
        self._reader_task: asyncio.Task[None] | None = None


class TerminalService:
    """
    Manages PTY processes per session with proper cleanup.

    Usage::

        service = TerminalService()
        session_id = await service.spawn("id-1", "/home/user", 80, 24, on_output)
        await service.write(session_id, "ls\\n")
        await service.resize(session_id, 120, 40)
        await service.kill(session_id)
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _PtySession] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def spawn(
        self,
        session_id: str,
        cwd: str | None,
        cols: int,
        rows: int,
        on_output: Callable[[str, bytes], Any] | None = None,
    ) -> str:
        """Spawn a new PTY process and return its session id."""
        if session_id in self._sessions:
            logger.warning(
                "Session %s already exists, killing old one first", session_id
            )
            await self.kill(session_id)

        work_dir = cwd or os.path.expanduser("~")
        shell = os.environ.get("SHELL", "/bin/bash")

        # Spawn PTY
        child_pid, master_fd = pty.fork()

        if child_pid == 0:
            # Child process — exec shell with sanitized environment
            os.chdir(work_dir)
            from .terminal_env import build_terminal_env

            env = build_terminal_env({
                "TERM": "xterm-256color",
                "COLORTERM": "truecolor",
                "PROMPT_EOL_MARK": "",
            })
            os.execvpe(shell, [shell, "-l"], env)
            # execvpe never returns

        # Parent process
        # Set initial window size
        self._set_winsize(master_fd, rows, cols)

        # Make master fd non-blocking for async reads
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        session = _PtySession(
            session_id=session_id,
            pid=child_pid,
            fd=master_fd,
            cols=cols,
            rows=rows,
            cwd=work_dir,
        )
        self._sessions[session_id] = session

        # Start async reader if callback provided
        if on_output is not None:
            session._reader_task = asyncio.create_task(
                self._read_loop(session, on_output)
            )

        logger.info(
            "Spawned PTY session=%s pid=%d shell=%s cwd=%s",
            session_id,
            child_pid,
            shell,
            work_dir,
        )
        return session_id

    async def write(self, session_id: str, data: str) -> None:
        """Write data to a PTY session."""
        session = self._get_session(session_id)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, os.write, session.fd, data.encode())

    async def resize(self, session_id: str, cols: int, rows: int) -> None:
        """Resize a PTY session."""
        session = self._get_session(session_id)
        session.cols = cols
        session.rows = rows
        self._set_winsize(session.fd, rows, cols)

    async def kill(self, session_id: str) -> None:
        """Kill a PTY session and clean up resources."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return

        # Cancel reader task
        if session._reader_task is not None:
            session._reader_task.cancel()
            try:
                await session._reader_task
            except asyncio.CancelledError:
                pass

        # Close master fd
        try:
            os.close(session.fd)
        except OSError:
            pass

        # Kill child process
        try:
            os.kill(session.pid, signal.SIGTERM)
            # Give it a moment then force kill
            await asyncio.sleep(0.1)
            try:
                os.kill(session.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Reap zombie
            try:
                os.waitpid(session.pid, os.WNOHANG)
            except ChildProcessError:
                pass
        except ProcessLookupError:
            pass

        logger.info("Killed PTY session=%s pid=%d", session_id, session.pid)

    async def kill_all(self) -> None:
        """Kill all active PTY sessions. Called during shutdown."""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.kill(sid)

    def get_active_sessions(self) -> list[str]:
        """Return list of active session IDs."""
        return list(self._sessions.keys())

    def has_session(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_session(self, session_id: str) -> _PtySession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Terminal session not found: {session_id}")
        return session

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        """Set the window size of a PTY fd."""
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    @staticmethod
    async def _read_loop(
        session: _PtySession,
        on_output: Callable[[str, bytes], Any],
    ) -> None:
        """Continuously read from the PTY fd and invoke the callback."""
        loop = asyncio.get_event_loop()
        fd = session.fd

        while True:
            try:
                data = await loop.run_in_executor(
                    None, TerminalService._blocking_read, fd
                )
                if not data:
                    break
                result = on_output(session.session_id, data)
                if asyncio.iscoroutine(result):
                    await result
            except OSError:
                break
            except asyncio.CancelledError:
                break

    @staticmethod
    def _blocking_read(fd: int) -> bytes:
        """Blocking read from fd, suitable for run_in_executor."""
        try:
            readable, _, _ = select.select([fd], [], [], 0.1)
            if readable:
                return os.read(fd, 4096)
            return b""
        except OSError:
            return b""
