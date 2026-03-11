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
import defusedxml.ElementTree as ElementTree  # type: ignore[import-untyped]
from xml.etree.ElementTree import Element

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.test_runners.base import TestRunnerPlugin, TestResult
from lucidshark.plugins.utils import (
    ensure_python_binary,
    get_cli_version,
    coverage_has_source_config,
    detect_source_directory,
    _is_binary_executable,
)

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
        """Get pytest version."""
        try:
            binary = self.ensure_binary()
            # Output is like "pytest 8.0.0"
            return get_cli_version(
                binary, parser=lambda s: s.split()[1] if len(s.split()) >= 2 else s
            )
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure pytest is available."""
        return ensure_python_binary(
            self._project_root,
            "pytest",
            "pytest is not installed. Install it with: pip install pytest",
        )

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run pytest on the specified paths.

        Always attempts to wrap with ``coverage run -m pytest`` if the
        coverage binary is found. If not found, runs pytest directly.

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
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
                suggestion="pip install pytest",
            )
            return TestResult()

        # Always attempt to use coverage if available
        coverage_binary = self._find_coverage_binary()
        if coverage_binary:
            LOGGER.debug("Coverage binary found, wrapping pytest with coverage")
        else:
            LOGGER.debug("Coverage binary not found, running pytest without coverage")

        # Check if pytest-json-report is available
        if self._has_json_report_plugin(binary, context.project_root):
            return self._run_with_json_report(binary, context, coverage_binary)
        else:
            return self._run_with_junit_xml(binary, context, coverage_binary)

    def _find_coverage_binary(self) -> Optional[Path]:
        """Find coverage.py binary.

        Returns:
            Path to coverage binary, or None if not found.
        """
        # Check project venv first (with shebang validation)
        if self._project_root:
            venv_coverage = self._project_root / ".venv" / "bin" / "coverage"
            if venv_coverage.exists() and _is_binary_executable(venv_coverage):
                return venv_coverage

        # Check system PATH
        coverage_path = shutil.which("coverage")
        if coverage_path:
            return Path(coverage_path)

        return None

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
                encoding="utf-8",
                errors="replace",
                cwd=str(project_root),
                timeout=60,
            )
            # Check if json-report option is available
            help_result = subprocess.run(
                [str(binary), "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(project_root),
                timeout=30,
            )
            return "--json-report" in help_result.stdout
        except Exception:
            return False

    def _build_base_cmd(
        self,
        binary: Path,
        coverage_binary: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> List[str]:
        """Build base pytest command, optionally wrapped with coverage.

        When ``coverage_binary`` is provided, the command is wrapped as
        ``coverage run [--source <dir>] -m pytest``.  The ``--source``
        flag is added automatically unless the project already has an
        explicit coverage source configuration (pyproject.toml, .coveragerc,
        or setup.cfg).
        """
        if coverage_binary:
            cmd = [str(coverage_binary), "run"]
            # Add --source so coverage only measures project code, not
            # third-party libraries or test files.
            if project_root and not coverage_has_source_config(project_root):
                source_dir = detect_source_directory(project_root)
                if source_dir:
                    cmd.extend(["--source", source_dir])
                    LOGGER.debug("Coverage --source set to: %s", source_dir)
            cmd.extend(["-m", "pytest"])
            return cmd
        return [str(binary)]

    def _execute_pytest(
        self,
        cmd: List[str],
        context: ScanContext,
    ) -> bool:
        """Execute pytest command with streaming output.

        Note: Unlike linting, tests always run the full suite to ensure
        complete test coverage. We don't pass context.paths to pytest
        because:
        1. Changed source files don't map directly to test files
        2. Coverage measurement requires running ALL tests
        3. Pytest's own test discovery (via testpaths) is more reliable

        Returns:
            True if execution succeeded, False on timeout/error.
        """
        # Don't pass context.paths - let pytest discover tests via its config
        # This ensures full test suite runs for accurate coverage measurement

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="pytest",
                stream_handler=context.stream_handler,
                timeout=600,
            )
            return True
        except subprocess.TimeoutExpired:
            LOGGER.warning("pytest timed out after 600 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="pytest timed out after 600 seconds",
            )
            return False
        except Exception as e:
            LOGGER.error(f"Failed to run pytest: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run pytest: {e}",
            )
            return False

    def _execution_failure_result(self, cmd: List[str]) -> TestResult:
        """Create a TestResult indicating that test execution failed entirely.

        This prevents silent passes when pytest fails to start (e.g., broken
        binary, missing dependency) or times out.

        Args:
            cmd: The command that failed.

        Returns:
            TestResult with 1 error and an issue describing the failure.
        """
        cmd_str = " ".join(cmd)
        return TestResult(
            errors=1,
            issues=[
                UnifiedIssue(
                    id=self._generate_issue_id("execution-failure", cmd_str),
                    domain=ToolDomain.TESTING,
                    source_tool="pytest",
                    severity=Severity.HIGH,
                    rule_id="execution-failure",
                    title="pytest failed to execute",
                    description=(
                        f"Failed to run test command: {cmd_str}\n\n"
                        "This may be caused by a broken virtual environment, "
                        "missing pytest installation, or a timeout. "
                        "Check that pytest is installed and working."
                    ),
                    fixable=False,
                )
            ],
        )

    def _run_with_json_report(
        self,
        binary: Path,
        context: ScanContext,
        coverage_binary: Optional[Path] = None,
    ) -> TestResult:
        """Run pytest with JSON report output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "report.json"

            cmd = self._build_base_cmd(binary, coverage_binary, context.project_root)
            cmd.extend(
                [
                    "--tb=short",
                    "-v",
                    "--json-report",
                    f"--json-report-file={report_file}",
                ]
            )

            if not self._execute_pytest(cmd, context):
                return self._execution_failure_result(cmd)

            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root)
            LOGGER.warning("JSON report file not generated")
            return self._execution_failure_result(cmd)

    def _run_with_junit_xml(
        self,
        binary: Path,
        context: ScanContext,
        coverage_binary: Optional[Path] = None,
    ) -> TestResult:
        """Run pytest with JUnit XML output (fallback)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "junit.xml"

            cmd = self._build_base_cmd(binary, coverage_binary, context.project_root)
            cmd.extend(["--tb=short", "-v", f"--junit-xml={report_file}"])

            if not self._execute_pytest(cmd, context):
                return self._execution_failure_result(cmd)

            if report_file.exists():
                return self._parse_junit_xml(report_file, context.project_root)
            LOGGER.warning("JUnit XML report file not generated")
            return self._execution_failure_result(cmd)

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
            title = (
                f"{test_name} {outcome}: {message}"
                if message
                else f"{test_name} {outcome}"
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="pytest",
                severity=severity,
                rule_id=outcome,
                title=title,
                description=longrepr or f"Test {outcome}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
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
            assert root is not None
        except Exception as e:
            LOGGER.error(f"Failed to parse JUnit XML report: {e}")
            return TestResult()

        # Get testsuite element (may be root or child)
        if root.tag == "testsuite":
            testsuite = root
        else:
            found = root.find("testsuite")
            testsuite = found if found is not None else root

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
        testcase: Element,
        failure_elem: Element,
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
            title = (
                f"{name} {outcome}: {assertion}" if assertion else f"{name} {outcome}"
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="pytest",
                severity=severity,
                rule_id=outcome,
                title=title,
                description=content or message or f"Test {outcome}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
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
            if (
                stripped
                and not stripped.startswith(">")
                and not stripped.startswith("E ")
            ):
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
