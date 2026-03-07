"""Tests for git utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from lucidshark.core.git import (
    filter_files_by_extension,
    get_changed_files,
    get_changed_files_since_branch,
    get_git_root,
    is_git_repo,
)


class TestIsGitRepo:
    """Tests for is_git_repo function."""

    def test_is_git_repo_true(self, tmp_path: Path) -> None:
        """Test detection of a git repository."""
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        assert is_git_repo(tmp_path) is True

    def test_is_git_repo_false(self, tmp_path: Path) -> None:
        """Test detection of non-git directory."""
        assert is_git_repo(tmp_path) is False

    def test_is_git_repo_git_not_found(self, tmp_path: Path) -> None:
        """Test handling when git is not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert is_git_repo(tmp_path) is False


class TestGetGitRoot:
    """Tests for get_git_root function."""

    def test_get_git_root(self, tmp_path: Path) -> None:
        """Test getting git root directory."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        assert get_git_root(tmp_path) == tmp_path

    def test_get_git_root_subdir(self, tmp_path: Path) -> None:
        """Test getting git root from subdirectory."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        assert get_git_root(subdir) == tmp_path

    def test_get_git_root_not_repo(self, tmp_path: Path) -> None:
        """Test get_git_root on non-git directory."""
        assert get_git_root(tmp_path) is None


class TestGetChangedFiles:
    """Tests for get_changed_files function."""

    def test_get_changed_files_not_git_repo(self, tmp_path: Path) -> None:
        """Test returns None for non-git directory."""
        result = get_changed_files(tmp_path)
        assert result is None

    def test_get_changed_files_no_changes(self, tmp_path: Path) -> None:
        """Test returns empty list when no changes."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )
        result = get_changed_files(tmp_path)
        assert result == []

    def test_get_changed_files_untracked(self, tmp_path: Path) -> None:
        """Test detection of untracked files."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        # Create an untracked file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        result = get_changed_files(tmp_path)
        assert result is not None
        assert test_file in result

    def test_get_changed_files_staged(self, tmp_path: Path) -> None:
        """Test detection of staged files."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and stage a file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)

        result = get_changed_files(tmp_path)
        assert result is not None
        assert test_file in result

    def test_get_changed_files_modified(self, tmp_path: Path) -> None:
        """Test detection of modified files."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create, commit, then modify a file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Modify the file
        test_file.write_text("print('hello world')")

        result = get_changed_files(tmp_path)
        assert result is not None
        assert test_file in result


class TestFilterFilesByExtension:
    """Tests for filter_files_by_extension function."""

    def test_filter_no_extensions(self, tmp_path: Path) -> None:
        """Test filter returns all files when no extensions specified."""
        files = [tmp_path / "a.py", tmp_path / "b.js", tmp_path / "c.txt"]
        result = filter_files_by_extension(files, None)
        assert result == files

    def test_filter_single_extension(self, tmp_path: Path) -> None:
        """Test filter with single extension."""
        files = [tmp_path / "a.py", tmp_path / "b.js", tmp_path / "c.py"]
        result = filter_files_by_extension(files, [".py"])
        assert len(result) == 2
        assert tmp_path / "a.py" in result
        assert tmp_path / "c.py" in result

    def test_filter_multiple_extensions(self, tmp_path: Path) -> None:
        """Test filter with multiple extensions."""
        files = [tmp_path / "a.py", tmp_path / "b.js", tmp_path / "c.ts"]
        result = filter_files_by_extension(files, [".js", ".ts"])
        assert len(result) == 2
        assert tmp_path / "b.js" in result
        assert tmp_path / "c.ts" in result

    def test_filter_extension_without_dot(self, tmp_path: Path) -> None:
        """Test filter handles extensions without leading dot."""
        files = [tmp_path / "a.py", tmp_path / "b.js"]
        result = filter_files_by_extension(files, ["py"])
        assert len(result) == 1
        assert tmp_path / "a.py" in result

    def test_filter_case_insensitive(self, tmp_path: Path) -> None:
        """Test filter is case insensitive."""
        files = [tmp_path / "a.PY", tmp_path / "b.py"]
        result = filter_files_by_extension(files, [".py"])
        assert len(result) == 2


class TestGetChangedFilesSinceBranch:
    """Tests for get_changed_files_since_branch function."""

    def test_not_git_repo(self, tmp_path: Path) -> None:
        """Test returns None for non-git directory."""
        result = get_changed_files_since_branch(tmp_path, "main")
        assert result is None

    def test_branch_does_not_exist(self, tmp_path: Path) -> None:
        """Test returns None when base branch doesn't exist."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Try to compare against non-existent branch
        result = get_changed_files_since_branch(tmp_path, "nonexistent-branch")
        assert result is None

    def test_no_changes_since_branch(self, tmp_path: Path) -> None:
        """Test returns empty list when no changes since branch."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # HEAD is same as main, no changes
        result = get_changed_files_since_branch(tmp_path, "HEAD")
        assert result == []

    def test_detects_changes_on_feature_branch(self, tmp_path: Path) -> None:
        """Test detection of files changed on feature branch."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Add a new file on feature branch
        new_file = tmp_path / "new_feature.py"
        new_file.write_text("print('new feature')")
        subprocess.run(
            ["git", "add", "new_feature.py"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Compare feature branch against main
        result = get_changed_files_since_branch(tmp_path, "main")
        assert result is not None
        assert new_file in result
        assert test_file not in result  # Original file unchanged

    def test_detects_modified_files_on_feature_branch(self, tmp_path: Path) -> None:
        """Test detection of modified files on feature branch."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Modify existing file
        test_file.write_text("print('modified')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "modify file"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Compare feature branch against main
        result = get_changed_files_since_branch(tmp_path, "main")
        assert result is not None
        assert test_file in result

    def test_multiple_commits_on_feature_branch(self, tmp_path: Path) -> None:
        """Test detection with multiple commits on feature branch."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # First commit - add file1
        file1 = tmp_path / "file1.py"
        file1.write_text("print('file1')")
        subprocess.run(["git", "add", "file1.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file1"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Second commit - add file2
        file2 = tmp_path / "file2.py"
        file2.write_text("print('file2')")
        subprocess.run(["git", "add", "file2.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add file2"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Third commit - modify file1
        file1.write_text("print('file1 modified')")
        subprocess.run(["git", "add", "file1.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "modify file1"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Should detect both files changed since main
        result = get_changed_files_since_branch(tmp_path, "main")
        assert result is not None
        assert file1 in result
        assert file2 in result
        assert len(result) == 2

    def test_deleted_file_not_in_result(self, tmp_path: Path) -> None:
        """Test that deleted files are not included (they don't exist)."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit with two files on main
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("print('file1')")
        file2.write_text("print('file2')")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Delete file2 on feature branch
        subprocess.run(["git", "rm", "file2.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "delete file2"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Modify file1
        file1.write_text("print('file1 modified')")
        subprocess.run(["git", "add", "file1.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "modify file1"],
            cwd=tmp_path,
            capture_output=True,
        )

        # file2 doesn't exist anymore, so it shouldn't be in result
        result = get_changed_files_since_branch(tmp_path, "main")
        assert result is not None
        assert file1 in result
        assert file2 not in result  # Deleted file not included

    def test_git_timeout(self, tmp_path: Path) -> None:
        """Test handling of git command timeout."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=30)):
            result = get_changed_files_since_branch(tmp_path, "main")
            assert result is None

    def test_git_command_error(self, tmp_path: Path) -> None:
        """Test handling of git command error."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        with patch("subprocess.run", side_effect=subprocess.SubprocessError("git error")):
            result = get_changed_files_since_branch(tmp_path, "main")
            assert result is None

    def test_includes_uncommitted_changes_by_default(self, tmp_path: Path) -> None:
        """Test that uncommitted changes are included by default."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Add committed change on feature branch
        committed_file = tmp_path / "committed.py"
        committed_file.write_text("print('committed')")
        subprocess.run(["git", "add", "committed.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add committed file"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Add uncommitted changes
        uncommitted_file = tmp_path / "uncommitted.py"
        uncommitted_file.write_text("print('uncommitted')")

        # Default behavior includes uncommitted changes
        result = get_changed_files_since_branch(tmp_path, "main")
        assert result is not None
        assert committed_file in result
        assert uncommitted_file in result

    def test_excludes_uncommitted_when_disabled(self, tmp_path: Path) -> None:
        """Test that uncommitted changes are excluded when include_uncommitted=False."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Add committed change on feature branch
        committed_file = tmp_path / "committed.py"
        committed_file.write_text("print('committed')")
        subprocess.run(["git", "add", "committed.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add committed file"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Add uncommitted changes
        uncommitted_file = tmp_path / "uncommitted.py"
        uncommitted_file.write_text("print('uncommitted')")

        # Excluding uncommitted changes
        result = get_changed_files_since_branch(tmp_path, "main", include_uncommitted=False)
        assert result is not None
        assert committed_file in result
        assert uncommitted_file not in result

    def test_includes_staged_changes(self, tmp_path: Path) -> None:
        """Test that staged changes are included with uncommitted."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Add a staged file (not committed)
        staged_file = tmp_path / "staged.py"
        staged_file.write_text("print('staged')")
        subprocess.run(["git", "add", "staged.py"], cwd=tmp_path, capture_output=True)

        # Should include staged file
        result = get_changed_files_since_branch(tmp_path, "HEAD")
        assert result is not None
        assert staged_file in result

    def test_includes_unstaged_modifications(self, tmp_path: Path) -> None:
        """Test that unstaged modifications are included with uncommitted."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Modify the file without staging
        test_file.write_text("print('modified')")

        # Should include modified file
        result = get_changed_files_since_branch(tmp_path, "HEAD")
        assert result is not None
        assert test_file in result

    def test_combined_committed_and_uncommitted_changes(self, tmp_path: Path) -> None:
        """Test detection of both committed branch changes and uncommitted changes."""
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create initial commit on main
        initial_file = tmp_path / "initial.py"
        initial_file.write_text("print('initial')")
        subprocess.run(["git", "add", "initial.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Committed change on feature branch
        committed_file = tmp_path / "committed.py"
        committed_file.write_text("print('committed')")
        subprocess.run(["git", "add", "committed.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add committed"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Staged change (not committed)
        staged_file = tmp_path / "staged.py"
        staged_file.write_text("print('staged')")
        subprocess.run(["git", "add", "staged.py"], cwd=tmp_path, capture_output=True)

        # Unstaged modification
        committed_file.write_text("print('committed modified')")

        # Untracked file
        untracked_file = tmp_path / "untracked.py"
        untracked_file.write_text("print('untracked')")

        # Should include all types of changes
        result = get_changed_files_since_branch(tmp_path, "main")
        assert result is not None
        assert committed_file in result  # Committed + unstaged modification
        assert staged_file in result  # Staged
        assert untracked_file in result  # Untracked
        assert initial_file not in result  # Not changed
