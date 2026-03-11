"""TypeScript type checker plugin.

TypeScript uses the tsc compiler for type checking.
https://www.typescriptlang.org/
"""

from __future__ import annotations

import hashlib
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
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin
from lucidshark.plugins.utils import ensure_node_binary, get_cli_version

LOGGER = get_logger(__name__)

# TypeScript error pattern: file(line,col): error TS1234: message
TSC_ERROR_PATTERN = re.compile(
    r"^(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)$"
)


class TypeScriptChecker(TypeCheckerPlugin):
    """TypeScript type checker plugin using tsc."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize TypeScriptChecker.

        Args:
            project_root: Optional project root for finding tsc installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "typescript"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["typescript"]

    @property
    def supports_strict_mode(self) -> bool:
        """TypeScript supports strict mode via tsconfig.json."""
        return True

    def get_version(self) -> str:
        """Get TypeScript version."""
        try:
            binary = self.ensure_binary()
            # Output is like "Version 5.3.3"
            return get_cli_version(
                binary, parser=lambda s: s.split()[1] if len(s.split()) >= 2 else s
            )
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure tsc is available."""
        return ensure_node_binary(
            self._project_root,
            "tsc",
            "TypeScript is not installed. Install it with:\n"
            "  npm install typescript --save-dev\n"
            "  OR\n"
            "  npm install -g typescript",
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run TypeScript type checking.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking issues.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        # Check for tsconfig.json
        tsconfig = context.project_root / "tsconfig.json"
        if not tsconfig.exists():
            LOGGER.warning(
                f"No tsconfig.json found in {context.project_root}, skipping TypeScript checking"
            )
            return []

        # Build command
        cmd = [
            str(binary),
            "--noEmit",  # Don't emit compiled files
            "--pretty",
            "false",  # Plain output for parsing
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(context.project_root),
                timeout=180,  # 3 minute timeout
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("tsc timed out after 180 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message="tsc timed out after 180 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run tsc: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run tsc: {e}",
            )
            return []

        # Parse output (tsc outputs to stdout on success, stderr on error)
        output = result.stdout or result.stderr
        issues = self._parse_output(output, context.project_root)

        LOGGER.info(f"TypeScript found {len(issues)} issues")
        return issues

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse tsc output.

        tsc outputs errors in format:
        file(line,col): error TS1234: message

        Args:
            output: Output from tsc command.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        issues = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            match = TSC_ERROR_PATTERN.match(line)
            if match:
                issue = self._match_to_issue(match, project_root)
                if issue:
                    issues.append(issue)
            else:
                LOGGER.debug(f"Skipping non-matching line: {line}")

        return issues

    def _match_to_issue(
        self,
        match: re.Match,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert regex match to UnifiedIssue.

        Args:
            match: Regex match from TSC_ERROR_PATTERN.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            file_path_str = match.group(1)
            line = int(match.group(2))
            column = int(match.group(3))
            severity_str = match.group(4)
            code = match.group(5)
            message = match.group(6)

            # TypeScript errors are always high severity
            severity = Severity.HIGH if severity_str == "error" else Severity.MEDIUM

            # Build file path
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            # Generate deterministic ID
            issue_id = self._generate_issue_id(
                code, file_path_str, line, column, message
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="typescript",
                severity=severity,
                rule_id=code,
                title=f"[{code}] {message}",
                description=message,
                documentation_url=f"https://typescript.tv/errors/#{code}",
                file_path=file_path,
                line_start=line,
                line_end=line,
                column_start=column,
                fixable=False,
                metadata={
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse tsc error: {e}")
            return None

    def _generate_issue_id(
        self,
        code: str,
        file: str,
        line: int,
        column: int,
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            code: TypeScript error code (e.g., TS1234).
            file: File path.
            line: Line number.
            column: Column number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{code}:{file}:{line}:{column}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"ts-{code}-{hash_val}"
