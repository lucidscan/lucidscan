"""Integration tests for MCP server and tools."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lucidscan.config import LucidScanConfig
from lucidscan.mcp.server import LucidScanMCPServer
from lucidscan.mcp.tools import MCPToolExecutor
from lucidscan.mcp.watcher import LucidScanFileWatcher


class TestMCPServerIntegration:
    """Integration tests for MCP server."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Create a temporary project root with some files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create a Python file
            src_dir = root / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("print('hello')\n")

            yield root

    @pytest.fixture
    def config(self) -> LucidScanConfig:
        """Create test configuration."""
        return LucidScanConfig()

    def test_mcp_server_initialization(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test MCP server initialization."""
        server = LucidScanMCPServer(project_root, config)

        assert server.project_root == project_root
        assert server.config == config
        assert server.executor is not None
        assert server.server is not None

    def test_mcp_tool_executor_integration(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test tool executor with real project structure."""
        executor = MCPToolExecutor(project_root, config)

        # Test status - should work without any scans
        import asyncio
        result = asyncio.run(executor.get_status())

        assert result["project_root"] == str(project_root)
        assert "available_tools" in result
        assert "scanners" in result["available_tools"]
        assert "linters" in result["available_tools"]

    @pytest.mark.asyncio
    async def test_check_file_with_real_file(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test checking a real file."""
        executor = MCPToolExecutor(project_root, config)

        # Check the Python file we created
        result = await executor.check_file("src/main.py")

        # Should not have error (file exists)
        assert "error" not in result or "not found" not in result.get("error", "")
        # Should return formatted result
        assert "total_issues" in result

    @pytest.mark.asyncio
    async def test_scan_empty_project(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test scanning a project with minimal files."""
        executor = MCPToolExecutor(project_root, config)

        result = await executor.scan(["linting"])

        # Should return valid result structure
        assert "total_issues" in result
        assert "blocking" in result
        assert "instructions" in result
        assert isinstance(result["instructions"], list)


class TestFileWatcherIntegration:
    """Integration tests for file watcher."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Create a temporary project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create source directory
            src_dir = root / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("x = 1\n")

            yield root

    @pytest.fixture
    def config(self) -> LucidScanConfig:
        """Create test configuration."""
        return LucidScanConfig()

    def test_watcher_initialization_with_real_project(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test watcher initialization with real project."""
        watcher = LucidScanFileWatcher(
            project_root, config, debounce_ms=100
        )

        assert watcher.project_root == project_root
        assert watcher.debounce_ms == 100

    def test_watcher_ignore_patterns(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test watcher correctly ignores patterns."""
        watcher = LucidScanFileWatcher(project_root, config)

        # Create directories that should be ignored
        git_dir = project_root / ".git"
        git_dir.mkdir()
        (git_dir / "config").touch()

        cache_dir = project_root / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "main.cpython-310.pyc").touch()

        # Test that these paths are ignored
        assert watcher._should_ignore(git_dir / "config") is True
        assert watcher._should_ignore(cache_dir / "main.cpython-310.pyc") is True

        # Test that source files are not ignored
        assert watcher._should_ignore(project_root / "src" / "main.py") is False

    def test_watcher_callback_registration(
        self, project_root: Path, config: LucidScanConfig
    ) -> None:
        """Test callback registration."""
        watcher = LucidScanFileWatcher(project_root, config)

        results = []
        def callback(result):
            results.append(result)

        watcher.on_result(callback)

        assert len(watcher._callbacks) == 1


class TestMCPEndToEnd:
    """End-to-end tests for MCP workflow."""

    @pytest.fixture
    def project_with_issues(self) -> Path:
        """Create a project with intentional issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create Python file with type issue
            src_dir = root / "src"
            src_dir.mkdir()
            (src_dir / "app.py").write_text('''
def greet(name: str) -> str:
    return "Hello, " + name

# Intentional issue: unused variable
unused_var = 42
''')

            yield root

    @pytest.fixture
    def config(self) -> LucidScanConfig:
        """Create test configuration."""
        return LucidScanConfig()

    @pytest.mark.asyncio
    async def test_scan_and_format_workflow(
        self, project_with_issues: Path, config: LucidScanConfig
    ) -> None:
        """Test complete scan and format workflow."""
        executor = MCPToolExecutor(project_with_issues, config)

        # Run scan
        result = await executor.scan(["linting"])

        # Verify result structure
        assert "total_issues" in result
        assert "blocking" in result
        assert "summary" in result
        assert "instructions" in result

        # Each instruction should have required fields
        for instruction in result["instructions"]:
            assert "priority" in instruction
            assert "action" in instruction
            assert "summary" in instruction
            assert "file" in instruction
            assert "fix_steps" in instruction

    @pytest.mark.asyncio
    async def test_check_specific_file(
        self, project_with_issues: Path, config: LucidScanConfig
    ) -> None:
        """Test checking a specific file."""
        executor = MCPToolExecutor(project_with_issues, config)

        result = await executor.check_file("src/app.py")

        # Should have scanned the file
        assert "total_issues" in result
        assert isinstance(result["instructions"], list)

    @pytest.mark.asyncio
    async def test_issue_caching_and_retrieval(
        self, project_with_issues: Path, config: LucidScanConfig
    ) -> None:
        """Test that issues are cached and can be retrieved."""
        executor = MCPToolExecutor(project_with_issues, config)

        # Run scan to populate cache
        result = await executor.scan(["linting"])

        if result["total_issues"] > 0:
            # Get issue ID from first instruction
            issue_id = result["instructions"][0]["issue_id"]

            # Should be able to get detailed instructions
            detail = await executor.get_fix_instructions(issue_id)
            assert "error" not in detail
            assert detail["issue_id"] == issue_id
