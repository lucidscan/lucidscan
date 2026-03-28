"""clang-format formatter plugin.

Wraps `clang-format` for C++ code formatting.
https://clang.llvm.org/docs/ClangFormat.html
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
from lucidshark.plugins.cpp_utils import (
    CPP_EXTENSIONS,
    ensure_cpp_tools_in_path,
    find_clang_format,
    get_tool_version,
)
from lucidshark.plugins.formatters.base import FormatterPlugin
from lucidshark.plugins.linters.base import FixResult

LOGGER = get_logger(__name__)


class ClangFormatFormatter(FormatterPlugin):
    """clang-format formatter plugin for C++ code formatting."""

    @property
    def name(self) -> str:
        return "clang_format"

    @property
    def languages(self) -> List[str]:
        return ["c++"]

    def get_version(self) -> str:
        return get_tool_version(find_clang_format)

    def ensure_binary(self) -> Path:
        return find_clang_format()

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Check formatting without modifying files.

        Uses clang-format --dry-run --Werror to detect formatting violations.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of formatting issues.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        paths = self._resolve_paths(context, CPP_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            LOGGER.debug("No C++ files to format-check")
            return []

        cmd = [str(binary), "--dry-run", "--Werror"] + paths

        env_vars = ensure_cpp_tools_in_path()

        try:
            with temporary_env(env_vars):
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="clang-format",
                    stream_handler=context.stream_handler,
                    timeout=120,
                )
        except subprocess.TimeoutExpired:
            LOGGER.warning("clang-format check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="clang-format check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run clang-format: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run clang-format: {e}",
            )
            return []

        # clang-format --dry-run --Werror outputs warnings to stderr
        # for files that would be reformatted
        stderr = result.stderr or ""
        stdout = result.stdout or ""
        combined = stderr + "\n" + stdout

        issues = self._parse_check_output(combined, context.project_root)
        LOGGER.info(f"clang-format found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply formatting fixes.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            FixResult with statistics.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        paths = self._resolve_paths(context, CPP_EXTENSIONS, fallback_to_cwd=False)
        if not paths:
            return FixResult()

        cmd = [str(binary), "-i"] + paths

        env_vars = ensure_cpp_tools_in_path()

        try:
            with temporary_env(env_vars):
                run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="clang-format-fix",
                    stream_handler=context.stream_handler,
                    timeout=120,
                )
        except Exception as e:
            LOGGER.error(f"Failed to run clang-format: {e}")
            return FixResult()

        return FixResult(
            files_modified=len(paths),
            issues_fixed=0,
            issues_remaining=0,
        )

    def _parse_check_output(
        self, output: str, project_root: Path
    ) -> List[UnifiedIssue]:
        """Parse clang-format --dry-run --Werror output.

        clang-format outputs lines like:
            /path/to/file.cpp:42:15: warning: code should be clang-formatted [-Wclang-format-violations]

        Args:
            output: Combined stderr/stdout from clang-format.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        issues = []
        seen_files = set()

        import re

        # Pattern matches clang-format warning lines
        warning_re = re.compile(
            r"^(.+\.(?:cpp|cc|cxx|hpp|h|hh|hxx)):(\d+):\d+:\s+warning:"
        )

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            match = warning_re.match(line)
            if match:
                file_str = match.group(1)

                # Only create one issue per file
                if file_str in seen_files:
                    continue
                seen_files.add(file_str)

                file_path = Path(file_str)
                if not file_path.is_absolute():
                    file_path = project_root / file_path

                content = f"clang-format:{file_str}"
                hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

                issues.append(
                    UnifiedIssue(
                        id=f"clang-format-{hash_val}",
                        domain=ToolDomain.FORMATTING,
                        source_tool="clang-format",
                        severity=Severity.LOW,
                        rule_id="format",
                        title=f"File needs formatting: {file_str}",
                        description=f"File {file_str} does not match clang-format style.",
                        file_path=file_path,
                        fixable=True,
                        suggested_fix="Run clang-format to fix formatting.",
                    )
                )

        return issues
