"""Summary reporter plugin for lucidshark."""

from __future__ import annotations

from typing import IO, List

from lucidshark.core.models import ScanResult
from lucidshark.plugins.reporters.base import ReporterPlugin


class SummaryReporter(ReporterPlugin):
    """Reporter plugin that outputs a brief scan summary.

    Produces a concise summary with:
    - Total issue count
    - Breakdown by severity
    - Breakdown by scanner domain
    - Scan duration and project info
    """

    @property
    def name(self) -> str:
        return "summary"

    def report(self, result: ScanResult, output: IO[str]) -> None:
        """Format scan result as a summary and write to output.

        Args:
            result: The scan result to format.
            output: Output stream to write to.
        """
        lines = self._format_summary(result)
        output.write("\n".join(lines))
        output.write("\n")

    def _format_summary(self, result: ScanResult) -> List[str]:
        """Format scan result as a brief summary."""
        lines: List[str] = []

        if result.summary:
            # total is active issues count, ignored_total is separately tracked
            if result.summary.ignored_total > 0:
                lines.append(
                    f"Total issues: {result.summary.total} "
                    f"({result.summary.ignored_total} ignored)"
                )
            else:
                lines.append(f"Total issues: {result.summary.total}")

            if result.summary.by_severity:
                lines.append("\nBy severity:")
                for sev in ["critical", "high", "medium", "low", "info"]:
                    count = result.summary.by_severity.get(sev, 0)
                    if count > 0:
                        lines.append(f"  {sev.upper()}: {count}")

            if result.summary.by_scanner:
                lines.append("\nBy domain:")
                for domain, count in result.summary.by_scanner.items():
                    lines.append(f"  {domain.upper()}: {count}")
        else:
            lines.append("All checks passed. No issues found.")

        # Coverage summary
        if result.coverage_summary:
            cs = result.coverage_summary
            status = "PASSED" if cs.passed else "FAILED"
            lines.append(f"\nCoverage: {cs.coverage_percentage:.1f}% ({status})")
            lines.append(f"  Threshold: {cs.threshold}%")
            lines.append(f"  Lines: {cs.covered_lines}/{cs.total_lines} covered")
            if cs.tests_total > 0:
                lines.append(
                    f"  Tests: {cs.tests_passed} passed, {cs.tests_failed} failed, "
                    f"{cs.tests_skipped} skipped"
                )

        # Duplication summary
        if result.duplication_summary:
            ds = result.duplication_summary
            status = "PASSED" if ds.passed else "FAILED"
            lines.append(f"\nDuplication: {ds.duplication_percent:.1f}% ({status})")
            lines.append(f"  Threshold: {ds.threshold}%")
            lines.append(f"  Blocks: {ds.duplicate_blocks}, Lines: {ds.duplicate_lines}")

        if result.metadata:
            lines.append(f"\nScan duration: {result.metadata.duration_ms}ms")
            lines.append(f"Project: {result.metadata.project_root}")

        return lines
