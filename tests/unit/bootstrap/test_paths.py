"""Tests for path management functionality."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


from lucidscan.bootstrap.paths import (
    get_lucidscan_home,
    LucidscanPaths,
    DEFAULT_HOME_DIR_NAME,
)


class TestGetLucidscanHome:
    """Tests for get_lucidscan_home function."""

    def test_returns_default_in_cwd(self) -> None:
        """Default is cwd/.lucidscan when no project_root is provided."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove LUCIDSCAN_HOME if it exists
            os.environ.pop("LUCIDSCAN_HOME", None)
            home = get_lucidscan_home()
            assert home == Path.cwd() / DEFAULT_HOME_DIR_NAME

    def test_returns_project_root_lucidscan(self, tmp_path: Path) -> None:
        """When project_root is provided, returns {project_root}/.lucidscan."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LUCIDSCAN_HOME", None)
            home = get_lucidscan_home(project_root=tmp_path)
            assert home == tmp_path / DEFAULT_HOME_DIR_NAME

    def test_respects_lucidscan_home_env_var(self, tmp_path: Path) -> None:
        """LUCIDSCAN_HOME env var overrides project-local path."""
        custom_home = tmp_path / "custom-lucidscan"
        with patch.dict(os.environ, {"LUCIDSCAN_HOME": str(custom_home)}):
            # Even with project_root, env var takes precedence
            home = get_lucidscan_home(project_root=tmp_path / "some_project")
            assert home == custom_home

    def test_returns_path_object(self) -> None:
        home = get_lucidscan_home()
        assert isinstance(home, Path)


class TestLucidscanPaths:
    """Tests for LucidscanPaths class."""

    def test_paths_from_home(self, tmp_path: Path) -> None:
        home = tmp_path / ".lucidscan"
        paths = LucidscanPaths(home)

        assert paths.home == home
        assert paths.bin_dir == home / "bin"
        assert paths.cache_dir == home / "cache"
        assert paths.config_dir == home / "config"
        assert paths.logs_dir == home / "logs"

    def test_plugin_bin_dir(self, tmp_path: Path) -> None:
        """Test plugin-specific binary directory structure."""
        home = tmp_path / ".lucidscan"
        paths = LucidscanPaths(home)

        # Generic plugin bin dir works for any plugin name
        assert paths.plugin_bin_dir("my_plugin", "1.0.0") == home / "bin" / "my_plugin" / "1.0.0"
        assert paths.plugin_bin_dir("another", "2.5.3") == home / "bin" / "another" / "2.5.3"

    def test_plugin_cache_dir(self, tmp_path: Path) -> None:
        """Test plugin-specific cache directory."""
        home = tmp_path / ".lucidscan"
        paths = LucidscanPaths(home)

        assert paths.plugin_cache_dir("my_plugin") == home / "cache" / "my_plugin"
        assert paths.plugin_cache_dir("another") == home / "cache" / "another"

    def test_ensure_directories_creates_all_dirs(self, tmp_path: Path) -> None:
        home = tmp_path / ".lucidscan"
        paths = LucidscanPaths(home)

        # Directories should not exist yet
        assert not paths.home.exists()

        # Create directories
        paths.ensure_directories()

        # All directories should now exist
        assert paths.home.exists()
        assert paths.bin_dir.exists()
        assert paths.cache_dir.exists()
        assert paths.config_dir.exists()
        assert paths.logs_dir.exists()

    def test_ensure_directories_is_idempotent(self, tmp_path: Path) -> None:
        home = tmp_path / ".lucidscan"
        paths = LucidscanPaths(home)

        # Call multiple times
        paths.ensure_directories()
        paths.ensure_directories()

        # Should still work
        assert paths.home.exists()

    def test_is_initialized_false_when_empty(self, tmp_path: Path) -> None:
        home = tmp_path / ".lucidscan"
        paths = LucidscanPaths(home)

        assert paths.is_initialized() is False

    def test_is_initialized_true_when_plugin_installed(self, tmp_path: Path) -> None:
        """Test that is_initialized returns True when a plugin directory exists."""
        home = tmp_path / ".lucidscan"
        paths = LucidscanPaths(home)

        paths.ensure_directories()
        # Create a plugin directory
        plugin_dir = paths.plugin_bin_dir("some_plugin", "1.0.0")
        plugin_dir.mkdir(parents=True, exist_ok=True)

        assert paths.is_initialized() is True

    def test_default_factory(self) -> None:
        """Test that default() creates paths from lucidscan home."""
        with patch("lucidscan.bootstrap.paths.get_lucidscan_home") as mock_home:
            mock_home.return_value = Path("/mock/home/.lucidscan")
            paths = LucidscanPaths.default()

            assert paths.home == Path("/mock/home/.lucidscan")
            mock_home.assert_called_once()
