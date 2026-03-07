"""Git utilities for detecting changed files.

Provides functionality to detect uncommitted changes in a git repository
for partial/incremental scanning.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)


def _collect_files_from_git_command(
    cmd: List[str],
    project_root: Path,
    changed_files: set[Path],
) -> None:
    """Run a git command and collect file paths from its output.

    Args:
        cmd: Git command to run.
        project_root: Root directory of the project.
        changed_files: Set to add discovered file paths to.
    """
    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            if line:
                file_path = project_root / line
                if file_path.exists():
                    changed_files.add(file_path)


def is_git_repo(path: Path) -> bool:
    """Check if the given path is inside a git repository.

    Args:
        path: Path to check.

    Returns:
        True if inside a git repository, False otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def get_git_root(path: Path) -> Optional[Path]:
    """Get the root directory of the git repository.

    Args:
        path: Path inside the repository.

    Returns:
        Path to git root, or None if not a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
        return None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def get_changed_files(
    project_root: Path,
    include_untracked: bool = True,
    include_staged: bool = True,
    include_unstaged: bool = True,
) -> Optional[List[Path]]:
    """Get list of changed files in the git repository.

    Returns files that have uncommitted changes (staged, unstaged, or untracked).

    Args:
        project_root: Root directory of the project.
        include_untracked: Include untracked files.
        include_staged: Include staged (added to index) files.
        include_unstaged: Include unstaged modifications.

    Returns:
        List of changed file paths (absolute), or None if not a git repo
        or git command fails.
    """
    if not is_git_repo(project_root):
        LOGGER.debug(f"Not a git repository: {project_root}")
        return None

    changed_files: set[Path] = set()

    try:
        # Get staged files (files added to index)
        if include_staged:
            _collect_files_from_git_command(
                ["git", "diff", "--cached", "--name-only"],
                project_root,
                changed_files,
            )

        # Get unstaged modifications (modified but not staged)
        if include_unstaged:
            _collect_files_from_git_command(
                ["git", "diff", "--name-only"],
                project_root,
                changed_files,
            )

        # Get untracked files
        if include_untracked:
            _collect_files_from_git_command(
                ["git", "ls-files", "--others", "--exclude-standard"],
                project_root,
                changed_files,
            )

        LOGGER.debug(f"Found {len(changed_files)} changed files in {project_root}")
        return sorted(changed_files)

    except subprocess.TimeoutExpired:
        LOGGER.warning("Git command timed out, falling back to full scan")
        return None
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        LOGGER.warning(f"Git command failed: {e}, falling back to full scan")
        return None


def get_changed_files_since_branch(
    project_root: Path,
    base_branch: str,
    include_uncommitted: bool = True,
) -> Optional[List[Path]]:
    """Get list of files changed between base branch and HEAD, plus uncommitted changes.

    Uses 'git diff base...HEAD --name-only' (three-dot syntax) to get files
    changed since the current branch diverged from base_branch. This is useful
    for PR-based incremental coverage reporting.

    When include_uncommitted is True (default), also includes:
    - Staged changes (git add)
    - Unstaged modifications
    - Untracked files

    This allows local development workflows where you want to see coverage
    for both committed branch changes AND current uncommitted work.

    Args:
        project_root: Root directory of the project.
        base_branch: Base branch to compare against (e.g., 'origin/main').
        include_uncommitted: If True, also include uncommitted local changes.
            This is useful for local development. In CI (where working tree
            is clean), this has no effect.

    Returns:
        List of changed file paths (absolute), or None if not a git repo
        or git command fails (e.g., branch doesn't exist).
    """
    if not is_git_repo(project_root):
        LOGGER.debug(f"Not a git repository: {project_root}")
        return None

    changed_files: set[Path] = set()

    try:
        # Use three-dot syntax to get files changed since branch diverged
        result = subprocess.run(
            ["git", "diff", f"{base_branch}...HEAD", "--name-only"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Git command failed (e.g., branch doesn't exist)
            stderr = result.stderr.strip()
            LOGGER.error(f"git diff against '{base_branch}' failed: {stderr}")
            return None

        for line in result.stdout.strip().split("\n"):
            if line:
                file_path = project_root / line
                if file_path.exists():
                    changed_files.add(file_path)

        committed_count = len(changed_files)
        LOGGER.debug(
            f"Found {committed_count} files changed since {base_branch}"
        )

        # Also include uncommitted local changes (for local development)
        if include_uncommitted:
            uncommitted_before = len(changed_files)

            # Staged changes
            _collect_files_from_git_command(
                ["git", "diff", "--cached", "--name-only"],
                project_root,
                changed_files,
            )

            # Unstaged modifications
            _collect_files_from_git_command(
                ["git", "diff", "--name-only"],
                project_root,
                changed_files,
            )

            # Untracked files
            _collect_files_from_git_command(
                ["git", "ls-files", "--others", "--exclude-standard"],
                project_root,
                changed_files,
            )

            uncommitted_added = len(changed_files) - uncommitted_before
            if uncommitted_added > 0:
                LOGGER.debug(
                    f"Also including {uncommitted_added} uncommitted file(s)"
                )

        return sorted(changed_files)

    except subprocess.TimeoutExpired:
        LOGGER.error(f"Git diff against '{base_branch}' timed out")
        return None
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        LOGGER.error(f"Git diff against '{base_branch}' failed: {e}")
        return None


def filter_files_by_extension(
    files: List[Path],
    extensions: Optional[List[str]] = None,
) -> List[Path]:
    """Filter files by extension.

    Args:
        files: List of file paths.
        extensions: List of extensions to include (e.g., [".py", ".js"]).
            If None, returns all files.

    Returns:
        Filtered list of files.
    """
    if extensions is None:
        return files

    # Normalize extensions to include the dot
    normalized_extensions = set()
    for ext in extensions:
        if not ext.startswith("."):
            ext = f".{ext}"
        normalized_extensions.add(ext.lower())

    return [f for f in files if f.suffix.lower() in normalized_extensions]
