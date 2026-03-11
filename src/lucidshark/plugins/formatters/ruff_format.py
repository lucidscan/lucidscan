"""Ruff formatter plugin.

Wraps `ruff format` for Python code formatting.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import List

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.formatters.base import FormatterPlugin
from lucidshark.plugins.linters.base import FixResult
from lucidshark.plugins.utils import ensure_python_binary, get_cli_version

LOGGER = get_logger(__name__)

PYTHON_EXTENSIONS = {".py", ".pyi", ".pyw"}


class RuffFormatter(FormatterPlugin):
    """Ruff formatter plugin for Python code formatting."""

    @property
    def name(self) -> str:
        return "ruff_format"

    @property
    def languages(self) -> List[str]:
        return ["python"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        return ensure_python_binary(
            self._project_root,
            "ruff",
            "Ruff is not installed. Install it with:\n"
            "  pip install ruff\n"
            "  OR\n"
            "  uv add --dev ruff",
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        cmd = [str(binary), "format", "--check"]

        paths = self._resolve_paths(context, PYTHON_EXTENSIONS, fallback_to_cwd=True)
        if not paths:
            LOGGER.debug("No Python files to format-check")
            return []

        cmd.extend(paths)

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ruff-format",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Ruff format check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="Ruff format check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run ruff format: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run ruff format: {e}",
            )
            return []

        if result.returncode == 0:
            return []

        # Parse output: each line is a file that would be reformatted
        issues = []
        stdout = result.stdout.strip() if result.stdout else ""
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("error"):
                continue
            # Line format: "Would reformat: path/to/file.py" or just the file path
            file_path_str = line.replace("Would reformat: ", "").strip()
            if not file_path_str:
                continue
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"ruff_format:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"ruff_format-format-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="ruff_format",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match ruff format style.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run ruff format to fix formatting.",
                )
            )

        LOGGER.info(f"Ruff format found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        cmd = [str(binary), "format"]

        paths = self._resolve_paths(context, PYTHON_EXTENSIONS, fallback_to_cwd=True)
        if not paths:
            return FixResult()

        cmd.extend(paths)

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ruff-format-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run ruff format: {e}")
            return FixResult()

        # Count reformatted files from ruff output (e.g. "1 file reformatted")
        fixed = 0
        stdout = result.stdout.strip() if result.stdout else ""
        for line in stdout.splitlines():
            if "reformatted" in line.lower():
                parts = line.split()
                if parts and parts[0].isdigit():
                    fixed = int(parts[0])
                    break

        # Domain runner calls check() after fix to get remaining issues
        return FixResult(
            files_modified=fixed,
            issues_fixed=fixed,
            issues_remaining=0,
        )
