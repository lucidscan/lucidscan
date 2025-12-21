"""Gitignore-style pattern parsing and matching.

Handles loading and matching of ignore patterns from:
- .lucidscanignore file (gitignore syntax)
- config.ignore list (gitignore syntax)

Uses pathspec library for full gitignore compliance including:
- ** recursive globbing
- ! negation patterns
- # comments
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import pathspec

from lucidscan.core.logging import get_logger

if TYPE_CHECKING:
    pass

LOGGER = get_logger(__name__)

LUCIDSCANIGNORE_NAMES = [".lucidscanignore"]


class IgnorePatterns:
    """Manages ignore patterns from multiple sources."""

    def __init__(
        self,
        patterns: List[str],
        source: str = "config",
    ) -> None:
        """Initialize with a list of gitignore-style patterns.

        Args:
            patterns: List of gitignore-style patterns.
            source: Source description for logging.
        """
        self._source = source
        self._raw_patterns = patterns

        # Filter out empty lines and comments for the PathSpec
        clean_patterns = [
            p for p in patterns if p.strip() and not p.strip().startswith("#")
        ]

        self._spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern,
            clean_patterns,
        )

        if clean_patterns:
            LOGGER.debug(f"Loaded {len(clean_patterns)} ignore patterns from {source}")

    def matches(self, path: Path, root: Path) -> bool:
        """Check if a path matches any ignore pattern.

        Args:
            path: Path to check (absolute or relative).
            root: Project root for relative path calculation.

        Returns:
            True if path should be ignored, False otherwise.
        """
        try:
            rel_path = path.relative_to(root)
        except ValueError:
            rel_path = path

        # pathspec expects forward-slash paths
        rel_str = str(rel_path).replace("\\", "/")
        return self._spec.match_file(rel_str)

    def get_exclude_patterns(self) -> List[str]:
        """Get patterns suitable for scanner --exclude flags.

        Returns clean patterns without comments, suitable for
        passing to scanner CLIs.
        """
        return [
            p.strip()
            for p in self._raw_patterns
            if p.strip() and not p.strip().startswith("#")
        ]

    @classmethod
    def from_file(cls, file_path: Path) -> Optional["IgnorePatterns"]:
        """Load patterns from a file.

        Args:
            file_path: Path to ignore file.

        Returns:
            IgnorePatterns instance, or None if file doesn't exist.
        """
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            patterns = content.splitlines()
            return cls(patterns, source=str(file_path))
        except Exception as e:
            LOGGER.warning(f"Failed to load ignore file {file_path}: {e}")
            return None

    @classmethod
    def merge(cls, *pattern_sets: Optional["IgnorePatterns"]) -> "IgnorePatterns":
        """Merge multiple IgnorePatterns instances.

        Args:
            pattern_sets: IgnorePatterns instances to merge.

        Returns:
            New IgnorePatterns with combined patterns.
        """
        all_patterns: List[str] = []
        sources: List[str] = []

        for ps in pattern_sets:
            if ps is not None:
                all_patterns.extend(ps._raw_patterns)
                sources.append(ps._source)

        return cls(all_patterns, source="+".join(sources) if sources else "empty")


def find_lucidscanignore(project_root: Path) -> Optional[Path]:
    """Find .lucidscanignore file in project root.

    Args:
        project_root: Project root directory.

    Returns:
        Path to ignore file if found, None otherwise.
    """
    for name in LUCIDSCANIGNORE_NAMES:
        ignore_path = project_root / name
        if ignore_path.exists():
            return ignore_path
    return None


def load_ignore_patterns(
    project_root: Path,
    config_patterns: List[str],
) -> IgnorePatterns:
    """Load and merge ignore patterns from all sources.

    Loads patterns from:
    1. .lucidscanignore file (if present)
    2. config.ignore list from .lucidscan.yml

    Args:
        project_root: Project root directory.
        config_patterns: Patterns from config.ignore.

    Returns:
        Merged IgnorePatterns instance.
    """
    # Load from .lucidscanignore
    ignore_file = find_lucidscanignore(project_root)
    file_patterns = IgnorePatterns.from_file(ignore_file) if ignore_file else None

    # Load from config
    config_ignore = (
        IgnorePatterns(config_patterns, source="config.ignore")
        if config_patterns
        else None
    )

    # Merge (file patterns first, then config)
    return IgnorePatterns.merge(file_patterns, config_ignore)
