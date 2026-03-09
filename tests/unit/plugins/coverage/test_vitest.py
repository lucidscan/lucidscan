"""Unit tests for Vitest coverage plugin."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.coverage.vitest import VitestCoveragePlugin


class TestVitestCoveragePlugin:
    """Tests for VitestCoveragePlugin class."""

    def test_name(self) -> None:
        runner = VitestCoveragePlugin()
        assert runner.name == "vitest_coverage"

    def test_languages(self) -> None:
        runner = VitestCoveragePlugin()
        assert runner.languages == ["javascript", "typescript"]

    def test_domain(self) -> None:
        runner = VitestCoveragePlugin()
        assert runner.domain == ToolDomain.COVERAGE


class TestVitestCoverageBinaryFinding:
    """Tests for binary finding logic."""

    def test_find_in_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            plugin = VitestCoveragePlugin(project_root=project_root)
            binary = plugin.ensure_binary()
            assert binary == vitest_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/local/bin/vitest"
        plugin = VitestCoveragePlugin()
        binary = plugin.ensure_binary()
        assert binary == Path("/usr/local/bin/vitest")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        plugin = VitestCoveragePlugin()
        with pytest.raises(FileNotFoundError) as exc:
            plugin.ensure_binary()
        assert "Vitest is not installed" in str(exc.value)


class TestVitestCoverageGetVersion:
    """Tests for version detection."""

    def test_get_version_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            plugin = VitestCoveragePlugin(project_root=project_root)
            with patch(
                "lucidshark.plugins.coverage.base.get_cli_version",
                return_value="3.0.4",
            ):
                assert plugin.get_version() == "3.0.4"

    @patch("shutil.which", return_value=None)
    def test_get_version_unknown_when_not_found(self, mock_which: MagicMock) -> None:
        plugin = VitestCoveragePlugin()
        assert plugin.get_version() == "unknown"


class TestVitestMeasureCoverage:
    """Tests for coverage measurement flow."""

    def test_no_coverage_data_returns_no_data_issue(self) -> None:
        """Test that when no coverage report exists, a no-data issue is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            plugin = VitestCoveragePlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context)
            assert result.total_lines == 0
            assert result.tool == "vitest_coverage"
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"
            assert result.issues[0].source_tool == "vitest_coverage"

    def test_existing_summary_report_parsed(self) -> None:
        """Test that an existing coverage-summary.json is parsed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cov_dir = project_root / "coverage"
            cov_dir.mkdir()

            report = {
                "total": {
                    "lines": {"total": 100, "covered": 85, "pct": 85.0},
                    "statements": {"total": 100, "covered": 85, "pct": 85.0},
                    "branches": {"total": 20, "covered": 16, "pct": 80.0},
                    "functions": {"total": 10, "covered": 9, "pct": 90.0},
                },
            }
            (cov_dir / "coverage-summary.json").write_text(json.dumps(report))

            plugin = VitestCoveragePlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context)
            assert result.total_lines == 100
            assert result.covered_lines == 85
            assert len(result.issues) == 0


class TestVitestSummaryReportParsing:
    """Tests for coverage-summary.json parsing via base class."""

    def test_parse_summary_report(self) -> None:
        plugin = VitestCoveragePlugin()

        report = {
            "total": {
                "lines": {"total": 100, "covered": 80, "skipped": 0, "pct": 80.0},
                "statements": {"total": 120, "covered": 96, "skipped": 0, "pct": 80.0},
                "branches": {"total": 30, "covered": 20, "skipped": 0, "pct": 66.67},
                "functions": {"total": 25, "covered": 22, "skipped": 0, "pct": 88.0},
            },
            "/project/src/index.ts": {
                "lines": {"total": 50, "covered": 45, "skipped": 0, "pct": 90.0},
                "statements": {"total": 60, "covered": 54, "skipped": 0, "pct": 90.0},
                "branches": {"total": 15, "covered": 12, "skipped": 0, "pct": 80.0},
                "functions": {"total": 10, "covered": 9, "skipped": 0, "pct": 90.0},
            },
            "/project/src/utils.ts": {
                "lines": {"total": 50, "covered": 35, "skipped": 0, "pct": 70.0},
                "statements": {"total": 60, "covered": 42, "skipped": 0, "pct": 70.0},
                "branches": {"total": 15, "covered": 8, "skipped": 0, "pct": 53.33},
                "functions": {"total": 15, "covered": 13, "skipped": 0, "pct": 86.67},
            },
        }

        result = plugin._parse_istanbul_summary(report, Path("/project"), threshold=80.0)

        assert result.total_lines == 100
        assert result.covered_lines == 80
        assert result.percentage == 80.0
        assert result.passed is True
        assert len(result.issues) == 0
        assert len(result.files) == 2
        assert result.tool == "vitest_coverage"

    def test_parse_summary_below_threshold(self) -> None:
        plugin = VitestCoveragePlugin()

        report = {
            "total": {
                "lines": {"total": 100, "covered": 60, "skipped": 0, "pct": 60.0},
                "statements": {"total": 100, "covered": 60, "skipped": 0, "pct": 60.0},
                "branches": {"total": 20, "covered": 10, "skipped": 0, "pct": 50.0},
                "functions": {"total": 20, "covered": 15, "skipped": 0, "pct": 75.0},
            },
        }

        result = plugin._parse_istanbul_summary(report, Path("/project"), threshold=80.0)

        assert result.percentage == 60.0
        assert result.passed is False
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.source_tool == "vitest_coverage"
        assert issue.rule_id == "coverage_below_threshold"
        assert "60.0%" in issue.title
        assert "80.0%" in issue.title


class TestVitestFinalReportParsing:
    """Tests for coverage-final.json parsing via base class."""

    def test_parse_final_report(self) -> None:
        plugin = VitestCoveragePlugin()

        report = {
            "/project/src/index.ts": {
                "s": {"0": 5, "1": 3, "2": 0, "3": 10},
            },
            "/project/src/utils.ts": {
                "s": {"0": 1, "1": 0},
            },
        }

        result = plugin._parse_istanbul_final(report, Path("/project"), threshold=80.0)

        assert result.total_lines == 6  # 4 + 2
        assert result.covered_lines == 4  # 3 covered + 1 covered
        assert len(result.files) == 2
        assert result.tool == "vitest_coverage"

    def test_parse_final_report_missing_lines(self) -> None:
        plugin = VitestCoveragePlugin()

        report = {
            "/project/src/index.ts": {
                "s": {"0": 5, "1": 0, "2": 0, "3": 10},
            },
        }

        result = plugin._parse_istanbul_final(report, Path("/project"), threshold=80.0)

        file_cov = result.files["src/index.ts"]
        assert file_cov.covered_lines == 2
        assert file_cov.total_lines == 4
        assert sorted(file_cov.missing_lines) == [1, 2]


class TestVitestFindAndParseReport:
    """Tests for report discovery logic."""

    def test_finds_summary_report(self) -> None:
        plugin = VitestCoveragePlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cov_dir = project_root / "coverage"
            cov_dir.mkdir()

            report = {
                "total": {
                    "lines": {"total": 50, "covered": 40, "pct": 80.0},
                    "statements": {"total": 50, "covered": 40, "pct": 80.0},
                    "branches": {"total": 10, "covered": 8, "pct": 80.0},
                    "functions": {"total": 10, "covered": 8, "pct": 80.0},
                },
            }
            (cov_dir / "coverage-summary.json").write_text(json.dumps(report))

            result = plugin._find_and_parse_report(project_root, threshold=80.0)
            assert result.total_lines == 50
            assert result.covered_lines == 40

    def test_falls_back_to_final_report(self) -> None:
        plugin = VitestCoveragePlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cov_dir = project_root / "coverage"
            cov_dir.mkdir()

            report = {
                f"{tmpdir}/src/index.ts": {
                    "s": {"0": 5, "1": 3},
                },
            }
            (cov_dir / "coverage-final.json").write_text(json.dumps(report))

            result = plugin._find_and_parse_report(project_root, threshold=80.0)
            assert result.total_lines == 2

    def test_no_report_found(self) -> None:
        plugin = VitestCoveragePlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = plugin._find_and_parse_report(Path(tmpdir), threshold=80.0)
            assert result.total_lines == 0
            assert result.tool == "vitest_coverage"


class TestVitestCoverageIssue:
    """Tests for coverage issue creation (base class method)."""

    def test_high_severity_below_50(self) -> None:
        plugin = VitestCoveragePlugin()
        issue = plugin._create_coverage_issue(30.0, 80.0, 100, 30)
        assert issue.severity == Severity.HIGH

    def test_medium_severity(self) -> None:
        plugin = VitestCoveragePlugin()
        issue = plugin._create_coverage_issue(60.0, 80.0, 100, 60)
        assert issue.severity == Severity.MEDIUM

    def test_low_severity_near_threshold(self) -> None:
        plugin = VitestCoveragePlugin()
        issue = plugin._create_coverage_issue(75.0, 80.0, 100, 75)
        assert issue.severity == Severity.LOW

    def test_issue_metadata(self) -> None:
        plugin = VitestCoveragePlugin()
        issue = plugin._create_coverage_issue(60.0, 80.0, 200, 120)
        assert issue.metadata["coverage_percentage"] == 60.0
        assert issue.metadata["threshold"] == 80.0
        assert issue.metadata["total_lines"] == 200
        assert issue.metadata["covered_lines"] == 120
        assert issue.metadata["missing_lines"] == 80
        assert issue.metadata["gap_percentage"] == 20.0

    def test_issue_with_detailed_stats(self) -> None:
        plugin = VitestCoveragePlugin()
        issue = plugin._create_coverage_issue(
            60.0,
            80.0,
            100,
            60,
            statements={"total": 120, "covered": 72, "pct": 60.0},
            branches={"total": 30, "covered": 15, "pct": 50.0},
            functions={"total": 20, "covered": 14, "pct": 70.0},
        )
        assert "Statements:" in issue.description
        assert "Branches:" in issue.description
        assert "Functions:" in issue.description

    def test_issue_id_is_deterministic(self) -> None:
        plugin = VitestCoveragePlugin()
        issue1 = plugin._create_coverage_issue(60.0, 80.0, 100, 60)
        issue2 = plugin._create_coverage_issue(60.0, 80.0, 100, 60)
        assert issue1.id == issue2.id
        assert issue1.id.startswith("vitest_coverage-cov-")

    def test_issue_id_differs_for_different_coverage(self) -> None:
        plugin = VitestCoveragePlugin()
        issue1 = plugin._create_coverage_issue(60.0, 80.0, 100, 60)
        issue2 = plugin._create_coverage_issue(70.0, 80.0, 100, 70)
        assert issue1.id != issue2.id


class TestVitestNoDataIssue:
    """Tests for _create_no_data_issue."""

    def test_no_data_issue_fields(self) -> None:
        plugin = VitestCoveragePlugin()
        issue = plugin._create_no_data_issue()
        assert issue.id == "no-coverage-data-vitest_coverage"
        assert issue.rule_id == "no_coverage_data"
        assert issue.source_tool == "vitest_coverage"
        assert issue.severity == Severity.HIGH
        assert issue.domain == ToolDomain.COVERAGE
        assert "vitest" in issue.description.lower()
