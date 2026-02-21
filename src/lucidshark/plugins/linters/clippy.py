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

# Clippy lint category to severity mapping
CATEGORY_SEVERITY = {
    "clippy::correctness": Severity.HIGH,
    "clippy::suspicious": Severity.HIGH,
    "clippy::complexity": Severity.MEDIUM,
    "clippy::perf": Severity.MEDIUM,
    "clippy::style": Severity.LOW,
    "clippy::pedantic": Severity.LOW,
    "clippy::nursery": Severity.LOW,
    "clippy::restriction": Severity.LOW,
    "clippy::cargo": Severity.LOW,
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
            "-W", "clippy::all",
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
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run Clippy: {e}")
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
            "-W", "clippy::all",
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

        files_modified = len(set(
            str(issue.file_path)
            for issue in pre_issues
            if str(issue.file_path) not in {str(i.file_path) for i in post_issues}
        ))

        return FixResult(
            files_modified=files_modified,
            issues_fixed=len(pre_issues) - len(post_issues),
            issues_remaining=len(post_issues),
        )

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
        # Check category-based severity first
        for category, severity in CATEGORY_SEVERITY.items():
            if code.startswith(category):
                return severity

        # Fall back to level-based severity
        return LEVEL_SEVERITY.get(level, Severity.MEDIUM)
