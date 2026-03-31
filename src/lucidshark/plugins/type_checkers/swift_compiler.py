"""Swift compiler type checker plugin.

Uses the Swift compiler's diagnostics via `swift build` to detect
type errors, missing members, and other compile-time problems.
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
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.swift_utils import (
    find_swift,
    generate_issue_id,
    has_package_swift,
)
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin

LOGGER = get_logger(__name__)

# Compiler diagnostic level to severity mapping
LEVEL_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "note": Severity.LOW,
}

# Regex for parsing Swift compiler output lines:
#   /path/to/File.swift:42:15: error: cannot convert value of type 'Int' to 'String'
_DIAGNOSTIC_RE = re.compile(
    r"^(.+\.swift):(\d+):(\d+):\s+(error|warning|note):\s+(.+)$"
)


class SwiftCompilerChecker(TypeCheckerPlugin):
    """Swift compiler plugin for type checking via swift build diagnostics."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "swift_compiler"

    @property
    def languages(self) -> List[str]:
        return ["swift"]

    @property
    def supports_strict_mode(self) -> bool:
        return False

    def get_version(self) -> str:
        from lucidshark.plugins.swift_utils import get_swift_version

        return get_swift_version()

    def ensure_binary(self) -> Path:
        return find_swift()

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            swift_bin = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        if not has_package_swift(context.project_root):
            LOGGER.info("No Package.swift found, skipping swift build")
            return []

        cmd = [str(swift_bin), "build"]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        stdout = ""
        stderr = ""
        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="swift-build",
                stream_handler=context.stream_handler,
                timeout=300,
            )
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            LOGGER.warning("swift build timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message="swift build timed out after 300 seconds",
            )
            return []
        except subprocess.CalledProcessError as e:
            # swift build returns non-zero on errors - that's expected
            LOGGER.debug(f"swift build completed with: {e}")
            stdout = e.stdout or ""
            stderr = e.stderr or ""
        except Exception as e:
            LOGGER.debug(f"swift build completed with: {e}")

        # Swift compiler outputs diagnostics to stderr
        combined = (stdout or "") + "\n" + (stderr or "")
        issues = self._parse_output(combined, context.project_root)
        LOGGER.info(f"swift build found {len(issues)} issues")
        return issues

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Swift compiler text output."""
        if not output.strip():
            return []

        issues = []
        seen_ids = set()

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            match = _DIAGNOSTIC_RE.match(line)
            if not match:
                continue

            file_str = match.group(1)
            line_num = int(match.group(2))
            col_num = int(match.group(3))
            level = match.group(4)
            message = match.group(5)

            # Only process errors and warnings
            if level not in ("error", "warning"):
                continue

            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            severity = LEVEL_SEVERITY.get(level, Severity.MEDIUM)
            title = f"[{level}] {message}"

            issue_id = generate_issue_id(
                "swift-compiler", level, str(file_path), line_num, col_num, message
            )

            if issue_id in seen_ids:
                continue
            seen_ids.add(issue_id)

            issues.append(
                UnifiedIssue(
                    id=issue_id,
                    domain=ToolDomain.TYPE_CHECKING,
                    source_tool="swift_compiler",
                    severity=severity,
                    rule_id=level,
                    title=title,
                    description=message,
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    column_start=col_num,
                    column_end=None,
                    fixable=False,
                    metadata={
                        "level": level,
                    },
                )
            )

        return issues
