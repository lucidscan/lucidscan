"""Scan command implementation."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path
from typing import List, Optional

from lucidscan.cli.commands import Command
from lucidscan.cli.config_bridge import ConfigBridge
from lucidscan.cli.exit_codes import (
    EXIT_ISSUES_FOUND,
    EXIT_SCANNER_ERROR,
    EXIT_SUCCESS,
)
from lucidscan.config.ignore import load_ignore_patterns
from lucidscan.config.models import LucidScanConfig
from lucidscan.core.logging import get_logger
from lucidscan.core.models import ScanContext, ScanResult, UnifiedIssue
from lucidscan.pipeline import PipelineConfig, PipelineExecutor
from lucidscan.plugins.reporters import get_reporter_plugin

LOGGER = get_logger(__name__)

# Plugin to supported languages mapping
PLUGIN_LANGUAGES = {
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
    # Coverage
    "coverage_py": ["python"],
    "istanbul": ["javascript", "typescript"],
}


def _filter_plugins_by_language(
    plugins: dict, project_languages: List[str]
) -> dict:
    """Filter plugins to only those supporting the project's languages.

    Args:
        plugins: Dict of plugin_name -> plugin_class.
        project_languages: List of languages from project config.

    Returns:
        Filtered dict of plugins that support at least one project language.
    """
    if not project_languages:
        # No language filter if not specified
        return plugins

    filtered = {}
    for name, cls in plugins.items():
        supported_langs = PLUGIN_LANGUAGES.get(name, [])
        # Include plugin if it supports any of the project languages
        if not supported_langs or any(
            lang.lower() in [l.lower() for l in supported_langs]
            for lang in project_languages
        ):
            filtered[name]= cls

    return filtered


class ScanCommand(Command):
    """Executes security scanning."""

    def __init__(self, version: str):
        """Initialize ScanCommand.

        Args:
            version: Current lucidscan version string.
        """
        self._version = version

    @property
    def name(self) -> str:
        """Command identifier."""
        return "scan"

    def execute(self, args: Namespace, config: LucidScanConfig | None = None) -> int:
        """Execute the scan command.

        Args:
            args: Parsed command-line arguments.
            config: Loaded configuration.

        Returns:
            Exit code based on scan results.
        """
        if config is None:
            LOGGER.error("Configuration is required for scan command")
            return EXIT_SCANNER_ERROR

        try:
            result = self._run_scan(args, config)

            # Determine output format: CLI > config > default (json)
            if args.format:
                output_format = args.format
            elif config.output.format:
                output_format = config.output.format
            else:
                output_format = "json"

            reporter = get_reporter_plugin(output_format)
            if not reporter:
                LOGGER.error(f"Reporter plugin '{output_format}' not found")
                return EXIT_SCANNER_ERROR

            # Write output to stdout
            reporter.report(result, sys.stdout)

            # Check severity threshold - CLI overrides config
            # Use get_fail_on_threshold to handle both string and dict formats
            threshold = args.fail_on if args.fail_on else config.get_fail_on_threshold("security")
            if self._check_severity_threshold(result, threshold):
                return EXIT_ISSUES_FOUND

            return EXIT_SUCCESS

        except FileNotFoundError as e:
            LOGGER.error(str(e))
            raise
        except Exception as e:
            LOGGER.error(f"Scan failed: {e}")
            raise

    def _run_scan(
        self, args: Namespace, config: LucidScanConfig
    ) -> ScanResult:
        """Execute the scan based on CLI arguments and config.

        Uses PipelineExecutor to run the scan pipeline:
        1. Linting (if --lint or --all)
        2. Scanner execution (parallel by default)
        3. Enricher execution (sequential, in configured order)
        4. Result aggregation

        Args:
            args: Parsed CLI arguments.
            config: Loaded configuration.

        Returns:
            ScanResult containing all issues found.
        """
        project_root = Path(args.path).resolve()

        if not project_root.exists():
            raise FileNotFoundError(f"Path does not exist: {project_root}")

        enabled_domains = ConfigBridge.get_enabled_domains(config, args)

        # Load ignore patterns from .lucidscanignore and config
        ignore_patterns = load_ignore_patterns(project_root, config.ignore)

        # Build scan context
        context = ScanContext(
            project_root=project_root,
            paths=[project_root],
            enabled_domains=enabled_domains,
            config=config,
            ignore_patterns=ignore_patterns,
        )

        all_issues: List[UnifiedIssue] = []
        pipeline_result: Optional[ScanResult] = None

        # Run linting if requested
        lint_enabled = getattr(args, "lint", False) or getattr(args, "all", False)
        fix_enabled = getattr(args, "fix", False)

        if lint_enabled:
            lint_issues = self._run_linting(context, fix_enabled)
            all_issues.extend(lint_issues)

        # Run type checking if requested
        type_check_enabled = getattr(args, "type_check", False) or getattr(
            args, "all", False
        )

        if type_check_enabled:
            type_check_issues = self._run_type_checking(context)
            all_issues.extend(type_check_issues)

        # Run tests if requested
        test_enabled = getattr(args, "test", False) or getattr(args, "all", False)

        if test_enabled:
            test_issues = self._run_tests(context)
            all_issues.extend(test_issues)

        # Run coverage if requested
        coverage_enabled = getattr(args, "coverage", False) or getattr(
            args, "all", False
        )

        if coverage_enabled:
            coverage_threshold = getattr(args, "coverage_threshold", None) or 80.0
            coverage_issues = self._run_coverage(context, coverage_threshold)
            all_issues.extend(coverage_issues)

        # Run security scanning if any domains are enabled
        if enabled_domains:
            # Collect unique scanners needed based on config
            needed_scanners: List[str] = []
            for domain in enabled_domains:
                scanner_name = config.get_plugin_for_domain(domain.value)
                if scanner_name and scanner_name not in needed_scanners:
                    needed_scanners.append(scanner_name)
                elif not scanner_name:
                    LOGGER.warning(
                        f"No scanner plugin configured for domain: {domain.value}"
                    )

            if needed_scanners:
                # Build pipeline configuration
                pipeline_config = PipelineConfig(
                    sequential_scanners=getattr(args, "sequential", False),
                    max_workers=config.pipeline.max_workers,
                    enricher_order=config.pipeline.enrichers,
                )

                # Execute pipeline
                executor = PipelineExecutor(
                    config=config,
                    pipeline_config=pipeline_config,
                    lucidscan_version=self._version,
                )

                pipeline_result = executor.execute(needed_scanners, context)
                all_issues.extend(pipeline_result.issues)

        # Build final result
        result = ScanResult(issues=all_issues)
        result.summary = result.compute_summary()

        # Preserve metadata from pipeline execution
        if pipeline_result and pipeline_result.metadata:
            result.metadata = pipeline_result.metadata

        return result

    def _run_linting(
        self, context: ScanContext, fix: bool = False
    ) -> List[UnifiedIssue]:
        """Run linting checks.

        Args:
            context: Scan context.
            fix: If True, apply automatic fixes.

        Returns:
            List of linting issues.
        """
        from lucidscan.plugins.linters import discover_linter_plugins

        issues: List[UnifiedIssue] = []

        # Discover all linter plugins
        linter_plugins = discover_linter_plugins()

        if not linter_plugins:
            LOGGER.warning("No linter plugins found")
            return issues

        # Filter to only configured tools if config specifies them
        configured_tools = context.config.pipeline.get_enabled_tool_names("linting")
        if configured_tools:
            linter_plugins = {
                name: cls for name, cls in linter_plugins.items()
                if name in configured_tools
            }
        else:
            # Filter by project languages if no tools explicitly configured
            linter_plugins = _filter_plugins_by_language(
                linter_plugins, context.config.project.languages
            )

        for name, plugin_class in linter_plugins.items():
            try:
                LOGGER.info(f"Running linter: {name}")
                plugin = plugin_class(project_root=context.project_root)

                if fix and plugin.supports_fix:
                    # Run fix mode
                    fix_result = plugin.fix(context)
                    LOGGER.info(
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

    def _run_type_checking(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run type checking.

        Args:
            context: Scan context.

        Returns:
            List of type checking issues.
        """
        from lucidscan.plugins.type_checkers import discover_type_checker_plugins

        issues: List[UnifiedIssue] = []

        # Discover all type checker plugins
        type_checker_plugins = discover_type_checker_plugins()

        if not type_checker_plugins:
            LOGGER.warning("No type checker plugins found")
            return issues

        # Filter to only configured tools if config specifies them
        configured_tools = context.config.pipeline.get_enabled_tool_names("type_checking")
        if configured_tools:
            type_checker_plugins = {
                name: cls for name, cls in type_checker_plugins.items()
                if name in configured_tools
            }
        else:
            # Filter by project languages if no tools explicitly configured
            type_checker_plugins = _filter_plugins_by_language(
                type_checker_plugins, context.config.project.languages
            )

        for name, plugin_class in type_checker_plugins.items():
            try:
                LOGGER.info(f"Running type checker: {name}")
                plugin = plugin_class(project_root=context.project_root)
                issues.extend(plugin.check(context))

            except Exception as e:
                LOGGER.error(f"Type checker {name} failed: {e}")

        return issues

    def _run_tests(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run test suite.

        Args:
            context: Scan context.

        Returns:
            List of test failure issues.
        """
        from lucidscan.plugins.test_runners import discover_test_runner_plugins

        issues: List[UnifiedIssue] = []

        # Discover all test runner plugins
        test_runner_plugins = discover_test_runner_plugins()

        if not test_runner_plugins:
            LOGGER.warning("No test runner plugins found")
            return issues

        # Filter to only configured tools if config specifies them
        configured_tools = context.config.pipeline.get_enabled_tool_names("testing")
        if configured_tools:
            test_runner_plugins = {
                name: cls for name, cls in test_runner_plugins.items()
                if name in configured_tools
            }
        else:
            # Filter by project languages if no tools explicitly configured
            test_runner_plugins = _filter_plugins_by_language(
                test_runner_plugins, context.config.project.languages
            )

        for name, plugin_class in test_runner_plugins.items():
            try:
                LOGGER.info(f"Running test runner: {name}")
                plugin = plugin_class(project_root=context.project_root)
                result = plugin.run_tests(context)

                LOGGER.info(
                    f"{name}: {result.passed} passed, {result.failed} failed, "
                    f"{result.skipped} skipped, {result.errors} errors"
                )

                issues.extend(result.issues)

            except FileNotFoundError:
                # Plugin not available for this project (e.g., no pytest in Python project)
                LOGGER.debug(f"Test runner {name} not available")
            except Exception as e:
                LOGGER.error(f"Test runner {name} failed: {e}")

        return issues

    def _run_coverage(
        self, context: ScanContext, threshold: float = 80.0
    ) -> List[UnifiedIssue]:
        """Run coverage analysis.

        Args:
            context: Scan context.
            threshold: Coverage percentage threshold.

        Returns:
            List of coverage issues (if below threshold).
        """
        from lucidscan.plugins.coverage import discover_coverage_plugins

        issues: List[UnifiedIssue] = []

        # Discover all coverage plugins
        coverage_plugins = discover_coverage_plugins()

        if not coverage_plugins:
            LOGGER.warning("No coverage plugins found")
            return issues

        # Filter to only configured tools if config specifies them
        configured_tools = context.config.pipeline.get_enabled_tool_names("coverage")
        if configured_tools:
            coverage_plugins = {
                name: cls for name, cls in coverage_plugins.items()
                if name in configured_tools
            }
        else:
            # Filter by project languages if no tools explicitly configured
            coverage_plugins = _filter_plugins_by_language(
                coverage_plugins, context.config.project.languages
            )

        for name, plugin_class in coverage_plugins.items():
            try:
                LOGGER.info(f"Running coverage: {name}")
                plugin = plugin_class(project_root=context.project_root)
                result = plugin.measure_coverage(
                    context, threshold=threshold, run_tests=True
                )

                status = "PASSED" if result.passed else "FAILED"
                LOGGER.info(
                    f"{name}: {result.percentage:.1f}% ({result.covered_lines}/{result.total_lines} lines) "
                    f"- threshold: {threshold}% - {status}"
                )

                issues.extend(result.issues)

            except FileNotFoundError:
                # Plugin not available for this project
                LOGGER.debug(f"Coverage plugin {name} not available")
            except Exception as e:
                LOGGER.error(f"Coverage plugin {name} failed: {e}")

        return issues

    def _check_severity_threshold(
        self, result: ScanResult, threshold: Optional[str]
    ) -> bool:
        """Check if any issues meet or exceed the severity threshold.

        Args:
            result: Scan result to check.
            threshold: Severity threshold ('critical', 'high', 'medium', 'low').

        Returns:
            True if issues at or above threshold exist, False otherwise.
        """
        if not threshold or not result.issues:
            return False

        threshold_order = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }

        threshold_level = threshold_order.get(threshold.lower(), 99)

        for issue in result.issues:
            issue_level = threshold_order.get(issue.severity.value, 99)
            if issue_level <= threshold_level:
                return True

        return False
