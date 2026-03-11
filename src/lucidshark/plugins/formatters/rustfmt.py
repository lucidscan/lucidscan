"""Rustfmt formatter plugin.

Wraps `rustfmt` for Rust code formatting.
"""

from __future__ import annotations

import hashlib
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
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

RUST_EXTENSIONS = {".rs"}


class RustfmtFormatter(FormatterPlugin):
    """Rustfmt formatter plugin for Rust code formatting."""

    @property
    def name(self) -> str:
        return "rustfmt"

    @property
    def languages(self) -> List[str]:
        return ["rust"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        system_binary = shutil.which("rustfmt")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "rustfmt is not installed. Install it with:\n  rustup component add rustfmt"
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        paths = self._resolve_paths(context, RUST_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            LOGGER.debug("No Rust files to format-check")
            return []

        cmd = [str(binary), "--check"] + paths

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="rustfmt",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("rustfmt check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="rustfmt check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run rustfmt: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run rustfmt: {e}",
            )
            return []

        if result.returncode == 0:
            return []

        # Parse output: rustfmt outputs diff to stdout on check failure.
        # Extract file paths from "Diff in" lines or "--- a/path" lines.
        issues = []
        seen_files: set[str] = set()
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        # rustfmt --check outputs diff with "Diff in <path>" headers
        for output in (stdout, stderr):
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("Diff in "):
                    # Format: "Diff in /path/to/file.rs at line N:"
                    parts = line[len("Diff in ") :].split(" at line ")
                    file_path_str = parts[0].strip().rstrip(":")
                    if file_path_str not in seen_files:
                        seen_files.add(file_path_str)

        for file_path_str in sorted(seen_files):
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"rustfmt:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"rustfmt-format-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="rustfmt",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match rustfmt style.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run rustfmt to fix formatting.",
                )
            )

        LOGGER.info(f"rustfmt found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        paths = self._resolve_paths(context, RUST_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            return FixResult()

        cmd = [str(binary)] + paths

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="rustfmt-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run rustfmt: {e}")
            return FixResult()

        # Domain runner calls check() after fix to get remaining issues
        return FixResult(
            files_modified=len(paths),
            issues_fixed=0,
            issues_remaining=0,
        )
