"""Shared domain runner for executing scanner plugins.

This module provides shared functionality for running scanner plugins
across both CLI and MCP interfaces.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from lucidscan.config import LucidScanConfig
from lucidscan.core.logging import get_logger
from lucidscan.core.models import ScanContext, ScanDomain, UnifiedIssue

LOGGER = get_logger(__name__)

# Plugin to supported languages mapping
PLUGIN_LANGUAGES: Dict[str, List[str]] = {
    # Linters
    "ruff": ["python"],
    "eslint": ["javascript", "typescript"],
    "biome": ["javascript", "typescript"],
    "checkstyle": ["java"],
    # Type checkers
    "mypy": ["python"],
    "pyright": ["python"],
    "typescript": ["typescript"],
    # Test runners
    "pytest": ["python"],
    "jest": ["javascript", "typescript"],
    "karma": ["javascript", "typescript"],
    "playwright": ["javascript", "typescript"],
    # Coverage
    "coverage_py": ["python"],
    "istanbul": ["javascript", "typescript"],
}

# File extension to language mapping
EXTENSION_LANGUAGE: Dict[str, str] = {
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


def filter_plugins_by_language(
    plugins: Dict[str, Type[Any]],
    project_languages: List[str],
) -> Dict[str, Type[Any]]:
    """Filter plugins to only those supporting the project's languages.

    Args:
        plugins: Dict of plugin_name -> plugin_class.
        project_languages: List of languages from project config.

    Returns:
        Filtered dict of plugins that support at least one project language.
    """
    if not project_languages:
        return plugins

    filtered = {}
    for name, cls in plugins.items():
        supported_langs = PLUGIN_LANGUAGES.get(name, [])
        # Include plugin if it supports any of the project languages
        # or if the plugin has no language restrictions
        if not supported_langs or any(
            lang.lower() in [sl.lower() for sl in supported_langs]
            for lang in project_languages
        ):
            filtered[name] = cls

    return filtered


def filter_plugins_by_config(
    plugins: Dict[str, Type[Any]],
    config: LucidScanConfig,
    domain: str,
) -> Dict[str, Type[Any]]:
    """Filter plugins based on configuration.

    First tries to filter by explicitly configured tools. If none are
    configured, falls back to language-based filtering.

    Args:
        plugins: Dict of plugin_name -> plugin_class.
        config: LucidScan configuration.
        domain: Domain name (linting, type_checking, testing, coverage).

    Returns:
        Filtered dict of plugins.
    """
    configured_tools = config.pipeline.get_enabled_tool_names(domain)
    if configured_tools:
        return {
            name: cls for name, cls in plugins.items()
            if name in configured_tools
        }
    return filter_plugins_by_language(plugins, config.project.languages)


def filter_scanners_by_config(
    scanners: Dict[str, Type[Any]],
    config: LucidScanConfig,
    domain: str,
) -> Dict[str, Type[Any]]:
    """Filter scanner plugins based on configuration for a specific domain.

    Args:
        scanners: Dict of scanner_name -> scanner_class.
        config: LucidScan configuration.
        domain: Scanner domain (sast, sca, iac, container).

    Returns:
        Filtered dict of scanners.
    """
    configured_plugin = config.get_plugin_for_domain(domain)
    if configured_plugin:
        return {
            name: cls for name, cls in scanners.items()
            if name == configured_plugin
        }
    return scanners


def detect_language(path: Path) -> str:
    """Detect language from file extension.

    Args:
        path: File path.

    Returns:
        Language name or "unknown".
    """
    suffix = path.suffix.lower()
    return EXTENSION_LANGUAGE.get(suffix, "unknown")


def get_domains_for_language(language: str) -> List[str]:
    """Get appropriate domains for a language.

    Args:
        language: Language name.

    Returns:
        List of domain names.
    """
    # Default domains for most languages - use specific security domains
    # "sast" for static analysis, "sca" for dependency scanning
    domains = ["linting", "sast", "sca"]

    if language == "python":
        domains.extend(["type_checking", "testing", "coverage"])
    elif language in ("javascript", "typescript"):
        domains.extend(["type_checking", "testing", "coverage"])
    elif language == "terraform":
        domains = ["iac"]
    elif language in ("yaml", "json"):
        domains = ["iac", "sast"]

    return domains


class DomainRunner:
    """Executes plugin-based domain scans.

    Provides a unified interface for running linting, type checking,
    testing, coverage, and security scans across both CLI and MCP.
    """

    def __init__(
        self,
        project_root: Path,
        config: LucidScanConfig,
        log_level: str = "info",
    ):
        """Initialize DomainRunner.

        Args:
            project_root: Project root directory.
            config: LucidScan configuration.
            log_level: Logging level for plugin execution ("info" or "debug").
        """
        self.project_root = project_root
        self.config = config
        self._log_level = log_level

    def _log(self, level: str, message: str) -> None:
        """Log a message at the configured level."""
        if level == "info" and self._log_level == "info":
            LOGGER.info(message)
        else:
            LOGGER.debug(message)

    def run_linting(
        self,
        context: ScanContext,
        fix: bool = False,
    ) -> List[UnifiedIssue]:
        """Run linting checks.

        Args:
            context: Scan context.
            fix: Whether to apply automatic fixes.

        Returns:
            List of linting issues.
        """
        from lucidscan.plugins.linters import discover_linter_plugins

        issues: List[UnifiedIssue] = []
        linters = discover_linter_plugins()

        if not linters:
            LOGGER.warning("No linter plugins found")
            return issues

        linters = filter_plugins_by_config(linters, self.config, "linting")

        for name, plugin_class in linters.items():
            try:
                self._log("info", f"Running linter: {name}")
                plugin = plugin_class(project_root=self.project_root)

                if fix and plugin.supports_fix:
                    fix_result = plugin.fix(context)
                    self._log(
                        "info",
                        f"{name}: Fixed {fix_result.issues_fixed} issues, "
                        f"{fix_result.issues_remaining} remaining"
                    )
                    # Run again to get remaining issues
                    issues.extend(plugin.lint(context))
                else:
                    issues.extend(plugin.lint(context))

            except Exception as e:
                LOGGER.error(f"Linter {name} failed: {e}")

        return issues

    def run_type_checking(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run type checking.

        Args:
            context: Scan context.

        Returns:
            List of type checking issues.
        """
        from lucidscan.plugins.type_checkers import discover_type_checker_plugins

        issues: List[UnifiedIssue] = []
        checkers = discover_type_checker_plugins()

        if not checkers:
            LOGGER.warning("No type checker plugins found")
            return issues

        checkers = filter_plugins_by_config(checkers, self.config, "type_checking")

        for name, plugin_class in checkers.items():
            try:
                self._log("info", f"Running type checker: {name}")
                plugin = plugin_class(project_root=self.project_root)
                issues.extend(plugin.check(context))

            except Exception as e:
                LOGGER.error(f"Type checker {name} failed: {e}")

        return issues

    def run_tests(
        self, context: ScanContext, with_coverage: bool = False
    ) -> List[UnifiedIssue]:
        """Run test suite.

        Args:
            context: Scan context.
            with_coverage: If True, run tests with coverage instrumentation.

        Returns:
            List of test failure issues.
        """
        from lucidscan.plugins.test_runners import discover_test_runner_plugins

        issues: List[UnifiedIssue] = []
        runners = discover_test_runner_plugins()

        if not runners:
            LOGGER.warning("No test runner plugins found")
            return issues

        runners = filter_plugins_by_config(runners, self.config, "testing")

        for name, plugin_class in runners.items():
            try:
                coverage_msg = " (with coverage)" if with_coverage else ""
                self._log("info", f"Running test runner: {name}{coverage_msg}")
                plugin = plugin_class(project_root=self.project_root)
                result = plugin.run_tests(context, with_coverage=with_coverage)

                self._log(
                    "info",
                    f"{name}: {result.passed} passed, {result.failed} failed, "
                    f"{result.skipped} skipped, {result.errors} errors"
                )

                issues.extend(result.issues)

            except FileNotFoundError:
                LOGGER.debug(f"Test runner {name} not available")
            except Exception as e:
                LOGGER.error(f"Test runner {name} failed: {e}")

        return issues

    def run_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
        run_tests: bool = True,
    ) -> List[UnifiedIssue]:
        """Run coverage analysis.

        Args:
            context: Scan context.
            threshold: Coverage percentage threshold.
            run_tests: Whether to run tests for coverage.

        Returns:
            List of coverage issues.
        """
        from lucidscan.plugins.coverage import discover_coverage_plugins

        issues: List[UnifiedIssue] = []
        plugins = discover_coverage_plugins()

        if not plugins:
            LOGGER.warning("No coverage plugins found")
            return issues

        plugins = filter_plugins_by_config(plugins, self.config, "coverage")

        for name, plugin_class in plugins.items():
            try:
                self._log("info", f"Running coverage: {name}")
                plugin = plugin_class(project_root=self.project_root)
                result = plugin.measure_coverage(
                    context, threshold=threshold, run_tests=run_tests
                )

                status = "PASSED" if result.passed else "FAILED"

                # Build log message with test stats if available
                log_parts = [
                    f"{name}: {result.percentage:.1f}%",
                    f"({result.covered_lines}/{result.total_lines} lines)",
                    f"- threshold: {threshold}%",
                    f"- {status}",
                ]
                if result.test_stats:
                    ts = result.test_stats
                    log_parts.append(
                        f"| Tests: {ts.total} total, {ts.passed} passed, "
                        f"{ts.failed} failed, {ts.skipped} skipped"
                    )

                self._log("info", " ".join(log_parts))

                # Store the coverage result in context for MCP to access
                context.coverage_result = result

                issues.extend(result.issues)

            except FileNotFoundError:
                LOGGER.debug(f"Coverage plugin {name} not available")
            except Exception as e:
                LOGGER.error(f"Coverage plugin {name} failed: {e}")

        return issues

    def run_security(
        self,
        context: ScanContext,
        domain: ScanDomain,
    ) -> List[UnifiedIssue]:
        """Run security scanner for a specific domain.

        Args:
            context: Scan context.
            domain: Scanner domain (SAST, SCA, IAC, CONTAINER).

        Returns:
            List of security issues.
        """
        from lucidscan.plugins.scanners import discover_scanner_plugins

        issues: List[UnifiedIssue] = []
        scanners = discover_scanner_plugins()

        if not scanners:
            LOGGER.warning("No scanner plugins found")
            return issues

        # Filter by configured plugin for this domain
        domain_str = domain.value.lower()
        scanners = filter_scanners_by_config(scanners, self.config, domain_str)

        for name, scanner_class in scanners.items():
            try:
                scanner = scanner_class(project_root=self.project_root)
                if domain in scanner.domains:
                    self._log("info", f"Running {domain_str} scanner: {name}")
                    result = scanner.scan(context)
                    issues.extend(result)

            except Exception as e:
                LOGGER.error(f"Scanner {name} failed: {e}")

        return issues


def check_severity_threshold(
    issues: List[UnifiedIssue],
    threshold: Optional[str],
) -> bool:
    """Check if any issues meet or exceed the severity threshold.

    Args:
        issues: List of issues to check.
        threshold: Severity threshold ('critical', 'high', 'medium', 'low').

    Returns:
        True if issues at or above threshold exist, False otherwise.
    """
    if not threshold or not issues:
        return False

    threshold_order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    threshold_level = threshold_order.get(threshold.lower(), 99)

    for issue in issues:
        issue_level = threshold_order.get(issue.severity.value, 99)
        if issue_level <= threshold_level:
            return True

    return False
