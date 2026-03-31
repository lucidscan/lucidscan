"""Swift test runner plugin.

Runs Swift tests via `swift test` and parses the output
for test results and failures.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.swift_utils import (
    find_swift,
    get_swift_version,
    has_package_swift,
)
from lucidshark.plugins.test_runners.base import TestResult, TestRunnerPlugin

LOGGER = get_logger(__name__)


class SwiftTestRunner(TestRunnerPlugin):
    """Swift test runner plugin for XCTest execution via swift test."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "swift_test"

    @property
    def languages(self) -> List[str]:
        return ["swift"]

    def get_version(self) -> str:
        return get_swift_version()

    def ensure_binary(self) -> Path:
        return find_swift()

    def run_tests(self, context: ScanContext) -> TestResult:
        try:
            swift_bin = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="swift_test")

        if not has_package_swift(context.project_root):
            LOGGER.info("No Package.swift found, skipping swift test")
            return TestResult(tool="swift_test")

        cmd = [str(swift_bin), "test"]

        # Add code coverage flag when coverage domain is enabled
        if ToolDomain.COVERAGE in context.enabled_domains:
            cmd.append("--enable-code-coverage")

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        stdout = ""
        stderr = ""
        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="swift-test",
                stream_handler=context.stream_handler,
                timeout=600,
            )
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            LOGGER.warning("swift test timed out after 600 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="swift test timed out after 600 seconds",
            )
            return TestResult(tool="swift_test")
        except subprocess.CalledProcessError as e:
            # swift test returns non-zero on failures - that's normal
            LOGGER.debug(f"swift test completed with: {e}")
            stdout = e.stdout or ""
            stderr = e.stderr or ""
        except Exception as e:
            LOGGER.debug(f"swift test completed with: {e}")

        combined = (stdout or "") + "\n" + (stderr or "")
        return self._parse_test_output(combined, context.project_root)

    def _parse_test_output(self, output: str, project_root: Path) -> TestResult:
        """Parse swift test text output.

        swift test outputs lines like:
            Test Case '-[MyTests.CalculatorTests testAdd]' passed (0.001 seconds).
            Test Case '-[MyTests.CalculatorTests testDivide]' failed (0.002 seconds).
            Test Suite 'All tests' passed at 2024-01-01 12:00:00.000.
                 Executed 5 tests, with 1 failure (0 unexpected) in 0.005 (0.006) seconds
        """
        result = TestResult(tool="swift_test")

        # Count individual test results
        # Pattern: Test Case '...' passed/failed
        passed_pattern = r"Test Case '.*' passed"
        failed_pattern = r"Test Case '.*' failed"

        result.passed = len(re.findall(passed_pattern, output))
        result.failed = len(re.findall(failed_pattern, output))

        # Parse summary line for more accurate counts:
        # "Executed N tests, with M failure(s) (K unexpected) in X (Y) seconds"
        summary_pattern = r"Executed (\d+) tests?, with (\d+) failures?"
        match = re.search(summary_pattern, output)
        if match:
            total = int(match.group(1))
            failures = int(match.group(2))
            # Use the summary counts if available
            result.passed = total - failures
            result.failed = failures

        # Extract failure details
        failed_tests = self._extract_failed_tests(output)
        for test_name, failure_message in failed_tests:
            issue = self._failure_to_issue(test_name, failure_message, project_root)
            if issue:
                result.issues.append(issue)

        LOGGER.info(
            f"swift_test: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )
        return result

    def _extract_failed_tests(self, output: str) -> List[Tuple[str, str]]:
        """Extract failed test names and their failure messages.

        Parses output sequentially: assertion failures appear before their
        corresponding "Test Case ... failed" line, so we collect pending
        assertions and associate them with the next failed test case.
        """
        failed_tests = []

        # XCTest failure line pattern:
        #   Test Case '-[Module.Class testMethod]' failed (X seconds).
        fail_pattern = re.compile(r"Test Case '-\[(.+?)\]' failed")

        # Swift Testing failure line pattern:
        #   Test "testName" failed (X seconds).
        swift_testing_fail = re.compile(r'Test "(.+?)" failed')

        # Assertion failure pattern (appears before the failed test case line):
        #   /path/File.swift:25: XCTAssertEqual failed: ("1") is not equal to ("0")
        assertion_pattern = re.compile(
            r".+\.swift:\d+:\s+(XCT\w+ failed:.+?)$"
        )

        pending_assertions: List[str] = []

        for line in output.splitlines():
            # Check for assertion failure lines
            assertion_match = assertion_pattern.match(line.strip())
            if assertion_match:
                pending_assertions.append(assertion_match.group(1))
                continue

            # Check for XCTest failed test case
            fail_match = fail_pattern.search(line)
            if not fail_match:
                fail_match = swift_testing_fail.search(line)

            if fail_match:
                test_name = fail_match.group(1)
                message = "; ".join(pending_assertions) if pending_assertions else "Test failed"
                failed_tests.append((test_name, message))
                pending_assertions = []

        return failed_tests

    def _failure_to_issue(
        self,
        test_name: str,
        failure_message: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a test failure to UnifiedIssue."""
        try:
            file_path = self._resolve_test_file(test_name, project_root)
            line_number = self._extract_line_from_message(failure_message)

            short_msg = (
                failure_message[:80] + "..."
                if len(failure_message) > 80
                else failure_message
            )
            short_msg = short_msg.replace("\n", " ")
            title = (
                f"{test_name} FAILED: {short_msg}"
                if short_msg
                else f"{test_name} FAILED"
            )

            issue_id = self._generate_swift_issue_id(test_name, failure_message)

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="swift_test",
                severity=Severity.HIGH,
                rule_id="test_failed",
                title=title,
                description=f"Test {test_name} failed:\n{failure_message[:500]}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "test_name": test_name,
                    "outcome": "failed",
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse test failure: {e}")
            return None

    def _resolve_test_file(self, test_name: str, project_root: Path) -> Optional[Path]:
        """Resolve test file path from test name."""
        # test_name format: "Module.TestClass testMethod"
        parts = test_name.split(".")
        if len(parts) >= 2:
            class_name = parts[-1].split(" ")[0] if " " in parts[-1] else parts[-1]
            # Check Tests/ directory
            for test_file in project_root.rglob("Tests/**/*.swift"):
                if class_name in test_file.name:
                    return test_file

        # Fallback: check for any test files
        tests_dir = project_root / "Tests"
        if tests_dir.exists():
            swift_files = list(tests_dir.rglob("*.swift"))
            if swift_files:
                return swift_files[0]

        return None

    def _extract_line_from_message(self, message: str) -> Optional[int]:
        """Extract line number from failure message."""
        match = re.search(r"\.swift:(\d+):", message)
        if match:
            return int(match.group(1))
        return None

    def _generate_swift_issue_id(self, test_name: str, message: str) -> str:
        """Generate deterministic issue ID."""
        content = f"{test_name}:{message[:50]}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"swift-test-{hash_val}"
