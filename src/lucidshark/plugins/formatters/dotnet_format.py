"""dotnet format formatter plugin.

Uses `dotnet format whitespace` for C# code formatting.
https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-format
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
from lucidshark.plugins.dotnet_utils import find_dotnet, find_project_file
from lucidshark.plugins.formatters.base import FormatterPlugin
from lucidshark.plugins.linters.base import FixResult
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

CS_EXTENSIONS = {".cs"}


class DotnetFormatFormatter(FormatterPlugin):
    """dotnet format formatter plugin for C# code formatting."""

    @property
    def name(self) -> str:
        return "dotnet_format_whitespace"

    @property
    def languages(self) -> List[str]:
        return ["csharp"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        return find_dotnet()

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Check formatting without modifying files.

        Uses `dotnet format whitespace --verify-no-changes` to detect
        whitespace/formatting violations.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of UnifiedIssue objects for each formatting violation.
        """
        try:
            dotnet = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        project_file = find_project_file(context.project_root)
        if not project_file:
            LOGGER.info("No .sln or .csproj found, skipping dotnet format whitespace")
            return []

        cmd = [
            str(dotnet),
            "format",
            "whitespace",
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
                tool_name="dotnet-format-whitespace",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("dotnet format whitespace timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="dotnet format whitespace timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run dotnet format whitespace: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run dotnet format whitespace: {e}",
            )
            return []

        if result.returncode == 0:
            return []

        # Parse output for formatted files
        issues = []
        seen_files: set[str] = set()
        combined = (result.stdout or "") + "\n" + (result.stderr or "")

        for line in combined.splitlines():
            line = line.strip()
            # dotnet format outputs lines like:
            # "Formatted code file '<path>'."
            if "Formatted code file" in line:
                # Extract path between single quotes
                start = line.find("'")
                end = line.rfind("'")
                if start >= 0 and end > start:
                    file_path_str = line[start + 1 : end]
                    if file_path_str not in seen_files:
                        seen_files.add(file_path_str)

            # Also match .cs file paths that appear in diagnostic output
            if line.endswith(".cs") or ".cs(" in line:
                for part in line.split():
                    if part.endswith(".cs") or ".cs(" in part:
                        clean = part.split("(")[0].strip()
                        if clean.endswith(".cs") and clean not in seen_files:
                            seen_files.add(clean)

        for file_path_str in sorted(seen_files):
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"dotnet_format_whitespace:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"dotnet-format-ws-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="dotnet_format_whitespace",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match dotnet format whitespace style.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run dotnet format whitespace to fix formatting.",
                )
            )

        LOGGER.info(f"dotnet format whitespace found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply formatting fixes.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            FixResult with statistics about fixes applied.
        """
        try:
            dotnet = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        project_file = find_project_file(context.project_root)
        if not project_file:
            return FixResult()

        pre_issues = self.check(context)

        cmd = [str(dotnet), "format", "whitespace", str(project_file)]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="dotnet-format-whitespace-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run dotnet format whitespace: {e}")
            return FixResult()

        post_issues = self.check(context)

        fixed = len(pre_issues) - len(post_issues)
        files_modified = len(
            {str(i.file_path) for i in pre_issues}
            - {str(i.file_path) for i in post_issues}
        )

        return FixResult(
            files_modified=files_modified,
            issues_fixed=max(fixed, 0),
            issues_remaining=len(post_issues),
        )
