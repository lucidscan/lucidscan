"""Cargo-tarpaulin coverage plugin.

Tarpaulin is a code coverage tool for Rust projects.
https://github.com/xd009642/tarpaulin
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from lucidshark.core.logging import get_logger
from lucidshark.core.models import ScanContext
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
    TestStatistics,
)
from lucidshark.plugins.rust_utils import (
    ensure_cargo_subcommand,
    get_cargo_version,
)
from lucidshark.plugins.utils import create_coverage_threshold_issue

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
        run_tests: bool = True,
    ) -> CoverageResult:
        """Run tarpaulin coverage analysis.

        Args:
            context: Scan context with paths and configuration.
            threshold: Coverage percentage threshold (default 80%).
            run_tests: Whether to run tests if no existing coverage data exists.

        Returns:
            CoverageResult with coverage statistics.
        """
        try:
            cargo = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return CoverageResult(threshold=threshold, tool="tarpaulin")

        # Check for Cargo.toml
        if not (context.project_root / "Cargo.toml").exists():
            LOGGER.info("No Cargo.toml found, skipping tarpaulin")
            return CoverageResult(threshold=threshold, tool="tarpaulin")

        test_stats: Optional[TestStatistics] = None

        # Check if tarpaulin report already exists
        report_path = context.project_root / "target" / "tarpaulin" / "tarpaulin-report.json"
        report_exists = report_path.exists()

        if run_tests and not report_exists:
            LOGGER.info("Running tests with tarpaulin coverage...")
            success, test_stats = self._run_tarpaulin(cargo, context)
            if not success:
                LOGGER.warning("Failed to run tarpaulin")
                return CoverageResult(threshold=threshold, tool="tarpaulin")
        elif report_exists:
            LOGGER.info("Using existing tarpaulin report...")

        # Parse report
        result = self._parse_report(context.project_root, threshold)
        result.test_stats = test_stats

        return result

    def _run_tarpaulin(
        self,
        cargo: Path,
        context: ScanContext,
    ) -> Tuple[bool, Optional[TestStatistics]]:
        """Run cargo tarpaulin.

        Args:
            cargo: Path to cargo binary.
            context: Scan context.

        Returns:
            Tuple of (success, test_stats).
        """
        output_dir = context.project_root / "target" / "tarpaulin"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(cargo),
            "tarpaulin",
            "--out", "json",
            "--output-dir", str(output_dir),
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="tarpaulin",
                stream_handler=context.stream_handler,
                timeout=600,
            )
            test_stats = self._parse_test_output(result.stdout + "\n" + result.stderr)
            return True, test_stats
        except subprocess.TimeoutExpired:
            LOGGER.warning("Tarpaulin timed out after 600 seconds")
            return False, None
        except Exception as e:
            # Tarpaulin may return non-zero on test failures but still produce coverage
            LOGGER.debug(f"Tarpaulin completed with: {e}")
            return True, TestStatistics()

    def _parse_test_output(self, output: str) -> TestStatistics:
        """Parse test statistics from tarpaulin output.

        Args:
            output: Combined stdout/stderr from tarpaulin.

        Returns:
            TestStatistics with parsed counts.
        """
        stats = TestStatistics()

        # Parse test summary: "test result: ok. 5 passed; 0 failed; 0 ignored"
        pattern = (
            r"test result: (?:ok|FAILED)\.\s+"
            r"(\d+)\s+passed;\s+"
            r"(\d+)\s+failed;\s+"
            r"(\d+)\s+ignored"
        )

        for match in re.finditer(pattern, output):
            stats.passed += int(match.group(1))
            stats.failed += int(match.group(2))
            stats.skipped += int(match.group(3))

        stats.total = stats.passed + stats.failed + stats.skipped + stats.errors

        return stats

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
            issue = create_coverage_threshold_issue(
                source_tool="tarpaulin",
                percentage=percentage,
                threshold=threshold,
                total_lines=total_coverable,
                covered_lines=total_covered,
                missing_lines=total_coverable - total_covered,
            )
            result.issues.append(issue)

        LOGGER.info(
            f"Tarpaulin coverage: {percentage:.1f}% ({total_covered}/{total_coverable} lines) "
            f"- threshold: {threshold}%"
        )

        return result
