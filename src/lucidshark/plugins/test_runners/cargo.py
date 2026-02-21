"""Cargo test runner plugin.

Runs Rust tests via `cargo test` and parses the output
for test results and failures.
"""

from __future__ import annotations

import hashlib
import re
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
from lucidshark.plugins.rust_utils import find_cargo, get_cargo_version
from lucidshark.plugins.test_runners.base import TestRunnerPlugin, TestResult

LOGGER = get_logger(__name__)


class CargoTestRunner(TestRunnerPlugin):
    """Cargo test runner plugin for Rust test execution."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize CargoTestRunner.

        Args:
            project_root: Optional project root for tool resolution.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "cargo"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["rust"]

    def get_version(self) -> str:
        """Get cargo version."""
        return get_cargo_version()

    def ensure_binary(self) -> Path:
        """Ensure cargo is available.

        Returns:
            Path to cargo binary.

        Raises:
            FileNotFoundError: If cargo is not available.
        """
        return find_cargo()

    def run_tests(
        self, context: ScanContext, with_coverage: bool = False
    ) -> TestResult:
        """Run tests using cargo test.

        Args:
            context: Scan context with paths and configuration.
            with_coverage: If True, coverage is handled by the tarpaulin plugin.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            cargo = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="cargo")

        # Check for Cargo.toml
        if not (context.project_root / "Cargo.toml").exists():
            LOGGER.info("No Cargo.toml found, skipping cargo test")
            return TestResult(tool="cargo")

        cmd = [str(cargo), "test"]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        stdout = ""
        stderr = ""
        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="cargo-test",
                stream_handler=context.stream_handler,
                timeout=600,
            )
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            LOGGER.warning("cargo test timed out after 600 seconds")
            return TestResult(tool="cargo")
        except Exception as e:
            # cargo test returns non-zero on test failures
            LOGGER.debug(f"cargo test completed with: {e}")

        # Combine stdout and stderr for parsing
        combined = stdout + "\n" + stderr
        return self._parse_test_output(combined, context.project_root)

    def _parse_test_output(self, output: str, project_root: Path) -> TestResult:
        """Parse cargo test text output.

        Args:
            output: Combined stdout/stderr from cargo test.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="cargo")

        # Parse summary line:
        # "test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out"
        # or: "test result: FAILED. 3 passed; 2 failed; 0 ignored; 0 measured; 0 filtered out"
        summary_pattern = (
            r"test result: (?:ok|FAILED)\.\s+"
            r"(\d+)\s+passed;\s+"
            r"(\d+)\s+failed;\s+"
            r"(\d+)\s+ignored;\s+"
            r"(\d+)\s+measured;\s+"
            r"(\d+)\s+filtered out"
        )

        total_passed = 0
        total_failed = 0
        total_skipped = 0

        for match in re.finditer(summary_pattern, output):
            total_passed += int(match.group(1))
            total_failed += int(match.group(2))
            total_skipped += int(match.group(3))

        result.passed = total_passed
        result.failed = total_failed
        result.skipped = total_skipped

        # Parse individual test failures
        failed_tests = self._extract_failed_tests(output)

        for test_name, failure_message in failed_tests:
            issue = self._failure_to_issue(
                test_name, failure_message, project_root
            )
            if issue:
                result.issues.append(issue)

        return result

    def _extract_failed_tests(self, output: str) -> List[tuple]:
        """Extract failed test names and their messages.

        Args:
            output: Combined test output.

        Returns:
            List of (test_name, failure_message) tuples.
        """
        failed_tests = []

        # Find individual test failures: "test tests::test_name ... FAILED"
        fail_pattern = r"test\s+([\w:]+)\s+\.\.\.\s+FAILED"
        failed_names = re.findall(fail_pattern, output)

        # Extract failure details from the "failures:" section
        failures_section = ""
        in_failures = False
        for line in output.splitlines():
            if line.strip() == "failures:":
                in_failures = True
                continue
            if in_failures and line.strip().startswith("test result:"):
                break
            if in_failures:
                failures_section += line + "\n"

        # Parse individual failure outputs
        for test_name in failed_names:
            # Look for "---- test_name stdout ----" section
            short_name = test_name.split("::")[-1]
            pattern = rf"---- {re.escape(test_name)} stdout ----\n(.*?)(?=\n---- |\nfailures:|\Z)"
            match = re.search(pattern, failures_section, re.DOTALL)
            if not match:
                # Try with short name
                pattern = rf"---- {re.escape(short_name)} stdout ----\n(.*?)(?=\n---- |\nfailures:|\Z)"
                match = re.search(pattern, failures_section, re.DOTALL)

            message = match.group(1).strip() if match else "Test failed"
            failed_tests.append((test_name, message))

        return failed_tests

    def _failure_to_issue(
        self,
        test_name: str,
        failure_message: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a test failure to UnifiedIssue.

        Args:
            test_name: Fully qualified test name (e.g., "tests::test_add").
            failure_message: Failure/assertion message.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            # Try to resolve file path from test name
            file_path = self._resolve_test_file(test_name, project_root)
            line_number = self._extract_line_from_message(failure_message)

            # Truncate message for title
            short_msg = failure_message[:80] + "..." if len(failure_message) > 80 else failure_message
            short_msg = short_msg.replace("\n", " ")
            title = f"{test_name} FAILED: {short_msg}" if short_msg else f"{test_name} FAILED"

            issue_id = self._generate_issue_id(test_name, failure_message)

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="cargo",
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

    def _resolve_test_file(
        self, test_name: str, project_root: Path
    ) -> Optional[Path]:
        """Resolve test file path from test name.

        Args:
            test_name: Test name like "test_calculator::test_add" or "tests::test_foo".
            project_root: Project root directory.

        Returns:
            Path to test file or None.
        """
        parts = test_name.split("::")

        # Check tests/ directory for integration tests
        if len(parts) >= 1:
            test_file = project_root / "tests" / f"{parts[0]}.rs"
            if test_file.exists():
                return test_file

        # Check src/lib.rs for unit tests
        lib_rs = project_root / "src" / "lib.rs"
        if lib_rs.exists():
            return lib_rs

        # Check src/main.rs
        main_rs = project_root / "src" / "main.rs"
        if main_rs.exists():
            return main_rs

        return None

    def _extract_line_from_message(self, message: str) -> Optional[int]:
        """Extract line number from failure message.

        Args:
            message: Failure message text.

        Returns:
            Line number or None.
        """
        # Look for patterns like "src/lib.rs:42:5"
        match = re.search(r"[\w/]+\.rs:(\d+):\d+", message)
        if match:
            return int(match.group(1))
        return None

    def _generate_issue_id(self, test_name: str, message: str) -> str:
        """Generate deterministic issue ID.

        Args:
            test_name: Test name.
            message: Failure message.

        Returns:
            Unique issue ID.
        """
        content = f"{test_name}:{message[:50]}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"cargo-test-{hash_val}"
