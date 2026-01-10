"""pytest test runner plugin.

pytest is a full-featured testing framework for Python.
https://docs.pytest.org/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import defusedxml.ElementTree as ElementTree

from lucidscan.core.logging import get_logger
from lucidscan.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidscan.plugins.test_runners.base import TestRunnerPlugin, TestResult

LOGGER = get_logger(__name__)


class PytestRunner(TestRunnerPlugin):
    """pytest test runner plugin for Python test execution."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize PytestRunner.

        Args:
            project_root: Optional project root for finding pytest installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "pytest"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["python"]

    def get_version(self) -> str:
        """Get pytest version.

        Returns:
            Version string or 'unknown' if unable to determine.
        """
        try:
            binary = self.ensure_binary()
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Output is like "pytest 8.0.0"
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    return parts[1]
        except Exception:
            pass
        return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure pytest is available.

        Checks for pytest in:
        1. Project's .venv/bin/pytest
        2. System PATH

        Returns:
            Path to pytest binary.

        Raises:
            FileNotFoundError: If pytest is not installed.
        """
        # Check project venv first
        if self._project_root:
            venv_pytest = self._project_root / ".venv" / "bin" / "pytest"
            if venv_pytest.exists():
                return venv_pytest

        # Check system PATH
        pytest_path = shutil.which("pytest")
        if pytest_path:
            return Path(pytest_path)

        raise FileNotFoundError(
            "pytest is not installed. Install it with: pip install pytest"
        )

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run pytest on the specified paths.

        Attempts to use pytest-json-report for JSON output.
        Falls back to JUnit XML if JSON plugin not available.

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

        # Check if pytest-json-report is available
        if self._has_json_report_plugin(binary, context.project_root):
            return self._run_with_json_report(binary, context)
        else:
            return self._run_with_junit_xml(binary, context)

    def _has_json_report_plugin(self, binary: Path, project_root: Path) -> bool:
        """Check if pytest-json-report plugin is available.

        Args:
            binary: Path to pytest binary.
            project_root: Project root directory.

        Returns:
            True if pytest-json-report is installed.
        """
        try:
            subprocess.run(
                [str(binary), "--co", "-q"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=60,
            )
            # Check if json-report option is available
            help_result = subprocess.run(
                [str(binary), "--help"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=30,
            )
            return "--json-report" in help_result.stdout
        except Exception:
            return False

    def _run_with_json_report(
        self,
        binary: Path,
        context: ScanContext,
    ) -> TestResult:
        """Run pytest with JSON report output.

        Args:
            binary: Path to pytest binary.
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "report.json"

            cmd = [
                str(binary),
                "--tb=short",
                "-q",
                "--json-report",
                f"--json-report-file={report_file}",
            ]

            # Add paths to test
            paths = [str(p) for p in context.paths] if context.paths else ["."]
            cmd.extend(paths)

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(context.project_root),
                    timeout=600,  # 10 minute timeout for test runs
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("pytest timed out after 600 seconds")
                return TestResult()
            except Exception as e:
                LOGGER.error(f"Failed to run pytest: {e}")
                return TestResult()

            # Parse JSON report
            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root)
            else:
                LOGGER.warning("JSON report file not generated")
                return TestResult()

    def _run_with_junit_xml(
        self,
        binary: Path,
        context: ScanContext,
    ) -> TestResult:
        """Run pytest with JUnit XML output (fallback).

        Args:
            binary: Path to pytest binary.
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "junit.xml"

            cmd = [
                str(binary),
                "--tb=short",
                "-q",
                f"--junit-xml={report_file}",
            ]

            # Add paths to test
            paths = [str(p) for p in context.paths] if context.paths else ["."]
            cmd.extend(paths)

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(context.project_root),
                    timeout=600,  # 10 minute timeout for test runs
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("pytest timed out after 600 seconds")
                return TestResult()
            except Exception as e:
                LOGGER.error(f"Failed to run pytest: {e}")
                return TestResult()

            # Parse JUnit XML report
            if report_file.exists():
                return self._parse_junit_xml(report_file, context.project_root)
            else:
                LOGGER.warning("JUnit XML report file not generated")
                return TestResult()

    def _parse_json_report(
        self,
        report_file: Path,
        project_root: Path,
    ) -> TestResult:
        """Parse pytest JSON report.

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
            LOGGER.error(f"Failed to parse JSON report: {e}")
            return TestResult()

        summary = report.get("summary", {})
        tests = report.get("tests", [])
        duration = report.get("duration", 0)

        result = TestResult(
            passed=summary.get("passed", 0),
            failed=summary.get("failed", 0),
            skipped=summary.get("skipped", 0) + summary.get("xfailed", 0),
            errors=summary.get("error", 0),
            duration_ms=int(duration * 1000),
        )

        # Convert failures to issues
        for test in tests:
            outcome = test.get("outcome", "")
            if outcome in ("failed", "error"):
                issue = self._test_to_issue(test, project_root, outcome)
                if issue:
                    result.issues.append(issue)

        LOGGER.info(
            f"pytest: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped, {result.errors} errors"
        )
        return result

    def _test_to_issue(
        self,
        test: Dict[str, Any],
        project_root: Path,
        outcome: str,
    ) -> Optional[UnifiedIssue]:
        """Convert pytest test failure to UnifiedIssue.

        Args:
            test: Test dict from JSON report.
            project_root: Project root directory.
            outcome: Test outcome (failed or error).

        Returns:
            UnifiedIssue or None.
        """
        try:
            nodeid = test.get("nodeid", "")
            call = test.get("call", {})
            longrepr = call.get("longrepr", "")
            duration = call.get("duration", 0)

            # Parse nodeid for file and test name
            # Format: path/to/test_file.py::TestClass::test_method
            # or: path/to/test_file.py::test_function
            file_path = None
            test_name = nodeid
            line_number = None

            if "::" in nodeid:
                parts = nodeid.split("::")
                file_part = parts[0]
                test_name = "::".join(parts[1:])
                file_path = project_root / file_part

            # Extract line number from lineno if available
            lineno = test.get("lineno")
            if lineno:
                line_number = lineno

            # Get crash info for more details
            crash = call.get("crash", {})
            if not line_number and crash:
                line_number = crash.get("lineno")

            # Build message from longrepr
            message = self._extract_assertion_message(longrepr)

            # Determine severity
            severity = Severity.HIGH if outcome == "failed" else Severity.MEDIUM

            # Generate deterministic ID
            issue_id = self._generate_issue_id(nodeid, message)

            # Build title
            title = f"{test_name} {outcome}: {message}" if message else f"{test_name} {outcome}"

            return UnifiedIssue(
                id=issue_id,
                scanner=ToolDomain.TESTING,
                source_tool="pytest",
                severity=severity,
                title=title,
                description=longrepr or f"Test {outcome}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                scanner_metadata={
                    "nodeid": nodeid,
                    "test_name": test_name,
                    "outcome": outcome,
                    "duration_ms": int(duration * 1000),
                    "assertion": message,
                    "traceback": longrepr,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse pytest test failure: {e}")
            return None

    def _parse_junit_xml(
        self,
        report_file: Path,
        project_root: Path,
    ) -> TestResult:
        """Parse pytest JUnit XML report.

        Args:
            report_file: Path to JUnit XML file.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        try:
            tree = ElementTree.parse(report_file)
            root = tree.getroot()
        except Exception as e:
            LOGGER.error(f"Failed to parse JUnit XML report: {e}")
            return TestResult()

        # Get testsuite element (may be root or child)
        testsuite = root if root.tag == "testsuite" else root.find("testsuite")
        if testsuite is None:
            testsuite = root

        # Parse summary from attributes
        tests_total = int(testsuite.get("tests", 0))
        failures = int(testsuite.get("failures", 0))
        errors = int(testsuite.get("errors", 0))
        skipped = int(testsuite.get("skipped", 0))
        time_str = testsuite.get("time", "0")
        duration_ms = int(float(time_str) * 1000)

        result = TestResult(
            passed=tests_total - failures - errors - skipped,
            failed=failures,
            skipped=skipped,
            errors=errors,
            duration_ms=duration_ms,
        )

        # Parse individual test cases for failures
        for testcase in testsuite.iter("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")

            if failure is not None:
                issue = self._xml_testcase_to_issue(
                    testcase, failure, project_root, "failed"
                )
                if issue:
                    result.issues.append(issue)
            elif error is not None:
                issue = self._xml_testcase_to_issue(
                    testcase, error, project_root, "error"
                )
                if issue:
                    result.issues.append(issue)

        LOGGER.info(
            f"pytest: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped, {result.errors} errors"
        )
        return result

    def _xml_testcase_to_issue(
        self,
        testcase: ElementTree.Element,
        failure_elem: ElementTree.Element,
        project_root: Path,
        outcome: str,
    ) -> Optional[UnifiedIssue]:
        """Convert JUnit XML testcase failure to UnifiedIssue.

        Args:
            testcase: testcase XML element.
            failure_elem: failure or error XML element.
            project_root: Project root directory.
            outcome: Test outcome (failed or error).

        Returns:
            UnifiedIssue or None.
        """
        try:
            classname = testcase.get("classname", "")
            name = testcase.get("name", "")
            file_attr = testcase.get("file", "")
            line_attr = testcase.get("line")

            # Build file path
            file_path = None
            if file_attr:
                file_path = project_root / file_attr
            elif classname:
                # Try to convert classname to file path
                # e.g., tests.test_example -> tests/test_example.py
                file_guess = classname.replace(".", "/") + ".py"
                file_path = project_root / file_guess
                if not file_path.exists():
                    file_path = None

            # Get line number
            line_number = int(line_attr) if line_attr else None

            # Get failure message and content
            message = failure_elem.get("message", "")
            content = failure_elem.text or ""

            # Extract assertion from content
            assertion = self._extract_assertion_message(content) or message

            # Build nodeid for consistency
            nodeid = f"{classname}::{name}" if classname else name

            # Determine severity
            severity = Severity.HIGH if outcome == "failed" else Severity.MEDIUM

            # Generate deterministic ID
            issue_id = self._generate_issue_id(nodeid, assertion)

            # Build title
            title = f"{name} {outcome}: {assertion}" if assertion else f"{name} {outcome}"

            return UnifiedIssue(
                id=issue_id,
                scanner=ToolDomain.TESTING,
                source_tool="pytest",
                severity=severity,
                title=title,
                description=content or message or f"Test {outcome}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                scanner_metadata={
                    "nodeid": nodeid,
                    "test_name": name,
                    "classname": classname,
                    "outcome": outcome,
                    "assertion": assertion,
                    "traceback": content,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse JUnit XML testcase: {e}")
            return None

    def _extract_assertion_message(self, longrepr: str) -> str:
        """Extract assertion message from pytest output.

        Args:
            longrepr: Long representation of the test failure.

        Returns:
            Extracted assertion message or empty string.
        """
        if not longrepr:
            return ""

        # Look for common assertion patterns
        lines = longrepr.strip().split("\n")

        # Try to find AssertionError or assert line
        for line in reversed(lines):
            stripped = line.strip()
            # Handle E prefix from pytest output (e.g., "E       assert 1 == 2")
            if stripped.startswith("E "):
                content = stripped[2:].strip()
                if content.startswith("assert "):
                    return content
                if "AssertionError" in content:
                    return content.replace("AssertionError:", "").strip()
            if stripped.startswith("AssertionError:"):
                return stripped.replace("AssertionError:", "").strip()
            if stripped.startswith("assert "):
                return stripped
            if "AssertionError" in stripped:
                return stripped

        # Return first non-empty line as fallback
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith(">") and not stripped.startswith("E "):
                return stripped[:100]  # Truncate long messages

        return ""

    def _generate_issue_id(self, nodeid: str, message: str) -> str:
        """Generate deterministic issue ID.

        Args:
            nodeid: Test node ID (path::classname::testname).
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{nodeid}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"pytest-{hash_val}"
