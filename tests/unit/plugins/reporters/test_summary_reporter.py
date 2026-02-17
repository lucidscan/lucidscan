"""Unit tests for Summary reporter plugin."""

from __future__ import annotations

import io

import pytest

from lucidshark.core.models import (
    CoverageSummary,
    DuplicationSummary,
    ScanMetadata,
    ScanResult,
    ScanSummary,
)
from lucidshark.plugins.reporters.summary_reporter import SummaryReporter


@pytest.fixture
def reporter() -> SummaryReporter:
    return SummaryReporter()


def _make_metadata() -> ScanMetadata:
    return ScanMetadata(
        lucidshark_version="0.5.0",
        scan_started_at="2024-01-01T00:00:00",
        scan_finished_at="2024-01-01T00:00:05",
        duration_ms=5000,
        project_root="/project",
    )


# --- Properties ---


class TestSummaryReporterProperties:
    def test_name(self, reporter: SummaryReporter) -> None:
        assert reporter.name == "summary"


# --- report ---


class TestSummaryReporterReport:
    def test_report_writes_to_output(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            summary=ScanSummary(total=5),
            metadata=_make_metadata(),
        )
        output = io.StringIO()
        reporter.report(result, output)
        output.seek(0)
        content = output.read()
        assert "Total issues: 5" in content

    def test_report_ends_with_newline(self, reporter: SummaryReporter) -> None:
        result = ScanResult(metadata=_make_metadata())
        output = io.StringIO()
        reporter.report(result, output)
        output.seek(0)
        content = output.read()
        assert content.endswith("\n")


# --- _format_summary ---


class TestSummaryFormatSummary:
    def test_no_summary(self, reporter: SummaryReporter) -> None:
        result = ScanResult()
        lines = reporter._format_summary(result)
        assert any("No issues found" in line for line in lines)

    def test_total_issues(self, reporter: SummaryReporter) -> None:
        result = ScanResult(summary=ScanSummary(total=42))
        lines = reporter._format_summary(result)
        assert "Total issues: 42" in lines[0]

    def test_severity_breakdown(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            summary=ScanSummary(
                total=10,
                by_severity={
                    "critical": 2,
                    "high": 3,
                    "medium": 4,
                    "low": 1,
                },
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "By severity:" in text
        assert "CRITICAL: 2" in text
        assert "HIGH: 3" in text
        assert "MEDIUM: 4" in text
        assert "LOW: 1" in text

    def test_zero_severity_hidden(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            summary=ScanSummary(
                total=2,
                by_severity={"critical": 0, "high": 2},
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "CRITICAL" not in text
        assert "HIGH: 2" in text

    def test_scanner_breakdown(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            summary=ScanSummary(
                total=5,
                by_scanner={"sca": 3, "iac": 2},
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "By domain:" in text
        assert "SCA: 3" in text
        assert "IAC: 2" in text

    def test_metadata(self, reporter: SummaryReporter) -> None:
        result = ScanResult(metadata=_make_metadata())
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Scan duration: 5000ms" in text
        assert "Project: /project" in text

    def test_no_metadata(self, reporter: SummaryReporter) -> None:
        result = ScanResult(summary=ScanSummary(total=0))
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Scan duration" not in text

    def test_coverage_summary_passed(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            coverage_summary=CoverageSummary(
                coverage_percentage=85.5,
                threshold=80.0,
                total_lines=1000,
                covered_lines=855,
                missing_lines=145,
                passed=True,
                tests_total=50,
                tests_passed=48,
                tests_failed=1,
                tests_skipped=1,
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Coverage: 85.5% (PASSED)" in text
        assert "Threshold: 80.0%" in text
        assert "Lines: 855/1000 covered" in text
        assert "Tests: 48 passed, 1 failed, 1 skipped" in text

    def test_coverage_summary_failed(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            coverage_summary=CoverageSummary(
                coverage_percentage=60.0,
                threshold=80.0,
                total_lines=1000,
                covered_lines=600,
                missing_lines=400,
                passed=False,
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Coverage: 60.0% (FAILED)" in text

    def test_coverage_no_tests(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            coverage_summary=CoverageSummary(
                coverage_percentage=90.0,
                threshold=80.0,
                total_lines=100,
                covered_lines=90,
                missing_lines=10,
                passed=True,
                tests_total=0,
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Coverage: 90.0% (PASSED)" in text
        assert "Tests:" not in text

    def test_duplication_summary_passed(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            duplication_summary=DuplicationSummary(
                files_analyzed=50,
                total_lines=5000,
                duplicate_blocks=3,
                duplicate_lines=45,
                duplication_percent=0.9,
                threshold=10.0,
                passed=True,
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Duplication: 0.9% (PASSED)" in text
        assert "Threshold: 10.0%" in text
        assert "Blocks: 3, Lines: 45" in text

    def test_duplication_summary_failed(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            duplication_summary=DuplicationSummary(
                files_analyzed=50,
                total_lines=5000,
                duplicate_blocks=20,
                duplicate_lines=800,
                duplication_percent=16.0,
                threshold=10.0,
                passed=False,
            )
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Duplication: 16.0% (FAILED)" in text

    def test_full_report(self, reporter: SummaryReporter) -> None:
        result = ScanResult(
            summary=ScanSummary(
                total=5,
                by_severity={"high": 3, "medium": 2},
                by_scanner={"sast": 5},
            ),
            metadata=_make_metadata(),
            coverage_summary=CoverageSummary(
                coverage_percentage=85.0,
                threshold=80.0,
                total_lines=1000,
                covered_lines=850,
                passed=True,
            ),
            duplication_summary=DuplicationSummary(
                duplication_percent=5.0,
                threshold=10.0,
                duplicate_blocks=2,
                duplicate_lines=30,
                passed=True,
            ),
        )
        lines = reporter._format_summary(result)
        text = "\n".join(lines)
        assert "Total issues: 5" in text
        assert "HIGH: 3" in text
        assert "SAST: 5" in text
        assert "Coverage: 85.0% (PASSED)" in text
        assert "Duplication: 5.0% (PASSED)" in text
        assert "Scan duration: 5000ms" in text
