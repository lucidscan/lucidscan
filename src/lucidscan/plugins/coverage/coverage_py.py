"""coverage.py coverage plugin.

coverage.py is a tool for measuring code coverage of Python programs.
https://coverage.readthedocs.io/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from lucidscan.core.logging import get_logger
from lucidscan.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidscan.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
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
        """Get coverage.py version.

        Returns:
            Version string or 'unknown' if unable to determine.
        """
        try:
            binary = self.ensure_binary()
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
            )
            # Output is like "Coverage.py, version 7.4.0 ..."
            if result.returncode == 0:
                output = result.stdout.strip()
                if "version" in output:
                    # Extract version number
                    parts = output.split("version")
                    if len(parts) >= 2:
                        version = parts[1].strip().split()[0]
                        return version.rstrip(",")
        except Exception:
            pass
        return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure coverage is available.

        Checks for coverage in:
        1. Project's .venv/bin/coverage
        2. System PATH

        Returns:
            Path to coverage binary.

        Raises:
            FileNotFoundError: If coverage is not installed.
        """
        # Check project venv first
        if self._project_root:
            venv_coverage = self._project_root / ".venv" / "bin" / "coverage"
            if venv_coverage.exists():
                return venv_coverage

        # Check system PATH
        coverage_path = shutil.which("coverage")
        if coverage_path:
            return Path(coverage_path)

        raise FileNotFoundError(
            "coverage is not installed. Install it with: pip install coverage"
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
            return CoverageResult(threshold=threshold)

        # Check for existing coverage data
        coverage_file = context.project_root / ".coverage"

        if not coverage_file.exists() and run_tests:
            LOGGER.info("No coverage data found, running tests with coverage...")
            if not self._run_tests_with_coverage(binary, context):
                LOGGER.warning("Failed to run tests with coverage")
                return CoverageResult(threshold=threshold)

        # Generate JSON report
        return self._generate_and_parse_report(binary, context, threshold)

    def _run_tests_with_coverage(
        self,
        binary: Path,
        context: ScanContext,
    ) -> bool:
        """Run pytest with coverage measurement.

        Args:
            binary: Path to coverage binary.
            context: Scan context.

        Returns:
            True if tests ran successfully.
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
            return False

        # Build command to run coverage with pytest
        cmd = [
            str(binary),
            "run",
            "-m",
            "pytest",
            "--tb=no",
            "-q",
        ]

        # Add paths
        paths = [str(p) for p in context.paths] if context.paths else []
        cmd.extend(paths)

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(context.project_root),
            )
            # Coverage run returns the pytest exit code
            # We consider it successful even if some tests fail
            return True
        except Exception as e:
            LOGGER.error(f"Failed to run tests with coverage: {e}")
            return False

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
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(context.project_root),
                )

                if result.returncode != 0:
                    LOGGER.warning(f"Coverage json failed: {result.stderr}")
                    return CoverageResult(threshold=threshold)

            except Exception as e:
                LOGGER.error(f"Failed to generate coverage report: {e}")
                return CoverageResult(threshold=threshold)

            # Parse JSON report
            if report_file.exists():
                return self._parse_json_report(report_file, context.project_root, threshold)
            else:
                LOGGER.warning("Coverage JSON report not generated")
                return CoverageResult(threshold=threshold)

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
            return CoverageResult(threshold=threshold)

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
        """Create a UnifiedIssue for coverage below threshold.

        Args:
            percentage: Actual coverage percentage.
            threshold: Required coverage threshold.
            total_lines: Total number of lines.
            covered_lines: Number of covered lines.
            missing_lines: Number of missing lines.

        Returns:
            UnifiedIssue for coverage failure.
        """
        # Determine severity based on how far below threshold
        if percentage < 50:
            severity = Severity.HIGH
        elif percentage < threshold - 10:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        # Generate deterministic ID
        issue_id = self._generate_issue_id(percentage, threshold)

        gap = threshold - percentage

        return UnifiedIssue(
            id=issue_id,
            scanner=ToolDomain.COVERAGE,
            source_tool="coverage.py",
            severity=severity,
            title=f"Coverage {percentage:.1f}% is below threshold {threshold}%",
            description=(
                f"Project coverage is {percentage:.1f}%, which is {gap:.1f}% below "
                f"the required threshold of {threshold}%. "
                f"{missing_lines} lines are not covered."
            ),
            file_path=None,  # Project-level issue
            line_start=None,
            line_end=None,
            scanner_metadata={
                "coverage_percentage": round(percentage, 2),
                "threshold": threshold,
                "total_lines": total_lines,
                "covered_lines": covered_lines,
                "missing_lines": missing_lines,
                "gap_percentage": round(gap, 2),
            },
        )

    def _generate_issue_id(self, percentage: float, threshold: float) -> str:
        """Generate deterministic issue ID.

        Args:
            percentage: Coverage percentage.
            threshold: Coverage threshold.

        Returns:
            Unique issue ID.
        """
        # ID based on rounded percentage and threshold for stability
        content = f"coverage:{round(percentage)}:{threshold}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"coverage-{hash_val}"
