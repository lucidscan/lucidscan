"""Vitest coverage plugin.

Vitest has built-in coverage support via @vitest/coverage-v8 or
@vitest/coverage-istanbul, outputting Istanbul-compatible JSON reports.
https://vitest.dev/guide/coverage
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
)
from lucidshark.plugins.utils import ensure_node_binary

LOGGER = get_logger(__name__)

# Standard locations where Vitest writes coverage-summary.json
_COVERAGE_REPORT_PATHS = [
    "coverage/coverage-summary.json",
    "coverage/coverage-final.json",
]


class VitestCoveragePlugin(CoveragePlugin):
    """Vitest coverage plugin for JavaScript/TypeScript coverage analysis.

    Uses Vitest's built-in coverage support which outputs Istanbul-compatible
    JSON reports. Requires @vitest/coverage-v8 or @vitest/coverage-istanbul
    to be installed in the project.
    """

    def __init__(self, project_root: Optional[Path] = None):
        """Initialize VitestCoveragePlugin.

        Args:
            project_root: Optional project root for finding Vitest installation.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "vitest_coverage"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript"]

    def ensure_binary(self) -> Path:
        """Ensure Vitest is available."""
        return ensure_node_binary(
            self._project_root,
            "vitest",
            "Vitest is not installed. Install it with:\n"
            "  npm install vitest --save-dev\n"
            "\n"
            "For coverage support, also install a coverage provider:\n"
            "  npm install @vitest/coverage-v8 --save-dev\n"
            "  OR\n"
            "  npm install @vitest/coverage-istanbul --save-dev",
        )

    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
    ) -> CoverageResult:
        """Parse existing Vitest coverage data.

        Looks for existing coverage data in the coverage/ directory.
        If no coverage data is found, returns an error issue directing
        the user to run the testing domain first.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).

        Returns:
            CoverageResult with coverage statistics and issues if below threshold.
        """
        result = self._find_and_parse_report(context.project_root, threshold)

        if result.total_lines == 0 and not result.issues:
            result.issues.append(self._create_no_data_issue())

        return result

    def _find_and_parse_report(
        self,
        project_root: Path,
        threshold: float,
    ) -> CoverageResult:
        """Find and parse the coverage JSON report.

        Args:
            project_root: Project root directory.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        for rel_path in _COVERAGE_REPORT_PATHS:
            report_file = project_root / rel_path
            if report_file.exists():
                report = self._load_json_report(report_file, threshold)
                if report is None:
                    return CoverageResult(threshold=threshold, tool=self.name)
                if rel_path.endswith("coverage-summary.json"):
                    return self._parse_istanbul_summary(report, project_root, threshold)
                else:
                    return self._parse_istanbul_final(report, project_root, threshold)

        LOGGER.warning(
            "No Vitest coverage report found. Ensure a coverage provider is installed:\n"
            "  npm install @vitest/coverage-v8 --save-dev"
        )
        return CoverageResult(threshold=threshold, tool=self.name)
