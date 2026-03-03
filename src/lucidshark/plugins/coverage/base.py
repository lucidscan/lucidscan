"""Base class for coverage plugins.

All coverage plugins inherit from CoveragePlugin and implement the measure_coverage() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Re-export TestStatistics for plugins
__all__ = ["CoveragePlugin", "CoverageResult", "FileCoverage", "TestStatistics"]

from typing import Any

from lucidshark.core.models import CoverageSummary, ScanContext, UnifiedIssue, ToolDomain


@dataclass
class FileCoverage:
    """Coverage statistics for a single file."""

    file_path: Path
    total_lines: int = 0
    covered_lines: int = 0
    missing_lines: List[int] = field(default_factory=list)
    excluded_lines: int = 0

    @property
    def percentage(self) -> float:
        """Coverage percentage for this file."""
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100


@dataclass
class TestStatistics:
    """Test execution statistics."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0

    @property
    def success(self) -> bool:
        """Whether all tests passed (no failures or errors)."""
        return self.failed == 0 and self.errors == 0


@dataclass
class CoverageResult:
    """Result statistics from coverage analysis."""

    total_lines: int = 0
    covered_lines: int = 0
    missing_lines: int = 0
    excluded_lines: int = 0
    threshold: float = 0.0
    files: Dict[str, FileCoverage] = field(default_factory=dict)
    issues: List[UnifiedIssue] = field(default_factory=list)
    # Test statistics (populated when tests are run for coverage)
    test_stats: Optional[TestStatistics] = None
    tool: str = ""  # Name of the coverage tool that produced this result

    @property
    def percentage(self) -> float:
        """Overall coverage percentage."""
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    @property
    def passed(self) -> bool:
        """Whether coverage meets the threshold and tests passed (if run)."""
        if self.test_stats is not None and not self.test_stats.success:
            return False
        return self.percentage >= self.threshold

    def to_summary(self) -> CoverageSummary:
        """Convert to CoverageSummary for CLI output.

        Returns:
            CoverageSummary dataclass with all coverage statistics.
        """
        summary = CoverageSummary(
            coverage_percentage=round(self.percentage, 2),
            threshold=self.threshold,
            total_lines=self.total_lines,
            covered_lines=self.covered_lines,
            missing_lines=self.missing_lines,
            passed=self.passed,
        )
        if self.test_stats is not None:
            summary.tests_total = self.test_stats.total
            summary.tests_passed = self.test_stats.passed
            summary.tests_failed = self.test_stats.failed
            summary.tests_skipped = self.test_stats.skipped
            summary.tests_errors = self.test_stats.errors
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MCP/JSON output.

        Returns:
            Dictionary with coverage statistics.
        """
        result: Dict[str, Any] = {
            "coverage_percentage": round(self.percentage, 2),
            "threshold": self.threshold,
            "total_lines": self.total_lines,
            "covered_lines": self.covered_lines,
            "missing_lines": self.missing_lines,
            "passed": self.passed,
        }
        if self.test_stats is not None:
            result["tests"] = {
                "total": self.test_stats.total,
                "passed": self.test_stats.passed,
                "failed": self.test_stats.failed,
                "skipped": self.test_stats.skipped,
                "errors": self.test_stats.errors,
                "success": self.test_stats.success,
            }
        return result


class CoveragePlugin(ABC):
    """Abstract base class for coverage plugins.

    Coverage plugins provide code coverage analysis functionality.
    Each plugin wraps a specific coverage tool (coverage.py, Istanbul, etc.).
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the coverage plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g., 'coverage_py', 'istanbul').

        Returns:
            Plugin name string.
        """

    @property
    @abstractmethod
    def languages(self) -> List[str]:
        """Languages this coverage tool supports.

        Returns:
            List of language names (e.g., ['python'], ['javascript', 'typescript']).
        """

    @property
    def domain(self) -> ToolDomain:
        """Tool domain (always COVERAGE for coverage plugins).

        Returns:
            ToolDomain.COVERAGE
        """
        return ToolDomain.COVERAGE

    @abstractmethod
    def get_version(self) -> str:
        """Get the version of the underlying coverage tool.

        Returns:
            Version string.
        """

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the coverage tool is installed.

        Finds or installs the tool if not present.

        Returns:
            Path to the tool binary.

        Raises:
            FileNotFoundError: If the tool cannot be found or installed.
        """

    @abstractmethod
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
