"""Base class for coverage plugins.

All coverage plugins inherit from CoveragePlugin and implement the measure_coverage() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from lucidscan.core.models import ScanContext, UnifiedIssue, ToolDomain


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
class CoverageResult:
    """Result statistics from coverage analysis."""

    total_lines: int = 0
    covered_lines: int = 0
    missing_lines: int = 0
    excluded_lines: int = 0
    threshold: float = 0.0
    files: Dict[str, FileCoverage] = field(default_factory=dict)
    issues: List[UnifiedIssue] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        """Overall coverage percentage."""
        if self.total_lines == 0:
            return 100.0
        return (self.covered_lines / self.total_lines) * 100

    @property
    def passed(self) -> bool:
        """Whether coverage meets the threshold."""
        return self.percentage >= self.threshold


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
