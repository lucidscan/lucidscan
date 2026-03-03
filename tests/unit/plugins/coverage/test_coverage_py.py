"""Unit tests for coverage.py plugin."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.coverage.base import CoverageResult
from lucidshark.plugins.coverage.coverage_py import CoveragePyPlugin
from lucidshark.plugins.utils import coverage_has_source_config


class TestCoveragePyPlugin:
    """Tests for CoveragePyPlugin class."""

    def test_name(self) -> None:
        """Test plugin name."""
        plugin = CoveragePyPlugin()
        assert plugin.name == "coverage_py"

    def test_languages(self) -> None:
        """Test supported languages."""
        plugin = CoveragePyPlugin()
        assert plugin.languages == ["python"]

    def test_domain(self) -> None:
        """Test domain is COVERAGE."""
        plugin = CoveragePyPlugin()
        assert plugin.domain == ToolDomain.COVERAGE


class TestCoveragePyBinaryFinding:
    """Tests for binary finding logic."""

    def test_find_in_venv(self) -> None:
        """Test finding coverage in project .venv."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            coverage_bin = venv_bin / "coverage"
            coverage_bin.touch()
            coverage_bin.chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)
            binary = plugin.ensure_binary()

            assert binary == coverage_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        """Test finding coverage in system PATH."""
        mock_which.return_value = "/usr/local/bin/coverage"

        plugin = CoveragePyPlugin()
        binary = plugin.ensure_binary()

        assert binary == Path("/usr/local/bin/coverage")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        """Test FileNotFoundError when coverage not found."""
        mock_which.return_value = None

        plugin = CoveragePyPlugin()
        with pytest.raises(FileNotFoundError) as exc:
            plugin.ensure_binary()

        assert "coverage is not installed" in str(exc.value)


class TestCoveragePyGetVersion:
    """Tests for version detection."""

    def test_get_version_success(self) -> None:
        """Test getting coverage.py version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            coverage_bin = venv_bin / "coverage"
            coverage_bin.touch()
            coverage_bin.chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)

            with patch("lucidshark.plugins.coverage.coverage_py.get_cli_version", return_value="7.4.0"):
                version = plugin.get_version()
                assert version == "7.4.0"

    @patch("shutil.which", return_value=None)
    def test_get_version_unknown_when_not_found(self, mock_which: MagicMock) -> None:
        """Test version returns 'unknown' when coverage not found."""
        plugin = CoveragePyPlugin()
        version = plugin.get_version()
        assert version == "unknown"


class TestCoveragePyMeasureCoverage:
    """Tests for measure_coverage flow."""

    @patch("shutil.which", return_value=None)
    def test_measure_coverage_binary_not_found(self, mock_which: MagicMock) -> None:
        """Test measure_coverage when coverage not found."""
        plugin = CoveragePyPlugin()
        context = MagicMock()
        context.project_root = Path("/project")

        result = plugin.measure_coverage(context, threshold=80.0)
        assert result.threshold == 80.0
        assert result.tool == "coverage_py"
        assert result.total_lines == 0

    def test_measure_coverage_run_tests_fails(self) -> None:
        """Test measure_coverage when test run fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            coverage_bin = venv_bin / "coverage"
            coverage_bin.touch()
            coverage_bin.chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            with patch.object(plugin, "_run_tests_with_coverage", return_value=(False, None)):
                result = plugin.measure_coverage(context, threshold=80.0, run_tests=True)
                assert result.threshold == 80.0
                assert result.tool == "coverage_py"

    def test_measure_coverage_skip_test_run(self) -> None:
        """Test measure_coverage with run_tests=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            coverage_bin = venv_bin / "coverage"
            coverage_bin.touch()
            coverage_bin.chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            with patch.object(plugin, "_generate_and_parse_report") as mock_report:
                mock_report.return_value = MagicMock(test_stats=None)
                plugin.measure_coverage(context, threshold=80.0, run_tests=False)
                mock_report.assert_called_once()

    def test_measure_coverage_includes_test_stats(self) -> None:
        """Test that test_stats from run are included in result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            coverage_bin = venv_bin / "coverage"
            coverage_bin.touch()
            coverage_bin.chmod(0o755)

            from lucidshark.plugins.coverage.base import CoverageResult, TestStatistics

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            test_stats = TestStatistics(total=10, passed=10, failed=0)

            with patch.object(plugin, "_run_tests_with_coverage", return_value=(True, test_stats)):
                with patch.object(plugin, "_generate_and_parse_report") as mock_report:
                    mock_report.return_value = CoverageResult(
                        total_lines=100, covered_lines=85, threshold=80.0, tool="coverage_py"
                    )
                    result = plugin.measure_coverage(context, threshold=80.0, run_tests=True)
                    assert result.test_stats is not None
                    assert result.test_stats.total == 10

    def test_measure_coverage_fails_when_tests_fail(self) -> None:
        """Test that coverage fails when tests have failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            coverage_bin = venv_bin / "coverage"
            coverage_bin.touch()
            coverage_bin.chmod(0o755)

            from lucidshark.plugins.coverage.base import TestStatistics

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root

            test_stats = TestStatistics(total=10, passed=9, failed=1)

            with patch.object(plugin, "_run_tests_with_coverage", return_value=(True, test_stats)):
                result = plugin.measure_coverage(context, threshold=80.0, run_tests=True)
                assert result.test_stats is not None
                assert result.test_stats.failed == 1
                assert result.passed is False
                assert len(result.issues) == 1
                assert result.issues[0].rule_id == "tests_failed"


class TestCoveragePyDetectSourceDirectory:
    """Tests for source directory detection."""

    def test_detect_src_with_package(self) -> None:
        """Test detecting src/ directory with Python package inside."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pkg_dir = project_root / "src" / "mypackage"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").touch()

            plugin = CoveragePyPlugin()
            result = plugin._detect_source_directory(project_root)
            assert result == "src/mypackage"

    def test_detect_src_fallback(self) -> None:
        """Test detecting src/ directory without package inside."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()

            plugin = CoveragePyPlugin()
            result = plugin._detect_source_directory(project_root)
            assert result == "src"

    def test_detect_root_package(self) -> None:
        """Test detecting package at root level matching project name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "my-project"
            project_root.mkdir()
            pkg_dir = project_root / "my_project"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").touch()

            plugin = CoveragePyPlugin()
            result = plugin._detect_source_directory(project_root)
            assert result == "my_project"

    def test_detect_none_when_nothing_found(self) -> None:
        """Test returns None when no source directory found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = CoveragePyPlugin()
            result = plugin._detect_source_directory(project_root)
            assert result is None

    def test_detect_from_pyproject_toml(self) -> None:
        """Test detecting source directory from pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pyproject = project_root / "pyproject.toml"
            pyproject.write_text("""
[tool.setuptools.packages.find]
where = ["lib"]
""")

            plugin = CoveragePyPlugin()
            result = plugin._detect_source_directory(project_root)
            assert result == "lib"


class TestCoveragePyRunTestsWithCoverage:
    """Tests for running tests with coverage."""

    def test_run_with_venv_pytest(self) -> None:
        """Test running coverage with venv pytest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            pytest_bin = venv_bin / "pytest"
            pytest_bin.touch()
            pytest_bin.chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            coverage_bin = venv_bin / "coverage"

            mock_result = MagicMock()
            mock_result.stdout = "5 passed in 0.10s"
            mock_result.stderr = ""

            with patch("lucidshark.plugins.coverage.coverage_py.run_with_streaming", return_value=mock_result):
                success, stats = plugin._run_tests_with_coverage(coverage_bin, context)
                assert success is True
                assert stats is not None
                assert stats.passed == 5

    def test_run_with_system_pytest(self) -> None:
        """Test running coverage with system pytest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            mock_result = MagicMock()
            mock_result.stdout = "3 passed in 0.05s"
            mock_result.stderr = ""

            with patch("shutil.which", return_value="/usr/bin/pytest"):
                with patch("lucidshark.plugins.coverage.coverage_py.run_with_streaming", return_value=mock_result):
                    success, stats = plugin._run_tests_with_coverage(Path("/usr/bin/coverage"), context)
                    assert success is True

    def test_run_pytest_not_found(self) -> None:
        """Test handling when pytest is not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("shutil.which", return_value=None):
                success, stats = plugin._run_tests_with_coverage(Path("/usr/bin/coverage"), context)
                assert success is False
                assert stats is None

    def test_run_tests_exception(self) -> None:
        """Test handling exception during test execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            pytest_bin = venv_bin / "pytest"
            pytest_bin.touch()
            pytest_bin.chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("lucidshark.plugins.coverage.coverage_py.run_with_streaming", side_effect=Exception("fail")):
                success, stats = plugin._run_tests_with_coverage(Path("/usr/bin/coverage"), context)
                assert success is False
                assert stats is None

    def test_run_with_source_directory(self) -> None:
        """Test that --source is added when source directory is detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            pytest_bin = venv_bin / "pytest"
            pytest_bin.touch()
            pytest_bin.chmod(0o755)

            # Create source package
            src_pkg = project_root / "src" / "myapp"
            src_pkg.mkdir(parents=True)
            (src_pkg / "__init__.py").touch()

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            mock_result = MagicMock()
            mock_result.stdout = "1 passed in 0.01s"
            mock_result.stderr = ""

            with patch("lucidshark.plugins.coverage.coverage_py.run_with_streaming", return_value=mock_result) as mock_run:
                plugin._run_tests_with_coverage(Path("/usr/bin/coverage"), context)
                cmd = mock_run.call_args[1]["cmd"] if "cmd" in mock_run.call_args[1] else mock_run.call_args[0][0]
                assert "--source" in cmd
                assert "src/myapp" in cmd


class TestCoveragePyParsePytestOutput:
    """Tests for parsing pytest output."""

    def test_parse_all_passed(self) -> None:
        """Test parsing output with all tests passed."""
        plugin = CoveragePyPlugin()

        output = "===== 9 passed in 0.12s ====="
        stats = plugin._parse_pytest_output(output)

        assert stats.total == 9
        assert stats.passed == 9
        assert stats.failed == 0

    def test_parse_mixed_results(self) -> None:
        """Test parsing output with mixed results."""
        plugin = CoveragePyPlugin()

        output = "===== 1 failed, 5 passed, 2 skipped in 0.15s ====="
        stats = plugin._parse_pytest_output(output)

        assert stats.total == 8
        assert stats.passed == 5
        assert stats.failed == 1
        assert stats.skipped == 2

    def test_parse_with_errors(self) -> None:
        """Test parsing output with errors."""
        plugin = CoveragePyPlugin()

        output = "===== 1 error, 3 passed in 0.10s ====="
        stats = plugin._parse_pytest_output(output)

        assert stats.total == 4
        assert stats.passed == 3
        assert stats.errors == 1

    def test_parse_no_summary(self) -> None:
        """Test parsing output without summary line."""
        plugin = CoveragePyPlugin()

        output = "some random output"
        stats = plugin._parse_pytest_output(output)

        assert stats.total == 0
        assert stats.passed == 0


class TestCoveragePyGenerateAndParseReport:
    """Tests for report generation and parsing."""

    def test_generate_report_success(self) -> None:
        """Test successful report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            call_count = [0]

            def fake_run(**kwargs):
                call_count[0] += 1
                cmd = kwargs.get("cmd", [])
                # Find the output file path
                if "json" in cmd:
                    idx = cmd.index("-o")
                    report_path = Path(cmd[idx + 1])
                    report = {
                        "totals": {
                            "num_statements": 100,
                            "covered_lines": 85,
                            "missing_lines": 15,
                            "excluded_lines": 0,
                            "percent_covered": 85.0,
                        },
                        "files": {},
                    }
                    report_path.write_text(json.dumps(report))
                result = MagicMock()
                result.returncode = 0
                result.stderr = ""
                return result

            with patch("lucidshark.plugins.coverage.coverage_py.run_with_streaming", side_effect=fake_run):
                result = plugin._generate_and_parse_report(Path("/usr/bin/coverage"), context, 80.0)
                assert result.total_lines == 100
                assert result.covered_lines == 85

    def test_generate_report_nonzero_exit(self) -> None:
        """Test handling non-zero exit from coverage json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "No data collected"

            with patch("lucidshark.plugins.coverage.coverage_py.run_with_streaming", return_value=mock_result):
                result = plugin._generate_and_parse_report(Path("/usr/bin/coverage"), context, 80.0)
                assert result.threshold == 80.0
                assert result.tool == "coverage_py"

    def test_generate_report_exception(self) -> None:
        """Test handling exception during report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = CoveragePyPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("lucidshark.plugins.coverage.coverage_py.run_with_streaming", side_effect=Exception("fail")):
                result = plugin._generate_and_parse_report(Path("/usr/bin/coverage"), context, 80.0)
                assert result.threshold == 80.0


class TestCoveragePyJsonParsing:
    """Tests for JSON report parsing."""

    def test_parse_json_report_below_threshold(self) -> None:
        """Test parsing JSON report when below threshold."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 100,
                "covered_lines": 75,
                "missing_lines": 25,
                "excluded_lines": 0,
                "percent_covered": 75.0,
            },
            "files": {
                "src/main.py": {
                    "summary": {
                        "num_statements": 50,
                        "covered_lines": 35,
                        "excluded_lines": 0,
                    },
                    "missing_lines": [10, 15, 20],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert result.total_lines == 100
            assert result.covered_lines == 75
            assert result.percentage == 75.0
            assert result.passed is False
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert "75.0%" in issue.title
            assert "80.0%" in issue.title
            assert issue.severity in [Severity.LOW, Severity.MEDIUM, Severity.HIGH]
            assert issue.domain == ToolDomain.COVERAGE
            assert issue.source_tool == "coverage.py"

    def test_parse_json_report_above_threshold(self) -> None:
        """Test parsing JSON report when above threshold."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 100,
                "covered_lines": 90,
                "missing_lines": 10,
                "excluded_lines": 0,
                "percent_covered": 90.0,
            },
            "files": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert result.percentage == 90.0
            assert result.passed is True
            assert len(result.issues) == 0

    def test_parse_json_report_per_file_coverage(self) -> None:
        """Test parsing per-file coverage data."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 200,
                "covered_lines": 180,
                "missing_lines": 20,
                "excluded_lines": 5,
                "percent_covered": 90.0,
            },
            "files": {
                "src/app.py": {
                    "summary": {
                        "num_statements": 100,
                        "covered_lines": 90,
                        "excluded_lines": 2,
                    },
                    "missing_lines": [10, 20],
                },
                "src/utils.py": {
                    "summary": {
                        "num_statements": 100,
                        "covered_lines": 90,
                        "excluded_lines": 3,
                    },
                    "missing_lines": [5],
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert len(result.files) == 2
            assert "src/app.py" in result.files
            assert result.files["src/app.py"].missing_lines == [10, 20]

    def test_parse_json_report_invalid_file(self) -> None:
        """Test parsing invalid JSON file."""
        plugin = CoveragePyPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text("invalid json")

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)
            assert result.total_lines == 0
            assert result.tool == "coverage_py"


class TestCoveragePyCoverageIssueCreation:
    """Tests for coverage issue creation."""

    def test_create_issue_high_severity(self) -> None:
        """Test creating issue with HIGH severity (< 50%)."""
        plugin = CoveragePyPlugin()

        issue = plugin._create_coverage_issue(
            percentage=40.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=40,
            missing_lines=60,
        )

        assert issue.severity == Severity.HIGH
        assert "40.0%" in issue.title
        assert "80.0%" in issue.title

    def test_create_issue_medium_severity(self) -> None:
        """Test creating issue with MEDIUM severity (< threshold - 10)."""
        plugin = CoveragePyPlugin()

        issue = plugin._create_coverage_issue(
            percentage=65.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=65,
            missing_lines=35,
        )

        assert issue.severity == Severity.MEDIUM

    def test_create_issue_low_severity(self) -> None:
        """Test creating issue with LOW severity (close to threshold)."""
        plugin = CoveragePyPlugin()

        issue = plugin._create_coverage_issue(
            percentage=78.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=78,
            missing_lines=22,
        )

        assert issue.severity == Severity.LOW

    def test_issue_metadata(self) -> None:
        """Test issue contains correct metadata."""
        plugin = CoveragePyPlugin()

        issue = plugin._create_coverage_issue(
            percentage=75.0,
            threshold=80.0,
            total_lines=200,
            covered_lines=150,
            missing_lines=50,
        )

        metadata = issue.metadata
        assert metadata["coverage_percentage"] == 75.0
        assert metadata["threshold"] == 80.0
        assert metadata["total_lines"] == 200
        assert metadata["covered_lines"] == 150
        assert metadata["missing_lines"] == 50
        assert metadata["gap_percentage"] == 5.0


class TestDetectSourceDirectory:
    """Tests for _detect_source_directory to verify correct source path detection."""

    def test_src_package_layout(self) -> None:
        """Test detection of src/<package> layout (e.g. src/mypackage/__init__.py)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pkg_dir = project_root / "src" / "mypackage"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").touch()

            plugin = CoveragePyPlugin(project_root=project_root)
            result = plugin._detect_source_directory(project_root)

            assert result == "src/mypackage"

    def test_src_dir_without_package(self) -> None:
        """Test fallback to 'src' when src/ exists but has no package with __init__.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()
            # Just files, no package directory with __init__.py
            (src_dir / "utils.py").touch()

            plugin = CoveragePyPlugin(project_root=project_root)
            result = plugin._detect_source_directory(project_root)

            assert result == "src"

    def test_flat_package_layout(self) -> None:
        """Test detection of flat <package>/ layout at project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a project named "my-project" so package would be "my_project"
            project_root = Path(tmpdir) / "my-project"
            project_root.mkdir()
            pkg_dir = project_root / "my_project"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").touch()

            plugin = CoveragePyPlugin(project_root=project_root)
            result = plugin._detect_source_directory(project_root)

            assert result == "my_project"

    def test_no_source_directory_found(self) -> None:
        """Test returns None when no recognizable source layout exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "random-project"
            project_root.mkdir()
            # No src/ dir, no matching package dir, no pyproject.toml
            (project_root / "README.md").touch()

            plugin = CoveragePyPlugin(project_root=project_root)
            result = plugin._detect_source_directory(project_root)

            assert result is None

    def test_pyproject_toml_setuptools_packages_where(self) -> None:
        """Test detection from pyproject.toml [tool.setuptools.packages] where.

        The code looks for packages.where (not packages.find.where), so the TOML
        must use [tool.setuptools.packages] with a where key directly.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "some-project"
            project_root.mkdir()

            pyproject_content = """
[build-system]
requires = ["setuptools"]

[tool.setuptools.packages]
where = ["lib"]
"""
            (project_root / "pyproject.toml").write_text(pyproject_content)

            plugin = CoveragePyPlugin(project_root=project_root)
            result = plugin._detect_source_directory(project_root)

            assert result == "lib"

    def test_src_layout_preferred_over_flat(self) -> None:
        """Test that src/<package> layout takes priority over flat package layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "my-project"
            project_root.mkdir()

            # Create both layouts
            src_pkg = project_root / "src" / "my_project"
            src_pkg.mkdir(parents=True)
            (src_pkg / "__init__.py").touch()

            flat_pkg = project_root / "my_project"
            flat_pkg.mkdir()
            (flat_pkg / "__init__.py").touch()

            plugin = CoveragePyPlugin(project_root=project_root)
            result = plugin._detect_source_directory(project_root)

            # src/ layout should be detected first
            assert result == "src/my_project"


class TestCoverageRunWithSource:
    """Tests verifying that coverage run includes --source for accurate measurement."""

    def test_run_tests_with_coverage_includes_source_flag(self) -> None:
        """When _run_tests_with_coverage is called and a source directory is detected,
        the command must include --source to restrict coverage to project code only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Set up src/mypackage layout
            pkg_dir = project_root / "src" / "mypackage"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").touch()

            # Create a fake venv with pytest
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "pytest").touch()
            (venv_bin / "pytest").chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)

            mock_context = MagicMock()
            mock_context.project_root = project_root
            mock_context.stream_handler = None

            coverage_binary = Path("/usr/bin/coverage")

            with patch(
                "lucidshark.plugins.coverage.coverage_py.run_with_streaming"
            ) as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="1 passed in 0.1s", stderr=""
                )
                plugin._run_tests_with_coverage(coverage_binary, mock_context)

                # Verify the command that was invoked
                call_args = mock_run.call_args
                cmd = call_args.kwargs.get("cmd") or call_args[1].get("cmd") or call_args[0][0]

                # The command must include --source with the detected source directory
                assert "--source" in cmd, (
                    f"Expected --source in coverage command but got: {cmd}"
                )
                source_idx = cmd.index("--source")
                assert cmd[source_idx + 1] == "src/mypackage", (
                    f"Expected --source src/mypackage but got --source {cmd[source_idx + 1]}"
                )

    def test_run_tests_without_source_when_not_detected(self) -> None:
        """When no source directory is detected, --source should not be in the command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "no-src-project"
            project_root.mkdir()

            # Create a fake venv with pytest but no recognizable source dir
            venv_bin = project_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "pytest").touch()
            (venv_bin / "pytest").chmod(0o755)

            plugin = CoveragePyPlugin(project_root=project_root)

            mock_context = MagicMock()
            mock_context.project_root = project_root
            mock_context.stream_handler = None

            coverage_binary = Path("/usr/bin/coverage")

            with patch(
                "lucidshark.plugins.coverage.coverage_py.run_with_streaming"
            ) as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="1 passed in 0.1s", stderr=""
                )
                plugin._run_tests_with_coverage(coverage_binary, mock_context)

                call_args = mock_run.call_args
                cmd = call_args.kwargs.get("cmd") or call_args[1].get("cmd") or call_args[0][0]

                assert "--source" not in cmd, (
                    f"--source should not be present when no source dir detected: {cmd}"
                )


class TestCoveragePercentageParsing:
    """Tests for accurate coverage percentage extraction from JSON reports."""

    def test_exact_percentage_from_json(self) -> None:
        """Verify percentage is taken directly from the JSON report totals."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 237,
                "covered_lines": 198,
                "missing_lines": 39,
                "excluded_lines": 5,
                "percent_covered": 83.54,
            },
            "files": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert result.total_lines == 237
            assert result.covered_lines == 198
            assert result.missing_lines == 39
            assert result.excluded_lines == 5
            # percentage is computed from covered_lines/total_lines
            assert abs(result.percentage - (198 / 237 * 100)) < 0.01

    def test_zero_statements_yields_100_percent(self) -> None:
        """When there are zero statements, percentage should be 100%."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 0,
                "covered_lines": 0,
                "missing_lines": 0,
                "excluded_lines": 0,
                "percent_covered": 0.0,
            },
            "files": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            # CoverageResult.percentage returns 100.0 when total_lines == 0
            assert result.percentage == 100.0
            assert result.passed is True

    def test_100_percent_coverage(self) -> None:
        """Test parsing report with 100% coverage."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 50,
                "covered_lines": 50,
                "missing_lines": 0,
                "excluded_lines": 0,
                "percent_covered": 100.0,
            },
            "files": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert result.percentage == 100.0
            assert result.passed is True
            assert len(result.issues) == 0

    def test_malformed_json_returns_empty_result(self) -> None:
        """Test that malformed JSON returns a default CoverageResult."""
        plugin = CoveragePyPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text("{not valid json")

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert result.total_lines == 0
            assert result.threshold == 80.0


class TestCoverageThresholdBoundary:
    """Tests for coverage threshold comparison at boundary values."""

    def test_exactly_at_threshold_passes(self) -> None:
        """Coverage exactly equal to threshold should pass."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            missing_lines=20,
            threshold=80.0,
        )
        assert result.percentage == 80.0
        assert result.passed is True

    def test_one_line_below_threshold_fails(self) -> None:
        """Coverage just below threshold should fail."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=79,
            missing_lines=21,
            threshold=80.0,
        )
        assert result.percentage == 79.0
        assert result.passed is False

    def test_one_line_above_threshold_passes(self) -> None:
        """Coverage just above threshold should pass."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=81,
            missing_lines=19,
            threshold=80.0,
        )
        assert result.percentage == 81.0
        assert result.passed is True

    def test_zero_threshold_always_passes(self) -> None:
        """Zero threshold should always pass."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=0,
            missing_lines=100,
            threshold=0.0,
        )
        assert result.passed is True

    def test_100_threshold_requires_full_coverage(self) -> None:
        """100% threshold requires full coverage."""
        result_pass = CoverageResult(
            total_lines=100,
            covered_lines=100,
            missing_lines=0,
            threshold=100.0,
        )
        assert result_pass.passed is True

        result_fail = CoverageResult(
            total_lines=100,
            covered_lines=99,
            missing_lines=1,
            threshold=100.0,
        )
        assert result_fail.passed is False

    def test_fractional_threshold_boundary(self) -> None:
        """Test threshold comparison with fractional percentages."""
        # 79.5% coverage with 80% threshold -> fail
        result = CoverageResult(
            total_lines=200,
            covered_lines=159,
            missing_lines=41,
            threshold=80.0,
        )
        assert result.percentage == 79.5
        assert result.passed is False

    def test_issue_created_at_exact_boundary(self) -> None:
        """Verify no issue is created when coverage exactly meets threshold."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 100,
                "covered_lines": 80,
                "missing_lines": 20,
                "excluded_lines": 0,
                "percent_covered": 80.0,
            },
            "files": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            # At exactly threshold, no issue should be created
            assert len(result.issues) == 0
            assert result.passed is True

    def test_issue_created_just_below_boundary(self) -> None:
        """Verify issue IS created when coverage is just below threshold."""
        plugin = CoveragePyPlugin()

        report = {
            "totals": {
                "num_statements": 100,
                "covered_lines": 79,
                "missing_lines": 21,
                "excluded_lines": 0,
                "percent_covered": 79.0,
            },
            "files": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "coverage.json"
            report_file.write_text(json.dumps(report))

            result = plugin._parse_json_report(report_file, project_root, threshold=80.0)

            assert len(result.issues) == 1
            assert "79.0%" in result.issues[0].title
            assert result.passed is False


class TestExistingCoverageConfig:
    """Tests verifying that existing [tool.coverage.run] source config is respected."""

    def test_pyproject_with_coverage_source_config(self) -> None:
        """When pyproject.toml has [tool.coverage.run] source, _detect_source_directory
        result should still work but the caller should check for existing config first.
        This test verifies the detection still works even with coverage config present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create src/myapp package
            pkg_dir = project_root / "src" / "myapp"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "__init__.py").touch()

            # Create pyproject.toml with [tool.coverage.run] source already configured
            pyproject_content = """
[build-system]
requires = ["setuptools"]

[tool.coverage.run]
source = ["src/myapp"]
"""
            (project_root / "pyproject.toml").write_text(pyproject_content)

            plugin = CoveragePyPlugin(project_root=project_root)
            # _detect_source_directory should still detect the src layout
            result = plugin._detect_source_directory(project_root)
            assert result == "src/myapp"

    def test_coverage_has_source_config_pyproject(self) -> None:
        """coverage_has_source_config returns True when pyproject.toml has [tool.coverage.run] source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pyproject_content = '[tool.coverage.run]\nsource = ["src/myapp"]\n'
            (project_root / "pyproject.toml").write_text(pyproject_content)

            assert coverage_has_source_config(project_root) is True

    def test_coverage_has_source_config_coveragerc(self) -> None:
        """coverage_has_source_config returns True when .coveragerc has source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            coveragerc_content = "[run]\nsource = src/myapp\n"
            (project_root / ".coveragerc").write_text(coveragerc_content)

            assert coverage_has_source_config(project_root) is True

    def test_coverage_has_source_config_setup_cfg(self) -> None:
        """coverage_has_source_config returns True when setup.cfg has [coverage:run] source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            setup_cfg_content = "[coverage:run]\nsource = src/myapp\n"
            (project_root / "setup.cfg").write_text(setup_cfg_content)

            assert coverage_has_source_config(project_root) is True

    def test_coverage_has_source_config_returns_false_when_absent(self) -> None:
        """coverage_has_source_config returns False when no coverage config files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            assert coverage_has_source_config(project_root) is False

    def test_coverage_has_source_config_pyproject_without_source(self) -> None:
        """coverage_has_source_config returns False when pyproject.toml has [tool.coverage.run] but no source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pyproject_content = '[tool.coverage.run]\nbranch = true\n'
            (project_root / "pyproject.toml").write_text(pyproject_content)

            assert coverage_has_source_config(project_root) is False
