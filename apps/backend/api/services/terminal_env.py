"""
Terminal Environment Sanitization
==================================

Build a minimal, safe environment dict for PTY terminal sessions.
Only explicitly allowed variables are passed through; any variable
whose name matches a blocked pattern (e.g. TOKEN, SECRET) is dropped
to prevent accidental credential leakage into spawned shells.
"""

from __future__ import annotations

import os

# Variables that are safe to pass through to terminal sessions
ALLOWED_ENV_VARS: set[str] = {
    "PATH", "HOME", "USER", "LOGNAME", "SHELL",
    "TERM", "COLORTERM", "TERM_PROGRAM",
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
    "EDITOR", "VISUAL", "PAGER",
    "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
    "SSH_AUTH_SOCK", "HOSTNAME", "PWD", "OLDPWD",
    "TMPDIR", "TMP", "TEMP",
}

# Any env var whose uppercased name contains one of these substrings
# will be rejected, even if passed via extra_vars.
BLOCKED_PATTERNS: set[str] = {
    "TOKEN", "SECRET", "KEY", "PASSWORD", "CREDENTIAL",
    "AUTH", "ANTHROPIC", "OPENAI", "GITHUB_TOKEN",
    "CLAUDE", "SENTRY_DSN",
}


def _is_blocked(var_name: str) -> bool:
    """Return True if the variable name matches any blocked pattern."""
    upper = var_name.upper()
    return any(pattern in upper for pattern in BLOCKED_PATTERNS)


def build_terminal_env(extra_vars: dict[str, str] | None = None) -> dict[str, str]:
    """Build a minimal, safe environment for terminal sessions.

    1. Copy only ALLOWED_ENV_VARS from os.environ.
    2. Also copy any ``LC_*`` variable (locale settings).
    3. Merge *extra_vars*, rejecting any that match BLOCKED_PATTERNS.

    Returns:
        A new dict suitable for passing to ``os.execvpe``.
    """
    env: dict[str, str] = {}

    # Copy allowed vars from current environment
    for var in ALLOWED_ENV_VARS:
        if var in os.environ:
            env[var] = os.environ[var]

    # Dynamically allow all LC_* locale variables
    for var, value in os.environ.items():
        if var.startswith("LC_") and var not in env:
            env[var] = value

    # Merge caller-supplied overrides, blocking sensitive names
    if extra_vars:
        for var, value in extra_vars.items():
            if not _is_blocked(var):
                env[var] = value

    return env
