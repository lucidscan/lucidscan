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
from lucidscan.reporters.sarif_reporter import SARIFReporter


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
        lucidscan_version="0.1.6",
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
        assert data["metadata"]["lucidscan_version"] == "0.1.6"

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


class TestSARIFReporter:
    """Tests for SARIFReporter."""

    def test_name_property(self) -> None:
        reporter = SARIFReporter()
        assert reporter.name == "sarif"

    def test_report_empty_result(self, empty_result: ScanResult) -> None:
        reporter = SARIFReporter()
        output = io.StringIO()

        reporter.report(empty_result, output)

        data = json.loads(output.getvalue())
        assert data["version"] == "2.1.0"
        assert "$schema" in data
        assert len(data["runs"]) == 1
        assert data["runs"][0]["results"] == []

    def test_report_with_issues(self, sample_result: ScanResult) -> None:
        reporter = SARIFReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        assert data["version"] == "2.1.0"
        assert len(data["runs"]) == 1

        run = data["runs"][0]
        assert run["tool"]["driver"]["name"] == "lucidscan"
        assert run["tool"]["driver"]["version"] == "0.1.6"
        assert len(run["results"]) == 3

    def test_sarif_schema_url(self, sample_result: ScanResult) -> None:
        reporter = SARIFReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        assert data["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"

    def test_rules_extracted_from_issues(self, sample_result: ScanResult) -> None:
        reporter = SARIFReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        rules = data["runs"][0]["tool"]["driver"]["rules"]

        # Should have 3 unique rules (one per issue)
        assert len(rules) == 3

        # Each rule should have required fields
        for rule in rules:
            assert "id" in rule
            assert "shortDescription" in rule
            assert "defaultConfiguration" in rule
            assert "properties" in rule
            assert "security-severity" in rule["properties"]

    def test_result_has_rule_id(self, sample_result: ScanResult) -> None:
        reporter = SARIFReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        results = data["runs"][0]["results"]

        for result in results:
            assert "ruleId" in result
            assert "message" in result
            assert "text" in result["message"]
            assert "level" in result

    def test_result_has_fingerprint(self, sample_result: ScanResult) -> None:
        reporter = SARIFReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        results = data["runs"][0]["results"]

        for result in results:
            assert "fingerprints" in result
            assert "v1" in result["fingerprints"]

    def test_result_has_location(self, sample_result: ScanResult) -> None:
        reporter = SARIFReporter()
        output = io.StringIO()

        reporter.report(sample_result, output)

        data = json.loads(output.getvalue())
        results = data["runs"][0]["results"]

        # All sample issues have file_path
        for result in results:
            assert "locations" in result
            assert len(result["locations"]) == 1
            location = result["locations"][0]
            assert "physicalLocation" in location
            assert "artifactLocation" in location["physicalLocation"]
            assert "uri" in location["physicalLocation"]["artifactLocation"]

    def test_severity_mapping_critical(self) -> None:
        issue = UnifiedIssue(
            id="test-1",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.CRITICAL,
            title="Critical Issue",
            description="A critical issue",
            scanner_metadata={"vulnerability_id": "CVE-TEST-001"},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        sarif_result = data["runs"][0]["results"][0]
        rule = data["runs"][0]["tool"]["driver"]["rules"][0]

        assert sarif_result["level"] == "error"
        assert rule["properties"]["security-severity"] == "9.5"

    def test_severity_mapping_info(self) -> None:
        issue = UnifiedIssue(
            id="test-2",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.INFO,
            title="Info Issue",
            description="An informational issue",
            scanner_metadata={"vulnerability_id": "CVE-TEST-002"},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        sarif_result = data["runs"][0]["results"][0]
        rule = data["runs"][0]["tool"]["driver"]["rules"][0]

        assert sarif_result["level"] == "note"
        assert rule["properties"]["security-severity"] == "0.0"

    def test_rule_id_from_vulnerability_id(self) -> None:
        """Test that vulnerability_id is used as rule ID for Trivy issues."""
        issue = UnifiedIssue(
            id="trivy-123",
            scanner=ScanDomain.SCA,
            source_tool="trivy",
            severity=Severity.HIGH,
            title="CVE-2021-1234: Vulnerability",
            description="Test vulnerability",
            scanner_metadata={"vulnerability_id": "CVE-2021-1234"},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        assert data["runs"][0]["results"][0]["ruleId"] == "CVE-2021-1234"
        assert data["runs"][0]["tool"]["driver"]["rules"][0]["id"] == "CVE-2021-1234"

    def test_rule_id_from_check_id(self) -> None:
        """Test that check_id is used as rule ID for Checkov issues."""
        issue = UnifiedIssue(
            id="checkov-123",
            scanner=ScanDomain.IAC,
            source_tool="checkov",
            severity=Severity.MEDIUM,
            title="CKV_AWS_123: S3 bucket encryption",
            description="S3 bucket should have encryption enabled",
            scanner_metadata={"check_id": "CKV_AWS_123"},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        assert data["runs"][0]["results"][0]["ruleId"] == "CKV_AWS_123"

    def test_rule_id_from_opengrep_rule_id(self) -> None:
        """Test that rule_id is used as rule ID for OpenGrep issues."""
        issue = UnifiedIssue(
            id="opengrep-123",
            scanner=ScanDomain.SAST,
            source_tool="opengrep",
            severity=Severity.HIGH,
            title="python.security.sql-injection",
            description="SQL injection detected",
            scanner_metadata={"rule_id": "python.security.sql-injection"},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        assert data["runs"][0]["results"][0]["ruleId"] == "python.security.sql-injection"

    def test_duplicate_rules_deduplicated(self) -> None:
        """Test that duplicate rule IDs are deduplicated."""
        issues = [
            UnifiedIssue(
                id="trivy-1",
                scanner=ScanDomain.SCA,
                source_tool="trivy",
                severity=Severity.HIGH,
                title="CVE-2021-1234 in package A",
                description="Vulnerability in package A",
                file_path=Path("package.json"),
                scanner_metadata={"vulnerability_id": "CVE-2021-1234"},
            ),
            UnifiedIssue(
                id="trivy-2",
                scanner=ScanDomain.SCA,
                source_tool="trivy",
                severity=Severity.HIGH,
                title="CVE-2021-1234 in package B",
                description="Same CVE in package B",
                file_path=Path("requirements.txt"),
                scanner_metadata={"vulnerability_id": "CVE-2021-1234"},
            ),
        ]
        result = ScanResult(issues=issues)
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        rules = data["runs"][0]["tool"]["driver"]["rules"]
        results = data["runs"][0]["results"]

        # Should have only 1 rule (deduplicated) but 2 results
        assert len(rules) == 1
        assert len(results) == 2

    def test_issue_without_file_path(self) -> None:
        """Test that issues without file_path don't have locations."""
        issue = UnifiedIssue(
            id="test-1",
            scanner=ScanDomain.CONTAINER,
            source_tool="trivy",
            severity=Severity.HIGH,
            title="Container vulnerability",
            description="Vulnerability in container image",
            file_path=None,
            scanner_metadata={"vulnerability_id": "CVE-TEST-001"},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        sarif_result = data["runs"][0]["results"][0]

        # Should not have locations key
        assert "locations" not in sarif_result

    def test_issue_with_line_numbers(self) -> None:
        """Test that line numbers are included in region."""
        issue = UnifiedIssue(
            id="opengrep-1",
            scanner=ScanDomain.SAST,
            source_tool="opengrep",
            severity=Severity.HIGH,
            title="SQL Injection",
            description="Possible SQL injection",
            file_path=Path("src/db.py"),
            line_start=42,
            line_end=45,
            scanner_metadata={"rule_id": "python.security.sql-injection"},
        )
        result = ScanResult(issues=[issue])
        result.summary = result.compute_summary()

        reporter = SARIFReporter()
        output = io.StringIO()
        reporter.report(result, output)

        data = json.loads(output.getvalue())
        location = data["runs"][0]["results"][0]["locations"][0]
        region = location["physicalLocation"]["region"]

        assert region["startLine"] == 42
        assert region["endLine"] == 45


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

    def test_discover_sarif_reporter(self) -> None:
        from lucidscan.reporters import get_reporter_plugin

        reporter = get_reporter_plugin("sarif")
        assert reporter is not None
        assert reporter.name == "sarif"

    def test_list_available_reporters(self) -> None:
        from lucidscan.reporters import list_available_reporters

        reporters = list_available_reporters()
        assert "json" in reporters
        assert "table" in reporters
        assert "summary" in reporters
        assert "sarif" in reporters
