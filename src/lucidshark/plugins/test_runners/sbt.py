"""sbt/Maven/Gradle test runner plugin for Scala.

Supports running Scala tests via:
- sbt test (with ScalaTest, specs2, MUnit, etc.)
- Maven Surefire/Failsafe (scala-maven-plugin projects)
- Gradle Test task (Scala plugin projects)

Automatically detects the build system and parses JUnit XML reports.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import defusedxml.ElementTree as ET  # type: ignore[import-untyped]
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
from lucidshark.plugins.utils import find_scala_build_tool

LOGGER = get_logger(__name__)


class SbtTestRunner(TestRunnerPlugin):
    """sbt/Maven/Gradle test runner plugin for Scala test execution."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        super().__init__(project_root=project_root, **kwargs)

    @property
    def name(self) -> str:
        return "sbt"

    @property
    def languages(self) -> List[str]:
        return ["scala"]

    def _detect_build_system(self) -> Tuple[Path, str]:
        """Detect the Scala build system."""
        project_root = self._project_root or Path.cwd()
        return find_scala_build_tool(project_root)

    def get_version(self) -> str:
        try:
            binary, build_system = self._detect_build_system()
            if build_system == "sbt":
                result = subprocess.run(
                    [str(binary), "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                if result.returncode == 0:
                    match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
                    if match:
                        return f"sbt-{match.group(1)}"
            return f"{build_system}"
        except Exception:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure build tool is available."""
        binary, _ = self._detect_build_system()
        return binary

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run tests using sbt, Maven, or Gradle.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            binary, build_system = self._detect_build_system()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
                suggestion="Ensure sbt, Maven, or Gradle is installed",
            )
            return TestResult(tool="sbt")

        if build_system == "sbt":
            return self._run_sbt_tests(binary, context)
        elif build_system == "maven":
            return self._run_maven_tests(binary, context)
        else:
            return self._run_gradle_tests(binary, context)

    def _tool_label(self, build_system: str) -> str:
        """Return the tool label for a given build system."""
        return build_system

    def _run_sbt_tests(
        self, binary: Path, context: ScanContext
    ) -> TestResult:
        """Run tests using sbt."""
        cmd = [str(binary), "--no-colors", "test"]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="sbt-test",
                stream_handler=context.stream_handler,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("sbt test timed out after 600 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="sbt test timed out after 600 seconds",
            )
            return TestResult(tool="sbt")
        except Exception as e:
            # sbt returns non-zero on test failures
            LOGGER.debug(f"sbt test completed with: {e}")

        # Parse JUnit XML reports from sbt's test-reports directory
        return self._parse_sbt_reports(context.project_root, tool_name="sbt")

    def _run_maven_tests(
        self, binary: Path, context: ScanContext
    ) -> TestResult:
        """Run tests using Maven with JaCoCo/Scoverage coverage."""
        cmd = [str(binary), "test", "-B"]

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
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="Maven test timed out after 600 seconds",
            )
            return TestResult(tool="maven")
        except Exception as e:
            LOGGER.debug(f"Maven test completed with: {e}")

        return self._parse_surefire_reports(context.project_root, tool_name="maven")

    def _run_gradle_tests(
        self, binary: Path, context: ScanContext
    ) -> TestResult:
        """Run tests using Gradle."""
        cmd = [str(binary), "test", "--no-daemon"]

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
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="Gradle test timed out after 600 seconds",
            )
            return TestResult(tool="gradle")
        except Exception as e:
            LOGGER.debug(f"Gradle test completed with: {e}")

        return self._parse_gradle_reports(context.project_root, tool_name="gradle")

    def _parse_sbt_reports(
        self, project_root: Path, tool_name: str = "sbt"
    ) -> TestResult:
        """Parse sbt JUnit XML test reports.

        sbt generates JUnit XML reports in target/test-reports/ by default.
        """
        result = TestResult(tool=tool_name)

        report_dirs = [
            project_root / "target" / "test-reports",
            project_root / "target" / "scala-2.13" / "test-reports",
            project_root / "target" / "scala-3" / "test-reports",
        ]

        # Also check for versioned scala directories
        target_dir = project_root / "target"
        if target_dir.exists():
            for child in target_dir.iterdir():
                if child.is_dir() and child.name.startswith("scala-"):
                    reports_dir = child / "test-reports"
                    if reports_dir.exists() and reports_dir not in report_dirs:
                        report_dirs.append(reports_dir)

        for reports_dir in report_dirs:
            if reports_dir.exists():
                dir_result = self._parse_junit_xml_dir(
                    reports_dir, project_root, tool_name=tool_name
                )
                result = self._merge_results(result, dir_result)

        return result

    def _parse_surefire_reports(
        self, project_root: Path, tool_name: str = "maven"
    ) -> TestResult:
        """Parse Maven Surefire JUnit XML reports."""
        result = TestResult(tool=tool_name)
        reports_dir = project_root / "target" / "surefire-reports"

        # Parse root module reports if present
        if reports_dir.exists():
            dir_result = self._parse_junit_xml_dir(
                reports_dir, project_root, tool_name=tool_name
            )
            result = self._merge_results(result, dir_result)

        # Also check child modules for multi-module Maven projects
        for child in project_root.iterdir():
            child_reports = child / "target" / "surefire-reports"
            if child_reports.exists():
                child_result = self._parse_junit_xml_dir(
                    child_reports, project_root, tool_name=tool_name
                )
                result = self._merge_results(result, child_result)

        return result

    def _parse_gradle_reports(
        self, project_root: Path, tool_name: str = "gradle"
    ) -> TestResult:
        """Parse Gradle JUnit XML reports."""
        result = TestResult(tool=tool_name)

        report_dirs = [
            project_root / "build" / "test-results" / "test",
        ]

        for reports_dir in report_dirs:
            if reports_dir.exists():
                dir_result = self._parse_junit_xml_dir(
                    reports_dir, project_root, tool_name=tool_name
                )
                result = self._merge_results(result, dir_result)

        return result

    def _parse_junit_xml_dir(
        self, reports_dir: Path, project_root: Path, tool_name: str = "sbt"
    ) -> TestResult:
        """Parse JUnit XML files from a directory."""
        result = TestResult(tool=tool_name)

        for xml_file in reports_dir.glob("TEST-*.xml"):
            try:
                file_result = self._parse_junit_xml(
                    xml_file, project_root, tool_name=tool_name
                )
                result = self._merge_results(result, file_result)
            except Exception as e:
                LOGGER.warning(f"Failed to parse {xml_file}: {e}")

        return result

    def _parse_junit_xml(
        self, xml_file: Path, project_root: Path, tool_name: str = "sbt"
    ) -> TestResult:
        """Parse a single JUnit XML file."""
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            assert root is not None
        except Exception as e:
            LOGGER.warning(f"Failed to parse JUnit XML {xml_file}: {e}")
            return TestResult(tool=tool_name)

        if root.tag == "testsuite":
            testsuite = root
        else:
            found = root.find("testsuite")
            if found is None:
                return TestResult(tool=tool_name)
            testsuite = found

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
            tool=tool_name,
        )

        for testcase in testsuite.iter("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")

            if failure is not None:
                issue = self._testcase_to_issue(
                    testcase, failure, project_root, "failed", tool_name=tool_name
                )
                if issue:
                    result.issues.append(issue)
            elif error is not None:
                issue = self._testcase_to_issue(
                    testcase, error, project_root, "error", tool_name=tool_name
                )
                if issue:
                    result.issues.append(issue)

        return result

    def _testcase_to_issue(
        self,
        testcase: Element,
        failure_elem: Element,
        project_root: Path,
        outcome: str,
        tool_name: str = "sbt",
    ) -> Optional[UnifiedIssue]:
        """Convert JUnit XML testcase failure to UnifiedIssue."""
        try:
            classname = testcase.get("classname", "")
            test_name = testcase.get("name", "")
            time_str = testcase.get("time", "0")

            failure_type = failure_elem.get("type", "")
            message = failure_elem.get("message", "")
            stacktrace = failure_elem.text or ""

            # Try to find source file from classname
            file_path = None
            line_number = None

            if classname:
                # Scala classname: com.example.MySpec -> src/test/scala/com/example/MySpec.scala
                class_path = classname.replace(".", "/") + ".scala"
                for src_dir in ["src/test/scala", "src/main/scala", "src"]:
                    potential_path = project_root / src_dir / class_path
                    if potential_path.exists():
                        file_path = potential_path
                        break

                if stacktrace and classname:
                    line_number = self._extract_line_from_stacktrace(
                        stacktrace, classname
                    )

            test_id = f"{classname}#{test_name}" if classname else test_name
            severity = Severity.HIGH if outcome == "failed" else Severity.MEDIUM

            issue_id = self._generate_issue_id(test_id, message)

            short_message = message[:80] + "..." if len(message) > 80 else message
            title = (
                f"{test_name} {outcome}: {short_message}"
                if short_message
                else f"{test_name} {outcome}"
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool=tool_name,
                severity=severity,
                rule_id=outcome,
                title=title,
                description=f"{failure_type}: {message}\n\n{stacktrace[:500]}"
                if stacktrace
                else f"{failure_type}: {message}",
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "test_class": classname,
                    "test_method": test_name,
                    "outcome": outcome,
                    "failure_type": failure_type,
                    "duration_ms": int(float(time_str) * 1000),
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse JUnit XML testcase: {e}")
            return None

    def _extract_line_from_stacktrace(
        self, stacktrace: str, classname: str
    ) -> Optional[int]:
        """Extract line number from stacktrace for the test class."""
        simple_classname = classname.split(".")[-1]
        # Scala stacktraces can have various formats:
        # at com.example.MySpec.testMethod(MySpec.scala:42)
        # at com.example.MySpec.should work(MySpec.scala:42)
        # at com.example.MySpec$Inner.test(MySpec.scala:10)
        pattern = rf"at\s+{re.escape(classname)}[.\$][^\(]+\({simple_classname}\.scala:(\d+)\)"

        match = re.search(pattern, stacktrace)
        if match:
            return int(match.group(1))

        return None

    def _merge_results(self, result1: TestResult, result2: TestResult) -> TestResult:
        """Merge two TestResults."""
        return TestResult(
            passed=result1.passed + result2.passed,
            failed=result1.failed + result2.failed,
            skipped=result1.skipped + result2.skipped,
            errors=result1.errors + result2.errors,
            duration_ms=result1.duration_ms + result2.duration_ms,
            issues=result1.issues + result2.issues,
            tool=result1.tool,
        )

    def _generate_issue_id(self, test_id: str, message: str) -> str:
        content = f"{test_id}:{message[:50]}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"sbt-test-{hash_val}"
