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
from lucidscan.core.models import ScanContext, ScanResult
from lucidscan.pipeline import PipelineConfig, PipelineExecutor
from lucidscan.reporters import get_reporter_plugin

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

    def execute(self, args: Namespace, config: LucidScanConfig) -> int:
        """Execute the scan command.

        Args:
            args: Parsed command-line arguments.
            config: Loaded configuration.

        Returns:
            Exit code based on scan results.
        """
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
            threshold = args.fail_on if args.fail_on else config.fail_on
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
        1. Scanner execution (parallel by default)
        2. Enricher execution (sequential, in configured order)
        3. Result aggregation

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
        if not enabled_domains:
            LOGGER.warning("No scan domains enabled")
            return ScanResult()

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

        return executor.execute(needed_scanners, context)

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
