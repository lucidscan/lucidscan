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

            with patch("lucidshark.plugins.coverage.istanbul.get_cli_version", return_value="15.1.0"):
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
    def test_measure_coverage_binary_not_found(self, mock_which: MagicMock) -> None:
        """Test measure_coverage when nyc not found."""
        plugin = IstanbulPlugin()
        context = MagicMock()
        context.project_root = Path("/project")

        result = plugin.measure_coverage(context, threshold=80.0)
        assert result.threshold == 80.0
        assert result.total_lines == 0

    def test_measure_coverage_run_tests_fails(self) -> None:
        """Test measure_coverage when test run fails."""
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

            with patch.object(plugin, "_run_tests_with_coverage", return_value=False):
                result = plugin.measure_coverage(context, threshold=80.0, run_tests=True)
                assert result.threshold == 80.0

    def test_measure_coverage_skip_test_run(self) -> None:
        """Test measure_coverage with run_tests=False."""
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

            with patch.object(plugin, "_generate_and_parse_report") as mock_report:
                mock_report.return_value = MagicMock(total_lines=100, covered_lines=85)
                plugin.measure_coverage(context, threshold=80.0, run_tests=False)
                mock_report.assert_called_once()


class TestIstanbulRunTestsWithCoverage:
    """Tests for running tests with NYC coverage."""

    def test_run_with_jest(self) -> None:
        """Test running nyc with jest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            nyc_bin = node_bin / "nyc"
            nyc_bin.touch()
            nyc_bin.chmod(0o755)
            jest_bin = node_bin / "jest"
            jest_bin.touch()
            jest_bin.chmod(0o755)

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            with patch("subprocess.run") as mock_run:
                result = plugin._run_tests_with_coverage(nyc_bin, context)
                assert result is True
                cmd = mock_run.call_args[0][0]
                assert str(nyc_bin) in cmd[0]

    def test_run_fallback_to_npm_test(self) -> None:
        """Test fallback to npm test when jest not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            nyc_bin = Path("/usr/local/bin/nyc")

            with patch("shutil.which", return_value=None):
                with patch("lucidshark.core.paths.resolve_node_bin", return_value=None):
                    with patch("subprocess.run") as mock_run:
                        result = plugin._run_tests_with_coverage(nyc_bin, context)
                        assert result is True
                        cmd = mock_run.call_args[0][0]
                        assert "npm" in cmd

    def test_run_tests_exception(self) -> None:
        """Test handling exception during test run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = IstanbulPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            with patch("shutil.which", return_value=None):
                with patch("lucidshark.core.paths.resolve_node_bin", return_value=None):
                    with patch("subprocess.run", side_effect=OSError("fail")):
                        result = plugin._run_tests_with_coverage(Path("/usr/bin/nyc"), context)
                        assert result is False


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
    """Tests for JSON report parsing."""

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

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage-summary.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

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

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage-summary.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

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

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage-summary.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert len(result.files) == 2
            assert "src/app.js" in result.files
            assert "src/utils.js" in result.files

    def test_parse_json_report_invalid_file(self) -> None:
        """Test parsing invalid JSON report file."""
        plugin = IstanbulPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage-summary.json"
            report_file.write_text("invalid json")

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)
            assert result.threshold == 80.0
            assert result.total_lines == 0


class TestIstanbulCoverageIssueCreation:
    """Tests for coverage issue creation."""

    def test_create_issue_high_severity(self) -> None:
        """Test creating issue with HIGH severity (< 50%)."""
        plugin = IstanbulPlugin()

        issue = plugin._create_coverage_issue(
            percentage=40.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=40,
            missing_lines=60,
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
            missing_lines=35,
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
            missing_lines=25,
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
            missing_lines=30,
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
            missing_lines=40,
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

        id1 = plugin._generate_issue_id(75.0, 80.0)
        id2 = plugin._generate_issue_id(75.0, 80.0)

        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Test different input produces different ID."""
        plugin = IstanbulPlugin()

        id1 = plugin._generate_issue_id(75.0, 80.0)
        id2 = plugin._generate_issue_id(60.0, 80.0)

        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID format starts with istanbul-."""
        plugin = IstanbulPlugin()

        issue_id = plugin._generate_issue_id(75.0, 80.0)

        assert issue_id.startswith("istanbul-")
