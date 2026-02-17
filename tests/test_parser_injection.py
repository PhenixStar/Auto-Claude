"""
Tests for Subshell Injection Detection
=======================================

Validates that the command parser correctly blocks shell syntax patterns
that could bypass command-level security (subshell substitution, backtick
execution, process substitution) while still allowing safe commands
including those with single-quoted literals.
"""

import pytest

from security.parser import detect_dangerous_syntax, extract_commands


# ---------------------------------------------------------------------------
# Test vectors
# ---------------------------------------------------------------------------

INJECTION_VECTORS = [
    "`rm -rf /` && echo ok",
    "echo $(cat /etc/passwd)",
    "cat <(echo malicious)",
    'echo "$(whoami)"',
    'git log --format="%H $(id)"',
    "ls `which python`",
]

SAFE_COMMANDS = [
    "git status",
    "npm install",
    "python3 -m pytest",
    "echo 'hello world'",
    "echo 'literal $() not executed'",  # single-quoted = safe
    "ls -la | grep test",
    "git commit -m 'fix: resolve issue'",
    "cat package.json && npm test",
    "git log --oneline -10",
]


# ---------------------------------------------------------------------------
# detect_dangerous_syntax unit tests
# ---------------------------------------------------------------------------

class TestDetectDangerousSyntax:
    """Unit tests for the detect_dangerous_syntax function."""

    @pytest.mark.parametrize("cmd", INJECTION_VECTORS)
    def test_detects_injection_vectors(self, cmd: str):
        """Each injection vector triggers at least one warning."""
        warnings = detect_dangerous_syntax(cmd)
        assert len(warnings) > 0, f"Expected warnings for: {cmd}"

    @pytest.mark.parametrize("cmd", SAFE_COMMANDS)
    def test_allows_safe_commands(self, cmd: str):
        """Safe commands produce no warnings."""
        warnings = detect_dangerous_syntax(cmd)
        assert warnings == [], f"Unexpected warnings for: {cmd}"

    def test_subshell_dollar_paren(self):
        """Detects $(...) substitution."""
        warnings = detect_dangerous_syntax("echo $(id)")
        assert any("subshell" in w for w in warnings)

    def test_backtick_substitution(self):
        """Detects backtick substitution."""
        warnings = detect_dangerous_syntax("echo `id`")
        assert any("backtick" in w for w in warnings)

    def test_process_substitution_input(self):
        """Detects <(...) process substitution."""
        warnings = detect_dangerous_syntax("diff <(ls dir1) <(ls dir2)")
        assert any("process substitution" in w for w in warnings)

    def test_process_substitution_output(self):
        """Detects >(...) process substitution."""
        warnings = detect_dangerous_syntax("tee >(grep error > log)")
        assert any("process substitution" in w for w in warnings)

    def test_single_quoted_dollar_paren_is_safe(self):
        """$() inside single quotes is a literal, not executed."""
        warnings = detect_dangerous_syntax("echo '$(not executed)'")
        assert warnings == []

    def test_single_quoted_backtick_is_safe(self):
        """Backticks inside single quotes are literals."""
        warnings = detect_dangerous_syntax("echo '`not executed`'")
        assert warnings == []

    def test_mixed_safe_and_dangerous(self):
        """Dangerous syntax outside single quotes is still caught."""
        warnings = detect_dangerous_syntax("echo 'safe' && echo $(id)")
        assert len(warnings) > 0

    def test_empty_string(self):
        """Empty string produces no warnings."""
        assert detect_dangerous_syntax("") == []

    def test_double_quoted_subshell_is_dangerous(self):
        """$() inside double quotes IS executed by shell."""
        warnings = detect_dangerous_syntax('echo "$(whoami)"')
        assert len(warnings) > 0


# ---------------------------------------------------------------------------
# extract_commands integration tests
# ---------------------------------------------------------------------------

class TestExtractCommandsInjectionBlocking:
    """Verify extract_commands returns empty list for injection vectors."""

    @pytest.mark.parametrize("cmd", INJECTION_VECTORS)
    def test_blocks_injection_vectors(self, cmd: str):
        """Injection vectors cause extract_commands to return empty list."""
        commands = extract_commands(cmd)
        assert commands == [], f"Should be blocked: {cmd}"

    @pytest.mark.parametrize("cmd", SAFE_COMMANDS)
    def test_allows_safe_commands(self, cmd: str):
        """Safe commands still parse correctly."""
        commands = extract_commands(cmd)
        assert len(commands) > 0, f"Should parse: {cmd}"

    def test_git_format_with_subshell_blocked(self):
        """Git log with subshell in format string is blocked."""
        commands = extract_commands('git log --format="%H $(id)"')
        assert commands == []

    def test_chained_safe_commands_allowed(self):
        """Chained safe commands parse normally."""
        commands = extract_commands("mkdir build && cd build && cmake ..")
        assert "mkdir" in commands
        assert "cd" in commands

    def test_pipe_safe_commands_allowed(self):
        """Piped safe commands parse normally."""
        commands = extract_commands("cat file.txt | grep pattern | wc -l")
        assert commands == ["cat", "grep", "wc"]
