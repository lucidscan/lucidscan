"""coverage.py coverage plugin.

coverage.py is a tool for measuring code coverage of Python programs.
https://coverage.readthedocs.io/
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext, SkipReason, ToolDomain
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
)
from lucidshark.plugins.utils import (
    ensure_python_binary,
    get_cli_version,
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
    ) -> CoverageResult:
        """Parse existing coverage data.

        Looks for an existing .coverage file and generates a JSON report from it.
        If no .coverage file exists or report generation fails, returns an error
        issue directing the user to run the testing domain first.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).

        Returns:
            CoverageResult with coverage statistics and issues if below threshold.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return CoverageResult(threshold=threshold, tool="coverage_py")

        # Check if .coverage data file exists
        coverage_data = context.project_root / ".coverage"
        if not coverage_data.exists():
            LOGGER.warning("No .coverage data file found")
            result = CoverageResult(threshold=threshold, tool="coverage_py")
            result.issues.append(self._create_no_data_issue())
            return result

        # Generate JSON report from existing coverage data
        result = self._generate_and_parse_report(binary, context, threshold)

        # If report generation returned an empty result (failure), add no-data issue
        if result.total_lines == 0 and not result.issues:
            result.issues.append(self._create_no_data_issue())

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
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.COVERAGE,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Failed to generate coverage report: {e}",
                )
                return CoverageResult(threshold=threshold, tool="coverage_py")

            # Parse JSON report
            if report_file.exists():
                return self._parse_json_report(
                    report_file, context.project_root, threshold
                )
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
                percent_covered, threshold, total_lines, covered_lines
            )
            result.issues.append(issue)

        LOGGER.info(
            f"Coverage: {percent_covered:.1f}% ({covered_lines}/{total_lines} lines) "
            f"- threshold: {threshold}%"
        )

        return result
