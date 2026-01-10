"""Base class for linter plugins.

All linter plugins inherit from LinterPlugin and implement the lint() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from lucidscan.core.models import ScanContext, UnifiedIssue, ToolDomain


@dataclass
class FixResult:
    """Result of applying automatic fixes."""

    files_modified: int = 0
    issues_fixed: int = 0
    issues_remaining: int = 0
    details: List[str] = None  # type: ignore

    def __post_init__(self):
        if self.details is None:
            self.details = []


class LinterPlugin(ABC):
    """Abstract base class for linter plugins.

    Linter plugins provide code linting functionality for the quality pipeline.
    Each plugin wraps a specific linting tool (Ruff, ESLint, etc.).
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the linter plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g., 'ruff', 'eslint').

        Returns:
            Plugin name string.
        """

    @property
    @abstractmethod
    def languages(self) -> List[str]:
        """Languages this linter supports.

        Returns:
            List of language names (e.g., ['python'], ['javascript', 'typescript']).
        """

    @property
    def domain(self) -> ToolDomain:
        """Tool domain (always LINTING for linters).

        Returns:
            ToolDomain.LINTING
        """
        return ToolDomain.LINTING

    @property
    def supports_fix(self) -> bool:
        """Whether this linter supports auto-fix mode.

        Returns:
            True if the linter can automatically fix issues.
        """
        return False

    @abstractmethod
    def get_version(self) -> str:
        """Get the version of the underlying linting tool.

        Returns:
            Version string.
        """

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the linting tool is installed.

        Downloads or installs the tool if not present.

        Returns:
            Path to the tool binary.
        """

    @abstractmethod
    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run linting on the specified paths.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of UnifiedIssue objects for each linting violation.
        """

    def fix(self, context: ScanContext) -> FixResult:
        """Apply automatic fixes for linting issues.

        Override this method if the linter supports auto-fix.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            FixResult with statistics about fixes applied.

        Raises:
            NotImplementedError: If the linter doesn't support auto-fix.
        """
        raise NotImplementedError(f"{self.name} does not support auto-fix")
