"""coverage.py coverage plugin.

coverage.py is a tool for measuring code coverage of Python programs.
https://coverage.readthedocs.io/
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext, UnifiedIssue
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
    TestStatistics,
)
from lucidshark.plugins.utils import (
    ensure_python_binary,
    get_cli_version,
    create_coverage_threshold_issue,
    create_test_failure_issue,
    detect_source_directory,
)

LOGGER = get_logger(__name__)


class CoveragePyPlugin(CoveragePlugin):
    """coverage.py plugin for Python code coverage analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize CoveragePyPlugin.

        Args:
            project_root: Optional project root for finding coverage installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "coverage_py"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["python"]

    def get_version(self) -> str:
        """Get coverage.py version."""
        try:
            binary = self.ensure_binary()
            # Output is like "Coverage.py, version 7.4.0 ..."
            def parse_coverage_version(output: str) -> str:
                if "version" in output:
                    parts = output.split("version")
                    if len(parts) >= 2:
                        version = parts[1].strip().split()[0]
                        return version.rstrip(",")
                return output
            return get_cli_version(binary, parser=parse_coverage_version)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure coverage is available."""
        return ensure_python_binary(
            self._project_root,
            "coverage",
            "coverage is not installed. Install it with: pip install coverage",
        )

    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
        run_tests: bool = True,
    ) -> CoverageResult:
        """Run coverage analysis on the specified paths.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).
            run_tests: Whether to run tests if no existing coverage data exists.

        Returns:
            CoverageResult with coverage statistics and issues if below threshold.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return CoverageResult(threshold=threshold, tool="coverage_py")

        test_stats: Optional[TestStatistics] = None

        # Always run tests fresh when run_tests=True to ensure accurate coverage
        if run_tests:
            LOGGER.info("Running tests with coverage...")
            success, test_stats = self._run_tests_with_coverage(binary, context)
            if not success:
                LOGGER.warning("Failed to run tests with coverage")
                return CoverageResult(threshold=threshold, tool="coverage_py")

            # If tests had failures/errors, fail coverage immediately
            # Don't parse potentially stale coverage data
            if test_stats and not test_stats.success:
                LOGGER.warning(
                    f"Tests failed ({test_stats.failed} failed, {test_stats.errors} errors) "
                    f"- coverage is invalid"
                )
                result = CoverageResult(threshold=threshold, tool="coverage_py")
                result.test_stats = test_stats
                result.issues.append(create_test_failure_issue(
                    source_tool="coverage.py",
                    failed=test_stats.failed,
                    errors=test_stats.errors,
                    total=test_stats.total,
                ))
                return result

        # Generate JSON report from coverage data
        result = self._generate_and_parse_report(binary, context, threshold)
        result.test_stats = test_stats

        return result

    def _detect_source_directory(self, project_root: Path) -> Optional[str]:
        """Detect the source directory for coverage measurement.

        Delegates to :func:`lucidshark.plugins.utils.detect_source_directory`.

        Args:
            project_root: Project root directory.

        Returns:
            Source directory path relative to project root, or None.
        """
        return detect_source_directory(project_root)

    def _run_tests_with_coverage(
        self,
        binary: Path,
        context: ScanContext,
    ) -> Tuple[bool, Optional[TestStatistics]]:
        """Run pytest with coverage measurement.

        Args:
            binary: Path to coverage binary.
            context: Scan context.

        Returns:
            Tuple of (success, test_stats). Success is True if tests ran.
            Test stats contain passed/failed/skipped/error counts.
        """
        # Check for pytest
        pytest_path = None
        if self._project_root:
            venv_pytest = self._project_root / ".venv" / "bin" / "pytest"
            if venv_pytest.exists():
                pytest_path = venv_pytest

        if not pytest_path:
            pytest_which = shutil.which("pytest")
            if pytest_which:
                pytest_path = Path(pytest_which)

        if not pytest_path:
            LOGGER.warning("pytest not found, cannot run tests for coverage")
            return False, None

        # Detect source directory for accurate coverage measurement
        source_dir = self._detect_source_directory(context.project_root)

        # Build command to run coverage with pytest
        # Always run full test suite - coverage needs complete test runs to be meaningful
        # (unlike linting which can work on individual changed files)
        cmd = [
            str(binary),
            "run",
        ]

        # Add --source to measure only the project's source code, not tests/libraries
        if source_dir:
            cmd.extend(["--source", source_dir])
            LOGGER.debug(f"Measuring coverage for source: {source_dir}")

        cmd.extend([
            "-m",
            "pytest",
            "--tb=no",
            "-q",
        ])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="coverage-run",
                stream_handler=context.stream_handler,
                timeout=600,
            )
            # Parse test statistics from pytest output
            test_stats = self._parse_pytest_output(result.stdout + "\n" + result.stderr)
            # Coverage run returns the pytest exit code
            # We consider it successful even if some tests fail
            return True, test_stats
        except Exception as e:
            LOGGER.error(f"Failed to run tests with coverage: {e}")
            return False, None

    def _parse_pytest_output(self, output: str) -> TestStatistics:
        """Parse pytest output to extract test statistics.

        Parses pytest summary lines like:
        - "9 passed in 0.12s"
        - "1 failed, 2 passed in 0.15s"
        - "3 passed, 1 skipped, 1 warning in 0.10s"

        Args:
            output: Combined stdout/stderr from pytest run.

        Returns:
            TestStatistics with parsed counts.
        """
        stats = TestStatistics()

        # Look for the summary line pattern
        # Example patterns:
        # "===== 1 failed, 2 passed in 0.15s ====="
        # "9 passed in 0.12s"
        # "1 passed, 1 skipped in 0.10s"
        summary_pattern = r"(?:=+\s*)?(\d+\s+\w+(?:,\s*\d+\s+\w+)*)\s+in\s+[\d.]+s\s*(?:=+)?"

        for line in output.split("\n"):
            match = re.search(summary_pattern, line)
            if match:
                summary = match.group(1)
                # Parse individual counts
                passed_match = re.search(r"(\d+)\s+passed", summary)
                failed_match = re.search(r"(\d+)\s+failed", summary)
                skipped_match = re.search(r"(\d+)\s+skipped", summary)
                error_match = re.search(r"(\d+)\s+error", summary)

                if passed_match:
                    stats.passed = int(passed_match.group(1))
                if failed_match:
                    stats.failed = int(failed_match.group(1))
                if skipped_match:
                    stats.skipped = int(skipped_match.group(1))
                if error_match:
                    stats.errors = int(error_match.group(1))

                stats.total = stats.passed + stats.failed + stats.skipped + stats.errors
                break

        return stats

    def _generate_and_parse_report(
        self,
        binary: Path,
        context: ScanContext,
        threshold: float,
    ) -> CoverageResult:
        """Generate JSON report and parse it.

        Args:
            binary: Path to coverage binary.
            context: Scan context.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "coverage.json"

            cmd = [
                str(binary),
                "json",
                "-o",
                str(report_file),
            ]

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="coverage-json",
                    stream_handler=context.stream_handler,
                    timeout=60,
                )

                if result.returncode != 0:
                    LOGGER.warning(f"Coverage json failed: {result.stderr}")
                    return CoverageResult(threshold=threshold, tool="coverage_py")

            except Exception as e:
                LOGGER.error(f"Failed to generate coverage report: {e}")
                return CoverageResult(threshold=threshold, tool="coverage_py")

            # Parse JSON report
            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root, threshold)
            else:
                LOGGER.warning("Coverage JSON report not generated")
                return CoverageResult(threshold=threshold, tool="coverage_py")

    def _parse_json_report(
        self,
        report_file: Path,
        project_root: Path,
        threshold: float,
    ) -> CoverageResult:
        """Parse coverage.py JSON report.

        Args:
            report_file: Path to JSON report file.
            project_root: Project root directory.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        try:
            with open(report_file) as f:
                report = json.load(f)
        except Exception as e:
            LOGGER.error(f"Failed to parse coverage JSON report: {e}")
            return CoverageResult(threshold=threshold, tool="coverage_py")

        totals = report.get("totals", {})
        files_data = report.get("files", {})

        # Parse totals
        total_lines = totals.get("num_statements", 0)
        covered_lines = totals.get("covered_lines", 0)
        missing_lines = totals.get("missing_lines", 0)
        excluded_lines = totals.get("excluded_lines", 0)
        percent_covered = totals.get("percent_covered", 0.0)

        result = CoverageResult(
            total_lines=total_lines,
            covered_lines=covered_lines,
            missing_lines=missing_lines,
            excluded_lines=excluded_lines,
            threshold=threshold,
            tool="coverage_py",
        )

        # Parse per-file coverage
        for file_path, file_data in files_data.items():
            summary = file_data.get("summary", {})
            missing = file_data.get("missing_lines", [])

            file_coverage = FileCoverage(
                file_path=project_root / file_path,
                total_lines=summary.get("num_statements", 0),
                covered_lines=summary.get("covered_lines", 0),
                missing_lines=missing,
                excluded_lines=summary.get("excluded_lines", 0),
            )
            result.files[file_path] = file_coverage

        # Generate issue if below threshold
        if percent_covered < threshold:
            issue = self._create_coverage_issue(
                percent_covered, threshold, total_lines, covered_lines, missing_lines
            )
            result.issues.append(issue)

        LOGGER.info(
            f"Coverage: {percent_covered:.1f}% ({covered_lines}/{total_lines} lines) "
            f"- threshold: {threshold}%"
        )

        return result

    def _create_coverage_issue(
        self,
        percentage: float,
        threshold: float,
        total_lines: int,
        covered_lines: int,
        missing_lines: int,
    ) -> UnifiedIssue:
        """Create a UnifiedIssue for coverage below threshold."""
        return create_coverage_threshold_issue(
            source_tool="coverage.py",
            percentage=percentage,
            threshold=threshold,
            total_lines=total_lines,
            covered_lines=covered_lines,
            missing_lines=missing_lines,
        )
