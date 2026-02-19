"""Table reporter plugin for lucidshark."""

from __future__ import annotations

from collections import defaultdict
from typing import IO, List

from lucidshark.core.models import ScanResult, Severity, UnifiedIssue
from lucidshark.plugins.reporters.base import ReporterPlugin

# Domains that use FILE:LINE layout instead of DEPENDENCY layout
_CODE_DOMAINS = {"linting", "type_checking", "testing", "duplication", "coverage"}

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


class TableReporter(ReporterPlugin):
    """Reporter plugin that outputs scan results as a human-readable table.

    Produces a formatted table suitable for terminal display with:
    - Issues grouped by domain
    - Domain-appropriate columns (FILE:LINE for code, DEPENDENCY for SCA)
    - Severity-sorted issues within each group
    - Summary statistics at the bottom
    """

    @property
    def name(self) -> str:
        return "table"

    def report(self, result: ScanResult, output: IO[str]) -> None:
        """Format scan result as a table and write to output.

        Args:
            result: The scan result to format.
            output: Output stream to write to.
        """
        lines = self._format_table(result)
        output.write("\n".join(lines))
        output.write("\n")

    def _format_table(self, result: ScanResult) -> List[str]:
        """Format scan result as a human-readable table."""
        lines: List[str] = []

        if not result.issues:
            lines.append("No issues found.")
            return lines

        # Group issues by domain
        by_domain: dict[str, List[UnifiedIssue]] = defaultdict(list)
        for issue in result.issues:
            by_domain[issue.domain.value].append(issue)

        # Sort each group by severity
        for domain_issues in by_domain.values():
            domain_issues.sort(key=lambda x: _SEVERITY_ORDER.get(x.severity, 5))

        # Render each domain group
        first = True
        for domain, domain_issues in by_domain.items():
            if not first:
                lines.append("")
            first = False

            lines.append(f"--- {domain.upper()} ({len(domain_issues)} issues) ---")

            if domain in _CODE_DOMAINS:
                self._render_code_table(domain_issues, lines)
            else:
                self._render_dependency_table(domain_issues, lines)

        # Summary
        lines.append("")
        lines.append("-" * 100)
        if result.summary:
            lines.append(f"Total: {result.summary.total} issues")
            sev_parts = [
                f"{sev}: {count}"
                for sev, count in result.summary.by_severity.items()
            ]
            if sev_parts:
                lines.append(f"By severity: {', '.join(sev_parts)}")

        # Coverage summary
        if result.coverage_summary:
            cs = result.coverage_summary
            status = "PASSED" if cs.passed else "FAILED"
            lines.append(f"Coverage: {cs.coverage_percentage:.1f}% (threshold: {cs.threshold}%) - {status}")

        # Duplication summary
        if result.duplication_summary:
            ds = result.duplication_summary
            status = "PASSED" if ds.passed else "FAILED"
            lines.append(f"Duplication: {ds.duplication_percent:.1f}% (threshold: {ds.threshold}%) - {status}")

        return lines

    def _render_code_table(
        self, issues: List[UnifiedIssue], lines: List[str]
    ) -> None:
        """Render issues using FILE:LINE + RULE + DESCRIPTION columns."""
        lines.append(f"{'SEVERITY':<10} {'FILE:LINE':<35} {'RULE':<20} {'DESCRIPTION'}")
        lines.append("-" * 100)

        for issue in issues:
            sev = issue.severity.value.upper()
            location = issue.file_path.as_posix() if issue.file_path else ""
            if issue.line_start is not None:
                location = f"{location}:{issue.line_start}"
            location = location[:35]
            rule = (issue.rule_id or "")[:20]
            title = issue.title[:60] if len(issue.title) > 60 else issue.title
            lines.append(f"{sev:<10} {location:<35} {rule:<20} {title}")

    def _render_dependency_table(
        self, issues: List[UnifiedIssue], lines: List[str]
    ) -> None:
        """Render issues using DEPENDENCY column (for SCA/security domains)."""
        lines.append(f"{'SEVERITY':<10} {'ID':<20} {'DEPENDENCY':<40} {'TITLE'}")
        lines.append("-" * 100)

        for issue in issues:
            sev = issue.severity.value.upper()
            rule_id = issue.rule_id or issue.metadata.get("vulnerability_id", issue.id)
            rule_id = rule_id[:20]
            dep = (issue.dependency or "")[:40]
            title = issue.title[:60] if len(issue.title) > 60 else issue.title
            lines.append(f"{sev:<10} {rule_id:<20} {dep:<40} {title}")
