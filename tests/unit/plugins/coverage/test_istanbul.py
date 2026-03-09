"""Unit tests for Istanbul/NYC coverage plugin."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.coverage.istanbul import IstanbulPlugin


class TestIstanbulPlugin:
    """Tests for IstanbulPlugin class."""

    def test_name(self) -> None:
        """Test plugin name."""
        plugin = IstanbulPlugin()
        assert plugin.name == "istanbul"

    def test_languages(self) -> None:
        """Test supported languages."""
        plugin = IstanbulPlugin()
        assert plugin.languages == ["javascript", "typescript"]

    def test_domain(self) -> None:
        """Test domain is COVERAGE."""
        plugin = IstanbulPlugin()
        assert plugin.domain == ToolDomain.COVERAGE


class TestIstanbulBinaryFinding:
    """Tests for binary finding logic."""

    def test_find_in_node_modules(self) -> None:
        """Test finding nyc in project node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            nyc_bin = node_bin / "nyc"
            nyc_bin.touch()
            nyc_bin.chmod(0o755)

            plugin = IstanbulPlugin(project_root=project_root)
            binary = plugin.ensure_binary()

            assert binary == nyc_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        """Test finding nyc in system PATH."""
        mock_which.return_value = "/usr/local/bin/nyc"

        plugin = IstanbulPlugin()
        binary = plugin.ensure_binary()

        assert binary == Path("/usr/local/bin/nyc")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        """Test FileNotFoundError when nyc not found."""
        mock_which.return_value = None

        plugin = IstanbulPlugin()
        with pytest.raises(FileNotFoundError) as exc:
            plugin.ensure_binary()

        assert "NYC (Istanbul) is not installed" in str(exc.value)


class TestIstanbulGetVersion:
    """Tests for version detection."""

    def test_get_version_success(self) -> None:
        """Test getting NYC version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            nyc_bin = node_bin / "nyc"
            nyc_bin.touch()
            nyc_bin.chmod(0o755)

            plugin = IstanbulPlugin(project_root=project_root)

            with patch("lucidshark.plugins.coverage.base.get_cli_version", return_value="15.1.0"):
                version = plugin.get_version()
                assert version == "15.1.0"

    @patch("shutil.which", return_value=None)
    def test_get_version_unknown_when_not_found(self, mock_which: MagicMock) -> None:
        """Test version returns 'unknown' when nyc not found."""
        plugin = IstanbulPlugin()
        version = plugin.get_version()
        assert version == "unknown"


class TestIstanbulMeasureCoverage:
    """Tests for measure_coverage flow."""

    @patch("shutil.which", return_value=None)
    def test_measure_coverage_binary_not_found_no_direct_files(self, mock_which: MagicMock) -> None:
        """Test measure_coverage when nyc not found and no direct coverage files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            plugin = IstanbulPlugin()
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.threshold == 80.0
            assert result.total_lines == 0
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"

    def test_measure_coverage_reads_coverage_summary_json(self) -> None:
        """Test measure_coverage reads coverage/coverage-summary.json directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cov_dir = project_root / "coverage"
            cov_dir.mkdir()

            report = {
                "total": {
                    "lines": {"total": 100, "covered": 85, "pct": 85.0},
                    "statements": {"total": 100, "covered": 85, "pct": 85.0},
                    "branches": {"total": 50, "covered": 40, "pct": 80.0},
                    "functions": {"total": 20, "covered": 18, "pct": 90.0},
                },
                "src/app.js": {
                    "lines": {"total": 100, "covered": 85, "pct": 85.0},
                },
            }
            (cov_dir / "coverage-summary.json").write_text(json.dumps(report))

            # No nyc binary needed
            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 100
            assert result.covered_lines == 85
            assert result.passed is True
            assert len(result.files) == 1
            assert "src/app.js" in result.files

    def test_measure_coverage_reads_coverage_final_json(self) -> None:
        """Test measure_coverage reads coverage/coverage-final.json directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cov_dir = project_root / "coverage"
            cov_dir.mkdir()

            report = {
                f"{tmpdir}/src/index.js": {
                    "path": f"{tmpdir}/src/index.js",
                    "statementMap": {
                        "0": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 20}},
                        "1": {"start": {"line": 2, "column": 0}, "end": {"line": 2, "column": 20}},
                        "2": {"start": {"line": 5, "column": 0}, "end": {"line": 5, "column": 15}},
                    },
                    "s": {"0": 5, "1": 3, "2": 0},
                    "fnMap": {},
                    "f": {},
                    "branchMap": {},
                    "b": {},
                },
            }
            (cov_dir / "coverage-final.json").write_text(json.dumps(report))

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=50.0)
            assert result.total_lines == 3
            assert result.covered_lines == 2
            assert len(result.files) == 1
            file_cov = list(result.files.values())[0]
            assert file_cov.missing_lines == [5]

    def test_measure_coverage_prefers_direct_files_over_nyc_output(self) -> None:
        """Test that coverage/ files are preferred over .nyc_output/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create both coverage/ and .nyc_output/
            cov_dir = project_root / "coverage"
            cov_dir.mkdir()
            report = {
                "total": {
                    "lines": {"total": 200, "covered": 190, "pct": 95.0},
                    "statements": {"total": 200, "covered": 190, "pct": 95.0},
                    "branches": {"total": 100, "covered": 95, "pct": 95.0},
                    "functions": {"total": 40, "covered": 38, "pct": 95.0},
                },
            }
            (cov_dir / "coverage-summary.json").write_text(json.dumps(report))

            nyc_output = project_root / ".nyc_output"
            nyc_output.mkdir()
            (nyc_output / "data.json").write_text("{}")

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            # Should read from coverage/ directly, not invoke nyc report
            with patch("subprocess.run") as mock_run:
                result = plugin.measure_coverage(context, threshold=80.0)
                mock_run.assert_not_called()

            assert result.total_lines == 200
            assert result.covered_lines == 190

    def test_measure_coverage_no_coverage_or_nyc_output_returns_no_data_issue(self) -> None:
        """Test measure_coverage when neither coverage/ nor .nyc_output/ exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            nyc_bin = node_bin / "nyc"
            nyc_bin.touch()
            nyc_bin.chmod(0o755)

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 0
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"
            assert result.issues[0].source_tool == "istanbul"

    def test_measure_coverage_empty_nyc_output_returns_no_data_issue(self) -> None:
        """Test measure_coverage when .nyc_output directory is empty and no coverage/ files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            nyc_bin = node_bin / "nyc"
            nyc_bin.touch()
            nyc_bin.chmod(0o755)

            # Create empty .nyc_output directory (no coverage/ dir)
            (project_root / ".nyc_output").mkdir()

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 0
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"


class TestIstanbulGenerateAndParseReport:
    """Tests for report generation and parsing."""

    def test_generate_report_success(self) -> None:
        """Test successful report generation and parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            def fake_run(cmd, **kwargs):
                # Write coverage-summary.json to the report dir
                for arg in cmd:
                    if arg.startswith("--report-dir="):
                        report_dir = Path(arg.split("=", 1)[1])
                        report = {
                            "total": {
                                "lines": {"total": 100, "covered": 85, "pct": 85.0},
                                "statements": {"total": 100, "covered": 85, "pct": 85.0},
                                "branches": {"total": 50, "covered": 40, "pct": 80.0},
                                "functions": {"total": 20, "covered": 18, "pct": 90.0},
                            }
                        }
                        (report_dir / "coverage-summary.json").write_text(json.dumps(report))
                result = MagicMock()
                result.returncode = 0
                return result

            nyc_bin = Path("/usr/local/bin/nyc")
            with patch("subprocess.run", side_effect=fake_run):
                result = plugin._generate_and_parse_report(nyc_bin, context, 80.0)
                assert result.total_lines == 100
                assert result.covered_lines == 85

    def test_generate_report_nonzero_exit(self) -> None:
        """Test handling non-zero exit from nyc report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Error"

            nyc_bin = Path("/usr/local/bin/nyc")
            with patch("subprocess.run", return_value=mock_result):
                result = plugin._generate_and_parse_report(nyc_bin, context, 80.0)
                assert result.threshold == 80.0
                assert result.total_lines == 0

    def test_generate_report_exception(self) -> None:
        """Test handling exception during report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            nyc_bin = Path("/usr/local/bin/nyc")
            with patch("subprocess.run", side_effect=OSError("fail")):
                result = plugin._generate_and_parse_report(nyc_bin, context, 80.0)
                assert result.threshold == 80.0


class TestIstanbulJsonParsing:
    """Tests for JSON report parsing via base class."""

    def test_parse_json_report_below_threshold(self) -> None:
        """Test parsing JSON report when below threshold."""
        plugin = IstanbulPlugin()

        report = {
            "total": {
                "lines": {"total": 100, "covered": 70, "pct": 70.0},
                "statements": {"total": 120, "covered": 84, "pct": 70.0},
                "branches": {"total": 30, "covered": 21, "pct": 70.0},
                "functions": {"total": 20, "covered": 14, "pct": 70.0},
            },
            "src/main.js": {
                "lines": {"total": 50, "covered": 35, "pct": 70.0},
            },
        }

        result = plugin._parse_istanbul_summary(report, Path("/tmp/project"), threshold=80.0)

        assert result.total_lines == 100
        assert result.covered_lines == 70
        assert result.percentage == 70.0
        assert result.passed is False
        assert len(result.issues) == 1

        issue = result.issues[0]
        assert "70.0%" in issue.title
        assert "80.0%" in issue.title
        assert issue.domain == ToolDomain.COVERAGE
        assert issue.source_tool == "istanbul"

    def test_parse_json_report_above_threshold(self) -> None:
        """Test parsing JSON report when above threshold."""
        plugin = IstanbulPlugin()

        report = {
            "total": {
                "lines": {"total": 100, "covered": 90, "pct": 90.0},
                "statements": {"total": 100, "covered": 90, "pct": 90.0},
                "branches": {"total": 50, "covered": 45, "pct": 90.0},
                "functions": {"total": 20, "covered": 18, "pct": 90.0},
            },
        }

        result = plugin._parse_istanbul_summary(report, Path("/tmp/project"), threshold=80.0)

        assert result.percentage == 90.0
        assert result.passed is True
        assert len(result.issues) == 0

    def test_parse_json_report_with_per_file(self) -> None:
        """Test parsing JSON report with per-file coverage."""
        plugin = IstanbulPlugin()

        report = {
            "total": {
                "lines": {"total": 200, "covered": 180, "pct": 90.0},
                "statements": {"total": 200, "covered": 180, "pct": 90.0},
                "branches": {"total": 50, "covered": 45, "pct": 90.0},
                "functions": {"total": 30, "covered": 27, "pct": 90.0},
            },
            "src/app.js": {
                "lines": {"total": 100, "covered": 90, "pct": 90.0},
            },
            "src/utils.js": {
                "lines": {"total": 100, "covered": 90, "pct": 90.0},
            },
        }

        result = plugin._parse_istanbul_summary(report, Path("/tmp/project"), threshold=80.0)

        assert len(result.files) == 2
        assert "src/app.js" in result.files
        assert "src/utils.js" in result.files


class TestIstanbulFinalReportParsing:
    """Tests for _parse_istanbul_final (coverage-final.json)."""

    def test_parse_final_report_basic(self) -> None:
        """Test parsing a basic coverage-final.json file."""
        plugin = IstanbulPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = {
                f"{tmpdir}/src/index.js": {
                    "path": f"{tmpdir}/src/index.js",
                    "statementMap": {
                        "0": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 20}},
                        "1": {"start": {"line": 3, "column": 0}, "end": {"line": 3, "column": 20}},
                        "2": {"start": {"line": 5, "column": 0}, "end": {"line": 5, "column": 15}},
                        "3": {"start": {"line": 7, "column": 0}, "end": {"line": 7, "column": 10}},
                    },
                    "s": {"0": 10, "1": 5, "2": 0, "3": 0},
                    "fnMap": {},
                    "f": {},
                    "branchMap": {},
                    "b": {},
                },
            }

            result = plugin._parse_istanbul_final(report, project_root, threshold=80.0)

            assert result.total_lines == 4
            assert result.covered_lines == 2
            assert result.tool == "istanbul"

            file_cov = list(result.files.values())[0]
            assert file_cov.total_lines == 4
            assert file_cov.covered_lines == 2
            assert file_cov.missing_lines == [5, 7]

    def test_parse_final_report_multiple_files(self) -> None:
        """Test parsing coverage-final.json with multiple files."""
        plugin = IstanbulPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = {
                f"{tmpdir}/src/a.js": {
                    "statementMap": {
                        "0": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 10}},
                    },
                    "s": {"0": 1},
                },
                f"{tmpdir}/src/b.js": {
                    "statementMap": {
                        "0": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 10}},
                    },
                    "s": {"0": 0},
                },
            }

            result = plugin._parse_istanbul_final(report, project_root, threshold=80.0)

            assert result.total_lines == 2
            assert result.covered_lines == 1
            assert len(result.files) == 2
            # 50% < 80% threshold => issue
            assert len(result.issues) == 1

    def test_parse_final_report_all_covered(self) -> None:
        """Test parsing coverage-final.json when all statements are covered."""
        plugin = IstanbulPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = {
                f"{tmpdir}/src/a.js": {
                    "statementMap": {
                        "0": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 10}},
                    },
                    "s": {"0": 5},
                },
            }

            result = plugin._parse_istanbul_final(report, project_root, threshold=80.0)
            assert result.total_lines == 1
            assert result.covered_lines == 1
            assert len(result.issues) == 0


class TestIstanbulCoverageIssueCreation:
    """Tests for coverage issue creation (base class method)."""

    def test_create_issue_high_severity(self) -> None:
        """Test creating issue with HIGH severity (< 50%)."""
        plugin = IstanbulPlugin()
        issue = plugin._create_coverage_issue(
            percentage=40.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=40,
            statements={"total": 100, "covered": 40, "pct": 40.0},
            branches={"total": 50, "covered": 20, "pct": 40.0},
            functions={"total": 20, "covered": 8, "pct": 40.0},
        )
        assert issue.severity == Severity.HIGH
        assert "40.0%" in issue.title
        assert "80.0%" in issue.title

    def test_create_issue_medium_severity(self) -> None:
        """Test creating issue with MEDIUM severity."""
        plugin = IstanbulPlugin()
        issue = plugin._create_coverage_issue(
            percentage=65.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=65,
            statements={"total": 100, "covered": 65, "pct": 65.0},
            branches={"total": 50, "covered": 32, "pct": 65.0},
            functions={"total": 20, "covered": 13, "pct": 65.0},
        )
        assert issue.severity == Severity.MEDIUM

    def test_create_issue_low_severity(self) -> None:
        """Test creating issue with LOW severity (close to threshold)."""
        plugin = IstanbulPlugin()
        issue = plugin._create_coverage_issue(
            percentage=75.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=75,
            statements={"total": 100, "covered": 75, "pct": 75.0},
            branches={"total": 50, "covered": 37, "pct": 75.0},
            functions={"total": 20, "covered": 15, "pct": 75.0},
        )
        assert issue.severity == Severity.LOW

    def test_create_issue_includes_all_metrics(self) -> None:
        """Test issue description includes all coverage metrics."""
        plugin = IstanbulPlugin()
        issue = plugin._create_coverage_issue(
            percentage=70.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=70,
            statements={"total": 100, "covered": 70, "pct": 70.0},
            branches={"total": 50, "covered": 35, "pct": 70.0},
            functions={"total": 20, "covered": 14, "pct": 70.0},
        )
        desc = issue.description
        assert "Lines:" in desc or "Statements:" in desc
        assert issue.recommendation is not None

    def test_create_issue_metadata(self) -> None:
        """Test issue metadata contains all relevant data."""
        plugin = IstanbulPlugin()
        issue = plugin._create_coverage_issue(
            percentage=60.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=60,
            statements={"total": 100, "covered": 60, "pct": 60.0},
            branches={"total": 50, "covered": 30, "pct": 60.0},
            functions={"total": 20, "covered": 12, "pct": 60.0},
        )
        metadata = issue.metadata
        assert metadata["coverage_percentage"] == 60.0
        assert metadata["threshold"] == 80.0
        assert metadata["gap_percentage"] == 20.0
        assert metadata["total_lines"] == 100


class TestIstanbulIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        """Test same input produces same ID."""
        plugin = IstanbulPlugin()
        id1 = plugin._generate_coverage_issue_id(75.0, 80.0)
        id2 = plugin._generate_coverage_issue_id(75.0, 80.0)
        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Test different input produces different ID."""
        plugin = IstanbulPlugin()
        id1 = plugin._generate_coverage_issue_id(75.0, 80.0)
        id2 = plugin._generate_coverage_issue_id(60.0, 80.0)
        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID format starts with istanbul-cov-."""
        plugin = IstanbulPlugin()
        issue_id = plugin._generate_coverage_issue_id(75.0, 80.0)
        assert issue_id.startswith("istanbul-cov-")


class TestIstanbulNoDataIssue:
    """Tests for _create_no_data_issue."""

    def test_no_data_issue_fields(self) -> None:
        """Test no-data issue has correct fields."""
        plugin = IstanbulPlugin()
        issue = plugin._create_no_data_issue()
        assert issue.id == "no-coverage-data-istanbul"
        assert issue.rule_id == "no_coverage_data"
        assert issue.source_tool == "istanbul"
        assert issue.severity == Severity.HIGH
        assert issue.domain == ToolDomain.COVERAGE
        assert "istanbul" in issue.description.lower()
        assert "coverage/" in issue.description
        assert ".nyc_output/" in issue.description
