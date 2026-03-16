"""Gofmt formatter plugin.

Wraps `gofmt` for Go code formatting.
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
from lucidshark.core.subprocess_runner import run_with_streaming, temporary_env
from lucidshark.plugins.formatters.base import FormatterPlugin
from lucidshark.plugins.go_utils import ensure_go_in_path, find_gofmt
from lucidshark.plugins.linters.base import FixResult

LOGGER = get_logger(__name__)

GO_EXTENSIONS = {".go"}


class GofmtFormatter(FormatterPlugin):
    """Gofmt formatter plugin for Go code formatting."""

    @property
    def name(self) -> str:
        return "gofmt"

    @property
    def languages(self) -> List[str]:
        return ["go"]

    def get_version(self) -> str:
        try:
            self.ensure_binary()
            # gofmt doesn't have a --version flag; report as installed
            return "installed"
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        return find_gofmt()

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        paths = self._resolve_paths(context, GO_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            LOGGER.debug("No Go files to format-check")
            return []

        cmd = [str(binary), "-l"] + paths

        # Ensure 'go' command is in PATH
        env_vars = ensure_go_in_path()

        try:
            with temporary_env(env_vars):
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="gofmt",
                    stream_handler=context.stream_handler,
                    timeout=120,
                )
        except subprocess.TimeoutExpired:
            LOGGER.warning("gofmt check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="gofmt check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run gofmt: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run gofmt: {e}",
            )
            return []

        # gofmt -l always returns exit code 0; stdout lists files needing formatting
        stdout = result.stdout.strip() if result.stdout else ""
        if not stdout:
            return []

        issues = []
        for line in stdout.splitlines():
            file_path_str = line.strip()
            if not file_path_str:
                continue

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"gofmt:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"gofmt-format-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="gofmt",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match gofmt style.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run gofmt to fix formatting.",
                )
            )

        LOGGER.info(f"gofmt found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        paths = self._resolve_paths(context, GO_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            return FixResult()

        cmd = [str(binary), "-w"] + paths

        # Ensure 'go' command is in PATH
        env_vars = ensure_go_in_path()

        try:
            with temporary_env(env_vars):
                run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="gofmt-fix",
                    stream_handler=context.stream_handler,
                    timeout=120,
                )
        except Exception as e:
            LOGGER.error(f"Failed to run gofmt: {e}")
            return FixResult()

        # Domain runner calls check() after fix to get remaining issues
        return FixResult(
            files_modified=len(paths),
            issues_fixed=0,
            issues_remaining=0,
        )
