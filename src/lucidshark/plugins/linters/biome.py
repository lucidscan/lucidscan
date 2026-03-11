"""Biome linter plugin.

Biome is a fast linter and formatter for JavaScript, TypeScript, and more.
https://biomejs.dev/
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.linters.base import FixResult, LinterPlugin
from lucidshark.plugins.utils import ensure_node_binary, get_cli_version

LOGGER = get_logger(__name__)

# Biome severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "info": Severity.LOW,
}


class BiomeLinter(LinterPlugin):
    """Biome linter plugin for JavaScript/TypeScript code analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize BiomeLinter.

        Args:
            project_root: Optional project root for finding Biome installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "biome"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript", "json"]

    @property
    def supports_fix(self) -> bool:
        """Biome supports auto-fix."""
        return True

    def get_version(self) -> str:
        """Get Biome version."""
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def _resolve_target_paths(self, context: ScanContext) -> List[str]:
        """Resolve target paths for linting/checking.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of path strings to check.
        """
        if context.paths:
            return [p.as_posix() for p in context.paths]

        src_dir = context.project_root / "src"
        if src_dir.exists():
            return [src_dir.as_posix()]

        return ["."]

    def ensure_binary(self) -> Path:
        """Ensure Biome binary is available.

        Checks for Biome in project node_modules or system PATH.

        Returns:
            Path to Biome binary.

        Raises:
            FileNotFoundError: If Biome is not installed.
        """
        return ensure_node_binary(
            self._project_root,
            "biome",
            "Biome is not installed. Install it with:\n"
            "  npm install @biomejs/biome --save-dev\n"
            "  OR\n"
            "  npm install -g @biomejs/biome",
        )

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run Biome linting.

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

        # Build command
        cmd = [
            str(binary),
            "lint",
            "--reporter",
            "json",
        ]

        # Add paths to check
        cmd.extend(self._resolve_target_paths(context))

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="biome",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Biome lint timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="Biome lint timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run Biome: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run Biome: {e}",
            )
            return []

        # Parse output
        issues = self._parse_output(result.stdout, context.project_root)

        LOGGER.info(f"Biome found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply Biome auto-fixes.

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

        # Run without fix to count issues first
        pre_issues = self.lint(context)

        # Build fix command - Biome uses 'check --apply' for fixes
        cmd = [
            str(binary),
            "check",
            "--apply",
        ]

        cmd.extend(self._resolve_target_paths(context))

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="biome-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Biome fix timed out after 120 seconds")
            return FixResult()
        except Exception as e:
            LOGGER.error(f"Failed to run Biome fix: {e}")
            return FixResult()

        # Run lint again to get remaining issues
        post_issues = self.lint(context)

        # Calculate stats
        files_modified = len(
            set(
                str(issue.file_path) for issue in pre_issues if issue not in post_issues
            )
        )

        return FixResult(
            files_modified=files_modified,
            issues_fixed=len(pre_issues) - len(post_issues),
            issues_remaining=len(post_issues),
        )

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Biome JSON output.

        Args:
            output: JSON output from Biome.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse Biome output as JSON")
            return []

        issues = []
        diagnostics = data.get("diagnostics", [])

        for diagnostic in diagnostics:
            issue = self._diagnostic_to_issue(diagnostic, project_root)
            if issue:
                issues.append(issue)

        return issues

    def _diagnostic_to_issue(
        self,
        diagnostic: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert Biome diagnostic to UnifiedIssue.

        Args:
            diagnostic: Biome diagnostic dict.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            severity_str = diagnostic.get("severity", "error")
            message = diagnostic.get("message", "")
            # Handle structured message format
            if isinstance(message, list):
                message = " ".join(
                    m.get("content", "") if isinstance(m, dict) else str(m)
                    for m in message
                )

            category = diagnostic.get("category", "")
            location = diagnostic.get("location", {})

            # Get file path from location
            file_path_str = location.get("path", {}).get("file", "")

            # Get position info
            line_start = location.get("lineStart", 1)
            line_end = location.get("lineEnd", line_start)
            column_start = location.get("columnStart", 1)

            # Get severity
            severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            # Build file path
            file_path = Path(file_path_str) if file_path_str else Path("unknown")
            if not file_path.is_absolute() and file_path_str:
                file_path = project_root / file_path

            # Generate deterministic ID
            issue_id = self._generate_issue_id(
                category, file_path_str, line_start, column_start, message
            )

            # Build title
            title = f"[{category}] {message}" if category else message

            # Get column end
            column_end = location.get("columnEnd")

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="biome",
                severity=severity,
                rule_id=category or "unknown",
                title=title,
                description=message,
                documentation_url=f"https://biomejs.dev/linter/rules/{category.lower().replace('/', '-')}"
                if category
                else None,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                column_start=column_start,
                column_end=column_end,
                fixable=diagnostic.get("fixable", False),
                metadata={
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Biome diagnostic: {e}")
            return None

    def _generate_issue_id(
        self,
        category: str,
        file: str,
        line: int,
        column: int,
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            category: Rule category.
            file: File path.
            line: Line number.
            column: Column number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{category}:{file}:{line}:{column}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"biome-{category}-{hash_val}" if category else f"biome-{hash_val}"
