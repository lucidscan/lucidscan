"""dotnet format linter plugin.

Uses `dotnet format` in verify mode to detect C# code style violations.
https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-format
"""

from __future__ import annotations

import hashlib
import re
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
from lucidshark.plugins.dotnet_utils import find_dotnet, find_project_file
from lucidshark.plugins.linters.base import FixResult, LinterPlugin
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

# Diagnostic severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "info": Severity.LOW,
}


class DotnetFormatLinter(LinterPlugin):
    """dotnet format linter plugin for C# code style analysis."""

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "dotnet_format"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["csharp"]

    @property
    def supports_fix(self) -> bool:
        """dotnet format supports auto-fix."""
        return True

    def get_version(self) -> str:
        """Get dotnet format version."""
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure dotnet CLI is available.

        Returns:
            Path to dotnet binary.

        Raises:
            FileNotFoundError: If dotnet is not installed.
        """
        return find_dotnet()

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run dotnet format in verify mode.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        try:
            dotnet = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        project_file = find_project_file(context.project_root)
        if not project_file:
            LOGGER.info("No .sln or .csproj found, skipping dotnet format")
            return []

        cmd = [
            str(dotnet),
            "format",
            "style",
            str(project_file),
            "--verify-no-changes",
            "--verbosity",
            "diagnostic",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="dotnet-format",
                stream_handler=context.stream_handler,
                timeout=300,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except subprocess.TimeoutExpired:
            LOGGER.warning("dotnet format timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="dotnet format timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.debug(f"dotnet format completed with: {e}")
            stdout = getattr(e, "stdout", "") or ""
            stderr = getattr(e, "stderr", "") or ""

        issues = self._parse_output(stdout + "\n" + stderr, context.project_root)
        LOGGER.info(f"dotnet format found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply dotnet format auto-fixes.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            FixResult with statistics.
        """
        try:
            dotnet = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        project_file = find_project_file(context.project_root)
        if not project_file:
            return FixResult()

        pre_issues = self.lint(context)

        cmd = [str(dotnet), "format", "style", str(project_file)]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="dotnet-format-fix",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except Exception as e:
            LOGGER.debug(f"dotnet format fix completed with: {e}")

        post_issues = self.lint(context)

        return self._calculate_fix_stats(pre_issues, post_issues)

    def _parse_output(
        self, output: str, project_root: Path
    ) -> List[UnifiedIssue]:
        """Parse dotnet format diagnostic output.

        Args:
            output: Combined stdout/stderr from dotnet format.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        issues = []
        seen_ids: set[str] = set()

        # Match patterns like:
        # path/File.cs(10,5): warning IDE0055: Fix formatting
        # path/File.cs(10): info IDE0003: Remove this qualification
        # My Project/File.cs(10,5): warning IDE0055: Fix formatting
        pattern = re.compile(
            r"(.+?\.cs)\((\d+)(?:,(\d+))?\):\s+"
            r"(error|warning|info)\s+"
            r"(\w+):\s+"
            r"(.+?)(?:\s*\[|$)"
        )

        for line in output.splitlines():
            match = pattern.search(line.strip())
            if not match:
                continue

            file_str, line_str, col_str, level, rule_id, message = match.groups()

            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            line_num = int(line_str)
            col_num = int(col_str) if col_str else None
            severity = SEVERITY_MAP.get(level, Severity.MEDIUM)

            content = f"dotnet_format:{rule_id}:{file_str}:{line_num}:{col_num}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
            issue_id = f"dotnet-format-{hash_val}"

            if issue_id in seen_ids:
                continue
            seen_ids.add(issue_id)

            issues.append(
                UnifiedIssue(
                    id=issue_id,
                    domain=ToolDomain.LINTING,
                    source_tool="dotnet_format",
                    severity=severity,
                    rule_id=rule_id,
                    title=f"[{rule_id}] {message.strip()}",
                    description=message.strip(),
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    column_start=col_num,
                    fixable=self.supports_fix,
                    suggested_fix="Run dotnet format to fix style issues.",
                    metadata={
                        "level": level,
                        "rule_id": rule_id,
                    },
                )
            )

        return issues
