"""Scalafmt formatter plugin.

Scalafmt is the standard code formatter for Scala.
https://scalameta.org/scalafmt/
"""

from __future__ import annotations

import hashlib
import re
import shutil
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

LOGGER = get_logger(__name__)

SCALA_EXTENSIONS = {".scala", ".sc", ".sbt"}


class ScalafmtFormatter(FormatterPlugin):
    """Scalafmt formatter plugin for Scala code formatting."""

    @property
    def name(self) -> str:
        return "scalafmt"

    @property
    def languages(self) -> List[str]:
        return ["scala"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                match = re.search(r"(\d+\.\d+\.\d+)", output)
                if match:
                    return match.group(1)
                return output if output else "unknown"
        except Exception:
            pass
        return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure scalafmt is available on PATH.

        Returns:
            Path to the scalafmt binary.

        Raises:
            FileNotFoundError: If scalafmt is not installed.
        """
        system_binary = shutil.which("scalafmt")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "scalafmt is not installed. Install it with:\n"
            "  cs install scalafmt\n"
            "or add sbt-scalafmt plugin to your build."
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Check formatting without modifying files."""
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
                suggestion="Install scalafmt: cs install scalafmt",
            )
            return []

        paths = self._resolve_paths(context, SCALA_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            LOGGER.debug("No Scala files to format-check")
            return []

        # scalafmt --check --list returns non-zero and lists unformatted files
        cmd = [str(binary), "--check", "--list"] + paths

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="scalafmt",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("scalafmt check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="scalafmt check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run scalafmt: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run scalafmt: {e}",
            )
            return []

        if result.returncode == 0:
            return []

        # Parse output: scalafmt --list outputs unformatted file paths
        issues = []
        seen_files: set[str] = set()
        for output in (result.stdout or "", result.stderr or ""):
            for line in output.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # scalafmt --list outputs file paths that need formatting
                if line.endswith((".scala", ".sc", ".sbt")):
                    if line not in seen_files:
                        seen_files.add(line)

        for file_path_str in sorted(seen_files):
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"scalafmt:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"scalafmt-format-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="scalafmt",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match scalafmt style.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run scalafmt to fix formatting.",
                )
            )

        LOGGER.info(f"scalafmt found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply formatting fixes."""
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        paths = self._resolve_paths(context, SCALA_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            return FixResult()

        cmd = [str(binary)] + paths

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="scalafmt-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run scalafmt: {e}")
            return FixResult()

        return FixResult(
            files_modified=len(paths),
            issues_fixed=0,
            issues_remaining=0,
        )
