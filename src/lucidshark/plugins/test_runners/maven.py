"""Maven/Gradle test runner plugin.

Supports running Java tests via:
- Maven Surefire Plugin (mvn test)
- Gradle Test task (gradle test)

Automatically detects the build system and parses JUnit XML reports.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import defusedxml.ElementTree as ET  # type: ignore[import-untyped]
from xml.etree.ElementTree import Element

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.test_runners.base import TestRunnerPlugin, TestResult
from lucidshark.plugins.utils import find_java_build_tool

LOGGER = get_logger(__name__)


class MavenTestRunner(TestRunnerPlugin):
    """Maven/Gradle test runner plugin for Java test execution."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize MavenTestRunner.

        Args:
            project_root: Optional project root for finding build tools.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "maven"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["java", "kotlin"]

    def get_version(self) -> str:
        """Get Maven/Gradle version.

        Returns:
            Version string or 'unknown' if unable to determine.
        """
        try:
            binary, build_system = self._detect_build_system()
            if build_system == "maven":
                result = subprocess.run(
                    [str(binary), "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                if result.returncode == 0:
                    # Output like "Apache Maven 3.9.6"
                    for line in result.stdout.split("\n"):
                        if "Apache Maven" in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                return f"maven-{parts[2]}"
            elif build_system == "gradle":
                result = subprocess.run(
                    [str(binary), "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if "Gradle" in line:
                            parts = line.split()
                            if len(parts) >= 2:
                                return f"gradle-{parts[1]}"
        except Exception:
            pass
        return "unknown"

    def _detect_build_system(self) -> Tuple[Path, str]:
        """Detect the build system (Maven or Gradle)."""
        project_root = self._project_root or Path.cwd()
        return find_java_build_tool(project_root)

    def ensure_binary(self) -> Path:
        """Ensure Maven or Gradle is available.

        Returns:
            Path to build tool binary.

        Raises:
            FileNotFoundError: If no build tool is found.
        """
        binary, _ = self._detect_build_system()
        return binary

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run tests using Maven or Gradle.

        Always generates JaCoCo coverage data.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            binary, build_system = self._detect_build_system()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="maven")

        if build_system == "maven":
            return self._run_maven_tests(binary, context)
        else:
            return self._run_gradle_tests(binary, context)

    def _run_maven_tests(
        self,
        binary: Path,
        context: ScanContext,
    ) -> TestResult:
        """Run tests using Maven Surefire with JaCoCo coverage.

        Args:
            binary: Path to Maven binary.
            context: Scan context.

        Returns:
            TestResult with test statistics.
        """
        cmd = [str(binary), "test", "jacoco:report", "-B"]  # Always generate JaCoCo coverage

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="maven-test",
                stream_handler=context.stream_handler,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Maven test timed out after 600 seconds")
            return TestResult(tool="maven")
        except Exception as e:
            # Maven returns non-zero exit code on test failures
            # We still want to parse the results
            LOGGER.debug(f"Maven test completed with: {e}")

        # Parse Surefire reports
        return self._parse_surefire_reports(context.project_root)

    def _run_gradle_tests(
        self,
        binary: Path,
        context: ScanContext,
    ) -> TestResult:
        """Run tests using Gradle with JaCoCo coverage.

        Args:
            binary: Path to Gradle binary.
            context: Scan context.

        Returns:
            TestResult with test statistics.
        """
        cmd = [str(binary), "test", "jacocoTestReport", "--no-daemon"]  # Always generate JaCoCo coverage

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="gradle-test",
                stream_handler=context.stream_handler,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Gradle test timed out after 600 seconds")
            return TestResult(tool="maven")
        except Exception as e:
            # Gradle returns non-zero exit code on test failures
            LOGGER.debug(f"Gradle test completed with: {e}")

        # Parse Gradle test reports
        return self._parse_gradle_reports(context.project_root)

    def _parse_surefire_reports(self, project_root: Path) -> TestResult:
        """Parse Maven Surefire JUnit XML reports.

        Args:
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="maven")
        reports_dir = project_root / "target" / "surefire-reports"

        if not reports_dir.exists():
            # Check for multi-module projects
            for child in project_root.iterdir():
                child_reports = child / "target" / "surefire-reports"
                if child_reports.exists():
                    child_result = self._parse_junit_xml_dir(child_reports, project_root)
                    result = self._merge_results(result, child_result)
            return result

        return self._parse_junit_xml_dir(reports_dir, project_root)

    def _parse_gradle_reports(self, project_root: Path) -> TestResult:
        """Parse Gradle JUnit XML reports.

        Args:
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="maven")

        # Standard Gradle test report locations
        report_dirs = [
            project_root / "build" / "test-results" / "test",
            project_root / "build" / "test-results" / "testDebug",
            project_root / "build" / "test-results" / "testRelease",
        ]

        for reports_dir in report_dirs:
            if reports_dir.exists():
                dir_result = self._parse_junit_xml_dir(reports_dir, project_root)
                result = self._merge_results(result, dir_result)

        # Check for multi-module projects
        for child in project_root.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                for subdir in ["build/test-results/test", "build/test-results/testDebug"]:
                    child_reports = child / subdir
                    if child_reports.exists():
                        child_result = self._parse_junit_xml_dir(child_reports, project_root)
                        result = self._merge_results(result, child_result)

        return result

    def _parse_junit_xml_dir(self, reports_dir: Path, project_root: Path) -> TestResult:
        """Parse JUnit XML files from a directory.

        Args:
            reports_dir: Directory containing JUnit XML files.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="maven")

        for xml_file in reports_dir.glob("TEST-*.xml"):
            try:
                file_result = self._parse_junit_xml(xml_file, project_root)
                result = self._merge_results(result, file_result)
            except Exception as e:
                LOGGER.warning(f"Failed to parse {xml_file}: {e}")

        return result

    def _parse_junit_xml(self, xml_file: Path, project_root: Path) -> TestResult:
        """Parse a single JUnit XML file.

        Args:
            xml_file: Path to JUnit XML file.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            assert root is not None
        except Exception as e:
            LOGGER.warning(f"Failed to parse JUnit XML {xml_file}: {e}")
            return TestResult(tool="maven")

        # Get testsuite element
        if root.tag == "testsuite":
            testsuite = root
        else:
            found = root.find("testsuite")
            if found is None:
                return TestResult(tool="maven")
            testsuite = found

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
            tool="maven",
        )

        # Parse individual test cases for failures
        for testcase in testsuite.iter("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")

            if failure is not None:
                issue = self._testcase_to_issue(testcase, failure, project_root, "failed")
                if issue:
                    result.issues.append(issue)
            elif error is not None:
                issue = self._testcase_to_issue(testcase, error, project_root, "error")
                if issue:
                    result.issues.append(issue)

        return result

    def _testcase_to_issue(
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
            time_str = testcase.get("time", "0")

            # Get failure details
            failure_type = failure_elem.get("type", "")
            message = failure_elem.get("message", "")
            stacktrace = failure_elem.text or ""

            # Try to find source file from classname
            # e.g., com.example.MyTest -> src/test/java/com/example/MyTest.java
            file_path = None
            line_number = None

            if classname:
                class_path = classname.replace(".", "/") + ".java"
                for src_dir in ["src/test/java", "src/main/java", "src"]:
                    potential_path = project_root / src_dir / class_path
                    if potential_path.exists():
                        file_path = potential_path
                        break

                # Try to extract line number from stacktrace
                if stacktrace and classname:
                    line_number = self._extract_line_from_stacktrace(stacktrace, classname)

            # Build test identifier
            test_id = f"{classname}#{name}" if classname else name

            # Determine severity
            severity = Severity.HIGH if outcome == "failed" else Severity.MEDIUM

            # Generate deterministic ID
            issue_id = self._generate_issue_id(test_id, message)

            # Build title
            short_message = message[:80] + "..." if len(message) > 80 else message
            title = f"{name} {outcome}: {short_message}" if short_message else f"{name} {outcome}"

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="maven",
                severity=severity,
                rule_id=outcome,
                title=title,
                description=f"{failure_type}: {message}\n\n{stacktrace[:500]}" if stacktrace else f"{failure_type}: {message}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "test_class": classname,
                    "test_method": name,
                    "outcome": outcome,
                    "failure_type": failure_type,
                    "duration_ms": int(float(time_str) * 1000),
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse JUnit XML testcase: {e}")
            return None

    def _extract_line_from_stacktrace(self, stacktrace: str, classname: str) -> Optional[int]:
        """Extract line number from stacktrace for the test class.

        Args:
            stacktrace: Stack trace string.
            classname: Fully qualified class name.

        Returns:
            Line number or None.
        """
        import re

        # Look for pattern like "at com.example.MyTest.testMethod(MyTest.java:42)"
        simple_classname = classname.split(".")[-1]
        pattern = rf"at\s+{re.escape(classname)}\.\w+\({simple_classname}\.java:(\d+)\)"

        match = re.search(pattern, stacktrace)
        if match:
            return int(match.group(1))

        return None

    def _merge_results(self, result1: TestResult, result2: TestResult) -> TestResult:
        """Merge two TestResults.

        Args:
            result1: First result.
            result2: Second result.

        Returns:
            Merged TestResult.
        """
        return TestResult(
            passed=result1.passed + result2.passed,
            failed=result1.failed + result2.failed,
            skipped=result1.skipped + result2.skipped,
            errors=result1.errors + result2.errors,
            duration_ms=result1.duration_ms + result2.duration_ms,
            issues=result1.issues + result2.issues,
            tool="maven",
        )

    def _generate_issue_id(self, test_id: str, message: str) -> str:
        """Generate deterministic issue ID.

        Args:
            test_id: Test identifier (class#method).
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{test_id}:{message[:50]}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"maven-test-{hash_val}"
