"""CTest test runner plugin.

CTest is the test driver from CMake that runs tests registered via
add_test() in CMakeLists.txt. It supports Google Test, Catch2, and
any executable registered as a CMake test.
https://cmake.org/cmake/help/latest/manual/ctest.1.html
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
from lucidshark.core.subprocess_runner import run_with_streaming, temporary_env
from lucidshark.plugins.cpp_utils import (
    ensure_cpp_tools_in_path,
    find_build_dir,
    find_ctest,
    get_tool_version,
    has_cmake_project,
)
from lucidshark.plugins.test_runners.base import TestResult, TestRunnerPlugin

LOGGER = get_logger(__name__)


class CTestRunner(TestRunnerPlugin):
    """CTest test runner plugin for C++ test execution."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "ctest"

    @property
    def languages(self) -> List[str]:
        return ["c++"]

    def get_version(self) -> str:
        return get_tool_version(find_ctest)

    def ensure_binary(self) -> Path:
        return find_ctest()

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run tests using CTest.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            ctest_bin = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="ctest")

        if not has_cmake_project(context.project_root):
            LOGGER.info("No CMakeLists.txt found, skipping ctest")
            return TestResult(tool="ctest")

        # Find build directory
        build_dir = find_build_dir(context.project_root)
        if not build_dir:
            LOGGER.warning(
                "No CMake build directory found. Run cmake to configure the project first."
            )
            result = TestResult(tool="ctest")
            result.errors = 1
            result.issues.append(
                UnifiedIssue(
                    id="ctest-no-build-dir",
                    domain=ToolDomain.TESTING,
                    source_tool="ctest",
                    severity=Severity.HIGH,
                    rule_id="no_build_dir",
                    title="No CMake build directory found",
                    description=(
                        "CTest requires a configured CMake build directory. "
                        "Run 'cmake -B build' to configure the project first."
                    ),
                    fixable=False,
                )
            )
            return result

        cmd = [
            str(ctest_bin),
            "--test-dir",
            str(build_dir),
            "--output-on-failure",
            "--no-compress-output",
            "-T",
            "Test",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        env_vars = ensure_cpp_tools_in_path()

        stdout = ""
        stderr = ""
        try:
            with temporary_env(env_vars):
                proc = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="ctest",
                    stream_handler=context.stream_handler,
                    timeout=600,
                )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            if proc.returncode != 0:
                LOGGER.debug(f"ctest exited with code {proc.returncode}")
        except subprocess.TimeoutExpired:
            LOGGER.warning("ctest timed out after 600 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="ctest timed out after 600 seconds",
            )
            return TestResult(tool="ctest")
        except subprocess.CalledProcessError as e:
            LOGGER.debug(f"ctest raised CalledProcessError: {e}")
            if hasattr(e, "stdout") and e.stdout:
                stdout = (
                    e.stdout
                    if isinstance(e.stdout, str)
                    else e.stdout.decode("utf-8", errors="replace")
                )
            if hasattr(e, "stderr") and e.stderr:
                stderr = (
                    e.stderr
                    if isinstance(e.stderr, str)
                    else e.stderr.decode("utf-8", errors="replace")
                )
        except Exception as e:
            LOGGER.warning(f"ctest failed to execute: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"ctest failed to execute: {e}",
            )
            return TestResult(tool="ctest")

        combined = stdout + "\n" + stderr

        # Parse CTest output
        result = self._parse_ctest_output(combined, context.project_root)

        # Try to parse CTest XML results if available
        xml_result = self._parse_ctest_xml(build_dir, context.project_root)
        if xml_result and xml_result.total > 0:
            result = xml_result

        return result

    def _parse_ctest_output(self, output: str, project_root: Path) -> TestResult:
        """Parse CTest text output.

        CTest output typically looks like:
            Test project /path/to/build
                Start  1: test_basic
            1/5 Test  #1: test_basic ...................   Passed    0.01 sec
            2/5 Test  #2: test_advanced ................   Passed    0.02 sec
            3/5 Test  #3: test_failing .................***Failed    0.01 sec
            ...
            100% tests passed, 0 tests failed out of 5

        Args:
            output: CTest text output.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="ctest")

        if not output or not output.strip():
            return result

        # Pattern for individual test results
        # Matches: "1/5 Test  #1: test_name .........   Passed    0.01 sec"
        test_re = re.compile(
            r"\d+/\d+\s+Test\s+#\d+:\s+(\S+)\s+\.+\s*(Passed|Failed|\*\*\*Failed|Not Run|Timeout)\s+([\d.]+)\s+sec"
        )

        # Pattern for summary line
        summary_re = re.compile(
            r"(\d+)%\s+tests\s+passed,\s+(\d+)\s+tests?\s+failed\s+out\s+of\s+(\d+)"
        )

        total_elapsed_ms = 0
        failures = []

        for line in output.splitlines():
            line = line.strip()

            # Parse individual test results
            test_match = test_re.search(line)
            if test_match:
                test_name = test_match.group(1)
                status = test_match.group(2)
                elapsed = float(test_match.group(3))
                total_elapsed_ms += int(elapsed * 1000)

                if "Passed" in status:
                    result.passed += 1
                elif "Failed" in status:
                    result.failed += 1
                    failures.append(test_name)
                elif "Not Run" in status:
                    result.skipped += 1
                elif "Timeout" in status:
                    result.failed += 1
                    failures.append(test_name)
                continue

            # Parse summary line as fallback
            summary_match = summary_re.search(line)
            if summary_match:
                failed = int(summary_match.group(2))
                total = int(summary_match.group(3))
                passed = total - failed
                # Only use summary if we haven't parsed individual tests
                if result.passed == 0 and result.failed == 0:
                    result.passed = passed
                    result.failed = failed

        result.duration_ms = total_elapsed_ms

        # Create issues for failures
        for test_name in failures:
            issue = self._failure_to_issue(test_name, output, project_root)
            if issue:
                result.issues.append(issue)

        LOGGER.info(
            f"ctest: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )

        return result

    def _parse_ctest_xml(
        self, build_dir: Path, project_root: Path
    ) -> Optional[TestResult]:
        """Parse CTest XML results from Testing/ directory.

        CTest with -T Test generates XML results in Testing/TAG and
        Testing/<date>/Test.xml.

        Args:
            build_dir: CMake build directory.
            project_root: Project root directory.

        Returns:
            TestResult or None if no XML found.
        """
        testing_dir = build_dir / "Testing"
        if not testing_dir.exists():
            return None

        # Find the latest Test.xml
        tag_file = testing_dir / "TAG"
        if not tag_file.exists():
            return None

        try:
            tag_content = tag_file.read_text().strip()
            tag_dir = tag_content.splitlines()[0].strip()
            test_xml = testing_dir / tag_dir / "Test.xml"
        except Exception:
            return None

        if not test_xml.exists():
            return None

        try:
            import xml.etree.ElementTree as ET

            xml_content = test_xml.read_text(encoding="utf-8", errors="replace")
            root = ET.fromstring(xml_content)
        except Exception as e:
            LOGGER.debug(f"Failed to parse CTest XML: {e}")
            return None

        result = TestResult(tool="ctest")
        total_elapsed_ms = 0

        testing = root.find(".//Testing")
        if testing is None:
            testing = root

        for test in testing.findall(".//Test"):
            status = test.get("Status", "")
            name_elem = test.find("Name")
            test_name = (
                (name_elem.text or "unknown") if name_elem is not None else "unknown"
            )

            # Get execution time
            results_elem = test.find("Results")
            if results_elem is not None:
                for measurement in results_elem.findall("NamedMeasurement"):
                    if measurement.get("name") == "Execution Time":
                        value_elem = measurement.find("Value")
                        if value_elem is not None and value_elem.text:
                            try:
                                total_elapsed_ms += int(float(value_elem.text) * 1000)
                            except ValueError:
                                pass

            if status == "passed":
                result.passed += 1
            elif status == "failed":
                result.failed += 1
                # Get failure output
                output_elem = None
                if results_elem is not None:
                    for measurement in results_elem.findall("NamedMeasurement"):
                        if measurement.get("name") == "Output":
                            output_elem = measurement.find("Value")
                            break

                failure_output = ""
                if output_elem is not None and output_elem.text:
                    failure_output = output_elem.text

                issue = self._failure_to_issue(test_name, failure_output, project_root)
                if issue:
                    result.issues.append(issue)
            elif status == "notrun":
                result.skipped += 1

        result.duration_ms = total_elapsed_ms

        LOGGER.info(
            f"ctest XML: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )

        return result

    def _failure_to_issue(
        self,
        test_name: str,
        output: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a test failure to UnifiedIssue.

        Args:
            test_name: CTest test name.
            output: Test output/error text.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            short_message = self._extract_short_message(output)
            file_path, line_number = self._extract_location(output, project_root)

            title = f"{test_name} FAILED: {short_message}"
            if len(title) > 200:
                title = title[:197] + "..."

            issue_id = self._generate_ctest_issue_id(test_name)

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="ctest",
                severity=Severity.HIGH,
                rule_id="test_failed",
                title=title,
                description=f"Test {test_name} failed:\n{output[:500]}",
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
            LOGGER.warning(f"Failed to parse ctest failure: {e}")
            return None

    def _extract_short_message(self, output: str) -> str:
        """Extract a short failure message from test output.

        Args:
            output: Test output lines.

        Returns:
            Short message string.
        """
        if not output:
            return "Test failed"

        for line in output.splitlines():
            stripped = line.strip()
            # Look for assertion failures (Google Test, Catch2 patterns)
            if any(
                kw in stripped
                for kw in [
                    "FAILED",
                    "REQUIRE(",
                    "CHECK(",
                    "EXPECT_",
                    "ASSERT_",
                    "Expected:",
                    "Actual:",
                    "error:",
                ]
            ):
                cleaned = stripped.replace("\n", " ").strip()
                if len(cleaned) > 5:
                    return cleaned[:100]

        # Fallback: first non-empty line
        for line in output.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("---"):
                return stripped[:100]

        return "Test failed"

    def _extract_location(
        self,
        output: str,
        project_root: Path,
    ) -> Tuple[Optional[Path], Optional[int]]:
        """Extract file path and line number from test output.

        Args:
            output: Test output.
            project_root: Project root directory.

        Returns:
            Tuple of (file_path, line_number).
        """
        if not output:
            return None, None

        # Match C++ file patterns like "test_main.cpp:42:" or "test_main.cpp(42):"
        patterns = [
            re.compile(r"(\S+\.(?:cpp|cc|cxx|hpp|h)):(\d+):"),
            re.compile(r"(\S+\.(?:cpp|cc|cxx|hpp|h))\((\d+)\)"),
        ]

        for line in output.splitlines():
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    file_name = match.group(1)
                    line_number = int(match.group(2))
                    file_path = project_root / file_name
                    if file_path.exists():
                        return file_path, line_number
                    return None, line_number

        return None, None

    def _generate_ctest_issue_id(self, test_name: str) -> str:
        """Generate deterministic issue ID for a ctest failure.

        Args:
            test_name: CTest test name.

        Returns:
            Unique issue ID.
        """
        content = f"ctest::{test_name}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"ctest-{hash_val}"
