"""Scan command implementation."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path
from typing import List, Optional

from lucidshark.cli.commands import Command
from lucidshark.cli.config_bridge import ConfigBridge
from lucidshark.cli.exit_codes import (
    EXIT_ISSUES_FOUND,
    EXIT_SCANNER_ERROR,
    EXIT_SUCCESS,
)
from lucidshark.config.models import LucidSharkConfig
from lucidshark.core.domain_runner import DomainRunner, check_severity_threshold
from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    CoverageSummary,
    DuplicationSummary,
    ScanContext,
    ScanResult,
    UnifiedIssue,
)
from lucidshark.core.streaming import CLIStreamHandler, StreamHandler
from lucidshark.pipeline import PipelineConfig, PipelineExecutor
from lucidshark.plugins.reporters import get_reporter_plugin

LOGGER = get_logger(__name__)


class ScanCommand(Command):
    """Executes security scanning."""

    def __init__(self, version: str):
        """Initialize ScanCommand.

        Args:
            version: Current lucidshark version string.
        """
        self._version = version

    @property
    def name(self) -> str:
        """Command identifier."""
        return "scan"

    def execute(self, args: Namespace, config: LucidSharkConfig | None = None) -> int:
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

        # Handle dry-run mode
        if getattr(args, "dry_run", False):
            return self._dry_run(args, config)

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

            # Check fail_on thresholds for all domains
            # CLI --fail-on overrides all config thresholds
            if args.fail_on:
                # CLI flag applies to all issues regardless of domain
                if check_severity_threshold(result.issues, args.fail_on):
                    return EXIT_ISSUES_FOUND
            else:
                # Check per-domain thresholds from config
                if self._check_domain_thresholds(result, config):
                    return EXIT_ISSUES_FOUND

            return EXIT_SUCCESS

        except FileNotFoundError as e:
            LOGGER.error(str(e))
            raise
        except Exception as e:
            LOGGER.error(f"Scan failed: {e}")
            raise

    def _run_scan(
        self, args: Namespace, config: LucidSharkConfig
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

        # Determine which tool domains are enabled
        # --all means "all configured domains", specific flags override config
        all_flag = getattr(args, "all", False)
        fix_enabled = getattr(args, "fix", False)

        # Run linting if requested or if --all and linting is configured
        linting_flag = getattr(args, "linting", False)
        linting_configured = (
            config.pipeline.linting is None or config.pipeline.linting.enabled
        )
        linting_enabled = linting_flag or (all_flag and linting_configured)

        if linting_enabled:
            all_issues.extend(runner.run_linting(context, fix_enabled))

        # Run type checking if requested or if --all and type_checking is configured
        type_checking_flag = getattr(args, "type_checking", False)
        type_checking_configured = (
            config.pipeline.type_checking is None
            or config.pipeline.type_checking.enabled
        )
        type_checking_enabled = type_checking_flag or (
            all_flag and type_checking_configured
        )

        if type_checking_enabled:
            all_issues.extend(runner.run_type_checking(context))

        # Run tests if requested or if --all and testing is configured
        testing_flag = getattr(args, "testing", False)
        testing_configured = (
            config.pipeline.testing is not None and config.pipeline.testing.enabled
        )
        testing_enabled = testing_flag or (all_flag and testing_configured)

        # Run coverage if requested or if --all and coverage is configured
        coverage_flag = getattr(args, "coverage", False)
        coverage_configured = (
            config.pipeline.coverage is not None and config.pipeline.coverage.enabled
        )
        coverage_enabled = coverage_flag or (all_flag and coverage_configured)

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

        # Run duplication detection if requested or if --all and duplication is configured
        duplication_flag = getattr(args, "duplication", False)
        duplication_configured = (
            config.pipeline.duplication is not None
            and config.pipeline.duplication.enabled
        )
        duplication_enabled = duplication_flag or (all_flag and duplication_configured)

        duplication_summary: Optional[DuplicationSummary] = None
        if duplication_enabled:
            # Get threshold and options from CLI or config
            duplication_threshold = getattr(args, "duplication_threshold", None)
            min_lines = getattr(args, "min_lines", None)
            min_chars = 3  # Default
            exclude_patterns: Optional[List[str]] = None

            # Fall back to config values if not set on CLI
            if config.pipeline.duplication:
                if duplication_threshold is None:
                    duplication_threshold = config.pipeline.duplication.threshold
                if min_lines is None:
                    min_lines = config.pipeline.duplication.min_lines
                min_chars = config.pipeline.duplication.min_chars or min_chars
                exclude_patterns = config.pipeline.duplication.exclude or None

            # Apply defaults
            duplication_threshold = duplication_threshold or 10.0
            min_lines = min_lines or 4

            all_issues.extend(
                runner.run_duplication(
                    context,
                    duplication_threshold,
                    min_lines,
                    min_chars,
                    exclude_patterns,
                )
            )

            # Build duplication summary from context.duplication_result
            if context.duplication_result is not None:
                duplication_summary = context.duplication_result.to_summary()

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
                    lucidshark_version=self._version,
                )

                pipeline_result = executor.execute(needed_scanners, context)
                all_issues.extend(pipeline_result.issues)

        # Build final result
        result = ScanResult(issues=all_issues)
        result.summary = result.compute_summary()
        result.coverage_summary = coverage_summary
        result.duplication_summary = duplication_summary

        # Preserve metadata from pipeline execution
        if pipeline_result and pipeline_result.metadata:
            result.metadata = pipeline_result.metadata

        return result

    def _check_domain_thresholds(
        self, result: ScanResult, config: LucidSharkConfig
    ) -> bool:
        """Check if any issues exceed their domain's fail_on threshold.

        Groups issues by domain and checks each against its configured threshold.

        Args:
            result: Scan result containing issues and summaries.
            config: Configuration with per-domain thresholds.

        Returns:
            True if any domain exceeds its threshold, False otherwise.
        """
        from lucidshark.core.models import ScanDomain, ToolDomain

        issues = result.issues

        # Map issue domains to config domain names
        # ScanDomain values (SCA, CONTAINER, IAC, SAST) all map to "security"
        domain_mapping: dict[ScanDomain | ToolDomain, str] = {
            ToolDomain.LINTING: "linting",
            ToolDomain.TYPE_CHECKING: "type_checking",
            ToolDomain.SECURITY: "security",
            ToolDomain.TESTING: "testing",
            ToolDomain.COVERAGE: "coverage",
            ToolDomain.DUPLICATION: "duplication",
            ScanDomain.SCA: "security",
            ScanDomain.CONTAINER: "security",
            ScanDomain.IAC: "security",
            ScanDomain.SAST: "security",
        }

        # Group issues by domain
        issues_by_domain: dict[str, List[UnifiedIssue]] = {}
        for issue in issues:
            domain_name = domain_mapping.get(issue.domain, "security")
            if domain_name not in issues_by_domain:
                issues_by_domain[domain_name] = []
            issues_by_domain[domain_name].append(issue)

        # Check each domain against its threshold
        for domain_name, domain_issues in issues_by_domain.items():
            threshold = config.get_fail_on_threshold(domain_name)
            if threshold:
                # Handle special threshold values
                if threshold == "any" and domain_issues:
                    LOGGER.debug(f"Domain {domain_name}: {len(domain_issues)} issues exceed 'any' threshold")
                    return True
                elif threshold == "error":
                    # For linting/type_checking: fail on any HIGH severity (errors)
                    if any(i.severity.value in ("high", "critical") for i in domain_issues):
                        LOGGER.debug(f"Domain {domain_name}: issues exceed 'error' threshold")
                        return True
                elif threshold == "none":
                    # Never fail
                    continue
                elif threshold == "above_threshold":
                    # For duplication: fail if duplication exceeds configured threshold
                    if domain_name == "duplication" and result.duplication_summary:
                        if not result.duplication_summary.passed:
                            LOGGER.debug(
                                f"Domain {domain_name}: {result.duplication_summary.duplication_percent:.1f}% "
                                f"exceeds configured threshold of {result.duplication_summary.threshold}%"
                            )
                            return True
                elif threshold == "below_threshold":
                    # For coverage: fail if coverage is below configured threshold
                    if domain_name == "coverage" and result.coverage_summary:
                        if not result.coverage_summary.passed:
                            LOGGER.debug(
                                f"Domain {domain_name}: {result.coverage_summary.coverage_percentage:.1f}% "
                                f"is below configured threshold of {result.coverage_summary.threshold}%"
                            )
                            return True
                elif threshold.endswith("%"):
                    # Percentage threshold (used for duplication)
                    try:
                        threshold_pct = float(threshold.rstrip("%"))
                        if domain_name == "duplication" and result.duplication_summary:
                            if result.duplication_summary.duplication_percent > threshold_pct:
                                LOGGER.debug(
                                    f"Domain {domain_name}: {result.duplication_summary.duplication_percent:.1f}% "
                                    f"exceeds '{threshold}' threshold"
                                )
                                return True
                    except ValueError:
                        LOGGER.warning(f"Invalid percentage threshold: {threshold}")
                elif check_severity_threshold(domain_issues, threshold):
                    LOGGER.debug(f"Domain {domain_name}: issues exceed '{threshold}' threshold")
                    return True

        return False

    def _dry_run(self, args: Namespace, config: LucidSharkConfig) -> int:
        """Show what would be scanned without executing.

        Args:
            args: Parsed command-line arguments.
            config: Loaded configuration.

        Returns:
            EXIT_SUCCESS always.
        """
        project_root = Path(args.path).resolve()
        enabled_domains = ConfigBridge.get_enabled_domains(config, args)
        all_flag = getattr(args, "all", False)

        print("Dry run - showing what would be scanned:\n")

        # Project info
        print(f"Project root: {project_root}")
        if config.project.name:
            print(f"Project name: {config.project.name}")
        if config.project.languages:
            print(f"Languages: {', '.join(config.project.languages)}")
        print()

        # Determine which domains would run
        domains_to_run: List[str] = []
        tools_to_run: List[tuple[str, str]] = []  # (domain, tool)

        # Linting
        linting_flag = getattr(args, "linting", False)
        linting_configured = (
            config.pipeline.linting is None or config.pipeline.linting.enabled
        )
        if linting_flag or (all_flag and linting_configured):
            domains_to_run.append("linting")
            if config.pipeline.linting and config.pipeline.linting.tools:
                for tool in config.pipeline.linting.tools:
                    tool_name = tool.name if hasattr(tool, "name") else str(tool)
                    tools_to_run.append(("linting", tool_name))
            else:
                tools_to_run.append(("linting", "ruff (default)"))

        # Type checking
        type_checking_flag = getattr(args, "type_checking", False)
        type_checking_configured = (
            config.pipeline.type_checking is None
            or config.pipeline.type_checking.enabled
        )
        if type_checking_flag or (all_flag and type_checking_configured):
            domains_to_run.append("type_checking")
            if config.pipeline.type_checking and config.pipeline.type_checking.tools:
                for tool in config.pipeline.type_checking.tools:
                    tool_name = tool.name if hasattr(tool, "name") else str(tool)
                    tools_to_run.append(("type_checking", tool_name))
            else:
                tools_to_run.append(("type_checking", "mypy (default)"))

        # Testing
        testing_flag = getattr(args, "testing", False)
        testing_configured = (
            config.pipeline.testing is not None and config.pipeline.testing.enabled
        )
        if testing_flag or (all_flag and testing_configured):
            domains_to_run.append("testing")
            if config.pipeline.testing and config.pipeline.testing.tools:
                for tool in config.pipeline.testing.tools:
                    tool_name = tool.name if hasattr(tool, "name") else str(tool)
                    tools_to_run.append(("testing", tool_name))
            else:
                tools_to_run.append(("testing", "pytest (default)"))

        # Coverage
        coverage_flag = getattr(args, "coverage", False)
        coverage_configured = (
            config.pipeline.coverage is not None and config.pipeline.coverage.enabled
        )
        if coverage_flag or (all_flag and coverage_configured):
            domains_to_run.append("coverage")
            threshold = getattr(args, "coverage_threshold", None) or 80.0
            tools_to_run.append(("coverage", f"coverage.py (threshold: {threshold}%)"))

        # Duplication
        duplication_flag = getattr(args, "duplication", False)
        duplication_configured = (
            config.pipeline.duplication is not None
            and config.pipeline.duplication.enabled
        )
        if duplication_flag or (all_flag and duplication_configured):
            domains_to_run.append("duplication")
            threshold = getattr(args, "duplication_threshold", None) or 10.0
            tools_to_run.append(("duplication", f"duplo (threshold: {threshold}%)"))

        # Security domains
        for domain in enabled_domains:
            domain_name = domain.value.lower()
            domains_to_run.append(domain_name)
            scanner_name = config.get_plugin_for_domain(domain.value)
            if scanner_name:
                tools_to_run.append((domain_name, scanner_name))

        # Print domains
        if domains_to_run:
            print("Domains to scan:")
            for d in domains_to_run:
                print(f"  - {d}")
            print()

            print("Tools that would run:")
            for d, t in tools_to_run:
                print(f"  - [{d}] {t}")
            print()
        else:
            print("No domains selected. Use --all or specific domain flags.")
            print()

        # File targeting
        files = getattr(args, "files", None)
        all_files = getattr(args, "all_files", False)

        print("File targeting:")
        if files:
            print(f"  Specific files: {', '.join(files)}")
        elif all_files:
            print("  All files in project")
        else:
            print("  Changed files only (uncommitted changes)")
        print()

        # Container images
        images = getattr(args, "images", None)
        if images:
            print("Container images to scan:")
            for img in images:
                print(f"  - {img}")
            print()

        # Output format
        output_format = args.format or config.output.format or "json"
        print(f"Output format: {output_format}")

        # Fail-on threshold
        if args.fail_on:
            print(f"Fail on: {args.fail_on} (CLI override)")
        else:
            print("Fail on: per-domain thresholds from config")

        return EXIT_SUCCESS
