"""Karma test runner plugin.

Karma is a test runner for JavaScript that works with Jasmine,
commonly used with Angular applications.
https://karma-runner.github.io/
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
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
from lucidshark.plugins.test_runners.base import TestRunnerPlugin, TestResult
from lucidshark.plugins.utils import ensure_node_binary

LOGGER = get_logger(__name__)


class KarmaRunner(TestRunnerPlugin):
    """Karma test runner plugin for Angular/JavaScript test execution."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize KarmaRunner.

        Args:
            project_root: Optional project root for finding Karma installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "karma"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    def ensure_binary(self) -> Path:
        """Ensure Karma is available."""
        return ensure_node_binary(
            self._project_root,
            "karma",
            "Karma is not installed. Install it with:\n"
            "  npm install karma --save-dev\n"
            "  OR\n"
            "  npm install -g karma-cli",
        )

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run Karma on the specified paths.

        Coverage is handled via Karma config, not a CLI flag.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "karma-results.json"

            # Find karma config file
            karma_config = self._find_karma_config(context.project_root)

            cmd = [
                str(binary),
                "start",
                "--single-run",
                "--no-auto-watch",
            ]

            if karma_config:
                cmd.append(str(karma_config))

            # Set environment variable for JSON reporter output
            env = {
                "KARMA_JSON_REPORTER_OUTPUT": str(report_file),
            }

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                import os

                full_env = os.environ.copy()
                full_env.update(env)

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(context.project_root),
                    timeout=600,  # 10 minute timeout for test runs
                    env=full_env,
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("Karma timed out after 600 seconds")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.TESTING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message="Karma timed out after 600 seconds",
                )
                return TestResult()
            except Exception as e:
                LOGGER.error(f"Failed to run Karma: {e}")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.TESTING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Failed to run Karma: {e}",
                )
                return TestResult()

            # Parse JSON report if karma-json-reporter was used
            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root)

            # Fallback: parse stdout for basic results
            return self._parse_stdout(
                result.stdout, result.stderr, context.project_root
            )

    def _find_karma_config(self, project_root: Path) -> Optional[Path]:
        """Find Karma configuration file.

        Args:
            project_root: Project root directory.

        Returns:
            Path to karma config or None.
        """
        config_names = [
            "karma.conf.js",
            "karma.conf.ts",
            "karma.config.js",
            "karma.config.ts",
        ]
        for name in config_names:
            config_path = project_root / name
            if config_path.exists():
                return config_path
        return None

    def _parse_json_report(
        self,
        report_file: Path,
        project_root: Path,
    ) -> TestResult:
        """Parse Karma JSON reporter output.

        Args:
            report_file: Path to JSON report file.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        try:
            with open(report_file) as f:
                report = json.load(f)
        except Exception as e:
            LOGGER.error(f"Failed to parse Karma JSON report: {e}")
            return TestResult()

        return self._process_report(report, project_root)

    def _process_report(
        self,
        report: Dict[str, Any],
        project_root: Path,
    ) -> TestResult:
        """Process Karma JSON report.

        Args:
            report: Parsed JSON report.
            project_root: Project root directory.

        Returns:
            TestResult with processed data.
        """
        summary = report.get("summary", {})
        num_passed = summary.get("success", 0)
        num_failed = summary.get("failed", 0)
        num_skipped = summary.get("skipped", 0)
        num_errors = summary.get("error", 0)

        # Get duration if available
        duration_ms = 0
        if "totalTime" in summary:
            duration_ms = int(summary["totalTime"])

        result = TestResult(
            passed=num_passed,
            failed=num_failed,
            skipped=num_skipped,
            errors=num_errors,
            duration_ms=duration_ms,
        )

        # Process browsers results
        browsers = report.get("browsers", {})
        for browser_name, browser_results in browsers.items():
            for test_result in browser_results.get("results", []):
                if not test_result.get("success", True):
                    issue = self._test_to_issue(test_result, project_root)
                    if issue:
                        result.issues.append(issue)

        LOGGER.info(
            f"Karma: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped, {result.errors} errors"
        )
        return result

    def _parse_stdout(
        self,
        stdout: str,
        stderr: str,
        project_root: Path,
    ) -> TestResult:
        """Parse Karma output from stdout/stderr.

        This is a fallback when JSON reporter is not available.

        Args:
            stdout: Standard output from Karma.
            stderr: Standard error from Karma.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult()

        # Look for summary line like "Executed 42 of 42 SUCCESS"
        # or "Executed 42 of 42 (1 FAILED)"
        import re

        # Pattern for success: "Executed X of Y SUCCESS"
        success_pattern = r"Executed (\d+) of (\d+).*SUCCESS"
        # Pattern for failures: "Executed X of Y (Z FAILED)"
        failure_pattern = r"Executed (\d+) of (\d+).*\((\d+) FAILED\)"
        # Pattern for skipped: "Executed X of Y (Z skipped)"
        skipped_pattern = r"\((\d+) skipped\)"

        output = stdout + stderr

        success_match = re.search(success_pattern, output)
        failure_match = re.search(failure_pattern, output)
        skipped_match = re.search(skipped_pattern, output)

        if failure_match:
            executed = int(failure_match.group(1))
            failed = int(failure_match.group(3))
            result.failed = failed
            result.passed = executed - failed
        elif success_match:
            executed = int(success_match.group(1))
            result.passed = executed

        if skipped_match:
            result.skipped = int(skipped_match.group(1))

        # Parse individual failure messages
        # Pattern: "FAILED: Suite Name Test Name"
        failure_lines = re.findall(r"FAILED[:\s]+(.+)", output)
        for failure in failure_lines:
            issue = self._failure_line_to_issue(failure, project_root)
            if issue:
                result.issues.append(issue)

        LOGGER.info(
            f"Karma: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )
        return result

    def _test_to_issue(
        self,
        test_result: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert Karma test failure to UnifiedIssue.

        Args:
            test_result: Test result dict from Karma JSON.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            suite = test_result.get("suite", [])
            description_name = test_result.get("description", "")
            log = test_result.get("log", [])

            # Build full test name
            full_name = " > ".join(suite + [description_name])

            # Get failure message
            message = log[0] if log else "Test failed"

            # Try to extract file path and line from error stack
            file_path, line_number = self._extract_location(message, project_root)

            # Generate deterministic ID
            issue_id = self._generate_issue_id(full_name, message)

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="karma",
                severity=Severity.HIGH,
                rule_id="failed",
                title=f"{full_name}: {self._truncate(message, 80)}",
                description=message,
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "full_name": full_name,
                    "suite": suite,
                    "description": description_name,
                    "log": log,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Karma test failure: {e}")
            return None

    def _failure_line_to_issue(
        self,
        failure: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a failure line to UnifiedIssue.

        Args:
            failure: Failure description string.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            issue_id = self._generate_issue_id(failure, "")

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="karma",
                severity=Severity.HIGH,
                rule_id="failed",
                title=self._truncate(failure, 100),
                description=failure,
                file_path=None,
                line_start=None,
                line_end=None,
                fixable=False,
                metadata={
                    "failure_line": failure,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Karma failure line: {e}")
            return None

    def _extract_location(
        self,
        message: str,
        project_root: Path,
    ) -> tuple[Optional[Path], Optional[int]]:
        """Extract file path and line number from error message.

        Args:
            message: Error message with potential stack trace.
            project_root: Project root directory.

        Returns:
            Tuple of (file_path, line_number) or (None, None).
        """
        import re

        # Look for patterns like "at Context.<anonymous> (src/app/foo.spec.ts:42:15)"
        # or "src/app/foo.spec.ts:42:15"
        patterns = [
            r"\(([^)]+\.(?:spec|test)\.ts):(\d+):\d+\)",
            r"([^\s]+\.(?:spec|test)\.ts):(\d+):\d+",
            r"\(([^)]+\.ts):(\d+):\d+\)",
            r"([^\s]+\.ts):(\d+):\d+",
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                file_str = match.group(1)
                line_num = int(match.group(2))
                file_path = Path(file_str)
                if not file_path.is_absolute():
                    file_path = project_root / file_path
                return file_path, line_num

        return None, None

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length.

        Args:
            text: Text to truncate.
            max_length: Maximum length.

        Returns:
            Truncated text.
        """
        text = text.replace("\n", " ").strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def _generate_issue_id(self, full_name: str, message: str) -> str:
        """Generate deterministic issue ID.

        Args:
            full_name: Full test name.
            message: Failure message.

        Returns:
            Unique issue ID.
        """
        content = f"{full_name}:{message[:100]}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"karma-{hash_val}"
