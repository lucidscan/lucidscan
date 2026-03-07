"""Unit tests for path utilities."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.paths import determine_scan_paths, resolve_node_bin


class TestDetermineScanPaths:
    """Tests for determine_scan_paths function."""

    def test_all_files_true_returns_project_root(self) -> None:
        """Test that all_files=True returns the project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = determine_scan_paths(project_root, all_files=True)

            assert result == [project_root]

    def test_specific_files_resolved_correctly(self) -> None:
        """Test that specific files are resolved to absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            test_file = project_root / "test.py"
            test_file.touch()

            result = determine_scan_paths(project_root, files=["test.py"])

            assert len(result) == 1
            assert result[0] == test_file

    def test_nonexistent_file_logs_warning(self) -> None:
        """Test that nonexistent files are skipped with a warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            existing_file = project_root / "exists.py"
            existing_file.touch()

            # Include both existing and nonexistent files
            result = determine_scan_paths(
                project_root,
                files=["exists.py", "nonexistent.py"]
            )

            # Only the existing file should be returned
            assert len(result) == 1
            assert result[0] == existing_file

    def test_all_files_nonexistent_returns_empty_list(self) -> None:
        """Test empty list returned when all specified files don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = determine_scan_paths(
                project_root,
                files=["nonexistent1.py", "nonexistent2.py"]
            )

            # Should return empty list (consistent with no changed files behavior)
            assert result == []

    def test_no_changed_files_returns_empty_list(self) -> None:
        """Test that no changed files returns empty list (not project root)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Mock get_changed_files to return empty list (git repo with no changes)
            with patch("lucidshark.core.paths.get_changed_files", return_value=[]):
                result = determine_scan_paths(project_root)

            assert result == []

    def test_git_unavailable_falls_back_to_project_root(self) -> None:
        """Test fallback to project root when git is unavailable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Mock get_changed_files to return None (git unavailable)
            with patch("lucidshark.core.paths.get_changed_files", return_value=None):
                result = determine_scan_paths(project_root)

            assert result == [project_root]

    def test_changed_files_returned_when_present(self) -> None:
        """Test that changed files are returned when detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            changed_file = project_root / "changed.py"
            changed_file.touch()

            with patch(
                "lucidshark.core.paths.get_changed_files",
                return_value=[changed_file]
            ):
                result = determine_scan_paths(project_root)

            assert result == [changed_file]


class TestResolveNodeBin:
    """Tests for resolve_node_bin function."""

    def test_finds_binary_in_node_modules(self) -> None:
        """Test finding a binary in node_modules/.bin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            bin_dir = project_root / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True)
            eslint_bin = bin_dir / "eslint"
            eslint_bin.touch()

            result = resolve_node_bin(project_root, "eslint")

            assert result == eslint_bin

    def test_returns_none_when_binary_not_found(self) -> None:
        """Test that None is returned when binary doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Don't create node_modules/.bin

            result = resolve_node_bin(project_root, "eslint")

            assert result is None

    def test_returns_none_when_node_modules_missing(self) -> None:
        """Test that None is returned when node_modules doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = resolve_node_bin(project_root, "eslint")

            assert result is None

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_prefers_cmd_on_windows(self) -> None:
        """Test that .cmd files are preferred on Windows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            bin_dir = project_root / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True)

            # Create both plain and .cmd versions
            plain_bin = bin_dir / "eslint"
            cmd_bin = bin_dir / "eslint.cmd"
            plain_bin.touch()
            cmd_bin.touch()

            result = resolve_node_bin(project_root, "eslint")

            # On Windows, should prefer .cmd
            assert result == cmd_bin

    def test_windows_cmd_resolution_mocked(self) -> None:
        """Test Windows .cmd resolution with platform mocking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            bin_dir = project_root / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True)
            cmd_bin = bin_dir / "eslint.cmd"
            cmd_bin.touch()

            # Mock sys.platform to simulate Windows
            with patch.object(sys, "platform", "win32"):
                result = resolve_node_bin(project_root, "eslint")

            assert result == cmd_bin
