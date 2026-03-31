"""PHPUnit test runner plugin.

Runs PHP tests via PHPUnit and parses JUnit XML output for test results.
https://phpunit.de/
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import defusedxml.ElementTree as ET  # type: ignore[import-untyped]
from pathlib import Path
from typing import Any, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.test_runners.base import TestResult, TestRunnerPlugin

LOGGER = get_logger(__name__)


def _find_phpunit(project_root: Optional[Path] = None) -> Path:
    """Find phpunit binary.

    Checks:
    1. Project vendor/bin/phpunit (Composer local install)
    2. System PATH

    Args:
        project_root: Optional project root.

    Returns:
        Path to phpunit binary.

    Raises:
        FileNotFoundError: If phpunit is not installed.
    """
    if project_root:
        vendor_bin = project_root / "vendor" / "bin" / "phpunit"
        if vendor_bin.exists():
            return vendor_bin

    system = shutil.which("phpunit")
    if system:
        return Path(system)

    raise FileNotFoundError(
        "PHPUnit is not installed. Install via: composer require --dev phpunit/phpunit"
    )


class PhpunitRunner(TestRunnerPlugin):
    """PHPUnit test runner plugin for PHP test execution."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "phpunit"

    @property
    def languages(self) -> List[str]:
        return ["php"]

    def ensure_binary(self) -> Path:
        return _find_phpunit(self._project_root)

    def run_tests(self, context: ScanContext) -> TestResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="phpunit")

        # Create temp file for JUnit XML output
        with tempfile.NamedTemporaryFile(
            suffix=".xml", delete=False, prefix="phpunit-"
        ) as tmp:
            junit_path = Path(tmp.name)

        cmd = [str(binary), "--log-junit", str(junit_path)]

        # Add coverage flags when coverage domain is enabled
        coverage_clover_path = None
        if ToolDomain.COVERAGE in context.enabled_domains:
            coverage_clover_path = context.project_root / "coverage-clover.xml"
            cmd.extend(["--coverage-clover", str(coverage_clover_path)])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        proc = self._run_test_subprocess(cmd, context, timeout=600)

        if proc is None:
            junit_path.unlink(missing_ok=True)
            return TestResult(tool="phpunit")

        # Parse JUnit XML results
        try:
            result = self._parse_junit_xml(junit_path, context.project_root)
        finally:
            junit_path.unlink(missing_ok=True)

        # If no test results found and there's stderr, report build error
        if (
            result.passed == 0
            and result.failed == 0
            and result.skipped == 0
            and result.errors == 0
            and proc.stderr
            and proc.stderr.strip()
        ):
            result.errors = 1
            result.issues.append(
                UnifiedIssue(
                    id="phpunit-build-failure",
                    domain=ToolDomain.TESTING,
                    source_tool="phpunit",
                    severity=Severity.HIGH,
                    rule_id="build_failed",
                    title="PHPUnit failed to run",
                    description=f"PHPUnit error:\n{proc.stderr[:500]}",
                    fixable=False,
                )
            )

        return result

    def _parse_junit_xml(self, junit_path: Path, project_root: Path) -> TestResult:
        """Parse PHPUnit JUnit XML output.

        Args:
            junit_path: Path to JUnit XML file.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="phpunit")

        if not junit_path.exists():
            LOGGER.warning("PHPUnit JUnit XML output not found")
            return result

        try:
            tree = ET.parse(junit_path)
        except ET.ParseError as e:
            LOGGER.warning(f"Failed to parse PHPUnit JUnit XML: {e}")
            return result

        root: Any = tree.getroot()

        # Parse only direct-child <testsuite> elements to avoid double counting.
        # root.iter() would visit nested testsuites too, inflating counts.
        for testsuite in root.findall("testsuite"):
            tests = int(testsuite.get("tests", "0"))
            failures = int(testsuite.get("failures", "0"))
            errors = int(testsuite.get("errors", "0"))
            skipped_count = int(testsuite.get("skipped", "0"))
            time_val = float(testsuite.get("time", "0"))

            result.passed += tests - failures - errors - skipped_count
            result.failed += failures
            result.errors += errors
            result.skipped += skipped_count
            result.duration_ms += int(time_val * 1000)

        # If we couldn't get counts from testsuite attrs, count testcases directly
        if result.passed == 0 and result.failed == 0 and result.skipped == 0:
            result = self._count_testcases(root, project_root)

        # Extract failure details
        for testcase in root.iter("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")

            if failure is not None or error is not None:
                issue = self._testcase_to_issue(testcase, project_root)
                if issue:
                    result.issues.append(issue)

        LOGGER.info(
            f"phpunit: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped, {result.errors} errors"
        )
        return result

    def _count_testcases(self, root: Any, project_root: Path) -> TestResult:
        """Count test results from individual testcase elements."""
        result = TestResult(tool="phpunit")

        for testcase in root.iter("testcase"):
            time_val = float(testcase.get("time", "0"))
            result.duration_ms += int(time_val * 1000)

            if testcase.find("failure") is not None:
                result.failed += 1
            elif testcase.find("error") is not None:
                result.errors += 1
            elif testcase.find("skipped") is not None:
                result.skipped += 1
            else:
                result.passed += 1

        return result

    def _testcase_to_issue(
        self, testcase: Any, project_root: Path
    ) -> Optional[UnifiedIssue]:
        """Convert a failed testcase to UnifiedIssue."""
        try:
            class_name = testcase.get("classname", "")
            test_name = testcase.get("name", "")
            file_attr = testcase.get("file", "")

            failure = testcase.find("failure")
            error = testcase.find("error")
            detail_elem = failure if failure is not None else error

            message = ""
            if detail_elem is not None:
                message = detail_elem.get("message", "")
                if not message and detail_elem.text:
                    message = detail_elem.text[:500]

            full_name = f"{class_name}::{test_name}" if class_name else test_name
            title = f"{full_name} FAILED"
            if message:
                short_msg = message.replace("\n", " ").strip()[:100]
                title = f"{full_name}: {short_msg}"
            if len(title) > 200:
                title = title[:197] + "..."

            file_path = None
            line_number = None
            if file_attr:
                file_path = Path(file_attr)
                if not file_path.is_absolute():
                    file_path = project_root / file_path
            line_str = testcase.get("line")
            if line_str:
                line_number = int(line_str)

            issue_id = self._generate_phpunit_issue_id(class_name, test_name)

            description = f"Test {full_name} failed"
            if detail_elem is not None and detail_elem.text:
                description = detail_elem.text[:500]

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="phpunit",
                severity=Severity.HIGH,
                rule_id="test_failed",
                title=title,
                description=description,
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "classname": class_name,
                    "test_name": test_name,
                    "outcome": "failed",
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse PHPUnit testcase: {e}")
            return None

    def _generate_phpunit_issue_id(self, class_name: str, test_name: str) -> str:
        content = f"{class_name}::{test_name}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"phpunit-{hash_val}"
