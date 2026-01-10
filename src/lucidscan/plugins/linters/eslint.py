"""ESLint linter plugin.

ESLint is a pluggable linting utility for JavaScript and TypeScript.
https://eslint.org/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidscan.core.logging import get_logger
from lucidscan.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidscan.plugins.linters.base import FixResult, LinterPlugin

LOGGER = get_logger(__name__)

# ESLint severity mapping
# ESLint uses: 1=warning, 2=error
SEVERITY_MAP = {
    2: Severity.HIGH,    # error
    1: Severity.MEDIUM,  # warning
}


class ESLintLinter(LinterPlugin):
    """ESLint linter plugin for JavaScript/TypeScript code analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize ESLintLinter.

        Args:
            project_root: Optional project root for finding ESLint installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "eslint"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    @property
    def supports_fix(self) -> bool:
        """ESLint supports auto-fix."""
        return True

    def get_version(self) -> str:
        """Get ESLint version.

        Returns:
            Version string or 'unknown' if unable to determine.
        """
        try:
            binary = self.ensure_binary()
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Output is like "v8.56.0"
            if result.returncode == 0:
                return result.stdout.strip().lstrip("v")
        except Exception:
            pass
        return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure ESLint is available.

        Checks for ESLint in:
        1. Project's node_modules/.bin/eslint
        2. System PATH (globally installed)

        Returns:
            Path to ESLint binary.

        Raises:
            FileNotFoundError: If ESLint is not installed.
        """
        # Check project node_modules first
        if self._project_root:
            node_eslint = self._project_root / "node_modules" / ".bin" / "eslint"
            if node_eslint.exists():
                return node_eslint

        # Check system PATH
        eslint_path = shutil.which("eslint")
        if eslint_path:
            return Path(eslint_path)

        raise FileNotFoundError(
            "ESLint is not installed. Install it with:\n"
            "  npm install eslint --save-dev\n"
            "  OR\n"
            "  npm install -g eslint"
        )

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run ESLint linting.

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
            "--format", "json",
        ]

        # Add paths to check - default to src if exists, otherwise current dir
        if context.paths:
            paths = [str(p) for p in context.paths]
        else:
            src_dir = context.project_root / "src"
            if src_dir.exists():
                paths = [str(src_dir)]
            else:
                paths = ["."]

        cmd.extend(paths)

        # Add ignore patterns
        exclude_patterns = context.get_exclude_patterns()
        for pattern in exclude_patterns:
            cmd.extend(["--ignore-pattern", pattern])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(context.project_root),
                timeout=120,  # 2 minute timeout
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("ESLint lint timed out after 120 seconds")
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run ESLint: {e}")
            return []

        # Parse output
        issues = self._parse_output(result.stdout, context.project_root)

        LOGGER.info(f"ESLint found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply ESLint auto-fixes.

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

        # Build fix command
        cmd = [
            str(binary),
            "--fix",
            "--format", "json",
        ]

        if context.paths:
            paths = [str(p) for p in context.paths]
        else:
            src_dir = context.project_root / "src"
            if src_dir.exists():
                paths = [str(src_dir)]
            else:
                paths = ["."]

        cmd.extend(paths)

        exclude_patterns = context.get_exclude_patterns()
        for pattern in exclude_patterns:
            cmd.extend(["--ignore-pattern", pattern])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(context.project_root),
                timeout=120,  # 2 minute timeout
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("ESLint fix timed out after 120 seconds")
            return FixResult()
        except Exception as e:
            LOGGER.error(f"Failed to run ESLint fix: {e}")
            return FixResult()

        # Parse remaining issues
        post_issues = self._parse_output(result.stdout, context.project_root)

        # Calculate stats
        files_modified = len(set(
            str(issue.file_path)
            for issue in pre_issues
            if issue not in post_issues
        ))

        return FixResult(
            files_modified=files_modified,
            issues_fixed=len(pre_issues) - len(post_issues),
            issues_remaining=len(post_issues),
        )

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse ESLint JSON output.

        Args:
            output: JSON output from ESLint.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            results = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse ESLint output as JSON")
            return []

        issues = []
        for file_result in results:
            file_path = file_result.get("filePath", "")
            messages = file_result.get("messages", [])

            for message in messages:
                issue = self._message_to_issue(message, file_path, project_root)
                if issue:
                    issues.append(issue)

        return issues

    def _message_to_issue(
        self,
        message: Dict[str, Any],
        file_path: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert ESLint message to UnifiedIssue.

        Args:
            message: ESLint message dict.
            file_path: File path from ESLint.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            severity_int = message.get("severity", 2)
            rule_id = message.get("ruleId", "")
            msg = message.get("message", "")
            line = message.get("line")
            column = message.get("column")
            end_line = message.get("endLine")
            end_column = message.get("endColumn")

            # Get severity
            severity = SEVERITY_MAP.get(severity_int, Severity.MEDIUM)

            # Build file path
            path = Path(file_path)
            if not path.is_absolute():
                path = project_root / path

            # Generate deterministic ID
            issue_id = self._generate_issue_id(rule_id, file_path, line, column, msg)

            # Build title
            title = f"[{rule_id}] {msg}" if rule_id else msg

            # Check if fixable
            fixable = message.get("fix") is not None

            return UnifiedIssue(
                id=issue_id,
                scanner=ToolDomain.LINTING,
                source_tool="eslint",
                severity=severity,
                title=title,
                description=msg,
                file_path=path,
                line_start=line,
                line_end=end_line or line,
                scanner_metadata={
                    "rule": rule_id,
                    "fixable": fixable,
                    "column": column,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse ESLint message: {e}")
            return None

    def _generate_issue_id(
        self,
        rule: str,
        file: str,
        line: Optional[int],
        column: Optional[int],
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            rule: Rule ID.
            file: File path.
            line: Line number.
            column: Column number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{rule}:{file}:{line or 0}:{column or 0}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"eslint-{rule}-{hash_val}" if rule else f"eslint-{hash_val}"
