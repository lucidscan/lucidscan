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

    def filter_to_changed_files(
        self,
        changed_files: List[Path],
        project_root: Path,
    ) -> "DuplicationResult":
        """Create filtered copy with only duplicates involving changed files.

        A duplicate is included if either file1 OR file2 is in changed files.
        This is useful for PR-based incremental scanning where you want to
        see duplicates that involve the code being changed.

        Args:
            changed_files: List of changed file paths (absolute).
            project_root: Project root for path resolution.

        Returns:
            New DuplicationResult with filtered duplicates and recalculated stats.
        """
        from typing import Set

        if not changed_files:
            return DuplicationResult(
                files_analyzed=0,
                total_lines=0,
                duplicate_blocks=0,
                duplicate_lines=0,
                threshold=self.threshold,
                duplicates=[],
                issues=[],
            )

        # Build set of changed file paths (both absolute and relative)
        changed_set: Set[str] = set()
        for f in changed_files:
            changed_set.add(str(f))  # Absolute path
            try:
                changed_set.add(str(f.relative_to(project_root)))  # Relative
            except ValueError:
                pass

        def path_matches(p: Path) -> bool:
            """Check if path matches any changed file."""
            p_str = str(p)
            try:
                p_rel = str(p.relative_to(project_root))
            except ValueError:
                p_rel = p_str
            return p_str in changed_set or p_rel in changed_set

        # Filter duplicates to those involving at least one changed file
        filtered_duplicates: List[DuplicateBlock] = []
        filtered_lines = 0
        involved_files: Set[str] = set()

        for dup in self.duplicates:
            if path_matches(dup.file1) or path_matches(dup.file2):
                filtered_duplicates.append(dup)
                filtered_lines += dup.line_count
                involved_files.add(str(dup.file1))
                involved_files.add(str(dup.file2))

        # Filter issues to those involving changed files
        from lucidshark.core.filtering import filter_issues_by_changed_files

        filtered_issues = filter_issues_by_changed_files(
            self.issues, changed_files, project_root
        )

        return DuplicationResult(
            # Keep original counts for consistency and meaningful percentage calculation.
            # The filtered result shows duplicates involving changed files, but the
            # percentage is relative to the full project for context.
            files_analyzed=self.files_analyzed,  # Keep original for consistency
            total_lines=self.total_lines,  # Keep original for % calculation context
            duplicate_blocks=len(filtered_duplicates),
            duplicate_lines=filtered_lines,
            threshold=self.threshold,
            duplicates=filtered_duplicates,
            issues=filtered_issues,
        )


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
        use_baseline: bool = False,
        use_cache: bool = True,
        use_git: bool = True,
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
            use_baseline: If True, track known duplicates and only report new ones.
            use_cache: If True, cache processed files for faster re-runs.
            use_git: If True, use git ls-files for file discovery when in a git repo.

        Returns:
            DuplicationResult with statistics and detected duplicates.
        """
