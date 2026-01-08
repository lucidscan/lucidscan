"""Unit tests for MCP file watcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucidscan.config import LucidScanConfig
from lucidscan.mcp.watcher import LucidScanFileWatcher


class TestLucidScanFileWatcher:
    """Tests for LucidScanFileWatcher."""

    @pytest.fixture
    def project_root(self, tmp_path: Path) -> Path:
        """Create a temporary project root."""
        return tmp_path

    @pytest.fixture
    def config(self) -> LucidScanConfig:
        """Create a test configuration."""
        return LucidScanConfig()

    @pytest.fixture
    def watcher(
        self, project_root: Path, config: LucidScanConfig
    ) -> LucidScanFileWatcher:
        """Create a watcher instance."""
        return LucidScanFileWatcher(project_root, config)

    def test_watcher_initialization(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test watcher initialization."""
        assert watcher.project_root == project_root
        assert watcher.debounce_ms == 1000
        assert len(watcher._pending_files) == 0
        assert len(watcher._callbacks) == 0

    def test_watcher_custom_debounce(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test watcher with custom debounce."""
        watcher = LucidScanFileWatcher(
            project_root, config, debounce_ms=500
        )
        assert watcher.debounce_ms == 500

    def test_on_result_callback(self, watcher: LucidScanFileWatcher) -> None:
        """Test registering callbacks."""
        callback = MagicMock()
        watcher.on_result(callback)

        assert len(watcher._callbacks) == 1
        assert callback in watcher._callbacks

    def test_on_result_multiple_callbacks(
        self, watcher: LucidScanFileWatcher
    ) -> None:
        """Test registering multiple callbacks."""
        callback1 = MagicMock()
        callback2 = MagicMock()
        watcher.on_result(callback1)
        watcher.on_result(callback2)

        assert len(watcher._callbacks) == 2

    def test_default_ignore_patterns(
        self, watcher: LucidScanFileWatcher
    ) -> None:
        """Test default ignore patterns."""
        assert ".git" in watcher.ignore_patterns
        assert "__pycache__" in watcher.ignore_patterns
        assert "node_modules" in watcher.ignore_patterns
        assert ".venv" in watcher.ignore_patterns
        assert ".lucidscan" in watcher.ignore_patterns

    def test_custom_ignore_patterns(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test custom ignore patterns."""
        watcher = LucidScanFileWatcher(
            project_root,
            config,
            ignore_patterns=["custom_dir", "*.log"],
        )

        assert "custom_dir" in watcher.ignore_patterns
        assert "*.log" in watcher.ignore_patterns
        # Default patterns should still be present
        assert ".git" in watcher.ignore_patterns

    def test_should_ignore_git(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test ignoring .git directory."""
        git_file = project_root / ".git" / "config"
        assert watcher._should_ignore(git_file) is True

    def test_should_ignore_pycache(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test ignoring __pycache__ directory."""
        cache_file = project_root / "__pycache__" / "module.cpython-310.pyc"
        assert watcher._should_ignore(cache_file) is True

    def test_should_ignore_node_modules(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test ignoring node_modules directory."""
        node_file = project_root / "node_modules" / "package" / "index.js"
        assert watcher._should_ignore(node_file) is True

    def test_should_ignore_pyc_files(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test ignoring .pyc files."""
        pyc_file = project_root / "src" / "module.pyc"
        assert watcher._should_ignore(pyc_file) is True

    def test_should_not_ignore_regular_files(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test that regular files are not ignored."""
        py_file = project_root / "src" / "main.py"
        assert watcher._should_ignore(py_file) is False

        js_file = project_root / "app" / "index.js"
        assert watcher._should_ignore(js_file) is False

    def test_should_not_ignore_nested_regular_files(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test that nested regular files are not ignored."""
        nested_file = project_root / "src" / "components" / "Button.tsx"
        assert watcher._should_ignore(nested_file) is False

    def test_not_running_initially(
        self, watcher: LucidScanFileWatcher
    ) -> None:
        """Test that watcher is not running initially."""
        assert watcher._running is False

    def test_stop_when_not_running(
        self, watcher: LucidScanFileWatcher
    ) -> None:
        """Test stopping when not running doesn't error."""
        watcher.stop()  # Should not raise
        assert watcher._running is False


class TestFileWatcherAsync:
    """Async tests for file watcher."""

    @pytest.fixture
    def project_root(self, tmp_path: Path) -> Path:
        """Create a temporary project root."""
        return tmp_path

    @pytest.fixture
    def config(self) -> LucidScanConfig:
        """Create a test configuration."""
        return LucidScanConfig()

    @pytest.fixture
    def watcher(
        self, project_root: Path, config: LucidScanConfig
    ) -> LucidScanFileWatcher:
        """Create a watcher instance."""
        return LucidScanFileWatcher(project_root, config, debounce_ms=10)

    @pytest.mark.asyncio
    async def test_process_pending_empty(
        self, watcher: LucidScanFileWatcher
    ) -> None:
        """Test processing with no pending files."""
        # Should complete without error
        await watcher._process_pending()
        assert len(watcher._pending_files) == 0

    @pytest.mark.asyncio
    async def test_on_file_change_ignores_directories(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test that directories are ignored in file changes."""
        dir_path = project_root / "src"
        dir_path.mkdir()

        watcher._on_file_change(dir_path)
        assert len(watcher._pending_files) == 0

    @pytest.mark.asyncio
    async def test_on_file_change_ignores_excluded(
        self, watcher: LucidScanFileWatcher, project_root: Path
    ) -> None:
        """Test that excluded files are ignored."""
        git_dir = project_root / ".git"
        git_dir.mkdir()
        git_file = git_dir / "config"
        git_file.touch()

        watcher._on_file_change(git_file)
        assert len(watcher._pending_files) == 0
