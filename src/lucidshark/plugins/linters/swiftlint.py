"""SwiftLint linter plugin.

SwiftLint is a tool to enforce Swift style and conventions.
https://github.com/realm/SwiftLint
"""

from __future__ import annotations

import json
import shutil
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
from lucidshark.plugins.linters.base import FixResult, LinterPlugin
from lucidshark.plugins.swift_utils import generate_issue_id
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

# SwiftLint rule severity mapping by category
# Rules documented at https://realm.github.io/SwiftLint/rule-directory.html
RULE_SEVERITY = {
    # High severity - correctness & safety
    "force_cast": Severity.HIGH,
    "force_try": Severity.HIGH,
    "force_unwrapping": Severity.HIGH,
    "implicitly_unwrapped_optional": Severity.HIGH,
    "unavailable_function": Severity.HIGH,
    "class_delegate_protocol": Severity.HIGH,
    "discarded_notification_center_observer": Severity.HIGH,
    "duplicate_imports": Severity.HIGH,
    "dynamic_inline": Severity.HIGH,
    "is_disjoint": Severity.HIGH,
    "nsobject_prefer_isequal": Severity.HIGH,
    "private_unit_test": Severity.HIGH,
    "quick_discouraged_call": Severity.HIGH,
    "unused_capture_list": Severity.HIGH,
    "valid_ibinspectable": Severity.HIGH,
    # Medium severity - complexity & performance
    "cyclomatic_complexity": Severity.MEDIUM,
    "function_body_length": Severity.MEDIUM,
    "file_length": Severity.MEDIUM,
    "type_body_length": Severity.MEDIUM,
    "large_tuple": Severity.MEDIUM,
    "nesting": Severity.MEDIUM,
    "function_parameter_count": Severity.MEDIUM,
    "closure_body_length": Severity.MEDIUM,
    "empty_count": Severity.MEDIUM,
    "first_where": Severity.MEDIUM,
    "flatmap_over_map_reduce": Severity.MEDIUM,
    "last_where": Severity.MEDIUM,
    "reduce_boolean": Severity.MEDIUM,
    "reduce_into": Severity.MEDIUM,
    "sorted_first_last": Severity.MEDIUM,
    "contains_over_first_not_nil": Severity.MEDIUM,
    "contains_over_filter_count": Severity.MEDIUM,
    "contains_over_filter_is_empty": Severity.MEDIUM,
    "contains_over_range_nil_comparison": Severity.MEDIUM,
    # Low severity - style
    "line_length": Severity.LOW,
    "trailing_whitespace": Severity.LOW,
    "trailing_newline": Severity.LOW,
    "trailing_comma": Severity.LOW,
    "trailing_semicolon": Severity.LOW,
    "vertical_whitespace": Severity.LOW,
    "opening_brace": Severity.LOW,
    "closing_brace": Severity.LOW,
    "colon": Severity.LOW,
    "comma": Severity.LOW,
    "identifier_name": Severity.LOW,
    "type_name": Severity.LOW,
    "operator_whitespace": Severity.LOW,
    "return_arrow_whitespace": Severity.LOW,
    "statement_position": Severity.LOW,
    "todo": Severity.LOW,
    "mark": Severity.LOW,
    "void_return": Severity.LOW,
    "unused_import": Severity.LOW,
    "redundant_optional_initialization": Severity.LOW,
    "redundant_string_enum_value": Severity.LOW,
    "redundant_void_return": Severity.LOW,
    "redundant_nil_coalescing": Severity.LOW,
    "shorthand_operator": Severity.LOW,
    "syntactic_sugar": Severity.LOW,
}

# SwiftLint severity text to our severity mapping
LEVEL_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
}


class SwiftLintLinter(LinterPlugin):
    """SwiftLint linter plugin for Swift code analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "swiftlint"

    @property
    def languages(self) -> List[str]:
        return ["swift"]

    @property
    def supports_fix(self) -> bool:
        return True

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        system_binary = shutil.which("swiftlint")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "swiftlint is not installed. Install it with:\n"
            "  brew install swiftlint  (macOS)\n"
            "  or see https://github.com/realm/SwiftLint#installation"
        )

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        # Check for Swift files
        swift_files = list(context.project_root.rglob("*.swift"))
        if not swift_files:
            LOGGER.info("No Swift files found, skipping SwiftLint")
            return []

        cmd = [
            str(binary),
            "lint",
            "--reporter",
            "json",
            "--quiet",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="swiftlint",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("SwiftLint timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="SwiftLint timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run SwiftLint: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run SwiftLint: {e}",
            )
            return []

        issues = self._parse_output(result.stdout, context.project_root)
        LOGGER.info(f"SwiftLint found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        swift_files = list(context.project_root.rglob("*.swift"))
        if not swift_files:
            return FixResult()

        pre_issues = self.lint(context)

        cmd = [
            str(binary),
            "lint",
            "--fix",
            "--quiet",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="swiftlint-fix",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("SwiftLint fix timed out after 300 seconds")
            return FixResult()
        except Exception as e:
            LOGGER.debug(f"SwiftLint fix completed with: {e}")

        post_issues = self.lint(context)

        return self._calculate_fix_stats(pre_issues, post_issues)

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse SwiftLint JSON output."""
        if not output or not output.strip():
            return []

        try:
            violations = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse SwiftLint output as JSON")
            return []

        if not isinstance(violations, list):
            return []

        issues = []
        seen_ids = set()

        for violation in violations:
            issue = self._violation_to_issue(violation, project_root)
            if issue and issue.id not in seen_ids:
                issues.append(issue)
                seen_ids.add(issue.id)

        return issues

    def _violation_to_issue(
        self, violation: dict, project_root: Path
    ) -> Optional[UnifiedIssue]:
        """Convert a SwiftLint violation to UnifiedIssue."""
        try:
            file_path_str = violation.get("file", "")
            line = violation.get("line")
            column = violation.get("character")
            rule_id = violation.get("rule_id", "")
            reason = violation.get("reason", "")
            severity_str = violation.get("severity", "warning").lower()

            if not file_path_str:
                return None

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            severity = self._get_severity(rule_id, severity_str)
            title = f"[{rule_id}] {reason}" if rule_id else reason

            issue_id = generate_issue_id(
                "swiftlint", rule_id, str(file_path), line, column, reason
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="swiftlint",
                severity=severity,
                rule_id=rule_id or "unknown",
                title=title,
                description=reason,
                documentation_url=(
                    f"https://realm.github.io/SwiftLint/{rule_id}.html"
                    if rule_id
                    else None
                ),
                file_path=file_path,
                line_start=line,
                line_end=line,
                column_start=column,
                column_end=None,
                fixable=self.supports_fix,
                metadata={
                    "severity": severity_str,
                    "rule_id": rule_id,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse SwiftLint violation: {e}")
            return None

    def _get_severity(self, rule_id: str, level: str) -> Severity:
        """Get severity for a SwiftLint rule."""
        if rule_id in RULE_SEVERITY:
            return RULE_SEVERITY[rule_id]
        return LEVEL_SEVERITY.get(level, Severity.MEDIUM)
