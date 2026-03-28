"""RuboCop linter plugin.

RuboCop is a Ruby static code analyzer and code formatter.
https://rubocop.org/
"""

from __future__ import annotations

import hashlib
import json
import shutil
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
from lucidshark.plugins.linters.base import FixResult, LinterPlugin

LOGGER = get_logger(__name__)

RUBY_EXTENSIONS = {".rb", ".rake", ".gemspec"}

# RuboCop severity mapping
SEVERITY_MAP = {
    "refactor": Severity.LOW,
    "convention": Severity.LOW,
    "warning": Severity.MEDIUM,
    "error": Severity.HIGH,
    "fatal": Severity.HIGH,
}

# Cop department to severity overrides
DEPARTMENT_SEVERITY = {
    "Security": Severity.HIGH,
    "Lint": Severity.MEDIUM,
    "Layout": Severity.LOW,
    "Style": Severity.LOW,
    "Naming": Severity.LOW,
    "Metrics": Severity.LOW,
}


def _find_rubocop(project_root: Optional[Path] = None) -> Path:
    """Find RuboCop binary.

    Checks for RuboCop in:
    1. Project binstubs (bin/rubocop)
    2. System PATH

    Args:
        project_root: Optional project root for binstub lookup.

    Returns:
        Path to the rubocop binary.

    Raises:
        FileNotFoundError: If RuboCop is not installed.
    """
    if project_root:
        binstub = project_root / "bin" / "rubocop"
        if binstub.exists():
            return binstub

    system_binary = shutil.which("rubocop")
    if system_binary:
        return Path(system_binary)

    raise FileNotFoundError(
        "RuboCop is not installed. Install it with:\n"
        "  gem install rubocop\n"
        "  OR add to your Gemfile:\n"
        "  gem 'rubocop', require: false"
    )


class RubocopLinter(LinterPlugin):
    """RuboCop linter plugin for Ruby code analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "rubocop"

    @property
    def languages(self) -> List[str]:
        return ["ruby"]

    @property
    def supports_fix(self) -> bool:
        return True

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

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        binary = self._ensure_binary_safe()
        if binary is None:
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message="RuboCop is not installed",
                suggestion="gem install rubocop",
            )
            return []

        cmd = [str(binary), "--format", "json", "--force-exclusion"]

        paths = self._resolve_ruby_paths(context)
        if not paths:
            LOGGER.debug("No Ruby files to lint")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.NO_APPLICABLE_FILES,
                message="No Ruby files to lint",
            )
            return []

        cmd.extend(paths)

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        stdout = self._run_linter_command(cmd, context, tool_label="rubocop")
        if stdout is None:
            return []

        issues = self._parse_output(stdout, context.project_root)
        LOGGER.info(f"RuboCop found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        binary = self._ensure_binary_safe()
        if binary is None:
            return FixResult()

        pre_issues = self.lint(context)

        cmd = [str(binary), "--format", "json", "--force-exclusion", "-a"]

        paths = self._resolve_ruby_paths(context)
        if not paths:
            return FixResult()

        cmd.extend(paths)

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        stdout = self._run_linter_command(cmd, context, tool_label="rubocop-fix")
        if stdout is None:
            return FixResult()

        post_issues = self._parse_output(stdout, context.project_root)
        return self._calculate_fix_stats(pre_issues, post_issues)

    def _resolve_ruby_paths(self, context: ScanContext) -> Optional[List[str]]:
        if context.paths:
            paths_to_use = context.paths
            if context.ignore_patterns is not None:
                paths_to_use = [
                    p
                    for p in paths_to_use
                    if not context.ignore_patterns.matches(p, context.project_root)
                ]
            return self._filter_paths(paths_to_use) or None
        return ["."]

    def _filter_paths(self, paths: List[Path]) -> List[str]:
        filtered = []
        for path in paths:
            if path.is_dir():
                filtered.append(str(path))
            elif path.suffix.lower() in RUBY_EXTENSIONS:
                filtered.append(str(path))
        return filtered

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        if not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse RuboCop output as JSON")
            return []

        files = data.get("files", [])
        issues = []

        for file_data in files:
            file_path_str = file_data.get("path", "")
            offenses = file_data.get("offenses", [])

            for offense in offenses:
                issue = self._offense_to_issue(offense, file_path_str, project_root)
                if issue:
                    issues.append(issue)

        return issues

    def _offense_to_issue(
        self,
        offense: Dict[str, Any],
        file_path_str: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        try:
            severity_str = offense.get("severity", "warning")
            message = offense.get("message", "")
            cop_name = offense.get("cop_name", "")
            corrected = offense.get("corrected", False)
            correctable = offense.get("correctable", False)
            location = offense.get("location", {})

            severity = self._get_severity(severity_str, cop_name)

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            issue_id = self._generate_issue_id(
                cop_name, file_path_str, location, message
            )

            line_start = location.get("start_line") or location.get("line")
            line_end = location.get("last_line") or line_start
            col_start = location.get("start_column") or location.get("column")
            col_end = location.get("last_column")

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="rubocop",
                severity=severity,
                rule_id=cop_name,
                title=f"{cop_name}: {message}",
                description=message,
                documentation_url=f"https://docs.rubocop.org/rubocop/cops_{cop_name.replace('/', '_').lower()}.html"
                if "/" in cop_name
                else None,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                column_start=col_start,
                column_end=col_end,
                fixable=correctable and not corrected,
                suggested_fix="Run rubocop -a to auto-correct" if correctable else None,
                metadata={
                    "cop_name": cop_name,
                    "corrected": corrected,
                    "correctable": correctable,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse RuboCop offense: {e}")
            return None

    def _get_severity(self, severity_str: str, cop_name: str) -> Severity:
        department = cop_name.split("/")[0] if "/" in cop_name else ""
        if department in DEPARTMENT_SEVERITY:
            dept_severity = DEPARTMENT_SEVERITY[department]
            base_severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)
            # Use the higher of the two
            severity_order = {
                Severity.INFO: 0,
                Severity.LOW: 1,
                Severity.MEDIUM: 2,
                Severity.HIGH: 3,
            }
            if severity_order.get(base_severity, 0) > severity_order.get(
                dept_severity, 0
            ):
                return base_severity
            return dept_severity
        return SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

    def _generate_issue_id(
        self,
        cop_name: str,
        filename: str,
        location: Dict[str, int],
        message: str,
    ) -> str:
        line = location.get("start_line") or location.get("line", 0)
        col = location.get("start_column") or location.get("column", 0)
        content = f"{cop_name}:{filename}:{line}:{col}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"rubocop-{cop_name.replace('/', '-')}-{hash_val}"
