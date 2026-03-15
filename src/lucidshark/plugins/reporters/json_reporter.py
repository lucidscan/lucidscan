"""JSON reporter plugin for lucidshark."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, IO

from lucidshark.core.models import ScanResult, UnifiedIssue
from lucidshark.plugins.reporters.base import ReporterPlugin


class JSONReporter(ReporterPlugin):
    """Reporter plugin that outputs scan results as JSON.

    Produces machine-readable JSON output containing:
    - Schema version
    - All issues with normalized fields
    - Scan metadata (timestamps, scanners used)
    - Summary statistics
    """

    @property
    def name(self) -> str:
        return "json"

    def report(self, result: ScanResult, output: IO[str]) -> None:
        """Format scan result as JSON and write to output.

        Args:
            result: The scan result to format.
            output: Output stream to write to.
        """
        formatted = self._format_result(result)
        json.dump(formatted, output, indent=2)
        output.write("\n")

    def _format_result(self, result: ScanResult) -> Dict[str, Any]:
        """Convert ScanResult to a JSON-serializable dict."""
        output: Dict[str, Any] = {
            "schema_version": result.schema_version,
            "issues": [self._issue_to_dict(issue) for issue in result.issues],
        }

        if result.metadata:
            output["metadata"] = asdict(result.metadata)

        if result.summary:
            output["summary"] = asdict(result.summary)

        if result.coverage_summary:
            output["coverage_summary"] = asdict(result.coverage_summary)

        if result.duplication_summary:
            output["duplication_summary"] = asdict(result.duplication_summary)

        return output

    def _issue_to_dict(self, issue: UnifiedIssue) -> Dict[str, Any]:
        """Convert a UnifiedIssue to a JSON-serializable dict."""
        return {
            "id": issue.id,
            "domain": issue.domain.value,
            "source_tool": issue.source_tool,
            "severity": issue.severity.value,
            "rule_id": issue.rule_id,
            "title": issue.title,
            "description": issue.description,
            "recommendation": issue.recommendation,
            "documentation_url": issue.documentation_url,
            "file_path": str(issue.file_path) if issue.file_path else None,
            "line_start": issue.line_start,
            "line_end": issue.line_end,
            "column_start": issue.column_start,
            "column_end": issue.column_end,
            "code_snippet": issue.code_snippet,
            "fixable": issue.fixable,
            "suggested_fix": issue.suggested_fix,
            "dependency": issue.dependency,
            "iac_resource": issue.iac_resource,
            "ignored": issue.ignored,
            "ignore_reason": issue.ignore_reason,
            "metadata": issue.metadata,
        }
