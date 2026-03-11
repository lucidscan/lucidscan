"""Istanbul/NYC coverage plugin.

Istanbul (via NYC) is a JavaScript code coverage tool.
https://istanbul.js.org/
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext, SkipReason, ToolDomain
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
)
from lucidshark.plugins.utils import ensure_node_binary

LOGGER = get_logger(__name__)

# Standard locations where Jest writes Istanbul-format coverage reports.
_JEST_COVERAGE_PATHS = [
    "coverage/coverage-summary.json",
    "coverage/coverage-final.json",
]


class IstanbulPlugin(CoveragePlugin):
    """Istanbul/NYC coverage plugin for JavaScript/TypeScript coverage analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize IstanbulPlugin.

        Args:
            project_root: Optional project root for finding NYC installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "istanbul"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    def ensure_binary(self) -> Path:
        """Ensure NYC is available."""
        return ensure_node_binary(
            self._project_root,
            "nyc",
            "NYC (Istanbul) is not installed. Install it with:\n"
            "  npm install nyc --save-dev\n"
            "  OR\n"
            "  npm install -g nyc",
        )

    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
    ) -> CoverageResult:
        """Parse existing coverage data.

        Looks for existing .nyc_output directory and generates a report from it.
        If no coverage data exists or report generation fails, returns an error
        issue directing the user to run the testing domain first.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).

        Returns:
            CoverageResult with coverage statistics and issues if below threshold.
        """
        # First, check if Jest/Istanbul wrote coverage files directly
        for rel_path in _JEST_COVERAGE_PATHS:
            report_file = context.project_root / rel_path
            if report_file.exists():
                report = self._load_json_report(report_file, threshold)
                if report is None:
                    result = CoverageResult(threshold=threshold, tool=self.name)
                    result.issues.append(self._create_no_data_issue())
                    return result
                if rel_path.endswith("coverage-summary.json"):
                    result = self._parse_istanbul_summary(
                        report, context.project_root, threshold
                    )
                else:
                    result = self._parse_istanbul_final(
                        report, context.project_root, threshold
                    )
                if result.total_lines == 0 and not result.issues:
                    result.issues.append(self._create_no_data_issue())
                return result

        # Fallback: use .nyc_output/ + nyc report (for projects using NYC directly)
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            result = CoverageResult(threshold=threshold, tool=self.name)
            result.issues.append(self._create_no_data_issue())
            return result

        # Check if .nyc_output directory exists with coverage data
        nyc_output = context.project_root / ".nyc_output"
        if not nyc_output.exists() or not any(nyc_output.iterdir()):
            LOGGER.warning(
                "No coverage/ or .nyc_output/ directory found with coverage data"
            )
            result = CoverageResult(threshold=threshold, tool=self.name)
            result.issues.append(self._create_no_data_issue())
            return result

        # Generate JSON report from existing coverage data
        result = self._generate_and_parse_report(binary, context, threshold)

        if result.total_lines == 0 and not result.issues:
            result.issues.append(self._create_no_data_issue())

        return result

    def _generate_and_parse_report(
        self,
        binary: Path,
        context: ScanContext,
        threshold: float,
    ) -> CoverageResult:
        """Generate JSON report and parse it.

        Args:
            binary: Path to NYC binary.
            context: Scan context.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)

            cmd = [
                str(binary),
                "report",
                "--reporter=json-summary",
                f"--report-dir={report_dir}",
            ]

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(context.project_root),
                )

                if result.returncode != 0:
                    LOGGER.warning(f"NYC report failed: {result.stderr}")
                    return CoverageResult(threshold=threshold, tool=self.name)

            except Exception as e:
                LOGGER.error(f"Failed to generate coverage report: {e}")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.COVERAGE,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Failed to generate coverage report: {e}",
                )
                return CoverageResult(threshold=threshold, tool=self.name)

            # Parse JSON report
            report_file = report_dir / "coverage-summary.json"
            if report_file.exists():
                report = self._load_json_report(report_file, threshold)
                if report is None:
                    return CoverageResult(threshold=threshold, tool=self.name)
                return self._parse_istanbul_summary(
                    report, context.project_root, threshold
                )
            else:
                LOGGER.warning("Coverage JSON report not generated")
                return CoverageResult(threshold=threshold, tool=self.name)

    def _create_no_data_issue(self):
        """Create a UnifiedIssue when no coverage data is found.

        Overrides base to add Istanbul-specific details about file locations.
        """
        issue = super()._create_no_data_issue()
        issue.description = (
            "No coverage data found for istanbul. "
            "Looked for coverage/coverage-summary.json, coverage/coverage-final.json, "
            "and .nyc_output/ but none were found. "
            "Ensure the testing domain is active and has run before coverage analysis. "
            "Test runners generate coverage data automatically when they execute."
        )
        return issue
