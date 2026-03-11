"""pyright type checker plugin.

pyright is a fast static type checker for Python.
https://github.com/microsoft/pyright

Note: pyright must be installed via npm or pip. LucidShark does not download it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.paths import resolve_node_bin
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin

LOGGER = get_logger(__name__)

# pyright severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "information": Severity.LOW,
}


class PyrightChecker(TypeCheckerPlugin):
    """pyright type checker plugin for Python code analysis."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
    ):
        """Initialize PyrightChecker.

        Args:
            project_root: Optional project root for tool installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "pyright"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["python"]

    @property
    def supports_strict_mode(self) -> bool:
        """pyright supports strict mode."""
        return True

    def ensure_binary(self) -> Path:
        """Ensure pyright is available.

        Checks for pyright in:
        1. Project's .venv/bin/pyright (pip installed pyright)
        2. Project's node_modules/.bin/pyright
        3. System PATH (npm or pip installed)

        Returns:
            Path to pyright binary.

        Raises:
            FileNotFoundError: If pyright is not installed.
        """
        # Check project venv first (pip install pyright)
        if self._project_root:
            venv_pyright = self._project_root / ".venv" / "bin" / "pyright"
            if venv_pyright.exists():
                return venv_pyright

        # Check project node_modules
        if self._project_root:
            node_pyright = resolve_node_bin(self._project_root, "pyright")
            if node_pyright:
                return node_pyright

        # Check system PATH (npm or pip installed)
        pyright_path = shutil.which("pyright")
        if pyright_path:
            return Path(pyright_path)

        raise FileNotFoundError(
            "pyright is not installed. Install it with:\n"
            "  pip install pyright\n"
            "  OR\n"
            "  npm install -g pyright"
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run pyright type checking.

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
            "--outputjson",
        ]

        # Add paths to check
        paths = [str(p) for p in context.paths] if context.paths else ["."]
        cmd.extend(paths)

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(context.project_root),
                timeout=180,  # 3 minute timeout
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("pyright timed out after 180 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message="pyright timed out after 180 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run pyright: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run pyright: {e}",
            )
            return []

        # Parse output
        issues = self._parse_output(result.stdout, context.project_root)

        LOGGER.info(f"pyright found {len(issues)} issues")
        return issues

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse pyright JSON output.

        Args:
            output: JSON output from pyright.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse pyright output as JSON")
            return []

        issues = []
        diagnostics = data.get("generalDiagnostics", [])

        for diagnostic in diagnostics:
            issue = self._diagnostic_to_issue(diagnostic, project_root)
            if issue:
                issues.append(issue)

        return issues

    def _diagnostic_to_issue(
        self,
        diagnostic: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert pyright diagnostic to UnifiedIssue.

        Args:
            diagnostic: pyright diagnostic dict.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            severity_str = diagnostic.get("severity", "error")
            message = diagnostic.get("message", "")
            file = diagnostic.get("file", "")
            rule = diagnostic.get("rule", "")

            # Get range info
            range_info = diagnostic.get("range", {})
            start = range_info.get("start", {})
            end = range_info.get("end", {})

            line_start = start.get("line", 0) + 1  # pyright uses 0-based lines
            line_end = end.get("line", 0) + 1
            column = start.get("character", 0) + 1

            # Get severity
            severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            # Build file path
            file_path = Path(file)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            # Generate deterministic ID
            issue_id = self._generate_issue_id(rule, file, line_start, column, message)

            # Build title
            title = f"[{rule}] {message}" if rule else message

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="pyright",
                severity=severity,
                rule_id=rule or "unknown",
                title=title,
                description=message,
                documentation_url="https://github.com/microsoft/pyright/blob/main/docs/configuration.md",
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                column_start=column,
                fixable=False,
                metadata={
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse pyright diagnostic: {e}")
            return None

    def _generate_issue_id(
        self,
        rule: str,
        file: str,
        line: int,
        column: int,
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            rule: Error rule/code.
            file: File path.
            line: Line number.
            column: Column number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{rule}:{file}:{line}:{column}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"pyright-{rule}-{hash_val}" if rule else f"pyright-{hash_val}"
