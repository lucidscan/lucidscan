"""dotnet test runner plugin.

Runs .NET tests via `dotnet test` and parses TRX reports
for test results and failures. Supports xUnit, NUnit, and MSTest.
https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-test
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
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
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.test_runners.base import TestRunnerPlugin, TestResult
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

# TRX namespace
TRX_NS = {"trx": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


def _find_dotnet() -> Path:
    """Find the dotnet CLI binary.

    Returns:
        Path to dotnet binary.

    Raises:
        FileNotFoundError: If dotnet is not installed.
    """
    dotnet = shutil.which("dotnet")
    if dotnet:
        return Path(dotnet)

    raise FileNotFoundError(
        "dotnet is not installed. Install the .NET SDK from:\n"
        "  https://dotnet.microsoft.com/download"
    )


def _find_project_file(project_root: Path) -> Optional[Path]:
    """Find a .sln or .csproj file in the project root.

    Args:
        project_root: Project root directory.

    Returns:
        Path to the project/solution file, or None.
    """
    sln_files = list(project_root.glob("*.sln"))
    if sln_files:
        return sln_files[0]

    csproj_files = list(project_root.glob("*.csproj"))
    if csproj_files:
        return csproj_files[0]

    csproj_files = list(project_root.glob("*/*.csproj"))
    if csproj_files:
        return csproj_files[0].parent

    return None


class DotnetTestRunner(TestRunnerPlugin):
    """dotnet test runner plugin for .NET test execution.

    Supports xUnit, NUnit, and MSTest frameworks via `dotnet test`.
    Parses TRX reports for detailed test results.
    """

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "dotnet_test"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["csharp"]

    def get_version(self) -> str:
        """Get dotnet SDK version."""
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure dotnet CLI is available.

        Returns:
            Path to dotnet binary.

        Raises:
            FileNotFoundError: If dotnet is not installed.
        """
        return _find_dotnet()

    def run_tests(self, context: ScanContext) -> TestResult:
        """Run tests using dotnet test.

        When the coverage domain is enabled, adds --collect:"XPlat Code Coverage"
        to generate Cobertura coverage data in the same pass.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
        try:
            dotnet = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return TestResult(tool="dotnet_test")

        project_file = _find_project_file(context.project_root)
        if not project_file:
            LOGGER.info("No .sln or .csproj found, skipping dotnet test")
            return TestResult(tool="dotnet_test")

        # Build the test command
        results_dir = context.project_root / "TestResults"
        cmd = [
            str(dotnet),
            "test",
            str(project_file),
            "--logger",
            "trx",
            "--results-directory",
            str(results_dir),
            "-v",
            "quiet",
            "--no-restore",
        ]

        # Add coverage collection if coverage domain is enabled
        if ToolDomain.COVERAGE in context.enabled_domains:
            cmd.extend(["--collect:XPlat Code Coverage"])
            LOGGER.info("Adding XPlat Code Coverage collection to dotnet test")

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        stdout = ""
        stderr = ""
        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="dotnet-test",
                stream_handler=context.stream_handler,
                timeout=600,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except subprocess.TimeoutExpired:
            LOGGER.warning("dotnet test timed out after 600 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TESTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="dotnet test timed out after 600 seconds",
            )
            return TestResult(tool="dotnet_test")
        except Exception as e:
            LOGGER.debug(f"dotnet test completed with: {e}")
            stdout = getattr(e, "stdout", "") or ""
            stderr = getattr(e, "stderr", "") or ""

        # Try to parse TRX report first
        trx_result = self._parse_trx_reports(results_dir, context.project_root)
        if trx_result and trx_result.total > 0:
            return trx_result

        # Fall back to parsing console output
        return self._parse_console_output(
            stdout + "\n" + stderr, context.project_root
        )

    def _parse_trx_reports(
        self, results_dir: Path, project_root: Path
    ) -> Optional[TestResult]:
        """Parse TRX report files from TestResults directory.

        Args:
            results_dir: Directory containing TRX report files.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data, or None if no reports found.
        """
        if not results_dir.exists():
            return None

        trx_files = sorted(results_dir.glob("**/*.trx"), key=lambda p: p.stat().st_mtime)
        if not trx_files:
            return None

        total_passed = 0
        total_failed = 0
        total_skipped = 0
        total_errors = 0
        all_issues: List[UnifiedIssue] = []

        for trx_file in trx_files:
            try:
                result = self._parse_single_trx(trx_file, project_root)
                total_passed += result.passed
                total_failed += result.failed
                total_skipped += result.skipped
                total_errors += result.errors
                all_issues.extend(result.issues)
            except Exception as e:
                LOGGER.warning(f"Failed to parse TRX report {trx_file}: {e}")

        return TestResult(
            passed=total_passed,
            failed=total_failed,
            skipped=total_skipped,
            errors=total_errors,
            issues=all_issues,
            tool="dotnet_test",
        )

    def _parse_single_trx(
        self, trx_file: Path, project_root: Path
    ) -> TestResult:
        """Parse a single TRX report file.

        Args:
            trx_file: Path to TRX file.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        tree = ET.parse(trx_file)
        root = tree.getroot()

        # Parse counters from ResultSummary
        counters_elem = root.find(".//trx:Counters", TRX_NS)
        if counters_elem is None:
            # Try without namespace
            counters_elem = root.find(".//{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Counters")

        passed = 0
        failed = 0
        skipped = 0
        errors = 0

        if counters_elem is not None:
            passed = int(counters_elem.get("passed", "0"))
            failed = int(counters_elem.get("failed", "0"))
            skipped = int(counters_elem.get("notExecuted", "0"))
            errors = int(counters_elem.get("error", "0"))

        # Parse individual test failures
        issues: List[UnifiedIssue] = []
        results = root.findall(".//trx:UnitTestResult", TRX_NS)
        if not results:
            results = root.findall(
                ".//{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}UnitTestResult"
            )

        for test_result in results:
            outcome = test_result.get("outcome", "")
            if outcome in ("Failed", "Error"):
                issue = self._trx_result_to_issue(test_result, project_root)
                if issue:
                    issues.append(issue)

        LOGGER.info(
            f"dotnet_test: {passed} passed, {failed} failed, "
            f"{skipped} skipped, {errors} errors"
        )

        return TestResult(
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            issues=issues,
            tool="dotnet_test",
        )

    def _trx_result_to_issue(
        self,
        test_result: ET.Element,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a TRX test result to UnifiedIssue.

        Args:
            test_result: XML element for a test result.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            test_name = test_result.get("testName", "Unknown")

            # Extract error message and stack trace
            output_elem = test_result.find("trx:Output", TRX_NS)
            if output_elem is None:
                output_elem = test_result.find(
                    "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Output"
                )

            message = "Test failed"
            stack_trace = ""

            if output_elem is not None:
                error_info = output_elem.find("trx:ErrorInfo", TRX_NS)
                if error_info is None:
                    error_info = output_elem.find(
                        "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}ErrorInfo"
                    )

                if error_info is not None:
                    msg_elem = error_info.find("trx:Message", TRX_NS)
                    if msg_elem is None:
                        msg_elem = error_info.find(
                            "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Message"
                        )
                    if msg_elem is not None and msg_elem.text:
                        message = msg_elem.text.strip()

                    trace_elem = error_info.find("trx:StackTrace", TRX_NS)
                    if trace_elem is None:
                        trace_elem = error_info.find(
                            "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}StackTrace"
                        )
                    if trace_elem is not None and trace_elem.text:
                        stack_trace = trace_elem.text.strip()

            # Extract file path and line number from stack trace
            file_path, line_number = self._extract_location(
                stack_trace, project_root
            )

            short_msg = self._truncate(message, 80)
            title = f"{test_name}: {short_msg}"

            issue_id = self._generate_issue_id(test_name, message)

            description = message
            if stack_trace:
                description += f"\n\nStack trace:\n{stack_trace[:500]}"

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TESTING,
                source_tool="dotnet_test",
                severity=Severity.HIGH,
                rule_id="test_failed",
                title=title,
                description=description,
                file_path=file_path,
                line_start=line_number,
                line_end=line_number,
                fixable=False,
                metadata={
                    "test_name": test_name,
                    "outcome": test_result.get("outcome", ""),
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse TRX test result: {e}")
            return None

    def _extract_location(
        self, stack_trace: str, project_root: Path
    ) -> tuple[Optional[Path], Optional[int]]:
        """Extract file path and line number from a .NET stack trace.

        Args:
            stack_trace: Stack trace text.
            project_root: Project root directory.

        Returns:
            Tuple of (file_path, line_number).
        """
        if not stack_trace:
            return None, None

        # Match patterns like "in /path/File.cs:line 42"
        match = re.search(r"in\s+(.+\.cs):line\s+(\d+)", stack_trace)
        if match:
            file_path = Path(match.group(1))
            if not file_path.is_absolute():
                file_path = project_root / file_path
            return file_path, int(match.group(2))

        return None, None

    def _parse_console_output(
        self, output: str, project_root: Path
    ) -> TestResult:
        """Parse dotnet test console output as fallback.

        Args:
            output: Combined stdout/stderr.
            project_root: Project root directory.

        Returns:
            TestResult with parsed data.
        """
        result = TestResult(tool="dotnet_test")

        # Parse summary line:
        # "Passed! - Failed: 0, Passed: 5, Skipped: 0, Total: 5"
        # "Failed! - Failed: 2, Passed: 3, Skipped: 0, Total: 5"
        summary_pattern = re.compile(
            r"(?:Passed|Failed)!\s*-\s*"
            r"Failed:\s*(\d+),\s*"
            r"Passed:\s*(\d+),\s*"
            r"Skipped:\s*(\d+),\s*"
            r"Total:\s*(\d+)"
        )

        for match in summary_pattern.finditer(output):
            result.failed += int(match.group(1))
            result.passed += int(match.group(2))
            result.skipped += int(match.group(3))

        # Parse individual test failures from output
        fail_pattern = re.compile(
            r"Failed\s+([\w.]+)\s*\[.*?\]\s*(.*?)(?=\n\s*(?:Failed|Passed|$))",
            re.DOTALL,
        )

        for match in fail_pattern.finditer(output):
            test_name = match.group(1)
            failure_text = match.group(2).strip()

            file_path, line_number = self._extract_location(
                failure_text, project_root
            )

            short_msg = self._truncate(failure_text, 80)
            title = (
                f"{test_name}: {short_msg}"
                if short_msg
                else f"{test_name} FAILED"
            )

            issue_id = self._generate_issue_id(test_name, failure_text)

            result.issues.append(
                UnifiedIssue(
                    id=issue_id,
                    domain=ToolDomain.TESTING,
                    source_tool="dotnet_test",
                    severity=Severity.HIGH,
                    rule_id="test_failed",
                    title=title,
                    description=f"Test {test_name} failed:\n{failure_text[:500]}",
                    file_path=file_path,
                    line_start=line_number,
                    line_end=line_number,
                    fixable=False,
                    metadata={
                        "test_name": test_name,
                        "outcome": "failed",
                    },
                )
            )

        return result
