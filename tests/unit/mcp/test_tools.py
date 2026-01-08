"""Unit tests for MCP tool executor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidscan.config import LucidScanConfig
from lucidscan.core.models import ScanDomain, Severity, ToolDomain, UnifiedIssue
from lucidscan.mcp.tools import MCPToolExecutor


class TestMCPToolExecutor:
    """Tests for MCPToolExecutor."""

    @pytest.fixture
    def project_root(self, tmp_path: Path) -> Path:
        """Create a temporary project root."""
        return tmp_path

    @pytest.fixture
    def config(self) -> LucidScanConfig:
        """Create a test configuration."""
        return LucidScanConfig()

    @pytest.fixture
    def executor(
        self, project_root: Path, config: LucidScanConfig
    ) -> MCPToolExecutor:
        """Create an executor instance."""
        return MCPToolExecutor(project_root, config)

    def test_domain_map_contains_all_domains(
        self, executor: MCPToolExecutor
    ) -> None:
        """Test that domain map covers all expected domains."""
        expected_domains = [
            "linting", "lint",
            "type_checking", "typecheck",
            "security", "sast",
            "sca", "iac", "container",
            "testing", "test",
            "coverage",
        ]
        for domain in expected_domains:
            assert domain in executor.DOMAIN_MAP

    def test_parse_domains_with_all(self, executor: MCPToolExecutor) -> None:
        """Test parsing 'all' domain."""
        domains = executor._parse_domains(["all"])
        # Should include both ScanDomain and ToolDomain values
        assert ToolDomain.LINTING in domains or ScanDomain.SAST in domains

    def test_parse_domains_with_specific(self, executor: MCPToolExecutor) -> None:
        """Test parsing specific domains."""
        domains = executor._parse_domains(["linting", "security"])
        assert ToolDomain.LINTING in domains
        assert ScanDomain.SAST in domains

    def test_parse_domains_ignores_unknown(self, executor: MCPToolExecutor) -> None:
        """Test that unknown domains are ignored."""
        domains = executor._parse_domains(["linting", "unknown_domain"])
        assert ToolDomain.LINTING in domains
        assert len([d for d in domains if d == ToolDomain.LINTING]) == 1

    def test_detect_language_python(self, executor: MCPToolExecutor) -> None:
        """Test Python language detection."""
        assert executor._detect_language(Path("test.py")) == "python"
        assert executor._detect_language(Path("test.pyi")) == "python"

    def test_detect_language_javascript(self, executor: MCPToolExecutor) -> None:
        """Test JavaScript language detection."""
        assert executor._detect_language(Path("test.js")) == "javascript"
        assert executor._detect_language(Path("test.jsx")) == "javascript"

    def test_detect_language_typescript(self, executor: MCPToolExecutor) -> None:
        """Test TypeScript language detection."""
        assert executor._detect_language(Path("test.ts")) == "typescript"
        assert executor._detect_language(Path("test.tsx")) == "typescript"

    def test_detect_language_terraform(self, executor: MCPToolExecutor) -> None:
        """Test Terraform language detection."""
        assert executor._detect_language(Path("main.tf")) == "terraform"

    def test_detect_language_unknown(self, executor: MCPToolExecutor) -> None:
        """Test unknown language detection."""
        assert executor._detect_language(Path("file.xyz")) == "unknown"

    def test_get_domains_for_python(self, executor: MCPToolExecutor) -> None:
        """Test domain selection for Python files."""
        domains = executor._get_domains_for_language("python")
        assert "linting" in domains
        assert "security" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains

    def test_get_domains_for_typescript(self, executor: MCPToolExecutor) -> None:
        """Test domain selection for TypeScript files."""
        domains = executor._get_domains_for_language("typescript")
        assert "linting" in domains
        assert "type_checking" in domains

    def test_get_domains_for_terraform(self, executor: MCPToolExecutor) -> None:
        """Test domain selection for Terraform files."""
        domains = executor._get_domains_for_language("terraform")
        assert "iac" in domains
        assert "linting" not in domains

    def test_build_context_with_files(
        self, executor: MCPToolExecutor, project_root: Path
    ) -> None:
        """Test context building with specific files."""
        context = executor._build_context(
            [ToolDomain.LINTING],
            files=["src/main.py", "src/utils.py"],
        )

        assert context.project_root == project_root
        assert len(context.paths) == 2
        assert context.paths[0] == project_root / "src/main.py"

    def test_build_context_without_files(
        self, executor: MCPToolExecutor, project_root: Path
    ) -> None:
        """Test context building without specific files."""
        context = executor._build_context([ToolDomain.LINTING])

        assert context.project_root == project_root
        assert len(context.paths) == 1
        assert context.paths[0] == project_root

    def test_issue_cache(self, executor: MCPToolExecutor) -> None:
        """Test that issues are cached for later retrieval."""
        issue = UnifiedIssue(
            id="cached-issue-1",
            scanner=ScanDomain.SAST,
            source_tool="test",
            severity=Severity.HIGH,
            title="Test issue",
            description="Test",
        )
        executor._issue_cache["cached-issue-1"] = issue

        assert "cached-issue-1" in executor._issue_cache
        assert executor._issue_cache["cached-issue-1"].title == "Test issue"


class TestMCPToolExecutorAsync:
    """Async tests for MCPToolExecutor."""

    @pytest.fixture
    def project_root(self, tmp_path: Path) -> Path:
        """Create a temporary project root."""
        return tmp_path

    @pytest.fixture
    def config(self) -> LucidScanConfig:
        """Create a test configuration."""
        return LucidScanConfig()

    @pytest.fixture
    def executor(
        self, project_root: Path, config: LucidScanConfig
    ) -> MCPToolExecutor:
        """Create an executor instance."""
        return MCPToolExecutor(project_root, config)

    @pytest.mark.asyncio
    async def test_check_file_not_found(self, executor: MCPToolExecutor) -> None:
        """Test checking a non-existent file."""
        result = await executor.check_file("nonexistent.py")
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_fix_instructions_not_found(
        self, executor: MCPToolExecutor
    ) -> None:
        """Test getting fix instructions for non-existent issue."""
        result = await executor.get_fix_instructions("nonexistent-id")
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_fix_instructions_found(
        self, executor: MCPToolExecutor
    ) -> None:
        """Test getting fix instructions for cached issue."""
        issue = UnifiedIssue(
            id="test-issue-1",
            scanner=ScanDomain.SAST,
            source_tool="test",
            severity=Severity.HIGH,
            title="Test vulnerability",
            description="Test description",
            file_path=Path("test.py"),
            line_start=10,
        )
        executor._issue_cache["test-issue-1"] = issue

        result = await executor.get_fix_instructions("test-issue-1")
        assert "error" not in result
        assert result["priority"] == 2  # HIGH severity
        assert result["file"] == "test.py"

    @pytest.mark.asyncio
    async def test_apply_fix_not_found(self, executor: MCPToolExecutor) -> None:
        """Test applying fix for non-existent issue."""
        result = await executor.apply_fix("nonexistent-id")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_apply_fix_non_linting(self, executor: MCPToolExecutor) -> None:
        """Test that apply_fix only works for linting issues."""
        issue = UnifiedIssue(
            id="security-issue",
            scanner=ScanDomain.SAST,
            source_tool="test",
            severity=Severity.HIGH,
            title="Security issue",
            description="Test",
        )
        executor._issue_cache["security-issue"] = issue

        result = await executor.apply_fix("security-issue")
        assert "error" in result
        assert "linting" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_status(self, executor: MCPToolExecutor) -> None:
        """Test getting status."""
        result = await executor.get_status()

        assert "project_root" in result
        assert "available_tools" in result
        assert "cached_issues" in result
        assert result["cached_issues"] == 0

    @pytest.mark.asyncio
    async def test_scan_with_empty_results(
        self, executor: MCPToolExecutor
    ) -> None:
        """Test scan that returns no issues."""
        # Mock the internal run methods to return empty lists
        with patch.object(executor, '_run_linting', return_value=[]):
            result = await executor.scan(["linting"])

            assert result["total_issues"] == 0
            assert result["blocking"] is False
