"""Clippy linter plugin.

Clippy is the official Rust linter, providing a collection of lints
to catch common mistakes and improve Rust code.
https://github.com/rust-lang/rust-clippy
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
from lucidshark.plugins.linters.base import FixResult, LinterPlugin
from lucidshark.plugins.rust_utils import (
    ensure_cargo_subcommand,
    extract_suggestion,
    generate_issue_id,
    get_cargo_version,
    parse_diagnostic_spans,
)

LOGGER = get_logger(__name__)

# Clippy lint name to severity mapping.
# Clippy lint codes (e.g., "clippy::needless_return") don't encode their
# category, so we maintain a curated set of overrides for common lints where
# the diagnostic-level fallback gives the wrong severity.
# Correctness lints are deny-by-default (emitted as errors → HIGH via
# LEVEL_SEVERITY), so they don't need overrides here.
LINT_SEVERITY = {
    # Suspicious lints — should be HIGH (warn-by-default → MEDIUM without override)
    "clippy::almost_swapped": Severity.HIGH,
    "clippy::arc_with_non_send_sync": Severity.HIGH,
    "clippy::float_equality_without_abs": Severity.HIGH,
    "clippy::iter_out_of_bounds": Severity.HIGH,
    "clippy::multi_assignments": Severity.HIGH,
    "clippy::mut_range_bound": Severity.HIGH,
    "clippy::mutable_key_type": Severity.HIGH,
    "clippy::non_canonical_clone_impl": Severity.HIGH,
    "clippy::non_canonical_partial_ord_impl": Severity.HIGH,
    "clippy::octal_escapes": Severity.HIGH,
    "clippy::suspicious_arithmetic_impl": Severity.HIGH,
    "clippy::suspicious_assignment_formatting": Severity.HIGH,
    "clippy::suspicious_command_arg_space": Severity.HIGH,
    "clippy::suspicious_doc_comments": Severity.HIGH,
    "clippy::suspicious_else_formatting": Severity.HIGH,
    "clippy::suspicious_map": Severity.HIGH,
    "clippy::suspicious_op_assign_impl": Severity.HIGH,
    "clippy::suspicious_open_options": Severity.HIGH,
    "clippy::suspicious_to_owned": Severity.HIGH,
    "clippy::suspicious_unary_op_formatting": Severity.HIGH,
    "clippy::unconditional_recursion": Severity.HIGH,
    # Style lints — should be LOW (warn-by-default → MEDIUM without override)
    "clippy::bool_assert_comparison": Severity.LOW,
    "clippy::collapsible_else_if": Severity.LOW,
    "clippy::collapsible_if": Severity.LOW,
    "clippy::comparison_to_empty": Severity.LOW,
    "clippy::enum_variant_names": Severity.LOW,
    "clippy::from_over_into": Severity.LOW,
    "clippy::len_without_is_empty": Severity.LOW,
    "clippy::len_zero": Severity.LOW,
    "clippy::let_and_return": Severity.LOW,
    "clippy::manual_map": Severity.LOW,
    "clippy::match_bool": Severity.LOW,
    "clippy::match_like_matches_macro": Severity.LOW,
    "clippy::needless_borrow": Severity.LOW,
    "clippy::needless_range_loop": Severity.LOW,
    "clippy::needless_return": Severity.LOW,
    "clippy::new_without_default": Severity.LOW,
    "clippy::ptr_arg": Severity.LOW,
    "clippy::question_mark": Severity.LOW,
    "clippy::redundant_clone": Severity.LOW,
    "clippy::redundant_closure": Severity.LOW,
    "clippy::redundant_field_names": Severity.LOW,
    "clippy::redundant_pattern": Severity.LOW,
    "clippy::redundant_static_lifetimes": Severity.LOW,
    "clippy::should_implement_trait": Severity.LOW,
    "clippy::single_match": Severity.LOW,
    "clippy::unnecessary_lazy_evaluations": Severity.LOW,
    "clippy::upper_case_acronyms": Severity.LOW,
    "clippy::wrong_self_convention": Severity.LOW,
}

# Compiler diagnostic level to severity mapping
LEVEL_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "note": Severity.LOW,
    "help": Severity.INFO,
    "ice": Severity.HIGH,
}


class ClippyLinter(LinterPlugin):
    """Clippy linter plugin for Rust code analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize ClippyLinter.

        Args:
            project_root: Optional project root for tool resolution.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "clippy"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["rust"]

    @property
    def supports_fix(self) -> bool:
        """Clippy supports auto-fix."""
        return True

    def get_version(self) -> str:
        """Get Clippy version."""
        return get_cargo_version("clippy")

    def ensure_binary(self) -> Path:
        """Ensure cargo and clippy are available.

        Returns:
            Path to cargo binary.

        Raises:
            FileNotFoundError: If cargo or clippy is not available.
        """
        return ensure_cargo_subcommand(
            "clippy",
            "clippy not available. Install with: rustup component add clippy",
        )

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run Clippy linting.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        try:
            cargo = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        # Check for Cargo.toml
        if not (context.project_root / "Cargo.toml").exists():
            LOGGER.info("No Cargo.toml found, skipping Clippy")
            return []

        cmd = [
            str(cargo),
            "clippy",
            "--message-format=json",
            "--quiet",
            "--",
            "-W",
            "clippy::all",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="clippy",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Clippy timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="Clippy timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run Clippy: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run Clippy: {e}",
            )
            return []

        issues = self._parse_output(result.stdout, context.project_root)
        LOGGER.info(f"Clippy found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply Clippy auto-fixes.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            FixResult with statistics.
        """
        try:
            cargo = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        if not (context.project_root / "Cargo.toml").exists():
            return FixResult()

        # Count issues before fix
        pre_issues = self.lint(context)

        cmd = [
            str(cargo),
            "clippy",
            "--fix",
            "--allow-dirty",
            "--allow-staged",
            "--message-format=json",
            "--quiet",
            "--",
            "-W",
            "clippy::all",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="clippy-fix",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Clippy fix timed out after 300 seconds")
            return FixResult()
        except Exception as e:
            LOGGER.debug(f"Clippy fix completed with: {e}")

        # Count remaining issues
        post_issues = self.lint(context)

        return self._calculate_fix_stats(pre_issues, post_issues)

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Clippy JSON output.

        Cargo outputs one JSON object per line. We only process lines
        where "reason" == "compiler-message".

        Args:
            output: Raw stdout from cargo clippy.
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

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("reason") != "compiler-message":
                continue

            message = data.get("message")
            if not message:
                continue

            issue = self._message_to_issue(message, project_root)
            if issue and issue.id not in seen_ids:
                issues.append(issue)
                seen_ids.add(issue.id)

        return issues

    def _message_to_issue(
        self, message: dict, project_root: Path
    ) -> Optional[UnifiedIssue]:
        """Convert a cargo diagnostic message to UnifiedIssue.

        Args:
            message: Parsed JSON message object.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            level = message.get("level", "")
            text = message.get("message", "")
            code_obj = message.get("code") or {}
            code = code_obj.get("code", "")

            # Skip non-clippy and non-warning/error messages
            if level not in ("error", "warning"):
                return None

            # Extract location from spans
            file_path, line_start, line_end, column_start, column_end, code_snippet = (
                parse_diagnostic_spans(message, project_root)
            )

            # Skip if no file (internal compiler messages)
            if not file_path:
                return None

            # Determine severity
            severity = self._get_severity(code, level)

            # Build title
            title = f"[{code}] {text}" if code else text

            # Generate deterministic ID
            issue_id = generate_issue_id(
                "clippy", code, str(file_path), line_start, column_start, text
            )

            suggestion = extract_suggestion(message)

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="clippy",
                severity=severity,
                rule_id=code or "unknown",
                title=title,
                description=text,
                documentation_url=(
                    f"https://rust-lang.github.io/rust-clippy/stable/index.html#{code.replace('clippy::', '')}"
                    if code.startswith("clippy::")
                    else None
                ),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                column_start=column_start,
                column_end=column_end,
                code_snippet=code_snippet,
                fixable=self.supports_fix,
                suggested_fix=suggestion,
                recommendation=suggestion,
                metadata={
                    "level": level,
                    "code": code,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Clippy message: {e}")
            return None

    def _get_severity(self, code: str, level: str) -> Severity:
        """Get severity for a Clippy lint.

        Args:
            code: Lint code (e.g., "clippy::unwrap_used").
            level: Diagnostic level (error, warning, etc.).

        Returns:
            Severity level.
        """
        # Direct lint name lookup
        if code in LINT_SEVERITY:
            return LINT_SEVERITY[code]

        # Catch-all for unlisted suspicious_ lints
        if code.startswith("clippy::suspicious_"):
            return Severity.HIGH

        # Fall back to level-based severity
        return LEVEL_SEVERITY.get(level, Severity.MEDIUM)
