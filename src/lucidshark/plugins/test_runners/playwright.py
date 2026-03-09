"""Playwright test runner plugin.

Playwright is a framework for end-to-end testing of web applications.
https://playwright.dev/
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
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.test_runners.base import TestRunnerPlugin, TestResult
from lucidshark.plugins.utils import ensure_node_binary, get_cli_version

LOGGER = get_logger(__name__)


class PlaywrightRunner(TestRunnerPlugin):
    """Playwright test runner plugin for E2E test execution."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize PlaywrightRunner.

        Args:
            project_root: Optional project root for finding Playwright installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "playwright"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    def get_version(self) -> str:
        """Get Playwright version."""
        try:
            binary = self.ensure_binary()

            def parse_playwright_version(output: str) -> str:
                # Output is like "Version 1.55.0"
                if output.startswith("Version "):
                    return output[8:]
                return output

            return get_cli_version(binary, parser=parse_playwright_version)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure Playwright is available."""
        return ensure_node_binary(
            self._project_root,
            "playwright",
            "Playwright is not installed. Install it with:\n"
            "  npm install @playwright/test --save-dev\n"
            "  npx playwright install"
        )

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run Playwright on the specified paths.

        Playwright does not typically produce coverage data.

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

        cmd = [
            str(binary),
            "test",
            "--reporter=json",
        ]

        # Add paths to test if specified
        if context.paths:
            paths = [str(p) for p in context.paths]
            cmd.extend(paths)

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(context.project_root),
                timeout=900,  # 15 minute timeout for E2E tests
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Playwright timed out after 900 seconds")
            return TestResult()
        except Exception as e:
            LOGGER.error(f"Failed to run Playwright: {e}")
            return TestResult()

        # Playwright outputs JSON to stdout when using --reporter=json
        return self._parse_json_output(result.stdout, context.project_root)

    def _parse_json_output(
        self,
        output: str,
        project_root: Path,
    ) -> TestResult:
        """Parse Playwright JSON output.

        Args:
            output: JSON output from Playwright.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        if not output.strip():
            return TestResult()

        try:
            report = json.loads(output)
        except json.JSONDecodeError as e:
            LOGGER.warning(f"Failed to parse Playwright JSON output: {e}")
            return TestResult()

        return self._process_report(report, project_root)

    def _process_report(
        self,
        report: Dict[str, Any],
        project_root: Path,
    ) -> TestResult:
        """Process Playwright JSON report.

        Args:
            report: Parsed JSON report.
            project_root: Project root directory.

        Returns:
            TestResult with processed data.
        """
        stats = report.get("stats", {})

        # Calculate statistics
        num_passed = stats.get("expected", 0)
        num_failed = stats.get("unexpected", 0)
        num_skipped = stats.get("skipped", 0)
        num_flaky = stats.get("flaky", 0)

        # Get duration
        duration_ms = stats.get("duration", 0)

        result = TestResult(
            passed=num_passed + num_flaky,  # Flaky tests eventually passed
            failed=num_failed,
            skipped=num_skipped,
            errors=0,
            duration_ms=duration_ms,
        )

        # Process suites and tests
        suites = report.get("suites", [])
        for suite in suites:
            self._process_suite(suite, [], project_root, result)

        LOGGER.info(
            f"Playwright: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )
        return result

    def _process_suite(
        self,
        suite: Dict[str, Any],
        ancestors: List[str],
        project_root: Path,
        result: TestResult,
    ) -> None:
        """Process a test suite recursively.

        Args:
            suite: Suite data from Playwright report.
            ancestors: List of parent suite titles.
            project_root: Project root directory.
            result: TestResult to append issues to.
        """
        suite_title = suite.get("title", "")
        current_ancestors = ancestors + [suite_title] if suite_title else ancestors

        # Process specs (test cases)
        for spec in suite.get("specs", []):
            self._process_spec(spec, current_ancestors, suite, project_root, result)

        # Process nested suites
        for nested_suite in suite.get("suites", []):
            self._process_suite(nested_suite, current_ancestors, project_root, result)

    def _process_spec(
        self,
        spec: Dict[str, Any],
        ancestors: List[str],
        suite: Dict[str, Any],
        project_root: Path,
        result: TestResult,
    ) -> None:
        """Process a test spec.

        Args:
            spec: Spec data from Playwright report.
            ancestors: List of parent suite titles.
            suite: Parent suite data.
            project_root: Project root directory.
            result: TestResult to append issues to.
        """
        # Check if any test failed
        for test in spec.get("tests", []):
            status = test.get("status", "")

            if status in ["unexpected", "failed"]:
                issue = self._test_to_issue(
                    spec, test, ancestors, suite, project_root
                )
                if issue:
                    result.issues.append(issue)

    def _test_to_issue(
        self,
        spec: Dict[str, Any],
        test: Dict[str, Any],
        ancestors: List[str],
        suite: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert Playwright test failure to UnifiedIssue.

        Args:
            spec: Spec data.
            test: Test data.
            ancestors: List of parent suite titles.
            suite: Parent suite data.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            test_title = spec.get("title", "")
            full_name = " > ".join(ancestors + [test_title])

            # Get error information from results
            results = test.get("results", [])
            error_message = ""
            error_stack = ""

            for result_item in results:
                if result_item.get("status") in ["unexpected", "failed"]:
                    error = result_item.get("error", {})
                    error_message = error.get("message", "")
                    error_stack = error.get("stack", "")
                    break

            # Get file location
            file_path = None
            line_number = None

            # Try to get location from spec
            spec_file = spec.get("file", "") or suite.get("file", "")
            spec_line = spec.get("line")

            if spec_file:
                file_path = Path(spec_file)
                if not file_path.is_absolute():
                    file_path = project_root / file_path
                line_number = spec_line

            # If no spec location, try to extract from stack trace
            if not file_path and error_stack:
                file_path, line_number = self._extract_location(
                    error_stack, project_root
                )

            # Build description
            description = error_message
            if error_stack and error_stack != error_message:
                description = f"{error_message}\n\n{error_stack}"

            # Generate deterministic ID
            issue_id = self._generate_issue_id(full_name, error_message)

            # Get browser info
            project_name = test.get("projectName", "")
            browser_info = f" [{project_name}]" if project_name else ""

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="playwright",
                severity=Severity.HIGH,
                rule_id="failed",
                title=f"{full_name}{browser_info}: {self._truncate(error_message, 60)}",
                description=description,
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "full_name": full_name,
                    "test_title": test_title,
                    "ancestors": ancestors,
                    "project_name": project_name,
                    "error_message": error_message,
                    "error_stack": error_stack,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Playwright test failure: {e}")
            return None

    def _extract_location(
        self,
        stack: str,
        project_root: Path,
    ) -> tuple[Optional[Path], Optional[int]]:
        """Extract file path and line number from stack trace.

        Args:
            stack: Error stack trace.
            project_root: Project root directory.

        Returns:
            Tuple of (file_path, line_number) or (None, None).
        """
        import re

        # Look for patterns like "at /path/to/file.ts:42:15"
        # or "file.spec.ts:42"
        patterns = [
            r"at\s+(?:[^\s]+\s+\()?([^:]+\.(?:spec|test)\.[tj]sx?):(\d+)",
            r"([^\s:]+\.(?:spec|test)\.[tj]sx?):(\d+)",
            r"at\s+(?:[^\s]+\s+\()?([^:]+\.[tj]sx?):(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, stack)
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
        if not text:
            return "Test failed"
        text = text.replace("\n", " ").strip()
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    def _generate_issue_id(self, full_name: str, message: str) -> str:
        """Generate deterministic issue ID.

        Args:
            full_name: Full test name.
            message: Failure message.

        Returns:
            Unique issue ID.
        """
        content = f"{full_name}:{message[:100] if message else ''}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"playwright-{hash_val}"
