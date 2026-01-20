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
from lucidscan.core.domain_runner import DomainRunner, check_severity_threshold
from lucidscan.core.git import get_changed_files
from lucidscan.core.logging import get_logger
from lucidscan.core.models import CoverageSummary, ScanContext, ScanResult, UnifiedIssue
from lucidscan.core.streaming import CLIStreamHandler, StreamHandler
from lucidscan.pipeline import PipelineConfig, PipelineExecutor
from lucidscan.plugins.reporters import get_reporter_plugin

LOGGER = get_logger(__name__)


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
            if check_severity_threshold(result.issues, threshold):
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
        1. Linting (if --linting or --all)
        2. Scanner execution (parallel by default)
        3. Enricher execution (sequential, in configured order)
        4. Result aggregation

        Partial Scanning (default behavior):
        - If --files is specified, scan only those files
        - If --all-files is specified, scan entire project
        - Otherwise, scan only changed files (uncommitted changes)

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

        # Determine which files to scan (partial scanning logic)
        scan_paths = self._determine_scan_paths(args, project_root)

        # Filter scan paths through ignore patterns
        # This is necessary because explicitly passed file paths bypass
        # the linter's --exclude flags (e.g., ruff only applies excludes
        # when expanding directories, not for explicit file arguments)
        if scan_paths and ignore_patterns:
            original_count = len(scan_paths)
            scan_paths = [
                p for p in scan_paths
                if not ignore_patterns.matches(p, project_root)
            ]
            filtered_count = original_count - len(scan_paths)
            if filtered_count > 0:
                LOGGER.debug(f"Filtered {filtered_count} files via ignore patterns")

        # Create stream handler if streaming is enabled
        stream_handler: Optional[StreamHandler] = None
        stream_enabled = getattr(args, "stream", False) or getattr(args, "verbose", False)
        if stream_enabled:
            stream_handler = CLIStreamHandler(
                output=sys.stderr,
                show_output=True,
                use_rich=False,  # Use plain output for better compatibility
            )

        # Build scan context
        context = ScanContext(
            project_root=project_root,
            paths=scan_paths,
            enabled_domains=enabled_domains,
            config=config,
            ignore_patterns=ignore_patterns,
            stream_handler=stream_handler,
        )

        # Create domain runner for executing tool-based scans
        runner = DomainRunner(project_root, config, log_level="info")

        all_issues: List[UnifiedIssue] = []
        pipeline_result: Optional[ScanResult] = None

        # Run linting if requested
        linting_enabled = getattr(args, "linting", False) or getattr(args, "all", False)
        fix_enabled = getattr(args, "fix", False)

        if linting_enabled:
            all_issues.extend(runner.run_linting(context, fix_enabled))

        # Run type checking if requested
        type_checking_enabled = getattr(args, "type_checking", False) or getattr(
            args, "all", False
        )

        if type_checking_enabled:
            all_issues.extend(runner.run_type_checking(context))

        # Run tests if requested
        testing_enabled = getattr(args, "testing", False) or getattr(args, "all", False)

        if testing_enabled:
            all_issues.extend(runner.run_tests(context))

        # Run coverage if requested
        coverage_enabled = getattr(args, "coverage", False) or getattr(
            args, "all", False
        )

        coverage_summary: Optional[CoverageSummary] = None
        if coverage_enabled:
            coverage_threshold = getattr(args, "coverage_threshold", None) or 80.0
            # Don't re-run tests if they were already run in the testing domain
            run_tests_for_coverage = not testing_enabled
            all_issues.extend(
                runner.run_coverage(context, coverage_threshold, run_tests_for_coverage)
            )

            # Build coverage summary from context.coverage_result
            if context.coverage_result is not None:
                cov = context.coverage_result
                coverage_summary = CoverageSummary(
                    coverage_percentage=round(cov.percentage, 2),
                    threshold=cov.threshold,
                    total_lines=cov.total_lines,
                    covered_lines=cov.covered_lines,
                    missing_lines=cov.missing_lines,
                    passed=cov.passed,
                )
                # Add test stats if available
                if cov.test_stats is not None:
                    ts = cov.test_stats
                    coverage_summary.tests_total = ts.total
                    coverage_summary.tests_passed = ts.passed
                    coverage_summary.tests_failed = ts.failed
                    coverage_summary.tests_skipped = ts.skipped
                    coverage_summary.tests_errors = ts.errors

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
        result.coverage_summary = coverage_summary

        # Preserve metadata from pipeline execution
        if pipeline_result and pipeline_result.metadata:
            result.metadata = pipeline_result.metadata

        return result

    def _determine_scan_paths(
        self, args: Namespace, project_root: Path
    ) -> List[Path]:
        """Determine which paths to scan based on CLI arguments.

        Priority:
        1. --files: Scan only specified files
        2. --all-files: Scan entire project
        3. Default: Scan only changed files (uncommitted changes)

        Args:
            args: Parsed CLI arguments.
            project_root: Project root directory.

        Returns:
            List of paths to scan.
        """
        # If --files is specified, use those files
        files_arg = getattr(args, "files", None)
        if files_arg:
            paths = []
            for file_path in files_arg:
                path = Path(file_path)
                if not path.is_absolute():
                    path = project_root / path
                path = path.resolve()
                if path.exists():
                    paths.append(path)
                else:
                    LOGGER.warning(f"File not found: {file_path}")
            if paths:
                LOGGER.info(f"Scanning {len(paths)} specified file(s)")
                return paths
            # Fall through to full scan if no valid files
            LOGGER.warning("No valid files specified, falling back to full scan")

        # If --all-files is specified, scan entire project
        all_files = getattr(args, "all_files", False)
        if all_files:
            LOGGER.info("Scanning entire project (--all-files)")
            return [project_root]

        # Default: scan only changed files
        changed_files = get_changed_files(project_root)
        if changed_files is not None and len(changed_files) > 0:
            LOGGER.info(f"Scanning {len(changed_files)} changed file(s)")
            return changed_files

        # Fall back to full scan if no changed files or not a git repo
        if changed_files is not None and len(changed_files) == 0:
            LOGGER.info("No changed files detected, nothing to scan")
            return []  # Return empty list - no files to scan
        else:
            LOGGER.info("Not a git repository, scanning entire project")
            return [project_root]
