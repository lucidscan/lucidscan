"""MCP tool executor for LucidScan operations.

Executes LucidScan scan operations and formats results for AI agents.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidscan.config import LucidScanConfig
from lucidscan.core.domain_runner import (
    DomainRunner,
    detect_language,
    get_domains_for_language,
)
from lucidscan.core.logging import get_logger
from lucidscan.core.models import DomainType, ScanContext, ScanDomain, ToolDomain, UnifiedIssue
from lucidscan.mcp.formatter import InstructionFormatter

LOGGER = get_logger(__name__)


class MCPToolExecutor:
    """Executes LucidScan operations for MCP tools."""

    # Map string domain names to the appropriate enum
    # ScanDomain for scanner plugins, ToolDomain for other tools
    DOMAIN_MAP: Dict[str, DomainType] = {
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
        # Use DomainRunner with debug logging for MCP (less verbose)
        self._runner = DomainRunner(project_root, config, log_level="debug")

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
            tasks.append(self._run_security(context, ScanDomain.SAST))
        if ScanDomain.SCA in enabled_domains:
            tasks.append(self._run_security(context, ScanDomain.SCA))
        if ScanDomain.IAC in enabled_domains:
            tasks.append(self._run_security(context, ScanDomain.IAC))
        if ScanDomain.CONTAINER in enabled_domains:
            tasks.append(self._run_security(context, ScanDomain.CONTAINER))
        if ToolDomain.TESTING in enabled_domains:
            tasks.append(self._run_testing(context))
        if ToolDomain.COVERAGE in enabled_domains:
            tasks.append(self._run_coverage(context))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    LOGGER.warning(f"Scan task failed: {result}")
                elif result is not None:
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
        language = detect_language(path)
        domains = get_domains_for_language(language)

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
            "enabled_domains": self.config.get_enabled_domains(),
            "cached_issues": len(self._issue_cache),
        }

    def _parse_domains(self, domains: List[str]) -> List[DomainType]:
        """Parse domain strings to domain enums.

        Args:
            domains: List of domain names.

        Returns:
            List of domain enums (ToolDomain or ScanDomain).
        """
        if "all" in domains:
            result: List[DomainType] = list(ToolDomain)
            return result

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
        domains: List[DomainType],
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
            config=self.config,
        )

    async def _run_linting(
        self,
        context: ScanContext,
        fix: bool = False,
    ) -> List[UnifiedIssue]:
        """Run linting checks asynchronously.

        Args:
            context: Scan context.
            fix: Whether to apply fixes.

        Returns:
            List of linting issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_linting, context, fix
        )

    async def _run_type_checking(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run type checking asynchronously.

        Args:
            context: Scan context.

        Returns:
            List of type checking issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_type_checking, context
        )

    async def _run_testing(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run test suite asynchronously.

        Args:
            context: Scan context.

        Returns:
            List of test failure issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_tests, context
        )

    async def _run_coverage(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run coverage analysis asynchronously.

        Args:
            context: Scan context.

        Returns:
            List of coverage issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_coverage, context
        )

    async def _run_security(
        self,
        context: ScanContext,
        domain: ScanDomain,
    ) -> List[UnifiedIssue]:
        """Run security scanner asynchronously.

        Args:
            context: Scan context.
            domain: Scanner domain (SAST, SCA, IAC, CONTAINER).

        Returns:
            List of security issues.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._runner.run_security, context, domain
        )
