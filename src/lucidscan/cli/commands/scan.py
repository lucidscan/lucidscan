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
from lucidscan.config.models import LucidScanConfig
from lucidscan.core.domain_runner import DomainRunner, check_severity_threshold
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

        # Create stream handler if streaming is enabled
        stream_handler: Optional[StreamHandler] = None
        stream_enabled = getattr(args, "stream", False) or getattr(args, "verbose", False)
        if stream_enabled:
            stream_handler = CLIStreamHandler(
                output=sys.stderr,
                show_output=True,
                use_rich=False,  # Use plain output for better compatibility
            )

        # Build scan context with path determination and ignore filtering
        context = ScanContext.create(
            project_root=project_root,
            config=config,
            enabled_domains=enabled_domains,
            files=getattr(args, "files", None),
            all_files=getattr(args, "all_files", False),
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

        # Run coverage if requested
        coverage_enabled = getattr(args, "coverage", False) or getattr(
            args, "all", False
        )

        # When both testing and coverage are enabled, run tests WITH coverage
        # instrumentation (via testing domain) to generate .coverage file.
        # Then coverage domain just reads the file to generate reports.
        if testing_enabled:
            # Run tests, with coverage instrumentation if coverage is also enabled
            all_issues.extend(runner.run_tests(context, with_coverage=coverage_enabled))

        coverage_summary: Optional[CoverageSummary] = None
        if coverage_enabled:
            coverage_threshold = getattr(args, "coverage_threshold", None) or 80.0
            # If testing ran with coverage, just read the .coverage file
            # Otherwise, run tests to generate coverage data
            run_tests_for_coverage = not testing_enabled
            all_issues.extend(
                runner.run_coverage(context, coverage_threshold, run_tests_for_coverage)
            )

            # Build coverage summary from context.coverage_result
            if context.coverage_result is not None:
                coverage_summary = context.coverage_result.to_summary()

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
