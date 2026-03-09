"""Base class for test runner plugins.

All test runner plugins inherit from TestRunnerPlugin and implement the run_tests() method.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)


@dataclass
class TestResult:
    """Result statistics from test execution."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: int = 0
    issues: List[UnifiedIssue] = field(default_factory=list)
    tool: str = ""  # Name of the test runner that produced this result

    @property
    def total(self) -> int:
        """Total number of tests run."""
        return self.passed + self.failed + self.skipped + self.errors

    @property
    def success(self) -> bool:
        """Whether all tests passed (no failures or errors)."""
        return self.failed == 0 and self.errors == 0


class TestRunnerPlugin(ABC):
    """Abstract base class for test runner plugins.

    Test runner plugins provide test execution functionality for the quality pipeline.
    Each plugin wraps a specific test framework (pytest, Jest, etc.).
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the test runner plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g., 'pytest', 'jest').

        Returns:
            Plugin name string.
        """

    @property
    @abstractmethod
    def languages(self) -> List[str]:
        """Languages this test runner supports.

        Returns:
            List of language names (e.g., ['python'], ['javascript', 'typescript']).
        """

    @property
    def domain(self) -> ToolDomain:
        """Tool domain (always TESTING for test runners).

        Returns:
            ToolDomain.TESTING
        """
        return ToolDomain.TESTING

    def get_version(self) -> str:
        """Get the version of the underlying test framework.

        Default implementation calls ``ensure_binary()`` and parses the
        CLI output via ``get_cli_version``.  Subclasses that need custom
        parsing (e.g. pytest, playwright) should override this method.

        Returns:
            Version string, or ``"unknown"`` on failure.
        """
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the test framework is installed.

        Finds or installs the tool if not present.

        Returns:
            Path to the tool binary.

        Raises:
            FileNotFoundError: If the tool cannot be found or installed.
        """

    @abstractmethod
    def run_tests(self, context: ScanContext) -> TestResult:
        """Run tests on the specified paths.

        Test runners that support it (pytest, jest, vitest, maven) include
        coverage instrumentation automatically. Others (cargo test, karma,
        playwright) do not — their coverage tools are either separate
        (tarpaulin) or config-driven (karma).

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """

    # --- Shared helpers for Jest-compatible JSON report processing ---

    def _parse_json_report_file(
        self,
        report_file: Path,
        project_root: Path,
    ) -> TestResult:
        """Parse a Jest-compatible JSON report file.

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
            LOGGER.error(f"Failed to parse {self.name} JSON report: {e}")
            return TestResult()

        return self._process_jest_report(report, project_root)

    def _parse_json_output(
        self,
        output: str,
        project_root: Path,
    ) -> TestResult:
        """Parse Jest-compatible JSON output from stdout.

        Args:
            output: JSON output string.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        if not output.strip():
            return TestResult()

        try:
            report = json.loads(output)
        except json.JSONDecodeError as e:
            LOGGER.warning(f"Failed to parse {self.name} JSON output: {e}")
            return TestResult()

        return self._process_jest_report(report, project_root)

    def _process_jest_report(
        self,
        report: Dict[str, Any],
        project_root: Path,
    ) -> TestResult:
        """Process a Jest-compatible JSON report.

        Both Jest and Vitest use this same format.

        Args:
            report: Parsed JSON report.
            project_root: Project root directory.

        Returns:
            TestResult with processed data.
        """
        num_passed = report.get("numPassedTests", 0)
        num_failed = report.get("numFailedTests", 0)
        num_pending = report.get("numPendingTests", 0)
        num_todo = report.get("numTodoTests", 0)

        test_results = report.get("testResults", [])
        duration_ms = 0
        for test_result in test_results:
            duration_ms += test_result.get("endTime", 0) - test_result.get(
                "startTime", 0
            )

        result = TestResult(
            passed=num_passed,
            failed=num_failed,
            skipped=num_pending + num_todo,
            errors=0,
            duration_ms=duration_ms,
        )

        # Convert failures to issues
        for test_file in test_results:
            if test_file.get("status") == "failed":
                for assertion in test_file.get("assertionResults", []):
                    if assertion.get("status") == "failed":
                        issue = self._assertion_to_issue(
                            assertion, test_file, project_root
                        )
                        if issue:
                            result.issues.append(issue)

        LOGGER.info(
            f"{self.name}: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )
        return result

    def _assertion_to_issue(
        self,
        assertion: Dict[str, Any],
        test_file: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a Jest-compatible assertion failure to UnifiedIssue.

        Args:
            assertion: Assertion result dict.
            test_file: Test file result dict.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            full_name = assertion.get("fullName", "")
            title_parts = assertion.get("ancestorTitles", [])
            test_name = assertion.get("title", "")
            failure_messages = assertion.get("failureMessages", [])
            location = assertion.get("location", {})

            file_name = test_file.get("name", "")
            file_path = Path(file_name)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            line_number = location.get("line") if location else None

            if title_parts:
                display_name = " > ".join(title_parts + [test_name])
            else:
                display_name = test_name

            message = failure_messages[0] if failure_messages else "Test failed"
            assertion_text = self._extract_assertion(message)

            issue_id = self._generate_issue_id(full_name, assertion_text)

            title = (
                f"{display_name}: {assertion_text}"
                if assertion_text
                else f"{display_name} failed"
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool=self.name,
                severity=Severity.HIGH,
                rule_id="failed",
                title=title,
                description=message,
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "full_name": full_name,
                    "test_name": test_name,
                    "ancestor_titles": title_parts,
                    "failure_messages": failure_messages,
                    "assertion": assertion_text,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse {self.name} assertion failure: {e}")
            return None

    def _extract_assertion(self, message: str) -> str:
        """Extract assertion from a Jest-compatible failure message.

        Args:
            message: Failure message.

        Returns:
            Extracted assertion or truncated message.
        """
        if not message:
            return ""

        lines = message.strip().split("\n")

        for line in lines:
            line = line.strip()
            if line.startswith("expect("):
                return line[:100]
            if line.startswith("Expected:"):
                idx = lines.index(line) if line in lines else -1
                if idx >= 0 and idx + 1 < len(lines):
                    received = lines[idx + 1].strip()
                    return f"{line} {received}"[:100]
                return line[:100]

        for line in lines:
            line = line.strip()
            if line and not line.startswith("at ") and len(line) > 5:
                return line[:100]

        return message[:100]

    def _generate_issue_id(self, full_name: str, assertion: str) -> str:
        """Generate deterministic issue ID for test failures.

        Args:
            full_name: Full test name with ancestors.
            assertion: Assertion message.

        Returns:
            Unique issue ID.
        """
        content = f"{full_name}:{assertion}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"{self.name}-{hash_val}"
