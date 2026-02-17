"""mypy type checker plugin.

mypy is a static type checker for Python.
https://mypy-lang.org/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)


def _glob_to_regex(pattern: str) -> str:
    """Convert a gitignore-style glob pattern to a regex for mypy.

    mypy's --exclude flag expects Python regex patterns, not glob patterns.
    This function converts common glob patterns to equivalent regex.

    Args:
        pattern: Gitignore-style glob pattern (e.g., '**/.venv/**', '*.pyc').

    Returns:
        Regex pattern suitable for mypy --exclude.
    """
    import re

    # Handle common directory patterns like **/.venv/** or .venv/
    # Extract the core directory/file name and create a simple regex
    if pattern.startswith("**/") and pattern.endswith("/**"):
        # Pattern like **/.venv/** - match directory anywhere in path
        core = pattern[3:-3]  # Remove **/ and /**
        # Escape regex special chars and create pattern
        escaped = re.escape(core)
        return f"(^|/){escaped}(/|$)"

    if pattern.startswith("**/"):
        # Pattern like **/foo or **/*.pyc - match at end of any path
        core = pattern[3:]
        escaped = re.escape(core)
        # Convert glob wildcards in the remaining pattern
        escaped = escaped.replace(r"\*\*", ".*")
        escaped = escaped.replace(r"\*", "[^/]*")
        escaped = escaped.replace(r"\?", "[^/]")
        return f"(^|/){escaped}$"

    if pattern.endswith("/**"):
        # Pattern like foo/** - match directory at start
        core = pattern[:-3]
        escaped = re.escape(core)
        return f"^{escaped}(/|$)"

    if pattern.endswith("/"):
        # Directory pattern like .venv/
        core = pattern[:-1]
        escaped = re.escape(core)
        return f"(^|/){escaped}(/|$)"

    # Handle wildcard patterns
    # Escape all regex special chars first
    escaped = re.escape(pattern)
    # Convert glob wildcards to regex
    # ** matches any path components
    escaped = escaped.replace(r"\*\*", ".*")
    # * matches anything except /
    escaped = escaped.replace(r"\*", "[^/]*")
    # ? matches single char except /
    escaped = escaped.replace(r"\?", "[^/]")

    return escaped


# mypy severity mapping
# mypy outputs: error, warning, note
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "note": Severity.LOW,
}


class MypyChecker(TypeCheckerPlugin):
    """mypy type checker plugin for Python code analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize MypyChecker.

        Args:
            project_root: Optional project root for finding mypy installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "mypy"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["python"]

    @property
    def supports_strict_mode(self) -> bool:
        """mypy supports strict mode."""
        return True

    def get_version(self) -> str:
        """Get mypy version."""
        try:
            binary = self.ensure_binary()
            # Output is like "mypy 1.8.0 (compiled: yes)"
            return get_cli_version(
                binary, parser=lambda s: s.split()[1] if len(s.split()) >= 2 else s
            )
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure mypy is available.

        Checks for mypy in:
        1. Project's .venv (bin/mypy on Unix, Scripts/mypy.exe on Windows)
        2. System PATH

        Returns:
            Path to mypy binary.

        Raises:
            FileNotFoundError: If mypy is not installed.
        """
        import sys

        # Check project venv first
        if self._project_root:
            if sys.platform == "win32":
                venv_mypy = self._project_root / ".venv" / "Scripts" / "mypy.exe"
            else:
                venv_mypy = self._project_root / ".venv" / "bin" / "mypy"
            if venv_mypy.exists():
                return venv_mypy

        # Check system PATH
        mypy_path = shutil.which("mypy")
        if mypy_path:
            return Path(mypy_path)

        raise FileNotFoundError(
            "mypy is not installed. Install it with: pip install mypy"
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run mypy type checking.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking issues.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        # Build command
        cmd = [
            str(binary),
            "--output", "json",
            "--no-error-summary",
        ]

        # Check for strict mode in config
        if context.config and hasattr(context.config, "type_checking"):
            type_config = context.config.type_checking
            if hasattr(type_config, "strict") and type_config.strict:
                cmd.append("--strict")

        # Check for mypy config file
        mypy_ini = context.project_root / "mypy.ini"
        setup_cfg = context.project_root / "setup.cfg"
        pyproject = context.project_root / "pyproject.toml"

        if mypy_ini.exists():
            cmd.extend(["--config-file", str(mypy_ini)])
        elif setup_cfg.exists():
            cmd.extend(["--config-file", str(setup_cfg)])
        elif pyproject.exists():
            cmd.extend(["--config-file", str(pyproject)])

        # Add paths to check (filter to Python files or directories)
        # When only path is project_root (a directory), pass "." so mypy runs from cwd reliably
        if context.paths:
            python_extensions = {".py", ".pyi", ".pyx"}
            filtered = [
                p for p in context.paths
                if p.is_dir() or p.suffix.lower() in python_extensions
            ]
            if not filtered:
                # No Python files or directories to check
                LOGGER.debug("No Python files or directories in scan paths, skipping mypy")
                return []
            # Single path that is project_root -> use "." for reliable discovery
            if len(filtered) == 1 and filtered[0].resolve() == context.project_root.resolve():
                paths = ["."]
            else:
                paths = [p.as_posix() for p in filtered]
        else:
            paths = ["."]
        cmd.extend(paths)

        # Add exclude patterns (convert glob patterns to regex for mypy)
        exclude_patterns = context.get_exclude_patterns()
        for pattern in exclude_patterns:
            regex_pattern = _glob_to_regex(pattern)
            cmd.extend(["--exclude", regex_pattern])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="mypy",
                stream_handler=context.stream_handler,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("mypy timed out after 180 seconds")
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run mypy: {e}")
            return []

        # Parse output (mypy may write to stdout or stderr depending on version)
        output = result.stdout or result.stderr or ""
        issues = self._parse_output(output, context.project_root)

        LOGGER.info(f"mypy found {len(issues)} issues")
        return issues

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse mypy JSON output.

        Supports: (1) one JSON object per line; (2) single JSON object with
        "messages" array (mypy 2.x).
        """
        if not output or not output.strip():
            return []

        issues = []
        # Try line-by-line (one JSON object per line)
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                # Single object with "messages" array (mypy 2.x)
                if isinstance(obj, dict) and "messages" in obj:
                    for error in obj.get("messages", []):
                        issue = self._error_to_issue(error, project_root)
                        if issue:
                            issues.append(issue)
                    continue
                # Single error object per line
                issue = self._error_to_issue(obj, project_root)
                if issue:
                    issues.append(issue)
            except json.JSONDecodeError:
                LOGGER.debug(f"Skipping non-JSON line: {line[:80]!r}")
                continue

        return issues

    def _error_to_issue(
        self,
        error: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert mypy error to UnifiedIssue.

        Args:
            error: mypy error dict from JSON output.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            severity_str = error.get("severity", "error")
            message = error.get("message", "")
            file = error.get("file", "")
            line = error.get("line")
            column = error.get("column")
            code = error.get("code", "")

            # Get severity
            severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            # Build file path
            file_path = Path(file)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            # Generate deterministic ID
            issue_id = self._generate_issue_id(code, file, line, column, message)

            # Build title
            title = f"[{code}] {message}" if code else message

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="mypy",
                severity=severity,
                rule_id=code or "unknown",
                title=title,
                description=message,
                documentation_url=f"https://mypy.readthedocs.io/en/stable/error_code_list.html#{code}" if code else None,
                file_path=file_path,
                line_start=line,
                line_end=line,
                column_start=column,
                fixable=False,
                metadata={
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse mypy error: {e}")
            return None

    def _generate_issue_id(
        self,
        code: str,
        file: str,
        line: Optional[int],
        column: Optional[int],
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            code: Error code.
            file: File path.
            line: Line number.
            column: Column number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{code}:{file}:{line or 0}:{column or 0}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"mypy-{code}-{hash_val}" if code else f"mypy-{hash_val}"
