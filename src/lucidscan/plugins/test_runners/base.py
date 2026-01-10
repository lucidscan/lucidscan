"""Base class for test runner plugins.

All test runner plugins inherit from TestRunnerPlugin and implement the run_tests() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from lucidscan.core.models import ScanContext, UnifiedIssue, ToolDomain


@dataclass
class TestResult:
    """Result statistics from test execution."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: int = 0
    issues: List[UnifiedIssue] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of tests run."""
        return self.passed + self.failed + self.skipped + self.errors

    @property
    def success(self) -> bool:
        """Whether all tests passed (no failures or errors)."""
        return self.failed == 0 and self.errors == 0


class TestRunnerPlugin(ABC):
    """Abstract base class for test runner plugins.

    Test runner plugins provide test execution functionality for the quality pipeline.
    Each plugin wraps a specific test framework (pytest, Jest, etc.).
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the test runner plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g., 'pytest', 'jest').

        Returns:
            Plugin name string.
        """

    @property
    @abstractmethod
    def languages(self) -> List[str]:
        """Languages this test runner supports.

        Returns:
            List of language names (e.g., ['python'], ['javascript', 'typescript']).
        """

    @property
    def domain(self) -> ToolDomain:
        """Tool domain (always TESTING for test runners).

        Returns:
            ToolDomain.TESTING
        """
        return ToolDomain.TESTING

    @abstractmethod
    def get_version(self) -> str:
        """Get the version of the underlying test framework.

        Returns:
            Version string.
        """

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the test framework is installed.

        Finds or installs the tool if not present.

        Returns:
            Path to the tool binary.

        Raises:
            FileNotFoundError: If the tool cannot be found or installed.
        """

    @abstractmethod
    def run_tests(self, context: ScanContext) -> TestResult:
        """Run tests on the specified paths.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            TestResult with test statistics and issues for failures.
        """
