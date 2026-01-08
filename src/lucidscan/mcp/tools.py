"""MCP tool executor for LucidScan operations.

Executes LucidScan scan operations and formats results for AI agents.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidscan.config import LucidScanConfig
from lucidscan.core.logging import get_logger
from lucidscan.core.models import ScanContext, ScanDomain, ToolDomain, UnifiedIssue
from lucidscan.mcp.formatter import InstructionFormatter

LOGGER = get_logger(__name__)


class MCPToolExecutor:
    """Executes LucidScan operations for MCP tools."""

    # Map string domain names to the appropriate enum
    # ScanDomain for scanner plugins, ToolDomain for other tools
    DOMAIN_MAP = {
        "linting": ToolDomain.LINTING,
        "lint": ToolDomain.LINTING,
        "type_checking": ToolDomain.TYPE_CHECKING,
        "typecheck": ToolDomain.TYPE_CHECKING,
        "security": ScanDomain.SAST,
        "sast": ScanDomain.SAST,
        "sca": ScanDomain.SCA,
        "iac": ScanDomain.IAC,
        "container": ScanDomain.CONTAINER,
        "testing": ToolDomain.TESTING,
        "test": ToolDomain.TESTING,
        "coverage": ToolDomain.COVERAGE,
    }

    # File extension to language mapping
    EXTENSION_LANGUAGE = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".tf": "terraform",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
    }

    def __init__(self, project_root: Path, config: LucidScanConfig):
        """Initialize MCPToolExecutor.

        Args:
            project_root: Project root directory.
            config: LucidScan configuration.
        """
        self.project_root = project_root
        self.config = config
        self.instruction_formatter = InstructionFormatter()
        self._issue_cache: Dict[str, UnifiedIssue] = {}

    async def scan(
        self,
        domains: List[str],
        files: Optional[List[str]] = None,
        fix: bool = False,
    ) -> Dict[str, Any]:
        """Execute scan and return AI-formatted results.

        Args:
            domains: List of domain names to scan (e.g., ["linting", "security"]).
            files: Optional list of specific files to scan.
            fix: Whether to apply auto-fixes (linting only).

        Returns:
            Structured scan result with AI instructions.
        """
        # Convert domain strings to ToolDomain enums
        enabled_domains = self._parse_domains(domains)

        # Build context
        context = self._build_context(enabled_domains, files)

        # Run scans in parallel for different domains
        all_issues: List[UnifiedIssue] = []

        tasks = []
        if ToolDomain.LINTING in enabled_domains:
            tasks.append(self._run_linting(context, fix))
        if ToolDomain.TYPE_CHECKING in enabled_domains:
            tasks.append(self._run_type_checking(context))
        if ScanDomain.SAST in enabled_domains:
            tasks.append(self._run_security(context))
        if ScanDomain.SCA in enabled_domains:
            tasks.append(self._run_sca(context))
        if ScanDomain.IAC in enabled_domains:
            tasks.append(self._run_iac(context))
        if ScanDomain.CONTAINER in enabled_domains:
            tasks.append(self._run_container(context))
        if ToolDomain.TESTING in enabled_domains:
            tasks.append(self._run_testing(context))
        if ToolDomain.COVERAGE in enabled_domains:
            tasks.append(self._run_coverage(context))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    LOGGER.warning(f"Scan task failed: {result}")
                elif result:
                    all_issues.extend(result)

        # Cache issues for later reference
        for issue in all_issues:
            self._issue_cache[issue.id] = issue

        # Format as AI instructions
        return self.instruction_formatter.format_scan_result(all_issues)

    async def check_file(self, file_path: str) -> Dict[str, Any]:
        """Check a single file.

        Args:
            file_path: Path to the file (relative to project root).

        Returns:
            Structured scan result for the file.
        """
        path = self.project_root / file_path
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        # Detect language and run appropriate checks
        language = self._detect_language(path)
        domains = self._get_domains_for_language(language)

        return await self.scan(domains, files=[file_path])

    async def get_fix_instructions(self, issue_id: str) -> Dict[str, Any]:
        """Get detailed fix instructions for an issue.

        Args:
            issue_id: The issue identifier.

        Returns:
            Detailed fix instructions.
        """
        issue = self._issue_cache.get(issue_id)
        if not issue:
            return {"error": f"Issue not found: {issue_id}"}

        return self.instruction_formatter.format_single_issue(issue, detailed=True)

    async def apply_fix(self, issue_id: str) -> Dict[str, Any]:
        """Apply auto-fix for an issue.

        Args:
            issue_id: The issue identifier to fix.

        Returns:
            Result of the fix operation.
        """
        issue = self._issue_cache.get(issue_id)
        if not issue:
            return {"error": f"Issue not found: {issue_id}"}

        # Only linting issues are auto-fixable
        if issue.scanner != ToolDomain.LINTING:
            return {
                "error": "Only linting issues support auto-fix",
                "issue_type": issue.scanner.value if issue.scanner else "unknown",
            }

        # Run linter in fix mode for the specific file
        if not issue.file_path:
            return {"error": "Issue has no file path for fixing"}

        try:
            context = self._build_context(
                [ToolDomain.LINTING],
                files=[str(issue.file_path)],
            )
            await self._run_linting(context, fix=True)
            return {
                "success": True,
                "message": f"Applied fix for {issue_id}",
                "file": str(issue.file_path),
            }
        except Exception as e:
            return {"error": f"Failed to apply fix: {e}"}

    async def get_status(self) -> Dict[str, Any]:
        """Get current LucidScan status and configuration.

        Returns:
            Status information.
        """
        from lucidscan.plugins.scanners import discover_scanner_plugins
        from lucidscan.plugins.linters import discover_linter_plugins
        from lucidscan.plugins.type_checkers import discover_type_checker_plugins

        scanners = discover_scanner_plugins()
        linters = discover_linter_plugins()
        type_checkers = discover_type_checker_plugins()

        return {
            "project_root": str(self.project_root),
            "available_tools": {
                "scanners": list(scanners.keys()),
                "linters": list(linters.keys()),
                "type_checkers": list(type_checkers.keys()),
            },
            "enabled_domains": [d.value for d in self.config.get_enabled_domains()],
            "cached_issues": len(self._issue_cache),
        }

    def _parse_domains(self, domains: List[str]) -> List[ToolDomain]:
        """Parse domain strings to ToolDomain enums.

        Args:
            domains: List of domain names.

        Returns:
            List of ToolDomain enums.
        """
        if "all" in domains:
            return list(ToolDomain)

        result = []
        for domain in domains:
            domain_lower = domain.lower()
            if domain_lower in self.DOMAIN_MAP:
                result.append(self.DOMAIN_MAP[domain_lower])
            else:
                LOGGER.warning(f"Unknown domain: {domain}")

        return result

    def _build_context(
        self,
        domains: List[ToolDomain],
        files: Optional[List[str]] = None,
    ) -> ScanContext:
        """Build scan context.

        Args:
            domains: Enabled domains.
            files: Optional specific files to scan.

        Returns:
            ScanContext instance.
        """
        if files:
            paths = [self.project_root / f for f in files]
        else:
            paths = [self.project_root]

        return ScanContext(
            project_root=self.project_root,
            paths=paths,
            enabled_domains=domains,
        )

    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension.

        Args:
            path: File path.

        Returns:
            Language name or "unknown".
        """
        suffix = path.suffix.lower()
        return self.EXTENSION_LANGUAGE.get(suffix, "unknown")

    def _get_domains_for_language(self, language: str) -> List[str]:
        """Get appropriate domains for a language.

        Args:
            language: Language name.

        Returns:
            List of domain names.
        """
        # Default domains for all languages
        domains = ["linting", "security"]

        if language == "python":
            domains.extend(["type_checking", "testing", "coverage"])
        elif language in ("javascript", "typescript"):
            domains.extend(["type_checking", "testing", "coverage"])
        elif language == "terraform":
            domains = ["iac"]
        elif language in ("yaml", "json"):
            domains = ["iac", "security"]

        return domains

    async def _run_linting(
        self,
        context: ScanContext,
        fix: bool = False,
    ) -> List[UnifiedIssue]:
        """Run linting checks.

        Args:
            context: Scan context.
            fix: Whether to apply fixes.

        Returns:
            List of linting issues.
        """
        from lucidscan.plugins.linters import discover_linter_plugins

        issues = []
        linters = discover_linter_plugins()

        for name, linter_class in linters.items():
            try:
                linter = linter_class(project_root=self.project_root)
                result = linter.lint(context, fix=fix)
                issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Linter {name} failed: {e}")

        return issues

    async def _run_type_checking(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run type checking.

        Args:
            context: Scan context.

        Returns:
            List of type checking issues.
        """
        from lucidscan.plugins.type_checkers import discover_type_checker_plugins

        issues = []
        checkers = discover_type_checker_plugins()

        for name, checker_class in checkers.items():
            try:
                checker = checker_class(project_root=self.project_root)
                result = checker.check(context)
                issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Type checker {name} failed: {e}")

        return issues

    async def _run_security(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run security (SAST) checks.

        Args:
            context: Scan context.

        Returns:
            List of security issues.
        """
        from lucidscan.plugins.scanners import discover_scanner_plugins

        issues = []
        scanners = discover_scanner_plugins()

        # Only use scanners that support SAST
        for name, scanner_class in scanners.items():
            try:
                scanner = scanner_class()
                if ScanDomain.SAST in scanner.domains:
                    result = scanner.scan(context)
                    issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Scanner {name} failed: {e}")

        return issues

    async def _run_sca(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run SCA (dependency) checks.

        Args:
            context: Scan context.

        Returns:
            List of SCA issues.
        """
        from lucidscan.plugins.scanners import discover_scanner_plugins

        issues = []
        scanners = discover_scanner_plugins()

        for name, scanner_class in scanners.items():
            try:
                scanner = scanner_class()
                if ScanDomain.SCA in scanner.domains:
                    result = scanner.scan(context)
                    issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Scanner {name} failed: {e}")

        return issues

    async def _run_iac(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run IaC checks.

        Args:
            context: Scan context.

        Returns:
            List of IaC issues.
        """
        from lucidscan.plugins.scanners import discover_scanner_plugins

        issues = []
        scanners = discover_scanner_plugins()

        for name, scanner_class in scanners.items():
            try:
                scanner = scanner_class()
                if ScanDomain.IAC in scanner.domains:
                    result = scanner.scan(context)
                    issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Scanner {name} failed: {e}")

        return issues

    async def _run_container(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run container vulnerability checks.

        Args:
            context: Scan context.

        Returns:
            List of container vulnerability issues.
        """
        from lucidscan.plugins.scanners import discover_scanner_plugins

        issues = []
        scanners = discover_scanner_plugins()

        for name, scanner_class in scanners.items():
            try:
                scanner = scanner_class()
                if ScanDomain.CONTAINER in scanner.domains:
                    result = scanner.scan(context)
                    issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Scanner {name} failed: {e}")

        return issues

    async def _run_testing(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run test suite.

        Args:
            context: Scan context.

        Returns:
            List of test failure issues.
        """
        from lucidscan.plugins.test_runners import discover_test_runner_plugins

        issues = []
        runners = discover_test_runner_plugins()

        for name, runner_class in runners.items():
            try:
                runner = runner_class(project_root=self.project_root)
                result = runner.run_tests(context)
                issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Test runner {name} failed: {e}")

        return issues

    async def _run_coverage(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run coverage analysis.

        Args:
            context: Scan context.

        Returns:
            List of coverage issues.
        """
        from lucidscan.plugins.coverage import discover_coverage_plugins

        issues = []
        plugins = discover_coverage_plugins()

        for name, plugin_class in plugins.items():
            try:
                plugin = plugin_class(project_root=self.project_root)
                result = plugin.measure(context)
                issues.extend(result.issues)
            except Exception as e:
                LOGGER.debug(f"Coverage plugin {name} failed: {e}")

        return issues
