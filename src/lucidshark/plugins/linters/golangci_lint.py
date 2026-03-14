"""golangci-lint linter plugin.

golangci-lint is a fast Go linters aggregator that runs linters in parallel,
reuses Go build cache, and caches analysis results.
https://golangci-lint.run/
"""

from __future__ import annotations

import json
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
from lucidshark.plugins.go_utils import (
    find_golangci_lint,
    generate_issue_id,
    get_golangci_lint_version,
    has_go_mod,
)
from lucidshark.plugins.linters.base import FixResult, LinterPlugin

LOGGER = get_logger(__name__)

# Linter name to severity mapping
LINTER_SEVERITY = {
    # High severity - correctness & security
    "govet": Severity.HIGH,
    "staticcheck": Severity.HIGH,
    "gosec": Severity.HIGH,
    "errcheck": Severity.HIGH,
    "typecheck": Severity.HIGH,
    "bodyclose": Severity.HIGH,
    "sqlclosecheck": Severity.HIGH,
    "rowserrcheck": Severity.HIGH,
    "nilerr": Severity.HIGH,
    # Medium severity - bugs & inefficiencies
    "ineffassign": Severity.MEDIUM,
    "unused": Severity.MEDIUM,
    "unparam": Severity.MEDIUM,
    "prealloc": Severity.MEDIUM,
    "exportloopref": Severity.MEDIUM,
    "gocritic": Severity.MEDIUM,
    "revive": Severity.MEDIUM,
    "exhaustive": Severity.MEDIUM,
    "errorlint": Severity.MEDIUM,
    "wrapcheck": Severity.MEDIUM,
    "makezero": Severity.MEDIUM,
    # Low severity - style & conventions
    "gosimple": Severity.LOW,
    "goconst": Severity.LOW,
    "stylecheck": Severity.LOW,
    "misspell": Severity.LOW,
    "whitespace": Severity.LOW,
    "gofmt": Severity.LOW,
    "goimports": Severity.LOW,
    "godot": Severity.LOW,
    "godox": Severity.LOW,
    "funlen": Severity.LOW,
    "lll": Severity.LOW,
    "cyclop": Severity.LOW,
    "gocyclo": Severity.LOW,
    "gocognit": Severity.LOW,
    "nestif": Severity.LOW,
    "nakedret": Severity.LOW,
    "nlreturn": Severity.LOW,
    "wsl": Severity.LOW,
    "dupl": Severity.LOW,
}

# Severity field mapping from JSON output
SEVERITY_FIELD_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
}


class GoLangCILintLinter(LinterPlugin):
    """golangci-lint linter plugin for Go code analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize GoLangCILintLinter.

        Args:
            project_root: Optional project root for tool resolution.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "golangci_lint"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["go"]

    @property
    def supports_fix(self) -> bool:
        """golangci-lint supports auto-fix."""
        return True

    def get_version(self) -> str:
        """Get golangci-lint version."""
        return get_golangci_lint_version()

    def ensure_binary(self) -> Path:
        """Ensure golangci-lint is available.

        Returns:
            Path to golangci-lint binary.

        Raises:
            FileNotFoundError: If golangci-lint is not available.
        """
        return find_golangci_lint()

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run golangci-lint linting.

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

        if not has_go_mod(context.project_root):
            LOGGER.info("No go.mod found, skipping golangci-lint")
            return []

        cmd = [
            str(binary),
            "run",
            "--out-format",
            "json",
            "./...",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="golangci-lint",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("golangci-lint timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="golangci-lint timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run golangci-lint: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run golangci-lint: {e}",
            )
            return []

        issues = self._parse_output(result.stdout, context.project_root)
        LOGGER.info(f"golangci-lint found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply golangci-lint auto-fixes.

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

        if not has_go_mod(context.project_root):
            return FixResult()

        # Count issues before fix
        pre_issues = self.lint(context)

        cmd = [
            str(binary),
            "run",
            "--fix",
            "--out-format",
            "json",
            "./...",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="golangci-lint-fix",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("golangci-lint fix timed out after 300 seconds")
            return FixResult()
        except Exception as e:
            LOGGER.debug(f"golangci-lint fix completed with: {e}")

        # Count remaining issues
        post_issues = self.lint(context)

        files_modified = len(
            set(
                str(issue.file_path)
                for issue in pre_issues
                if str(issue.file_path) not in {str(i.file_path) for i in post_issues}
            )
        )

        return FixResult(
            files_modified=files_modified,
            issues_fixed=len(pre_issues) - len(post_issues),
            issues_remaining=len(post_issues),
        )

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse golangci-lint JSON output.

        golangci-lint with --out-format json produces a single JSON object
        with an "Issues" array.

        Args:
            output: Raw stdout from golangci-lint.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse golangci-lint JSON output")
            return []

        raw_issues = data.get("Issues")
        if not raw_issues:
            return []

        issues = []
        seen_ids = set()

        for raw in raw_issues:
            issue = self._issue_to_unified(raw, project_root)
            if issue and issue.id not in seen_ids:
                issues.append(issue)
                seen_ids.add(issue.id)

        return issues

    def _issue_to_unified(
        self, raw: dict, project_root: Path
    ) -> Optional[UnifiedIssue]:
        """Convert a golangci-lint issue to UnifiedIssue.

        Args:
            raw: Parsed JSON issue object.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            from_linter = raw.get("FromLinter", "unknown")
            text = raw.get("Text", "")
            severity_field = raw.get("Severity", "")
            source_lines = raw.get("SourceLines", [])
            pos = raw.get("Pos", {})

            filename = pos.get("Filename", "")
            line = pos.get("Line")
            column = pos.get("Column")

            if not filename:
                return None

            # Resolve file path relative to project root
            file_path = Path(filename)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            # Determine severity: linter-based mapping takes precedence
            severity = self._get_severity(from_linter, severity_field)

            # Build title
            title = f"[{from_linter}] {text}"

            # Build code snippet from source lines
            code_snippet = "\n".join(source_lines) if source_lines else None

            # Documentation URL
            doc_url = f"https://golangci-lint.run/usage/linters/#{from_linter}"

            # Generate deterministic ID
            issue_id = generate_issue_id(
                "golangci-lint",
                from_linter,
                str(file_path),
                line,
                column,
                text,
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="golangci-lint",
                severity=severity,
                rule_id=from_linter,
                title=title,
                description=text,
                documentation_url=doc_url,
                file_path=file_path,
                line_start=line,
                line_end=line,
                column_start=column,
                code_snippet=code_snippet,
                fixable=True,
                metadata={
                    "from_linter": from_linter,
                    "severity_field": severity_field,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse golangci-lint issue: {e}")
            return None

    def _get_severity(self, from_linter: str, severity_field: str) -> Severity:
        """Get severity for a golangci-lint issue.

        Linter-based mapping takes precedence over the severity field.

        Args:
            from_linter: Name of the linter that reported the issue.
            severity_field: Severity string from the JSON output.

        Returns:
            Severity level.
        """
        # Linter-based mapping takes precedence
        if from_linter in LINTER_SEVERITY:
            return LINTER_SEVERITY[from_linter]

        # Fall back to severity field from JSON
        if severity_field in SEVERITY_FIELD_MAP:
            return SEVERITY_FIELD_MAP[severity_field]

        # Default to medium
        return Severity.MEDIUM
