"""RuboCop formatter plugin.

Wraps RuboCop's Layout cops for Ruby code formatting.
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
from lucidshark.plugins.linters.rubocop import _find_rubocop

LOGGER = get_logger(__name__)

RUBY_EXTENSIONS = {".rb", ".rake", ".gemspec"}


class RubocopFormatter(FormatterPlugin):
    """RuboCop formatter plugin for Ruby code formatting.

    Uses RuboCop's Layout cops for format checking and auto-correction.
    """

    @property
    def name(self) -> str:
        return "rubocop_format"

    @property
    def languages(self) -> List[str]:
        return ["ruby"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            from lucidshark.plugins.utils import get_cli_version

            return get_cli_version(
                binary,
                parser=lambda s: s.strip().split()[-1] if s.strip() else "unknown",
            )
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        return _find_rubocop(self._project_root)

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        paths = self._resolve_paths(context, RUBY_EXTENSIONS, fallback_to_cwd=True)
        if not paths:
            LOGGER.debug("No Ruby files to format-check")
            return []

        cmd = [
            str(binary),
            "--format",
            "json",
            "--force-exclusion",
            "--only",
            "Layout",
        ]
        cmd.extend(paths)

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="rubocop-format",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("RuboCop format check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="RuboCop format check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run rubocop format: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run rubocop format: {e}",
            )
            return []

        stdout = result.stdout or ""
        return self._parse_output(stdout, context.project_root)

    def fix(self, context: ScanContext) -> FixResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        paths = self._resolve_paths(context, RUBY_EXTENSIONS, fallback_to_cwd=True)
        if not paths:
            return FixResult()

        cmd = [
            str(binary),
            "--format",
            "json",
            "--force-exclusion",
            "--only",
            "Layout",
            "-a",
        ]
        cmd.extend(paths)

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="rubocop-format-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run rubocop format fix: {e}")
            return FixResult()

        # Count corrected offenses from JSON output
        fixed = 0
        stdout = result.stdout or ""
        if stdout.strip():
            try:
                import json

                data = json.loads(stdout)
                for file_data in data.get("files", []):
                    for offense in file_data.get("offenses", []):
                        if offense.get("corrected", False):
                            fixed += 1
            except (json.JSONDecodeError, KeyError):
                pass

        return FixResult(
            files_modified=fixed,
            issues_fixed=fixed,
            issues_remaining=0,
        )

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        if not output.strip():
            return []

        try:
            import json

            data = json.loads(output)
        except (json.JSONDecodeError, ValueError):
            LOGGER.warning("Failed to parse RuboCop format output as JSON")
            return []

        issues = []
        for file_data in data.get("files", []):
            file_path_str = file_data.get("path", "")
            offenses = file_data.get("offenses", [])

            if not offenses:
                continue

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            for offense in offenses:
                cop_name = offense.get("cop_name", "")
                message = offense.get("message", "")
                correctable = offense.get("correctable", False)
                location = offense.get("location", {})

                content = f"rubocop_format:{file_path_str}:{cop_name}:{location.get('line', 0)}"
                hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

                issues.append(
                    UnifiedIssue(
                        id=f"rubocop_format-{hash_val}",
                        domain=ToolDomain.FORMATTING,
                        source_tool="rubocop_format",
                        severity=Severity.LOW,
                        rule_id=cop_name or "format",
                        title=f"Formatting issue: {cop_name}: {message}",
                        description=f"{message} ({cop_name})",
                        file_path=file_path,
                        line_start=location.get("start_line") or location.get("line"),
                        line_end=location.get("last_line"),
                        column_start=location.get("start_column")
                        or location.get("column"),
                        column_end=location.get("last_column"),
                        fixable=correctable,
                        suggested_fix="Run rubocop -a --only Layout to fix formatting.",
                    )
                )

        LOGGER.info(f"RuboCop format found {len(issues)} issues")
        return issues
