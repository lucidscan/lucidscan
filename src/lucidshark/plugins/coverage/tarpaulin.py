"""Cargo-tarpaulin coverage plugin.

Tarpaulin is a code coverage tool for Rust projects.
https://github.com/xd009642/tarpaulin
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
)
from lucidshark.plugins.rust_utils import (
    ensure_cargo_subcommand,
    get_cargo_version,
)

LOGGER = get_logger(__name__)


class TarpaulinPlugin(CoveragePlugin):
    """Tarpaulin plugin for Rust code coverage analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize TarpaulinPlugin.

        Args:
            project_root: Optional project root for tool resolution.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "tarpaulin"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["rust"]

    def get_version(self) -> str:
        """Get tarpaulin version."""
        return get_cargo_version("tarpaulin")

    def ensure_binary(self) -> Path:
        """Ensure cargo-tarpaulin is available.

        Returns:
            Path to cargo binary.

        Raises:
            FileNotFoundError: If tarpaulin is not available.
        """
        return ensure_cargo_subcommand(
            "tarpaulin",
            "cargo-tarpaulin not available. Install with: cargo install cargo-tarpaulin",
        )

    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
    ) -> CoverageResult:
        """Parse existing tarpaulin coverage report.

        Looks for an existing tarpaulin report in target/tarpaulin/.
        If no report is found, returns an error issue directing the user to
        run the testing domain first.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).

        Returns:
            CoverageResult with coverage statistics.
        """
        # Check for Cargo.toml
        if not (context.project_root / "Cargo.toml").exists():
            LOGGER.info("No Cargo.toml found, skipping tarpaulin")
            return CoverageResult(threshold=threshold, tool="tarpaulin")

        # Check if tarpaulin report exists
        report_path = context.project_root / "target" / "tarpaulin" / "tarpaulin-report.json"
        if not report_path.exists():
            LOGGER.warning("No tarpaulin report found at %s", report_path)
            result = CoverageResult(threshold=threshold, tool="tarpaulin")
            result.issues.append(self._create_no_data_issue())
            return result

        LOGGER.info("Using existing tarpaulin report...")

        # Parse report
        result = self._parse_report(context.project_root, threshold)

        # If report parsing returned an empty result (failure), add no-data issue
        if result.total_lines == 0 and not result.issues:
            result.issues.append(self._create_no_data_issue())

        return result

    def _parse_report(
        self, project_root: Path, threshold: float
    ) -> CoverageResult:
        """Parse tarpaulin JSON report.

        Args:
            project_root: Project root directory.
            threshold: Coverage percentage threshold.

        Returns:
            CoverageResult with parsed data.
        """
        report_path = project_root / "target" / "tarpaulin" / "tarpaulin-report.json"

        if not report_path.exists():
            LOGGER.warning("Tarpaulin report not found at %s", report_path)
            return CoverageResult(threshold=threshold, tool="tarpaulin")

        try:
            data = json.loads(report_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            LOGGER.error(f"Failed to parse tarpaulin report: {e}")
            return CoverageResult(threshold=threshold, tool="tarpaulin")

        total_coverable = 0
        total_covered = 0

        result = CoverageResult(threshold=threshold, tool="tarpaulin")

        # Parse files from report
        files = data if isinstance(data, list) else data.get("files", [])

        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue

            file_path_str = file_entry.get("path", "")
            if not file_path_str:
                continue

            traces = file_entry.get("traces", [])
            coverable = len(traces)
            covered = sum(1 for t in traces if isinstance(t, dict) and t.get("stats", {}).get("Line", 0) > 0)

            # Also check for simpler format
            if "covered" in file_entry and "coverable" in file_entry:
                covered = file_entry["covered"]
                coverable = file_entry["coverable"]

            total_coverable += coverable
            total_covered += covered

            # Find missing lines
            missing_lines = []
            for trace in traces:
                if isinstance(trace, dict) and trace.get("stats", {}).get("Line", 0) == 0:
                    line_num = trace.get("line", 0)
                    if line_num:
                        missing_lines.append(line_num)

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            file_coverage = FileCoverage(
                file_path=file_path,
                total_lines=coverable,
                covered_lines=covered,
                missing_lines=missing_lines,
            )
            result.files[str(file_path)] = file_coverage

        result.total_lines = total_coverable
        result.covered_lines = total_covered
        result.missing_lines = total_coverable - total_covered

        # Generate issue if below threshold
        percentage = result.percentage
        if percentage < threshold:
            issue = self._create_coverage_issue(
                percentage, threshold, total_coverable, total_covered
            )
            result.issues.append(issue)

        LOGGER.info(
            f"Tarpaulin coverage: {percentage:.1f}% ({total_covered}/{total_coverable} lines) "
            f"- threshold: {threshold}%"
        )

        return result

