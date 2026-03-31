"""dotnet build type checker plugin.

Uses the Roslyn compiler via `dotnet build` to detect type errors,
null reference warnings, and other compile-time diagnostics.
https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-build
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
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

# MSBuild diagnostic level to severity mapping
LEVEL_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
}

# CS error codes that are always high severity
HIGH_SEVERITY_CODES = {
    "CS0029",  # Cannot implicitly convert type
    "CS0103",  # Name does not exist in context
    "CS0246",  # Type or namespace not found
    "CS0266",  # Cannot convert type
    "CS1061",  # Does not contain a definition
    "CS8600",  # Converting null literal
    "CS8602",  # Dereference of a possibly null reference
    "CS8604",  # Possible null reference argument
}


class DotnetBuildChecker(TypeCheckerPlugin):
    """dotnet build plugin for C# type checking and compiler diagnostics."""

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "dotnet_build"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["csharp"]

    @property
    def supports_strict_mode(self) -> bool:
        """Supports Nullable enable (strict null checking)."""
        return True

    def get_version(self) -> str:
        """Get dotnet SDK version."""
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

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run dotnet build for type checking.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking issues.
        """
        try:
            dotnet = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        project_file = find_project_file(context.project_root)
        if not project_file:
            LOGGER.info("No .sln or .csproj found, skipping dotnet build")
            return []

        cmd = [
            str(dotnet),
            "build",
            str(project_file),
            "--no-restore",
            "-v",
            "quiet",
            "-nologo",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        stdout = ""
        stderr = ""
        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="dotnet-build",
                stream_handler=context.stream_handler,
                timeout=300,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except subprocess.TimeoutExpired:
            LOGGER.warning("dotnet build timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message="dotnet build timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.debug(f"dotnet build completed with: {e}")
            stdout = getattr(e, "stdout", "") or ""
            stderr = getattr(e, "stderr", "") or ""

        combined = stdout + "\n" + stderr
        issues = self._parse_output(combined, context.project_root)
        LOGGER.info(f"dotnet build found {len(issues)} issues")
        return issues

    def _parse_output(
        self, output: str, project_root: Path
    ) -> List[UnifiedIssue]:
        """Parse dotnet build MSBuild diagnostic output.

        MSBuild outputs diagnostics in the format:
        path/File.cs(line,col): error CS1234: Message [project.csproj]

        Args:
            output: Raw stdout/stderr from dotnet build.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        issues = []
        seen_ids: set[str] = set()

        # Match MSBuild diagnostic format:
        # path/File.cs(10,5): error CS0103: The name 'x' does not exist [proj.csproj]
        # path/File.cs(10,5): warning CS8600: Converting null literal [proj.csproj]
        # My Project/File.cs(10,5): error CS0103: ... [proj.csproj]
        pattern = re.compile(
            r"(.+?\.cs)\((\d+),(\d+)\):\s+"
            r"(error|warning)\s+"
            r"(CS\d+):\s+"
            r"(.+?)(?:\s*\[|$)"
        )

        for line in output.splitlines():
            match = pattern.search(line.strip())
            if not match:
                continue

            file_str, line_str, col_str, level, code, message = match.groups()

            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            line_num = int(line_str)
            col_num = int(col_str)

            severity = self._get_severity(code, level)

            content = f"dotnet_build:{code}:{file_str}:{line_num}:{col_num}:{message.strip()}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
            issue_id = f"dotnet-build-{hash_val}"

            if issue_id in seen_ids:
                continue
            seen_ids.add(issue_id)

            issues.append(
                UnifiedIssue(
                    id=issue_id,
                    domain=ToolDomain.TYPE_CHECKING,
                    source_tool="dotnet_build",
                    severity=severity,
                    rule_id=code,
                    title=f"[{code}] {message.strip()}",
                    description=message.strip(),
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    column_start=col_num,
                    fixable=False,
                    metadata={
                        "level": level,
                        "code": code,
                    },
                )
            )

        return issues

    def _get_severity(self, code: str, level: str) -> Severity:
        """Get severity for a compiler diagnostic.

        Args:
            code: Diagnostic code (e.g., "CS0103").
            level: Diagnostic level (error, warning).

        Returns:
            Severity level.
        """
        if code in HIGH_SEVERITY_CODES:
            return Severity.HIGH

        return LEVEL_SEVERITY.get(level, Severity.MEDIUM)
