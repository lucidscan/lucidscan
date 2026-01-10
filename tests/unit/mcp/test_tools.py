"""Unit tests for MCP tool executor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidscan.config import LucidScanConfig
from lucidscan.core.domain_runner import detect_language, get_domains_for_language
from lucidscan.core.models import ScanContext, ScanDomain, Severity, ToolDomain, UnifiedIssue
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

    @pytest.mark.asyncio
    async def test_scan_with_issues(self, executor: MCPToolExecutor) -> None:
        """Test scan that returns issues."""
        mock_issue = UnifiedIssue(
            id="test-issue",
            scanner=ToolDomain.LINTING,
            source_tool="test",
            severity=Severity.HIGH,
            title="Test issue",
            description="Test description",
        )
        with patch.object(executor, '_run_linting', return_value=[mock_issue]):
            result = await executor.scan(["linting"])

            assert result["total_issues"] == 1
            assert len(executor._issue_cache) == 1

    @pytest.mark.asyncio
    async def test_scan_with_exception(self, executor: MCPToolExecutor) -> None:
        """Test scan handles exceptions gracefully."""
        with patch.object(executor, '_run_linting', side_effect=Exception("Test error")):
            result = await executor.scan(["linting"])
            # Should not raise, just return empty
            assert result["total_issues"] == 0

    @pytest.mark.asyncio
    async def test_scan_multiple_domains(self, executor: MCPToolExecutor) -> None:
        """Test scan with multiple domains."""
        with patch.object(executor, '_run_linting', return_value=[]), \
             patch.object(executor, '_run_type_checking', return_value=[]):
            result = await executor.scan(["linting", "type_checking"])
            assert result["total_issues"] == 0

    @pytest.mark.asyncio
    async def test_check_file_existing(
        self, executor: MCPToolExecutor, project_root: Path
    ) -> None:
        """Test checking an existing file."""
        # Create a test file
        test_file = project_root / "test.py"
        test_file.write_text("print('hello')")

        with patch.object(executor, 'scan', return_value={"total_issues": 0, "instructions": []}):
            result = await executor.check_file("test.py")
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_apply_fix_no_file_path(self, executor: MCPToolExecutor) -> None:
        """Test apply_fix when issue has no file path."""
        issue = UnifiedIssue(
            id="linting-issue",
            scanner=ToolDomain.LINTING,
            source_tool="ruff",
            severity=Severity.LOW,
            title="Linting issue",
            description="Test",
            file_path=None,
        )
        executor._issue_cache["linting-issue"] = issue

        result = await executor.apply_fix("linting-issue")
        assert "error" in result
        assert "file path" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_apply_fix_success(
        self, executor: MCPToolExecutor, project_root: Path
    ) -> None:
        """Test successful apply_fix."""
        test_file = project_root / "test.py"
        test_file.write_text("x=1")

        issue = UnifiedIssue(
            id="linting-issue",
            scanner=ToolDomain.LINTING,
            source_tool="ruff",
            severity=Severity.LOW,
            title="Linting issue",
            description="Test",
            file_path=test_file,
        )
        executor._issue_cache["linting-issue"] = issue

        with patch.object(executor, '_run_linting', return_value=[]):
            result = await executor.apply_fix("linting-issue")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_apply_fix_exception(
        self, executor: MCPToolExecutor, project_root: Path
    ) -> None:
        """Test apply_fix handles exceptions."""
        test_file = project_root / "test.py"
        test_file.write_text("x=1")

        issue = UnifiedIssue(
            id="linting-issue",
            scanner=ToolDomain.LINTING,
            source_tool="ruff",
            severity=Severity.LOW,
            title="Linting issue",
            description="Test",
            file_path=test_file,
        )
        executor._issue_cache["linting-issue"] = issue

        with patch.object(executor, '_run_linting', side_effect=Exception("Failed")):
            result = await executor.apply_fix("linting-issue")
            assert "error" in result


class TestMCPToolExecutorRunMethods:
    """Tests for MCPToolExecutor _run_* methods."""

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

    @pytest.fixture
    def mock_context(self, project_root: Path, config: LucidScanConfig) -> ScanContext:
        """Create a mock scan context."""
        return ScanContext(
            project_root=project_root,
            paths=[project_root],
            enabled_domains=[ToolDomain.LINTING],
            config=config,
        )

    @pytest.mark.asyncio
    async def test_run_linting_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_linting with mocked linters."""
        mock_linter = MagicMock()
        mock_linter.lint.return_value = []

        with patch('lucidscan.plugins.linters.discover_linter_plugins', return_value={'mock': lambda **k: mock_linter}):
            result = await executor._run_linting(mock_context)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_linting_with_exception(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_linting handles exceptions."""
        def create_failing_linter(**kwargs):
            linter = MagicMock()
            linter.lint.side_effect = Exception("Linter failed")
            return linter

        with patch('lucidscan.plugins.linters.discover_linter_plugins', return_value={'mock': create_failing_linter}):
            result = await executor._run_linting(mock_context)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_type_checking_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_type_checking with mocked checkers."""
        mock_checker = MagicMock()
        mock_checker.check.return_value = []

        with patch('lucidscan.plugins.type_checkers.discover_type_checker_plugins', return_value={'mock': lambda **k: mock_checker}):
            result = await executor._run_type_checking(mock_context)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_type_checking_with_exception(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_type_checking handles exceptions."""
        def create_failing_checker(**kwargs):
            checker = MagicMock()
            checker.check.side_effect = Exception("Checker failed")
            return checker

        with patch('lucidscan.plugins.type_checkers.discover_type_checker_plugins', return_value={'mock': create_failing_checker}):
            result = await executor._run_type_checking(mock_context)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_security_sast_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_security for SAST with mocked scanners."""
        mock_scanner = MagicMock()
        mock_scanner.domains = [ScanDomain.SAST]
        mock_scanner.scan.return_value = []

        with patch('lucidscan.plugins.scanners.discover_scanner_plugins', return_value={'mock': lambda **k: mock_scanner}):
            result = await executor._run_security(mock_context, ScanDomain.SAST)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_security_skips_wrong_domain(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_security skips scanners for wrong domain."""
        mock_scanner = MagicMock()
        mock_scanner.domains = [ScanDomain.SCA]  # Not SAST
        mock_scanner.scan.return_value = []

        with patch('lucidscan.plugins.scanners.discover_scanner_plugins', return_value={'mock': lambda **k: mock_scanner}):
            await executor._run_security(mock_context, ScanDomain.SAST)
            mock_scanner.scan.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_security_sca_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_security for SCA with mocked scanners."""
        mock_scanner = MagicMock()
        mock_scanner.domains = [ScanDomain.SCA]
        mock_scanner.scan.return_value = []

        with patch('lucidscan.plugins.scanners.discover_scanner_plugins', return_value={'mock': lambda **k: mock_scanner}):
            result = await executor._run_security(mock_context, ScanDomain.SCA)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_security_iac_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_security for IAC with mocked scanners."""
        mock_scanner = MagicMock()
        mock_scanner.domains = [ScanDomain.IAC]
        mock_scanner.scan.return_value = []

        with patch('lucidscan.plugins.scanners.discover_scanner_plugins', return_value={'mock': lambda **k: mock_scanner}):
            result = await executor._run_security(mock_context, ScanDomain.IAC)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_security_container_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_security for CONTAINER with mocked scanners."""
        mock_scanner = MagicMock()
        mock_scanner.domains = [ScanDomain.CONTAINER]
        mock_scanner.scan.return_value = []

        with patch('lucidscan.plugins.scanners.discover_scanner_plugins', return_value={'mock': lambda **k: mock_scanner}):
            result = await executor._run_security(mock_context, ScanDomain.CONTAINER)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_testing_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_testing with mocked runners."""
        mock_runner = MagicMock()
        mock_runner.run_tests.return_value = MagicMock(issues=[])

        with patch('lucidscan.plugins.test_runners.discover_test_runner_plugins', return_value={'mock': lambda **k: mock_runner}):
            result = await executor._run_testing(mock_context)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_testing_with_exception(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_testing handles exceptions."""
        def create_failing_runner(**kwargs):
            runner = MagicMock()
            runner.run_tests.side_effect = Exception("Runner failed")
            return runner

        with patch('lucidscan.plugins.test_runners.discover_test_runner_plugins', return_value={'mock': create_failing_runner}):
            result = await executor._run_testing(mock_context)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_coverage_with_mock(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_coverage with mocked plugins."""
        mock_plugin = MagicMock()
        mock_plugin.measure_coverage.return_value = MagicMock(issues=[])

        with patch('lucidscan.plugins.coverage.discover_coverage_plugins', return_value={'mock': lambda **k: mock_plugin}):
            result = await executor._run_coverage(mock_context)
            assert result == []

    @pytest.mark.asyncio
    async def test_run_coverage_with_exception(
        self, executor: MCPToolExecutor, mock_context: ScanContext
    ) -> None:
        """Test _run_coverage handles exceptions."""
        def create_failing_plugin(**kwargs):
            plugin = MagicMock()
            plugin.measure_coverage.side_effect = Exception("Coverage failed")
            return plugin

        with patch('lucidscan.plugins.coverage.discover_coverage_plugins', return_value={'mock': create_failing_plugin}):
            result = await executor._run_coverage(mock_context)
            assert result == []


class TestLanguageDetection:
    """Tests for language detection functions (now in domain_runner module)."""

    def test_detect_language_python(self) -> None:
        """Test Python language detection."""
        assert detect_language(Path("test.py")) == "python"
        assert detect_language(Path("test.pyi")) == "python"

    def test_detect_language_javascript(self) -> None:
        """Test JavaScript language detection."""
        assert detect_language(Path("test.js")) == "javascript"
        assert detect_language(Path("test.jsx")) == "javascript"

    def test_detect_language_typescript(self) -> None:
        """Test TypeScript language detection."""
        assert detect_language(Path("test.ts")) == "typescript"
        assert detect_language(Path("test.tsx")) == "typescript"

    def test_detect_language_terraform(self) -> None:
        """Test Terraform language detection."""
        assert detect_language(Path("main.tf")) == "terraform"

    def test_detect_language_unknown(self) -> None:
        """Test unknown language detection."""
        assert detect_language(Path("file.xyz")) == "unknown"

    def test_detect_language_java(self) -> None:
        """Test Java language detection."""
        assert detect_language(Path("Main.java")) == "java"

    def test_detect_language_go(self) -> None:
        """Test Go language detection."""
        assert detect_language(Path("main.go")) == "go"

    def test_detect_language_rust(self) -> None:
        """Test Rust language detection."""
        assert detect_language(Path("lib.rs")) == "rust"

    def test_detect_language_ruby(self) -> None:
        """Test Ruby language detection."""
        assert detect_language(Path("app.rb")) == "ruby"

    def test_detect_language_yaml(self) -> None:
        """Test YAML language detection."""
        assert detect_language(Path("config.yaml")) == "yaml"
        assert detect_language(Path("config.yml")) == "yaml"

    def test_detect_language_json(self) -> None:
        """Test JSON language detection."""
        assert detect_language(Path("package.json")) == "json"

    def test_get_domains_for_python(self) -> None:
        """Test domain selection for Python files."""
        domains = get_domains_for_language("python")
        assert "linting" in domains
        assert "security" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains

    def test_get_domains_for_typescript(self) -> None:
        """Test domain selection for TypeScript files."""
        domains = get_domains_for_language("typescript")
        assert "linting" in domains
        assert "type_checking" in domains

    def test_get_domains_for_terraform(self) -> None:
        """Test domain selection for Terraform files."""
        domains = get_domains_for_language("terraform")
        assert "iac" in domains
        assert "linting" not in domains

    def test_get_domains_for_javascript(self) -> None:
        """Test domain selection for JavaScript."""
        domains = get_domains_for_language("javascript")
        assert "linting" in domains
        assert "type_checking" in domains
        assert "testing" in domains
        assert "coverage" in domains

    def test_get_domains_for_yaml(self) -> None:
        """Test domain selection for YAML."""
        domains = get_domains_for_language("yaml")
        assert "iac" in domains
        assert "security" in domains

    def test_get_domains_for_json(self) -> None:
        """Test domain selection for JSON."""
        domains = get_domains_for_language("json")
        assert "iac" in domains
        assert "security" in domains

    def test_get_domains_for_unknown(self) -> None:
        """Test domain selection for unknown language."""
        domains = get_domains_for_language("unknown")
        assert "linting" in domains
        assert "security" in domains
