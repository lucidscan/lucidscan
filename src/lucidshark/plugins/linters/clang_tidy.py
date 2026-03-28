"""clang-tidy linter plugin.

clang-tidy is a clang-based C/C++ linter that provides diagnostics and
fixes for typical programming errors, style violations, and
interface misuse.
https://clang.llvm.org/extra/clang-tidy/
"""

from __future__ import annotations

import re
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
from lucidshark.core.subprocess_runner import run_with_streaming, temporary_env
from lucidshark.plugins.cpp_utils import (
    CPP_EXTENSIONS,
    ensure_cpp_tools_in_path,
    find_build_dir,
    find_clang_tidy,
    generate_issue_id,
    get_tool_version,
)
from lucidshark.plugins.linters.base import FixResult, LinterPlugin

LOGGER = get_logger(__name__)

# clang-tidy check category to severity mapping
CATEGORY_SEVERITY = {
    # High severity - correctness and security
    "bugprone": Severity.HIGH,
    "cert": Severity.HIGH,
    "concurrency": Severity.HIGH,
    "cppcoreguidelines": Severity.MEDIUM,
    "clang-analyzer": Severity.HIGH,
    "clang-diagnostic": Severity.HIGH,
    # Medium severity - potential bugs and performance
    "misc": Severity.MEDIUM,
    "modernize": Severity.MEDIUM,
    "performance": Severity.MEDIUM,
    "portability": Severity.MEDIUM,
    "hicpp": Severity.MEDIUM,
    # Low severity - style and readability
    "readability": Severity.LOW,
    "google": Severity.LOW,
    "llvm": Severity.LOW,
    "fuchsia": Severity.LOW,
    "abseil": Severity.LOW,
    "android": Severity.LOW,
    "darwin": Severity.LOW,
    "linuxkernel": Severity.LOW,
    "objc": Severity.LOW,
    "zircon": Severity.LOW,
    "altera": Severity.LOW,
    "boost": Severity.LOW,
}

# Diagnostic severity level from clang-tidy output
DIAG_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "note": Severity.LOW,
}

# Regex for parsing clang-tidy output lines:
#   /path/to/file.cpp:42:15: warning: some message [check-name]
_DIAG_RE = re.compile(
    r"^(.+?):(\d+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[([^\]]+)\])?$"
)


class ClangTidyLinter(LinterPlugin):
    """clang-tidy linter plugin for C/C++ code analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "clang_tidy"

    @property
    def languages(self) -> List[str]:
        return ["c", "c++"]

    @property
    def supports_fix(self) -> bool:
        return True

    def get_version(self) -> str:
        return get_tool_version(find_clang_tidy)

    def ensure_binary(self) -> Path:
        return find_clang_tidy()

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run clang-tidy linting.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        # Collect C/C++ source files
        files = self._collect_files(context)
        if not files:
            LOGGER.debug("No C/C++ files to lint")
            return []

        cmd = [str(binary)]

        # Add compile_commands.json path if available
        build_dir = find_build_dir(context.project_root)
        if build_dir:
            cmd.extend(["-p", str(build_dir)])

        cmd.extend(files)

        LOGGER.debug(f"Running: {' '.join(cmd[:5])}... ({len(files)} files)")

        env_vars = ensure_cpp_tools_in_path()

        try:
            with temporary_env(env_vars):
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="clang-tidy",
                    stream_handler=context.stream_handler,
                    timeout=300,
                )
        except subprocess.TimeoutExpired:
            LOGGER.warning("clang-tidy timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="clang-tidy timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run clang-tidy: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run clang-tidy: {e}",
            )
            return []

        # clang-tidy outputs diagnostics to stdout
        output = result.stdout or ""
        stderr = result.stderr or ""
        combined = output + "\n" + stderr

        issues = self._parse_output(combined, context.project_root)
        LOGGER.info(f"clang-tidy found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply clang-tidy auto-fixes.

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

        pre_issues = self.lint(context)

        files = self._collect_files(context)
        if not files:
            return FixResult()

        cmd = [str(binary), "--fix"]

        build_dir = find_build_dir(context.project_root)
        if build_dir:
            cmd.extend(["-p", str(build_dir)])

        cmd.extend(files)

        env_vars = ensure_cpp_tools_in_path()

        try:
            with temporary_env(env_vars):
                run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="clang-tidy-fix",
                    stream_handler=context.stream_handler,
                    timeout=300,
                )
        except Exception as e:
            LOGGER.debug(f"clang-tidy fix completed with: {e}")

        post_issues = self.lint(context)
        return self._calculate_fix_stats(pre_issues, post_issues)

    def _collect_files(self, context: ScanContext) -> List[str]:
        """Collect C/C++ files to lint.

        Args:
            context: Scan context.

        Returns:
            List of file path strings.
        """
        if context.paths:
            files = []
            for path in context.paths:
                if path.is_dir():
                    for ext in CPP_EXTENSIONS:
                        for f in path.rglob(f"*{ext}"):
                            if (
                                context.ignore_patterns is None
                                or not context.ignore_patterns.matches(
                                    f, context.project_root
                                )
                            ):
                                files.append(str(f))
                elif path.suffix.lower() in CPP_EXTENSIONS:
                    files.append(str(path))
            return files

        # Default: find all C/C++ files in project
        files = []
        for ext in CPP_EXTENSIONS:
            for f in context.project_root.rglob(f"*{ext}"):
                if (
                    context.ignore_patterns is None
                    or not context.ignore_patterns.matches(f, context.project_root)
                ):
                    files.append(str(f))
        return files

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse clang-tidy text output.

        Args:
            output: Raw output from clang-tidy.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        issues = []
        seen_ids = set()

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            match = _DIAG_RE.match(line)
            if not match:
                continue

            file_str = match.group(1)
            line_num = int(match.group(2))
            col_num = int(match.group(3))
            diag_level = match.group(4)
            message = match.group(5)
            check_name = match.group(6) or ""

            # Skip notes - they are context for warnings/errors
            if diag_level == "note":
                continue

            # Resolve file path
            file_path = Path(file_str)
            resolved_root = project_root.resolve()
            if not file_path.is_absolute():
                file_path = (resolved_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            severity = self._get_severity(check_name, diag_level)

            title = f"[{check_name}] {message}" if check_name else message

            issue_id = generate_issue_id(
                "clang-tidy",
                check_name or diag_level,
                str(file_path),
                line_num,
                col_num,
                message,
            )

            if issue_id in seen_ids:
                continue
            seen_ids.add(issue_id)

            doc_url = None
            if check_name:
                doc_url = (
                    f"https://clang.llvm.org/extra/clang-tidy/checks/"
                    f"{check_name.replace('-', '/')}.html"
                )

            issues.append(
                UnifiedIssue(
                    id=issue_id,
                    domain=ToolDomain.LINTING,
                    source_tool="clang-tidy",
                    severity=severity,
                    rule_id=check_name or diag_level,
                    title=title,
                    description=message,
                    documentation_url=doc_url,
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    column_start=col_num,
                    fixable=True,
                    metadata={
                        "check_name": check_name,
                        "diagnostic_level": diag_level,
                    },
                )
            )

        return issues

    def _get_severity(self, check_name: str, diag_level: str) -> Severity:
        """Get severity for a clang-tidy diagnostic.

        Check category mapping takes precedence over diagnostic level.

        Args:
            check_name: Full check name (e.g., "bugprone-use-after-move").
            diag_level: Diagnostic level string ("error", "warning", "note").

        Returns:
            Severity level.
        """
        if check_name:
            # Extract the category prefix (e.g., "bugprone" from "bugprone-use-after-move")
            category = check_name.split("-")[0]
            if category in CATEGORY_SEVERITY:
                return CATEGORY_SEVERITY[category]

        if diag_level in DIAG_SEVERITY:
            return DIAG_SEVERITY[diag_level]

        return Severity.MEDIUM
