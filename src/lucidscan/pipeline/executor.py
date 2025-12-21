"""Pipeline executor for orchestrating scan stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from lucidscan.core.logging import get_logger
from lucidscan.core.models import (
    ScanContext,
    ScanMetadata,
    ScanResult,
    UnifiedIssue,
)
from lucidscan.pipeline.parallel import ParallelScannerExecutor, ScannerResult

if TYPE_CHECKING:
    from lucidscan.config.models import LucidScanConfig

LOGGER = get_logger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""

    sequential_scanners: bool = False
    max_workers: int = 4
    enricher_order: List[str] = field(default_factory=list)


class PipelineExecutor:
    """Orchestrates the scan pipeline stages.

    Pipeline stages:
    1. Scanner execution (parallel by default)
    2. Enricher execution (sequential, in configured order)
    3. Result aggregation

    Reporter execution is handled separately in CLI.
    """

    def __init__(
        self,
        config: "LucidScanConfig",
        pipeline_config: Optional[PipelineConfig] = None,
        lucidscan_version: str = "unknown",
    ) -> None:
        """Initialize the pipeline executor.

        Args:
            config: LucidScan configuration.
            pipeline_config: Optional pipeline-specific configuration.
            lucidscan_version: Version string for metadata.
        """
        self._config = config
        self._pipeline_config = pipeline_config or PipelineConfig()
        self._lucidscan_version = lucidscan_version

    def execute(
        self,
        scanner_names: List[str],
        context: ScanContext,
    ) -> ScanResult:
        """Execute the full pipeline and return results.

        Args:
            scanner_names: List of scanner plugin names to run.
            context: Scan context for execution.

        Returns:
            Aggregated ScanResult with all issues and metadata.
        """
        start_time = datetime.now(timezone.utc)

        # Stage 1: Scanner Execution (parallel)
        all_issues, scanner_results = self._execute_scanners(scanner_names, context)

        # Stage 2: Enricher Execution (sequential)
        enriched_issues = self._execute_enrichers(all_issues, context)

        # Stage 3: Result Aggregation
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        result = ScanResult(issues=enriched_issues)
        result.metadata = ScanMetadata(
            lucidscan_version=self._lucidscan_version,
            scan_started_at=start_time.isoformat(),
            scan_finished_at=end_time.isoformat(),
            duration_ms=duration_ms,
            project_root=str(context.project_root),
            scanners_used=self._format_scanners_used(scanner_results),
        )
        result.summary = result.compute_summary()

        return result

    def _execute_scanners(
        self,
        scanner_names: List[str],
        context: ScanContext,
    ) -> tuple[List[UnifiedIssue], List[ScannerResult]]:
        """Execute scanner stage."""
        executor = ParallelScannerExecutor(
            max_workers=self._pipeline_config.max_workers,
            sequential=self._pipeline_config.sequential_scanners,
        )
        return executor.execute(scanner_names, context)

    def _execute_enrichers(
        self,
        issues: List[UnifiedIssue],
        context: ScanContext,
    ) -> List[UnifiedIssue]:
        """Execute enricher stage in configured order.

        Enrichers run sequentially, each receiving the output
        of the previous enricher.
        """
        # Import here to avoid circular imports
        from lucidscan.enrichers import get_enricher_plugin

        enriched = issues

        # Get enricher order from pipeline config, then from main config
        enricher_order = self._pipeline_config.enricher_order
        if not enricher_order:
            enricher_order = self._get_enricher_order_from_config()

        # Auto-add ai_explainer if AI is enabled and not already in list
        enricher_order = self._maybe_add_ai_enricher(enricher_order)

        for enricher_name in enricher_order:
            enricher = get_enricher_plugin(enricher_name)
            if not enricher:
                LOGGER.warning(
                    f"Enricher plugin '{enricher_name}' not found, skipping"
                )
                continue

            LOGGER.info(f"Running {enricher_name} enricher...")

            try:
                enriched = enricher.enrich(enriched, context)
                LOGGER.debug(f"{enricher_name}: processed {len(enriched)} issues")
            except Exception as e:
                LOGGER.error(f"Enricher {enricher_name} failed: {e}")
                # Continue with unenriched issues on failure

        return enriched

    def _get_enricher_order_from_config(self) -> List[str]:
        """Extract enricher order from config.

        Looks for pipeline.enrichers or enabled enrichers in config.
        """
        # Check for explicit pipeline ordering in config
        if hasattr(self._config, "pipeline") and self._config.pipeline:
            pipeline = self._config.pipeline
            if hasattr(pipeline, "enrichers") and pipeline.enrichers:
                return pipeline.enrichers

        # Fall back to enabled enrichers from enrichers config
        enabled = []
        for name, enricher_config in self._config.enrichers.items():
            if isinstance(enricher_config, dict):
                if enricher_config.get("enabled", True):
                    enabled.append(name)
            else:
                enabled.append(name)

        return enabled

    def _maybe_add_ai_enricher(self, enricher_order: List[str]) -> List[str]:
        """Auto-add ai_explainer enricher if AI is enabled.

        The AI enricher is added to the end of the pipeline if:
        - AI is enabled in config (ai.enabled=true or --ai flag)
        - ai_explainer is not already in the enricher list

        Args:
            enricher_order: Current enricher order list.

        Returns:
            Updated enricher order (may be a new list if modified).
        """
        ai_config = getattr(self._config, "ai", None)
        if not ai_config or not ai_config.enabled:
            return enricher_order

        if "ai_explainer" in enricher_order:
            return enricher_order

        # Create new list to avoid modifying original
        result = list(enricher_order) + ["ai_explainer"]
        LOGGER.debug("Auto-added ai_explainer to enricher pipeline")
        return result

    def _format_scanners_used(
        self,
        scanner_results: List[ScannerResult],
    ) -> List[Dict[str, Any]]:
        """Format scanner results for metadata."""
        return [
            {
                "name": r.scanner_name,
                "version": r.scanner_version,
                "domains": r.domains,
                "success": r.success,
                "error": r.error,
            }
            for r in scanner_results
        ]
