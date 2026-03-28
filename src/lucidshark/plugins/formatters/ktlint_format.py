"""Ktlint formatter plugin.

Wraps `ktlint --format` for Kotlin code formatting.
https://pinterest.github.io/ktlint/
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import List, Optional

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
from lucidshark.plugins.linters.ktlint import KtlintLinter

LOGGER = get_logger(__name__)

KOTLIN_EXTENSIONS = {".kt", ".kts"}


class KtlintFormatter(FormatterPlugin):
    """Ktlint formatter plugin for Kotlin code formatting.

    Reuses the ktlint linter's binary management. ktlint's --format flag
    rewrites files to match the Kotlin coding conventions.
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        super().__init__(project_root=project_root, **kwargs)
        self._ktlint = KtlintLinter(project_root=project_root)

    @property
    def name(self) -> str:
        return "ktlint_format"

    @property
    def languages(self) -> List[str]:
        return ["kotlin"]

    def get_version(self) -> str:
        return self._ktlint.get_version()

    def ensure_binary(self) -> Path:
        return self._ktlint.ensure_binary()

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Check formatting by running ktlint in lint-only mode.

        Files that have style violations are reported as formatting issues.
        """
        try:
            jar_path = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        paths = self._resolve_paths(context, KOTLIN_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            LOGGER.debug("No Kotlin files to format-check")
            return []

        cmd = [
            "java",
            "-jar",
            str(jar_path),
            "--reporter=plain",
        ]
        cmd.extend(paths)

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ktlint-format-check",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("ktlint format check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="ktlint format check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run ktlint format check: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run ktlint format check: {e}",
            )
            return []

        stdout = result.stdout.strip() if result.stdout else ""
        if not stdout:
            return []

        # ktlint plain output: "file:line:col: message (rule)"
        # Collect unique files with issues
        files_with_issues: set[str] = set()
        for line in stdout.splitlines():
            line = line.strip()
            if ":" in line:
                file_part = line.split(":")[0]
                if file_part:
                    files_with_issues.add(file_part)

        issues = []
        for file_path_str in sorted(files_with_issues):
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"ktlint_format:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"ktlint_format-format-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="ktlint_format",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match Kotlin coding conventions.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run ktlint --format to fix formatting.",
                )
            )

        LOGGER.info(f"ktlint formatter found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply formatting fixes using ktlint --format."""
        try:
            jar_path = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        paths = self._resolve_paths(context, KOTLIN_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            return FixResult()

        cmd = [
            "java",
            "-jar",
            str(jar_path),
            "--format",
        ]
        cmd.extend(paths)

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ktlint-format-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run ktlint format: {e}")
            return FixResult()

        return FixResult(
            files_modified=len(paths),
            issues_fixed=0,
            issues_remaining=0,
        )
