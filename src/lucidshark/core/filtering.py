"""Utilities for filtering scan results to changed files.

Provides functions for incremental scanning - filtering results to only
show issues/metrics for files that have changed since a base branch.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from lucidshark.core.models import UnifiedIssue


def filter_issues_by_changed_files(
    issues: List[UnifiedIssue],
    changed_files: Optional[List[Path]],
    project_root: Path,
) -> List[UnifiedIssue]:
    """Filter issues to only those in changed files.

    Args:
        issues: List of issues to filter.
        changed_files: List of changed file paths (absolute), or None.
            If None (git command failed), returns original issues unfiltered.
            If empty list (no changes), returns empty list.
        project_root: Project root for path resolution.

    Returns:
        Filtered list containing only issues in changed files.
        Returns original issues if changed_files is None.
    """
    # If changed_files is None (git failed), return original issues unfiltered
    # This is a defensive fallback - callers should handle None explicitly
    if changed_files is None:
        return issues

    # If empty list (git worked but no changes), return empty
    if not changed_files:
        return []

    # Build set of changed file paths (both absolute and relative)
    changed_set: Set[str] = set()
    for f in changed_files:
        changed_set.add(str(f))  # Absolute path
        try:
            changed_set.add(str(f.relative_to(project_root)))  # Relative path
        except ValueError:
            pass

    filtered = []
    for issue in issues:
        if issue.file_path is None:
            continue

        file_str = str(issue.file_path)
        try:
            rel_str = str(issue.file_path.relative_to(project_root))
        except ValueError:
            rel_str = file_str

        if file_str in changed_set or rel_str in changed_set:
            filtered.append(issue)

    return filtered
