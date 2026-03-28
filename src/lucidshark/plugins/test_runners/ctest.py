"""CTest test runner plugin.

Runs C tests via CMake's CTest and parses the output for test results
and failures.
https://cmake.org/cmake/help/latest/manual/ctest.1.html
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.plugins.c_utils import find_ctest, get_ctest_version, has_build_dir
from lucidshark.plugins.test_runners.base import TestResult, TestRunnerPlugin

LOGGER = get_logger(__name__)


class CTestRunner(TestRunnerPlugin):
    """CTest test runner plugin for C test execution."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "ctest"

    @property
    def languages(self) -> List[str]:
        return ["c"]

    def get_version(self) -> str:
        return get_ctest_version()

    def ensure_binary(self) -> Path:
        return find_ctest()

    def run_tests(self, context: ScanContext) -> TestResult:
        try:
            ctest_bin = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="ctest")

        # Find build directory
        build_dir = has_build_dir(context.project_root)
        if not build_dir:
            LOGGER.info("No CMake build directory found, skipping ctest")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=(
                    "No CMake build directory found. Run cmake to configure "
                    "and build the project first."
                ),
            )
            return TestResult(tool="ctest")

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

        proc = self._run_test_subprocess(cmd, context, timeout=600)
        if proc is None:
            return TestResult(tool="ctest")

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        # Try to parse CTest's XML output first (Tag/Test.xml)
        result = self._try_parse_xml(build_dir, context.project_root)
        if result is not None:
            return result

        # Fall back to parsing stdout text output
        result = self._parse_text_output(stdout, context.project_root)

        # If no tests found and there was stderr, record build error
        if (
            result.passed == 0
            and result.failed == 0
            and result.skipped == 0
            and stderr.strip()
        ):
            result.errors = 1
            result.issues.append(
                UnifiedIssue(
                    id="ctest-build-failure",
                    domain=ToolDomain.TESTING,
                    source_tool="ctest",
                    severity=Severity.HIGH,
                    rule_id="build_failed",
                    title="CTest execution failed",
                    description=f"CTest failed:\n{stderr[:500]}",
                    fixable=False,
                )
            )

        return result

    def _try_parse_xml(
        self, build_dir: Path, project_root: Path
    ) -> Optional[TestResult]:
        """Try to parse CTest XML output from Testing directory.

        Args:
            build_dir: CMake build directory.
            project_root: Project root directory.

        Returns:
            TestResult or None if XML output not found.
        """
        testing_dir = build_dir / "Testing"
        if not testing_dir.is_dir():
            return None

        # Find the Tag file to get the test results directory
        tag_file = testing_dir / "TAG"
        if not tag_file.exists():
            return None

        try:
            tag_content = tag_file.read_text(encoding="utf-8", errors="replace")
            tag_lines = tag_content.strip().splitlines()
            if not tag_lines:
                return None
        except OSError:
            return None

        # Look for Test.xml in the tagged directory
        test_xml = testing_dir / tag_lines[0] / "Test.xml"
        if not test_xml.exists():
            return None

        return self._parse_ctest_xml(test_xml, project_root)

    def _parse_ctest_xml(self, xml_path: Path, project_root: Path) -> TestResult:
        """Parse CTest XML output.

        Args:
            xml_path: Path to Test.xml file.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        import defusedxml.ElementTree as ET  # type: ignore[import-untyped]

        result = TestResult(tool="ctest")

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            if root is None:
                LOGGER.warning("CTest XML has no root element")
                return result
        except Exception as e:
            LOGGER.warning(f"Failed to parse CTest XML: {e}")
            return result

        for test_elem in root.iter("Test"):
            status = test_elem.get("Status", "")
            name_elem = test_elem.find("Name")
            test_name = (name_elem.text or "unknown") if name_elem is not None else "unknown"

            if status == "passed":
                result.passed += 1
            elif status == "failed":
                result.failed += 1
                # Extract failure output
                output_elem = test_elem.find(".//Value")
                output_text = output_elem.text if output_elem is not None else ""

                issue_id = self._generate_ctest_issue_id(test_name)
                result.issues.append(
                    UnifiedIssue(
                        id=issue_id,
                        domain=ToolDomain.TESTING,
                        source_tool="ctest",
                        severity=Severity.HIGH,
                        rule_id="test_failed",
                        title=f"{test_name} FAILED",
                        description=f"Test {test_name} failed:\n{(output_text or '')[:500]}",
                        fixable=False,
                        metadata={
                            "test_name": test_name,
                            "outcome": "failed",
                        },
                    )
                )
            elif status == "notrun":
                result.skipped += 1

        # Extract elapsed time
        elapsed_elem = root.find(".//ElapsedMinutes")
        if elapsed_elem is not None and elapsed_elem.text:
            try:
                result.duration_ms = int(float(elapsed_elem.text) * 60 * 1000)
            except ValueError:
                pass

        LOGGER.info(
            f"ctest: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )
        return result

    def _parse_text_output(self, output: str, project_root: Path) -> TestResult:
        """Parse CTest text output.

        CTest output looks like:
            Test project /path/to/build
                Start 1: test_math
            1/3 Test #1: test_math ......................   Passed    0.01 sec
                Start 2: test_string
            2/3 Test #2: test_string ....................***Failed    0.02 sec
            ...
            100% tests passed, 0 tests failed out of 3

        Args:
            output: stdout from ctest.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="ctest")

        if not output.strip():
            return result

        # Match individual test result lines
        test_re = re.compile(
            r"\d+/\d+\s+Test\s+#\d+:\s+(\S+)\s+\.+\s*(Passed|Failed|\*\*\*Failed|\*\*\*Not Run)\s+(\d+\.\d+)\s+sec"
        )

        for line in output.splitlines():
            match = test_re.search(line)
            if not match:
                continue

            test_name = match.group(1)
            status = match.group(2)
            elapsed = float(match.group(3))
            result.duration_ms += int(elapsed * 1000)

            if status == "Passed":
                result.passed += 1
            elif "Failed" in status:
                result.failed += 1
                issue_id = self._generate_ctest_issue_id(test_name)
                result.issues.append(
                    UnifiedIssue(
                        id=issue_id,
                        domain=ToolDomain.TESTING,
                        source_tool="ctest",
                        severity=Severity.HIGH,
                        rule_id="test_failed",
                        title=f"{test_name} FAILED",
                        description=f"Test {test_name} failed",
                        fixable=False,
                        metadata={
                            "test_name": test_name,
                            "outcome": "failed",
                        },
                    )
                )
            elif "Not Run" in status:
                result.skipped += 1

        LOGGER.info(
            f"ctest: {result.passed} passed, {result.failed} failed, "
            f"{result.skipped} skipped"
        )
        return result

    def _generate_ctest_issue_id(self, test_name: str) -> str:
        """Generate deterministic issue ID for a CTest failure."""
        content = f"ctest::{test_name}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"ctest-{hash_val}"
