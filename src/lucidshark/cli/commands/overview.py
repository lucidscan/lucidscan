"""Overview command implementation.

Generates and updates QUALITY.md with repository quality metrics and trends.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from lucidshark.cli.commands import Command
from lucidshark.cli.exit_codes import EXIT_SUCCESS, EXIT_SCANNER_ERROR
from lucidshark.core.logging import get_logger

if TYPE_CHECKING:
    from lucidshark.config.models import LucidSharkConfig
    from lucidshark.core.models import ScanResult
    from lucidshark.overview.generator import OverviewConfig as GeneratorOverviewConfig

LOGGER = get_logger(__name__)


class OverviewCommand(Command):
    """Generates QUALITY.md overview of repository quality state."""

    def __init__(self, version: str):
        """Initialize OverviewCommand.

        Args:
            version: Current lucidshark version string.
        """
        self._version = version

    @property
    def name(self) -> str:
        """Command identifier."""
        return "overview"

    def execute(self, args: Namespace, config: "LucidSharkConfig | None" = None) -> int:
        """Execute the overview command.

        Args:
            args: Parsed command-line arguments.
            config: LucidShark configuration.

        Returns:
            Exit code.
        """
        from lucidshark.core.git import get_current_branch, get_current_commit
        from lucidshark.overview.generator import (
            OverviewGenerator,
            create_snapshot_from_scan,
            get_top_files,
        )
        from lucidshark.overview.history import HistoryManager

        project_root = Path(args.path).resolve()

        # Get git info
        commit = get_current_commit(project_root) or "unknown"
        branch = get_current_branch(project_root) or "unknown"

        # Determine mode
        preview = getattr(args, "preview", False)
        update = getattr(args, "update", False)
        show = getattr(args, "show", False)

        # Default to show if no mode specified
        if not preview and not update and not show:
            show = True

        # Get overview config from lucidshark config
        overview_config = self._get_overview_config(config)

        # Initialize managers
        history_manager = HistoryManager(
            project_root=project_root,
            path=overview_config.get("history_file"),
            limit=overview_config.get("history_limit", 90),
        )
        generator = OverviewGenerator(
            config=self._build_generator_config(overview_config)
        )

        # Load existing history
        previous = history_manager.get_latest()
        history = history_manager.get_snapshots(count=10)

        # Get scan results
        scan_result = self._get_scan_results(args, config, project_root)
        if scan_result is None:
            LOGGER.error("No scan results available. Run 'lucidshark scan' first.")
            return EXIT_SCANNER_ERROR

        # Validate that scan was a full project scan (not incremental)
        # Overview should represent the entire repository's quality state
        # Require both: metadata exists AND all_files is True
        if not (scan_result.metadata and scan_result.metadata.all_files):
            LOGGER.error(
                "Overview requires a full project scan. "
                "Run 'lucidshark scan --all --all-files' first."
            )
            return EXIT_SCANNER_ERROR

        # Create snapshot from scan results
        snapshot = create_snapshot_from_scan(
            scan_result=scan_result,
            commit=commit,
            branch=branch,
            enabled_domains=overview_config.get("domains"),
        )

        # Get top files
        top_files = get_top_files(
            scan_result,
            limit=overview_config.get("top_files", 5),
            project_root=str(project_root),
        )

        # Generate markdown
        markdown = generator.generate(
            snapshot=snapshot,
            previous=previous,
            history=history,
            top_files=top_files,
        )

        # Handle output based on mode
        if show:
            print(markdown)
            return EXIT_SUCCESS

        if preview:
            output_path = project_root / overview_config.get("file", "QUALITY.md")
            print(f"Would write to: {output_path}")
            print()
            print("--- Preview ---")
            print(markdown)
            print("--- End Preview ---")
            return EXIT_SUCCESS

        if update:
            # Write markdown file
            output_path = project_root / overview_config.get("file", "QUALITY.md")
            output_path.write_text(markdown, encoding="utf-8")
            LOGGER.info(f"Updated {output_path}")

            # Update history
            history_manager.append(snapshot)
            history_manager.save()
            LOGGER.info(f"Updated {history_manager.path}")

            print(f"Updated {output_path}")
            print(f"Score: {snapshot.score:.1f}/10 | Issues: {snapshot.issues.total}")
            if snapshot.coverage is not None:
                print(f"Coverage: {snapshot.coverage:.1f}%")

            return EXIT_SUCCESS

        return EXIT_SUCCESS

    def _get_overview_config(self, config: "LucidSharkConfig | None") -> dict:
        """Extract overview config from LucidShark config.

        Args:
            config: LucidShark configuration.

        Returns:
            Overview configuration dictionary.
        """
        if config is None:
            return {}

        # Check if config has overview section
        if hasattr(config, "overview") and config.overview is not None:
            from lucidshark.config.models import OverviewConfig as ConfigOverviewConfig

            if isinstance(config.overview, ConfigOverviewConfig):
                return {
                    "enabled": config.overview.enabled,
                    "file": config.overview.file,
                    "history_file": config.overview.history_file,
                    "history_limit": config.overview.history_limit,
                    "domains": config.overview.domains,
                    "health_score": config.overview.health_score,
                    "domain_table": config.overview.domain_table,
                    "issue_breakdown": config.overview.issue_breakdown,
                    "top_files": config.overview.top_files,
                    "security_summary": config.overview.security_summary,
                    "coverage_breakdown": config.overview.coverage_breakdown,
                    "trend_chart": config.overview.trend_chart,
                }

        return {}

    def _build_generator_config(
        self, overview_config: dict
    ) -> "GeneratorOverviewConfig":
        """Build OverviewConfig from config dict.

        Args:
            overview_config: Overview configuration dictionary.

        Returns:
            OverviewConfig instance.
        """
        from lucidshark.overview.generator import OverviewConfig

        # Pass domains as-is (None triggers default in OverviewConfig.__post_init__)
        domains = overview_config.get("domains")

        return OverviewConfig(
            file=overview_config.get("file", "QUALITY.md"),
            domains=domains,  # type: ignore[arg-type]
            top_files=overview_config.get("top_files", 5),
            health_score=overview_config.get("health_score", True),
            domain_table=overview_config.get("domain_table", True),
            issue_breakdown=overview_config.get("issue_breakdown", True),
            security_summary=overview_config.get("security_summary", True),
            coverage_breakdown=overview_config.get("coverage_breakdown", True),
            trend_chart=overview_config.get("trend_chart", True),
        )

    def _get_scan_results(
        self,
        args: Namespace,
        config: "LucidSharkConfig | None",
        project_root: Path,
    ) -> "Optional[ScanResult]":
        """Get scan results, either from cache or by running a scan.

        Args:
            args: Parsed command-line arguments.
            config: LucidShark configuration.
            project_root: Project root path.

        Returns:
            ScanResult or None if not available.
        """
        # Check for cached results in .lucidshark/
        cache_path = project_root / ".lucidshark" / "last-scan.json"
        if cache_path.exists():
            try:
                import json

                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return self._parse_scan_result(data)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                LOGGER.debug(f"Could not load cached scan results: {e}")

        # If --scan flag is set, run a scan
        if getattr(args, "scan", False) and config is not None:
            return self._run_scan(args, config, project_root)

        return None

    def _parse_scan_result(self, data: dict) -> "ScanResult":
        """Parse scan result from JSON data.

        Args:
            data: JSON data dictionary.

        Returns:
            ScanResult instance.
        """
        from lucidshark.core.models import (
            CoverageSummary,
            DuplicationSummary,
            ScanMetadata,
            ScanResult as ScanResultModel,
            ScanSummary,
            Severity,
            UnifiedIssue,
        )

        issues = []
        for issue_data in data.get("issues", []):
            try:
                # Parse severity
                severity_str = issue_data.get("severity", "low").lower()
                severity = Severity(severity_str)

                # Parse domain - handle both string and dict formats
                domain_val = issue_data.get("domain", "linting")
                if isinstance(domain_val, dict):
                    domain_str = domain_val.get("value", "linting")
                else:
                    domain_str = str(domain_val)

                from lucidshark.core.models import parse_domain

                domain = parse_domain(domain_str)
                if domain is None:
                    from lucidshark.core.models import ToolDomain

                    domain = ToolDomain.LINTING

                issues.append(
                    UnifiedIssue(
                        id=issue_data.get("id", ""),
                        domain=domain,
                        source_tool=issue_data.get("source_tool", "unknown"),
                        severity=severity,
                        rule_id=issue_data.get("rule_id", ""),
                        title=issue_data.get("title", ""),
                        description=issue_data.get("description", ""),
                        file_path=Path(issue_data["file_path"])
                        if issue_data.get("file_path")
                        else None,
                        line_start=issue_data.get("line_start"),
                        ignored=issue_data.get("ignored", False),
                    )
                )
            except (KeyError, ValueError) as e:
                LOGGER.debug(f"Could not parse issue: {e}")
                continue

        # Parse summary
        summary = None
        if "summary" in data:
            summary_data = data["summary"]
            summary = ScanSummary(
                total=summary_data.get("total", 0),
                ignored_total=summary_data.get("ignored_total", 0),
                by_severity=summary_data.get("by_severity", {}),
                by_scanner=summary_data.get("by_scanner", {}),
            )

        # Parse coverage summary
        coverage_summary = None
        if "coverage_summary" in data and data["coverage_summary"]:
            cov_data = data["coverage_summary"]
            coverage_summary = CoverageSummary(
                coverage_percentage=cov_data.get("coverage_percentage", 0.0),
                threshold=cov_data.get("threshold", 80.0),
                total_lines=cov_data.get("total_lines", 0),
                covered_lines=cov_data.get("covered_lines", 0),
                missing_lines=cov_data.get("missing_lines", 0),
                passed=cov_data.get("passed", True),
            )

        # Parse duplication summary
        duplication_summary = None
        if "duplication_summary" in data and data["duplication_summary"]:
            dup_data = data["duplication_summary"]
            duplication_summary = DuplicationSummary(
                files_analyzed=dup_data.get("files_analyzed", 0),
                total_lines=dup_data.get("total_lines", 0),
                duplicate_blocks=dup_data.get("duplicate_blocks", 0),
                duplicate_lines=dup_data.get("duplicate_lines", 0),
                duplication_percent=dup_data.get("duplication_percent", 0.0),
                threshold=dup_data.get("threshold", 10.0),
                passed=dup_data.get("passed", True),
            )

        # Parse metadata
        metadata = None
        if "metadata" in data and data["metadata"]:
            meta_data = data["metadata"]
            metadata = ScanMetadata(
                lucidshark_version=meta_data.get("lucidshark_version", ""),
                scan_started_at=meta_data.get("scan_started_at", ""),
                scan_finished_at=meta_data.get("scan_finished_at", ""),
                duration_ms=meta_data.get("duration_ms", 0),
                project_root=meta_data.get("project_root", ""),
                scanners_used=meta_data.get("scanners_used", []),
                enabled_domains=meta_data.get("enabled_domains", []),
                executed_domains=meta_data.get("executed_domains", []),
                all_files=meta_data.get("all_files", False),
            )

        result = ScanResultModel(
            issues=issues,
            metadata=metadata,
            summary=summary,
            coverage_summary=coverage_summary,
            duplication_summary=duplication_summary,
        )

        # Compute summary if not provided
        if result.summary is None:
            result.summary = result.compute_summary()

        return result

    def _run_scan(
        self,
        args: Namespace,
        config: "LucidSharkConfig",  # noqa: ARG002
        project_root: Path,  # noqa: ARG002
    ) -> "Optional[ScanResult]":
        """Run a scan and return results.

        Args:
            args: Parsed command-line arguments.
            config: LucidShark configuration.
            project_root: Project root path.

        Returns:
            ScanResult or None if scan failed.
        """
        # This would need refactoring to return results directly
        # For now, rely on cached results
        _ = args  # Suppress unused warning
        LOGGER.warning("Running scan from overview not yet implemented")
        return None
