"""Unit tests for reporter plugins."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from lucidscan.core.models import (
    ScanDomain,
    ScanMetadata,
    ScanResult,
    ScanSummary,
    Severity,
    UnifiedIssue,
)
from lucidscan.reporters.json_reporter import JSONReporter
from lucidscan.reporters.table_reporter import TableReporter
from lucidscan.reporters.summary_reporter import SummaryReporter


@pytest.fixture
def sample_issues() -> list[UnifiedIssue]:
    """Create sample issues for testing."""
    return [
        UnifiedIssue(
            id="trivy-abc123",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.CRITICAL,
            title="CVE-2021-1234: Critical vulnerability in lodash",
            description="A critical vulnerability exists in lodash.",
            file_path=Path("package.json"),
            dependency="lodash@4.17.15 (npm)",
            recommendation="Upgrade lodash to version 4.17.21",
            scanner_metadata={
                "vulnerability_id": "CVE-2021-1234",
                "pkg_name": "lodash",
                "installed_version": "4.17.15",
                "fixed_version": "4.17.21",
            },
        ),
        UnifiedIssue(
            id="trivy-def456",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.HIGH,
            title="CVE-2021-5678: High severity issue",
            description="A high severity vulnerability.",
            file_path=Path("package.json"),
            dependency="express@4.17.0 (npm)",
            recommendation="Upgrade express to version 4.18.0",
            scanner_metadata={
                "vulnerability_id": "CVE-2021-5678",
                "pkg_name": "express",
                "installed_version": "4.17.0",
                "fixed_version": "4.18.0",
            },
        ),
        UnifiedIssue(
            id="trivy-ghi789",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.MEDIUM,
            title="CVE-2021-9999: Medium severity issue",
            description="A medium severity vulnerability.",
            file_path=Path("requirements.txt"),
            dependency="django@2.2.0 (pip)",
            recommendation="Upgrade django to version 3.0.0",
            scanner_metadata={
                "vulnerability_id": "CVE-2021-9999",
                "pkg_name": "django",
                "installed_version": "2.2.0",
                "fixed_version": "3.0.0",
            },
        ),
    ]


@pytest.fixture
def sample_result(sample_issues: list[UnifiedIssue]) -> ScanResult:
    """Create a sample scan result with issues."""
    result = ScanResult(issues=sample_issues)
    result.summary = result.compute_summary()
    result.metadata = ScanMetadata(
        lucidscan_version="0.1.5",
        scan_started_at="2025-01-01T10:00:00Z",
        scan_finished_at="2025-01-01T10:00:05Z",
        duration_ms=5000,
        project_root="/path/to/project",
        scanners_used=[{"name": "trivy", "version": "0.68.1"}],
    )
    return result


@pytest.fixture
def empty_result() -> ScanResult:
    """Create an empty scan result."""
    result = ScanResult(issues=[])
    result.summary = result.compute_summary()
    return result


class TestJSONReporter:
    """Tests for JSONReporter."""

    def test_name_property(self) -> None:
        reporter = JSONReporter()
        assert reporter.name == "json"

    def test_report_empty_result(self, empty_result: ScanResult) -> None:
        reporter = JSONReporter()
        output = io.StringIO()

        reporter.report(empty_result, output)

        data = json.loads(output.getvalue())
        assert data["schema_version"] == "1.0"
        assert data["issues"] == []
        assert data["summary"]["total"] == 0

    def test_report_with_issues(self, sample_result: ScanResult) -> None:
        reporter = JSONReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        assert data["schema_version"] == "1.0"
        assert len(data["issues"]) == 3
        assert data["summary"]["total"] == 3
        assert data["metadata"]["lucidscan_version"] == "0.1.5"

    def test_issue_serialization(self, sample_result: ScanResult) -> None:
        reporter = JSONReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        issue = data["issues"][0]

        assert "id" in issue
        assert "scanner" in issue
        assert "source_tool" in issue
        assert "severity" in issue
        assert "title" in issue
        assert "description" in issue
        assert "scanner_metadata" in issue


class TestTableReporter:
    """Tests for TableReporter."""

    def test_name_property(self) -> None:
        reporter = TableReporter()
        assert reporter.name == "table"

    def test_report_empty_result(self, empty_result: ScanResult) -> None:
        reporter = TableReporter()
        output = io.StringIO()

        reporter.report(empty_result, output)

        content = output.getvalue()
        assert "No issues found." in content

    def test_report_with_issues(self, sample_result: ScanResult) -> None:
        reporter = TableReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        content = output.getvalue()
        # Check header
        assert "SEVERITY" in content
        assert "ID" in content
        assert "DEPENDENCY" in content
        assert "TITLE" in content
        # Check issues are present
        assert "CRITICAL" in content
        assert "HIGH" in content
        assert "MEDIUM" in content
        assert "CVE-2021-1234" in content
        # Check summary
        assert "Total:" in content

    def test_issues_sorted_by_severity(self, sample_result: ScanResult) -> None:
        reporter = TableReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        content = output.getvalue()
        # CRITICAL should appear before HIGH, which should appear before MEDIUM
        critical_pos = content.find("CRITICAL")
        high_pos = content.find("HIGH")
        medium_pos = content.find("MEDIUM")

        assert critical_pos < high_pos < medium_pos

    def test_long_title_truncated(self) -> None:
        """Test that long titles are truncated."""
        long_title = "A" * 100  # 100 character title
        issue = UnifiedIssue(
            id="test-1",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.HIGH,
            title=long_title,
            description="Test",
            scanner_metadata={},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = TableReporter()
        output = io.StringIO()
        reporter.report(result, output)

        content = output.getvalue()
        # Title should be truncated to 60 chars
        assert "A" * 60 in content
        assert "A" * 100 not in content

    def test_summary_with_severity_breakdown(self, sample_result: ScanResult) -> None:
        reporter = TableReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        content = output.getvalue()
        assert "By severity:" in content


class TestSummaryReporter:
    """Tests for SummaryReporter."""

    def test_name_property(self) -> None:
        reporter = SummaryReporter()
        assert reporter.name == "summary"

    def test_report_empty_result(self, empty_result: ScanResult) -> None:
        reporter = SummaryReporter()
        output = io.StringIO()

        reporter.report(empty_result, output)

        content = output.getvalue()
        assert "Total issues: 0" in content

    def test_report_with_issues(self, sample_result: ScanResult) -> None:
        reporter = SummaryReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        content = output.getvalue()
        assert "Total issues: 3" in content

    def test_severity_breakdown(self, sample_result: ScanResult) -> None:
        reporter = SummaryReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        content = output.getvalue()
        assert "By severity:" in content
        assert "CRITICAL: 1" in content
        assert "HIGH: 1" in content
        assert "MEDIUM: 1" in content

    def test_scanner_domain_breakdown(self, sample_result: ScanResult) -> None:
        reporter = SummaryReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        content = output.getvalue()
        assert "By scanner domain:" in content
        assert "SCA: 3" in content

    def test_metadata_displayed(self, sample_result: ScanResult) -> None:
        reporter = SummaryReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        content = output.getvalue()
        assert "Scan duration: 5000ms" in content
        assert "Project: /path/to/project" in content

    def test_no_summary_available(self) -> None:
        """Test output when summary is None."""
        result = ScanResult(issues=[])
        result.summary = None

        reporter = SummaryReporter()
        output = io.StringIO()
        reporter.report(result, output)

        content = output.getvalue()
        assert "No summary available." in content


class TestReporterDiscovery:
    """Tests for reporter plugin discovery."""

    def test_discover_json_reporter(self) -> None:
        from lucidscan.reporters import get_reporter_plugin

        reporter = get_reporter_plugin("json")
        assert reporter is not None
        assert reporter.name == "json"

    def test_discover_table_reporter(self) -> None:
        from lucidscan.reporters import get_reporter_plugin

        reporter = get_reporter_plugin("table")
        assert reporter is not None
        assert reporter.name == "table"

    def test_discover_summary_reporter(self) -> None:
        from lucidscan.reporters import get_reporter_plugin

        reporter = get_reporter_plugin("summary")
        assert reporter is not None
        assert reporter.name == "summary"

    def test_list_available_reporters(self) -> None:
        from lucidscan.reporters import list_available_reporters

        reporters = list_available_reporters()
        assert "json" in reporters
        assert "table" in reporters
        assert "summary" in reporters
