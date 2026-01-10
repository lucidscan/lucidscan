"""Base class for type checker plugins.

All type checker plugins inherit from TypeCheckerPlugin and implement the check() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from lucidscan.core.models import ScanContext, UnifiedIssue, ToolDomain


@dataclass
class TypeCheckResult:
    """Result statistics from type checking."""

    errors: int = 0
    warnings: int = 0
    notes: int = 0
    files_checked: int = 0
    details: List[str] = field(default_factory=list)


class TypeCheckerPlugin(ABC):
    """Abstract base class for type checker plugins.

    Type checker plugins provide static type checking functionality.
    Each plugin wraps a specific type checking tool (mypy, pyright, tsc, etc.).
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the type checker plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g., 'mypy', 'pyright').

        Returns:
            Plugin name string.
        """

    @property
    @abstractmethod
    def languages(self) -> List[str]:
        """Languages this type checker supports.

        Returns:
            List of language names (e.g., ['python'], ['typescript']).
        """

    @property
    def domain(self) -> ToolDomain:
        """Tool domain (always TYPE_CHECKING for type checkers).

        Returns:
            ToolDomain.TYPE_CHECKING
        """
        return ToolDomain.TYPE_CHECKING

    @property
    def supports_strict_mode(self) -> bool:
        """Whether this type checker supports strict mode.

        Returns:
            True if the type checker has a strict mode.
        """
        return False

    @abstractmethod
    def get_version(self) -> str:
        """Get the version of the underlying type checking tool.

        Returns:
            Version string.
        """

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the type checking tool is installed.

        Downloads or installs the tool if not present.

        Returns:
            Path to the tool binary.
        """

    @abstractmethod
    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run type checking on the specified paths.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of UnifiedIssue objects for each type error.
        """
