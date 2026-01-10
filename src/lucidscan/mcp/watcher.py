"""File watcher for incremental LucidScan checks.

Watches for file changes and runs incremental quality checks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from lucidscan.config import LucidScanConfig
from lucidscan.core.logging import get_logger
from lucidscan.mcp.tools import MCPToolExecutor

LOGGER = get_logger(__name__)


class LucidScanFileWatcher:
    """Watches for file changes and runs incremental checks."""

    # Default patterns to ignore
    DEFAULT_IGNORE_PATTERNS = [
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".lucidscan",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "*.pyc",
        "*.pyo",
        ".coverage",
        "htmlcov",
        "dist",
        "build",
        "*.egg-info",
    ]

    def __init__(
        self,
        project_root: Path,
        config: LucidScanConfig,
        debounce_ms: int = 1000,
        ignore_patterns: Optional[List[str]] = None,
    ):
        """Initialize LucidScanFileWatcher.

        Args:
            project_root: Project root directory to watch.
            config: LucidScan configuration.
            debounce_ms: Debounce delay in milliseconds.
            ignore_patterns: Additional patterns to ignore.
        """
        self.project_root = project_root
        self.config = config
        self.debounce_ms = debounce_ms
        self.executor = MCPToolExecutor(project_root, config)

        # Combine default and custom ignore patterns
        self.ignore_patterns = set(self.DEFAULT_IGNORE_PATTERNS)
        if ignore_patterns:
            self.ignore_patterns.update(ignore_patterns)

        self._pending_files: Set[Path] = set()
        self._debounce_task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._observer: Optional[Observer] = None  # type: ignore[valid-type]
        self._running = False

    def on_result(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for scan results.

        Args:
            callback: Function to call with scan results.
        """
        self._callbacks.append(callback)

    async def start(self):
        """Start watching for file changes."""
        if self._running:
            LOGGER.warning("File watcher already running")
            return

        self._running = True
        handler = _FileChangeHandler(self._on_file_change)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.project_root), recursive=True)
        self._observer.start()

        LOGGER.info(f"Watching {self.project_root} for changes...")

        try:
            while self._running:
                await asyncio.sleep(0.1)
        finally:
            self.stop()

    def stop(self):
        """Stop the file watcher."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        LOGGER.info("File watcher stopped")

    def _on_file_change(self, path: Path):
        """Handle file change event.

        Args:
            path: Path to the changed file.
        """
        # Skip ignored paths
        if self._should_ignore(path):
            return

        # Skip non-files
        if not path.is_file():
            return

        LOGGER.debug(f"File changed: {path}")

        # Add to pending files
        self._pending_files.add(path)

        # Cancel existing debounce task
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        # Schedule new debounce task
        loop = asyncio.get_event_loop()
        self._debounce_task = loop.create_task(self._process_pending())

    async def _process_pending(self):
        """Process pending file changes after debounce."""
        await asyncio.sleep(self.debounce_ms / 1000)

        files = list(self._pending_files)
        self._pending_files.clear()

        if not files:
            return

        LOGGER.info(f"Processing {len(files)} changed file(s)...")

        # Get relative paths
        relative_files = []
        for f in files:
            try:
                rel = f.relative_to(self.project_root)
                relative_files.append(str(rel))
            except ValueError:
                # File not under project root
                relative_files.append(str(f))

        try:
            # Run incremental check
            result = await self.executor.scan(
                domains=["all"],
                files=relative_files,
            )

            # Add file list to result
            result["changed_files"] = relative_files

            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(result)
                except Exception as e:
                    LOGGER.error(f"Callback error: {e}")

        except Exception as e:
            LOGGER.error(f"Scan failed: {e}")
            # Notify callbacks of error
            error_result = {
                "error": str(e),
                "changed_files": relative_files,
            }
            for callback in self._callbacks:
                try:
                    callback(error_result)
                except Exception as ce:
                    LOGGER.error(f"Callback error: {ce}")

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored.

        Args:
            path: Path to check.

        Returns:
            True if path should be ignored.
        """
        path_str = str(path)
        path_parts = path.parts

        for pattern in self.ignore_patterns:
            # Check if pattern matches any path component
            if pattern in path_parts:
                return True
            # Check glob-style patterns
            if pattern.startswith("*") and path_str.endswith(pattern[1:]):
                return True
            # Check if pattern is in path string
            if pattern in path_str:
                return True

        return False


class _FileChangeHandler(FileSystemEventHandler):
    """Watchdog event handler for file changes."""

    def __init__(self, callback: Callable[[Path], None]):
        """Initialize handler.

        Args:
            callback: Function to call on file change.
        """
        self.callback = callback

    def on_modified(self, event):
        """Handle file modification."""
        if not event.is_directory:
            self.callback(Path(event.src_path))

    def on_created(self, event):
        """Handle file creation."""
        if not event.is_directory:
            self.callback(Path(event.src_path))
