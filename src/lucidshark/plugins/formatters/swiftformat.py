"""SwiftFormat formatter plugin.

Wraps `swiftformat` for Swift code formatting.
https://github.com/nicklockwood/SwiftFormat
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

SWIFT_EXTENSIONS = {".swift"}


class SwiftFormatFormatter(FormatterPlugin):
    """SwiftFormat formatter plugin for Swift code formatting."""

    @property
    def name(self) -> str:
        return "swiftformat"

    @property
    def languages(self) -> List[str]:
        return ["swift"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        system_binary = shutil.which("swiftformat")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "swiftformat is not installed. Install it with:\n"
            "  brew install swiftformat  (macOS)\n"
            "  or see https://github.com/nicklockwood/SwiftFormat#installation"
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        paths = self._resolve_paths(context, SWIFT_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            LOGGER.debug("No Swift files to format-check")
            return []

        # swiftformat --lint reports formatting issues without modifying files
        cmd = [str(binary), "--lint"] + paths

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="swiftformat",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("swiftformat check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="swiftformat check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run swiftformat: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run swiftformat: {e}",
            )
            return []

        if result.returncode == 0:
            return []

        # Parse output: swiftformat --lint outputs warnings to stderr
        # Format: "warning: <file>:<line>:<col>: <rule> <message>"
        # or just: "<file>: warning: <message>"
        issues = []
        seen_files: set[str] = set()
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""

        for output in (stdout, stderr):
            for line in output.splitlines():
                line = line.strip()
                # Look for file paths with .swift extension
                if ".swift" in line and ("warning:" in line or "error:" in line):
                    # Extract file path - it appears before the warning/error
                    parts = line.split(":")
                    for i, part in enumerate(parts):
                        if part.strip().endswith(".swift"):
                            file_path_str = ":".join(parts[: i + 1]).strip()
                            # Clean up leading "warning: " or similar
                            for prefix in ("warning: ", "error: "):
                                if file_path_str.startswith(prefix):
                                    file_path_str = file_path_str[len(prefix) :]
                            if file_path_str not in seen_files:
                                seen_files.add(file_path_str)
                            break

        for file_path_str in sorted(seen_files):
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"swiftformat:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"swiftformat-format-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="swiftformat",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match SwiftFormat style.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run swiftformat to fix formatting.",
                )
            )

        LOGGER.info(f"swiftformat found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        paths = self._resolve_paths(context, SWIFT_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            return FixResult()

        cmd = [str(binary)] + paths

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="swiftformat-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run swiftformat: {e}")
            return FixResult()

        # Domain runner calls check() after fix to get remaining issues
        return FixResult(
            files_modified=len(paths),
            issues_fixed=0,
            issues_remaining=0,
        )
