"""Unit tests for SARIF reporter plugin."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from lucidshark.core.models import (
    ScanDomain,
    ScanMetadata,
    ScanResult,
    ScanSummary,
    Severity,
    UnifiedIssue,
)
from lucidshark.plugins.reporters.sarif_reporter import (
    SARIF_SCHEMA,
    SARIF_VERSION,
    SEVERITY_MAP,
    SARIFReporter,
)


@pytest.fixture
def reporter() -> SARIFReporter:
    return SARIFReporter()


def _make_issue(
    rule_id: str = "CKV_AWS_18",
    severity: Severity = Severity.HIGH,
    domain: Any = ScanDomain.IAC,
    title: str = "CKV_AWS_18: S3 bucket logging",
    description: str = "Ensure S3 has logging enabled",
    file_path: Path | None = Path("main.tf"),
    line_start: int | None = 1,
    line_end: int | None = 10,
    documentation_url: str | None = None,
    recommendation: str | None = None,
    metadata: Dict[str, Any] | None = None,
) -> UnifiedIssue:
    return UnifiedIssue(
        id="test-id-001",
        domain=domain,
        source_tool="checkov",
        severity=severity,
        rule_id=rule_id,
        title=title,
        description=description,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        documentation_url=documentation_url,
        recommendation=recommendation,
        metadata=metadata or {},
    )


def _make_scan_result(issues: list[UnifiedIssue] | None = None) -> ScanResult:
    metadata = ScanMetadata(
        lucidshark_version="0.5.0",
        scan_started_at="2024-01-01T00:00:00",
        scan_finished_at="2024-01-01T00:00:05",
        duration_ms=5000,
        project_root="/project",
    )
    return ScanResult(
        issues=issues or [],
        metadata=metadata,
        summary=ScanSummary(total=len(issues or [])),
    )


# --- Properties ---


class TestSARIFReporterProperties:
    def test_name(self, reporter: SARIFReporter) -> None:
        assert reporter.name == "sarif"


# --- report ---


class TestSARIFReporterReport:
    def test_report_writes_valid_json(self, reporter: SARIFReporter) -> None:
        result = _make_scan_result([_make_issue()])
        output = io.StringIO()
        reporter.report(result, output)
        output.seek(0)
        sarif = json.loads(output.read())
        assert sarif["$schema"] == SARIF_SCHEMA
        assert sarif["version"] == SARIF_VERSION

    def test_report_empty_issues(self, reporter: SARIFReporter) -> None:
        result = _make_scan_result([])
        output = io.StringIO()
        reporter.report(result, output)
        output.seek(0)
        sarif = json.loads(output.read())
        assert sarif["runs"][0]["results"] == []
        assert sarif["runs"][0]["tool"]["driver"]["rules"] == []

    def test_report_ends_with_newline(self, reporter: SARIFReporter) -> None:
        result = _make_scan_result([])
        output = io.StringIO()
        reporter.report(result, output)
        output.seek(0)
        content = output.read()
        assert content.endswith("\n")


# --- _build_sarif ---


class TestSARIFBuildSarif:
    def test_structure(self, reporter: SARIFReporter) -> None:
        result = _make_scan_result([_make_issue()])
        sarif = reporter._build_sarif(result)
        assert "$schema" in sarif
        assert "version" in sarif
        assert len(sarif["runs"]) == 1
        run = sarif["runs"][0]
        assert "tool" in run
        assert "results" in run
        assert run["tool"]["driver"]["name"] == "lucidshark"
        assert run["tool"]["driver"]["version"] == "0.5.0"

    def test_no_metadata_uses_unknown_version(self, reporter: SARIFReporter) -> None:
        result = ScanResult(issues=[])
        sarif = reporter._build_sarif(result)
        assert sarif["runs"][0]["tool"]["driver"]["version"] == "unknown"

    def test_multiple_issues(self, reporter: SARIFReporter) -> None:
        issues = [
            _make_issue(rule_id="RULE1", title="Issue 1"),
            _make_issue(rule_id="RULE2", title="Issue 2"),
        ]
        result = _make_scan_result(issues)
        sarif = reporter._build_sarif(result)
        assert len(sarif["runs"][0]["results"]) == 2
        assert len(sarif["runs"][0]["tool"]["driver"]["rules"]) == 2


# --- _collect_rules ---


class TestSARIFCollectRules:
    def test_unique_rules(self, reporter: SARIFReporter) -> None:
        issues = [
            _make_issue(rule_id="RULE1", title="Issue 1"),
            _make_issue(rule_id="RULE1", title="Issue 1 duplicate"),
            _make_issue(rule_id="RULE2", title="Issue 2"),
        ]
        rules = reporter._collect_rules(issues)
        assert len(rules) == 2
        rule_ids = [r["id"] for r in rules]
        assert "RULE1" in rule_ids
        assert "RULE2" in rule_ids

    def test_empty_issues(self, reporter: SARIFReporter) -> None:
        rules = reporter._collect_rules([])
        assert rules == []


# --- _build_rule ---


class TestSARIFBuildRule:
    def test_basic_rule(self, reporter: SARIFReporter) -> None:
        issue = _make_issue()
        rule = reporter._build_rule(issue, "CKV_AWS_18")
        assert rule["id"] == "CKV_AWS_18"
        assert rule["shortDescription"]["text"] == issue.title
        assert rule["defaultConfiguration"]["level"] == "error"  # HIGH
        assert rule["properties"]["security-severity"] == "7.5"

    def test_rule_with_documentation_url(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(documentation_url="https://docs.example.com/rule")
        rule = reporter._build_rule(issue, "RULE1")
        assert rule["helpUri"] == "https://docs.example.com/rule"

    def test_rule_with_recommendation_url(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(recommendation="https://fix.example.com/rule")
        rule = reporter._build_rule(issue, "RULE1")
        assert rule["helpUri"] == "https://fix.example.com/rule"

    def test_rule_with_see_recommendation(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(recommendation="See: https://fix.example.com/rule")
        rule = reporter._build_rule(issue, "RULE1")
        assert rule["helpUri"] == "https://fix.example.com/rule"

    def test_rule_no_help_uri_for_non_url_recommendation(
        self, reporter: SARIFReporter
    ) -> None:
        issue = _make_issue(recommendation="Upgrade to latest version")
        rule = reporter._build_rule(issue, "RULE1")
        assert "helpUri" not in rule

    def test_rule_with_full_description(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(
            title="Short title",
            description="Long description with more details",
        )
        rule = reporter._build_rule(issue, "RULE1")
        assert "fullDescription" in rule
        assert rule["fullDescription"]["text"] == "Long description with more details"

    def test_rule_no_full_description_when_same_as_title(
        self, reporter: SARIFReporter
    ) -> None:
        issue = _make_issue(title="Same", description="Same")
        rule = reporter._build_rule(issue, "RULE1")
        assert "fullDescription" not in rule

    def test_rule_with_cwe_tags(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(metadata={"cwe": ["CWE-79", "CWE-80"]})
        rule = reporter._build_rule(issue, "RULE1")
        assert "tags" in rule["properties"]
        assert "CWE-79" in rule["properties"]["tags"]
        assert "CWE-80" in rule["properties"]["tags"]

    def test_rule_with_owasp_tags(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(metadata={"owasp": ["A03:2021"]})
        rule = reporter._build_rule(issue, "RULE1")
        assert "tags" in rule["properties"]
        assert "A03:2021" in rule["properties"]["tags"]

    def test_rule_with_string_cwe(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(metadata={"cwe": "CWE-79"})
        rule = reporter._build_rule(issue, "RULE1")
        assert "tags" in rule["properties"]
        assert "CWE-79" in rule["properties"]["tags"]

    def test_rule_with_string_owasp(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(metadata={"owasp": "A03:2021"})
        rule = reporter._build_rule(issue, "RULE1")
        assert "A03:2021" in rule["properties"]["tags"]

    def test_rule_severity_levels(self, reporter: SARIFReporter) -> None:
        for sev, expected in [
            (Severity.CRITICAL, "error"),
            (Severity.HIGH, "error"),
            (Severity.MEDIUM, "warning"),
            (Severity.LOW, "warning"),
            (Severity.INFO, "note"),
        ]:
            issue = _make_issue(severity=sev)
            rule = reporter._build_rule(issue, "RULE1")
            assert rule["defaultConfiguration"]["level"] == expected

    def test_see_recommendation_non_url(self, reporter: SARIFReporter) -> None:
        """Test See: prefix with non-URL value does not set helpUri."""
        issue = _make_issue(recommendation="See: the documentation for details")
        rule = reporter._build_rule(issue, "RULE1")
        assert "helpUri" not in rule


# --- _issue_to_result ---


class TestSARIFIssueToResult:
    def test_basic_result(self, reporter: SARIFReporter) -> None:
        issue = _make_issue()
        result = reporter._issue_to_result(issue)
        assert result["ruleId"] == "CKV_AWS_18"
        assert result["message"]["text"] == issue.description
        assert result["level"] == "error"
        assert result["fingerprints"]["v1"] == "test-id-001"

    def test_result_with_location(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(file_path=Path("main.tf"), line_start=5, line_end=10)
        result = reporter._issue_to_result(issue)
        assert "locations" in result
        loc = result["locations"][0]
        assert loc["physicalLocation"]["artifactLocation"]["uri"] == "main.tf"
        assert loc["physicalLocation"]["region"]["startLine"] == 5
        assert loc["physicalLocation"]["region"]["endLine"] == 10

    def test_result_without_file(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(file_path=None)
        result = reporter._issue_to_result(issue)
        assert "locations" not in result

    def test_result_uses_title_when_no_description(
        self, reporter: SARIFReporter
    ) -> None:
        issue = _make_issue(description="")
        result = reporter._issue_to_result(issue)
        # Falls back to title since description is falsy
        assert result["message"]["text"] == issue.title


# --- _build_location ---


class TestSARIFBuildLocation:
    def test_with_line_info(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(file_path=Path("src/file.py"), line_start=10, line_end=20)
        loc = reporter._build_location(issue)
        assert loc is not None
        assert loc["physicalLocation"]["region"]["startLine"] == 10
        assert loc["physicalLocation"]["region"]["endLine"] == 20

    def test_without_line_info(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(file_path=Path("src/file.py"), line_start=None)
        loc = reporter._build_location(issue)
        assert loc is not None
        assert "region" not in loc["physicalLocation"]

    def test_no_file_path(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(file_path=None)
        loc = reporter._build_location(issue)
        assert loc is None

    def test_start_line_only(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(
            file_path=Path("file.py"), line_start=5, line_end=None
        )
        loc = reporter._build_location(issue)
        assert loc is not None
        region = loc["physicalLocation"]["region"]
        assert region["startLine"] == 5
        assert "endLine" not in region

    def test_absolute_path(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(file_path=Path("/absolute/path/file.py"))
        loc = reporter._build_location(issue)
        assert loc is not None
        uri = loc["physicalLocation"]["artifactLocation"]["uri"]
        assert uri == "/absolute/path/file.py"


# --- _get_rule_id ---


class TestSARIFGetRuleId:
    def test_uses_rule_id_field(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(rule_id="CKV_AWS_18")
        assert reporter._get_rule_id(issue) == "CKV_AWS_18"

    def test_fallback_vulnerability_id(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(
            rule_id="",
            metadata={"vulnerability_id": "CVE-2024-1234"},
        )
        assert reporter._get_rule_id(issue) == "CVE-2024-1234"

    def test_fallback_rule_id_metadata(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(
            rule_id="",
            metadata={"rule_id": "python.lang.security.exec"},
        )
        assert reporter._get_rule_id(issue) == "python.lang.security.exec"

    def test_fallback_check_id_metadata(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(
            rule_id="",
            metadata={"check_id": "CKV2_AWS_1"},
        )
        assert reporter._get_rule_id(issue) == "CKV2_AWS_1"

    def test_fallback_construct_from_title(self, reporter: SARIFReporter) -> None:
        issue = _make_issue(
            rule_id="",
            title="Some Issue: with details",
            metadata={},
        )
        rule_id = reporter._get_rule_id(issue)
        assert rule_id == "checkov/Some Issue"


# --- _truncate ---


class TestSARIFTruncate:
    def test_short_text(self, reporter: SARIFReporter) -> None:
        assert reporter._truncate("short", 100) == "short"

    def test_exact_length(self, reporter: SARIFReporter) -> None:
        text = "a" * 100
        assert reporter._truncate(text, 100) == text

    def test_long_text(self, reporter: SARIFReporter) -> None:
        text = "a" * 200
        result = reporter._truncate(text, 100)
        assert len(result) == 100
        assert result.endswith("...")


# --- Severity mapping ---


class TestSARIFSeverityMap:
    def test_all_severities(self) -> None:
        assert SEVERITY_MAP[Severity.CRITICAL]["level"] == "error"
        assert SEVERITY_MAP[Severity.CRITICAL]["security-severity"] == "9.5"
        assert SEVERITY_MAP[Severity.HIGH]["level"] == "error"
        assert SEVERITY_MAP[Severity.MEDIUM]["level"] == "warning"
        assert SEVERITY_MAP[Severity.LOW]["level"] == "warning"
        assert SEVERITY_MAP[Severity.INFO]["level"] == "note"
        assert SEVERITY_MAP[Severity.INFO]["security-severity"] == "0.0"
