"""Base class for duplication detection plugins.

All duplication plugins inherit from DuplicationPlugin and implement
the detect_duplication() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.core.models import (
    DuplicationSummary,
    ScanContext,
    ToolDomain,
    UnifiedIssue,
)

__all__ = ["DuplicationPlugin", "DuplicationResult", "DuplicateBlock"]


@dataclass
class DuplicateBlock:
    """Represents a detected duplicate code block."""

    file1: Path
    file2: Path
    start_line1: int
    end_line1: int
    start_line2: int
    end_line2: int
    line_count: int
    code_snippet: Optional[str] = None


@dataclass
class DuplicationResult:
    """Result statistics from duplication analysis."""

    files_analyzed: int = 0
    total_lines: int = 0
    duplicate_blocks: int = 0
    duplicate_lines: int = 0
    threshold: float = 10.0  # Max allowed duplication %
    duplicates: List[DuplicateBlock] = field(default_factory=list)
    issues: List[UnifiedIssue] = field(default_factory=list)

    @property
    def duplication_percent(self) -> float:
        """Percentage of duplicated code."""
        if self.total_lines == 0:
            return 0.0
        return (self.duplicate_lines / self.total_lines) * 100

    @property
    def passed(self) -> bool:
        """Whether duplication is below threshold."""
        return self.duplication_percent <= self.threshold

    def to_summary(self) -> DuplicationSummary:
        """Convert to DuplicationSummary for CLI output.

        Returns:
            DuplicationSummary dataclass with all duplication statistics.
        """
        return DuplicationSummary(
            files_analyzed=self.files_analyzed,
            total_lines=self.total_lines,
            duplicate_blocks=self.duplicate_blocks,
            duplicate_lines=self.duplicate_lines,
            duplication_percent=round(self.duplication_percent, 2),
            threshold=self.threshold,
            passed=self.passed,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MCP/JSON output.

        Returns:
            Dictionary with duplication statistics.
        """
        return {
            "duplication_percent": round(self.duplication_percent, 2),
            "threshold": self.threshold,
            "files_analyzed": self.files_analyzed,
            "total_lines": self.total_lines,
            "duplicate_blocks": self.duplicate_blocks,
            "duplicate_lines": self.duplicate_lines,
            "passed": self.passed,
        }


class DuplicationPlugin(ABC):
    """Abstract base class for duplication detection plugins.

    Duplication plugins detect code clones and duplicates across files.
    Each plugin wraps a specific duplication detection tool.

    Note: Duplication detection always scans the entire project to detect
    cross-file duplicates, regardless of the paths in the scan context.
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the duplication plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g., 'duplo', 'jscpd').

        Returns:
            Plugin name string.
        """

    @property
    @abstractmethod
    def languages(self) -> List[str]:
        """Languages this duplication detector supports.

        Returns:
            List of language names (e.g., ['python', 'rust', 'java']).
        """

    @property
    def domain(self) -> ToolDomain:
        """Tool domain (always DUPLICATION for duplication plugins).

        Returns:
            ToolDomain.DUPLICATION
        """
        return ToolDomain.DUPLICATION

    @abstractmethod
    def get_version(self) -> str:
        """Get the version of the underlying duplication tool.

        Returns:
            Version string.
        """

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the duplication tool is installed.

        Downloads or installs the tool if not present.

        Returns:
            Path to the tool binary.

        Raises:
            FileNotFoundError: If the tool cannot be found or installed.
        """

    @abstractmethod
    def detect_duplication(
        self,
        context: ScanContext,
        threshold: float = 10.0,
        min_lines: int = 4,
        min_chars: int = 3,
        exclude_patterns: Optional[List[str]] = None,
    ) -> DuplicationResult:
        """Run duplication detection on the project.

        Note: Duplication detection always scans the entire project
        to detect cross-file duplicates, regardless of paths in context.

        Args:
            context: Scan context with project root and configuration.
            threshold: Maximum allowed duplication percentage.
            min_lines: Minimum lines for a duplicate block.
            min_chars: Minimum characters per line.
            exclude_patterns: Additional patterns to exclude from duplication scan.

        Returns:
            DuplicationResult with statistics and detected duplicates.
        """
