"""Unit tests for dotnet coverage plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.coverage.dotnet_coverage import DotnetCoveragePlugin


def _make_context(project_root: Path) -> ScanContext:
    return ScanContext(
        project_root=project_root,
        paths=[project_root],
        enabled_domains=[ToolDomain.COVERAGE],
    )


# Minimal Cobertura XML for testing
COBERTURA_REPORT = """\
<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.75" branch-rate="0" version="1.9"
          lines-covered="30" lines-valid="40" branches-covered="0" branches-valid="0">
  <packages>
    <package name="MyApp">
      <classes>
        <class name="MyApp.Program" filename="src/Program.cs" line-rate="0.8">
          <lines>
            <line number="1" hits="1" />
            <line number="2" hits="1" />
            <line number="3" hits="1" />
            <line number="4" hits="1" />
            <line number="5" hits="0" />
          </lines>
        </class>
        <class name="MyApp.Utils" filename="src/Utils.cs" line-rate="0.5">
          <lines>
            <line number="1" hits="1" />
            <line number="2" hits="0" />
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""

COBERTURA_HIGH_COVERAGE = """\
<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.95" branch-rate="0" version="1.9"
          lines-covered="95" lines-valid="100" branches-covered="0" branches-valid="0">
  <packages>
    <package name="MyApp">
      <classes>
        <class name="MyApp.Program" filename="src/Program.cs" line-rate="0.95">
          <lines>
            <line number="1" hits="1" />
            <line number="2" hits="1" />
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


class TestDotnetCoveragePluginProperties:
    """Basic property tests."""

    def test_name(self) -> None:
        plugin = DotnetCoveragePlugin()
        assert plugin.name == "dotnet_coverage"

    def test_languages(self) -> None:
        plugin = DotnetCoveragePlugin()
        assert plugin.languages == ["csharp"]

    def test_domain(self) -> None:
        plugin = DotnetCoveragePlugin()
        assert plugin.domain == ToolDomain.COVERAGE


class TestDotnetCoverageEnsureBinary:
    def test_found(self) -> None:
        plugin = DotnetCoveragePlugin()
        with patch("shutil.which", return_value="/usr/bin/dotnet"):
            binary = plugin.ensure_binary()
            assert binary == Path("/usr/bin/dotnet")

    def test_not_found(self) -> None:
        plugin = DotnetCoveragePlugin()
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError):
                plugin.ensure_binary()


class TestFindCoberturaReport:
    """Tests for _find_cobertura_report method."""

    def test_finds_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            results_dir = project_root / "TestResults" / "abc123"
            results_dir.mkdir(parents=True)
            report = results_dir / "coverage.cobertura.xml"
            report.write_text(COBERTURA_REPORT)

            plugin = DotnetCoveragePlugin()
            result = plugin._find_cobertura_report(project_root)
            assert result is not None
            assert result.name == "coverage.cobertura.xml"

    def test_no_results_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = DotnetCoveragePlugin()
            result = plugin._find_cobertura_report(Path(tmpdir))
            assert result is None

    def test_empty_results_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "TestResults"
            results_dir.mkdir()

            plugin = DotnetCoveragePlugin()
            result = plugin._find_cobertura_report(Path(tmpdir))
            assert result is None


class TestParseCobertura:
    """Tests for _parse_cobertura_report method."""

    def test_parses_coverage_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = project_root / "coverage.cobertura.xml"
            report.write_text(COBERTURA_REPORT)

            plugin = DotnetCoveragePlugin()
            result = plugin._parse_cobertura_report(report, project_root, 80.0)

            assert result.total_lines == 40
            assert result.covered_lines == 30
            assert result.missing_lines == 10
            assert result.tool == "dotnet_coverage"

    def test_parses_per_file_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = project_root / "coverage.cobertura.xml"
            report.write_text(COBERTURA_REPORT)

            plugin = DotnetCoveragePlugin()
            result = plugin._parse_cobertura_report(report, project_root, 80.0)

            assert "src/Program.cs" in result.files
            assert "src/Utils.cs" in result.files
            program_cov = result.files["src/Program.cs"]
            assert program_cov.total_lines == 5
            assert program_cov.covered_lines == 4
            assert 5 in program_cov.missing_lines

    def test_generates_issue_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = project_root / "coverage.cobertura.xml"
            report.write_text(COBERTURA_REPORT)

            plugin = DotnetCoveragePlugin()
            result = plugin._parse_cobertura_report(report, project_root, 80.0)

            # 75% < 80% threshold
            assert len(result.issues) == 1
            assert "below threshold" in result.issues[0].title

    def test_no_issue_above_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = project_root / "coverage.cobertura.xml"
            report.write_text(COBERTURA_HIGH_COVERAGE)

            plugin = DotnetCoveragePlugin()
            result = plugin._parse_cobertura_report(report, project_root, 80.0)

            assert len(result.issues) == 0

    def test_handles_invalid_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report = project_root / "coverage.cobertura.xml"
            report.write_text("not valid xml")

            plugin = DotnetCoveragePlugin()
            result = plugin._parse_cobertura_report(report, project_root, 80.0)

            assert result.total_lines == 0
            assert result.tool == "dotnet_coverage"


class TestMeasureCoverage:
    """Tests for measure_coverage method."""

    def test_no_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = DotnetCoveragePlugin()
            context = _make_context(Path(tmpdir))
            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.tool == "dotnet_coverage"
            assert result.total_lines == 0

    def test_no_report_generates_no_data_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            plugin = DotnetCoveragePlugin()
            context = _make_context(project_root)
            result = plugin.measure_coverage(context, threshold=80.0)

            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"

    def test_with_valid_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()
            results_dir = project_root / "TestResults" / "abc"
            results_dir.mkdir(parents=True)
            (results_dir / "coverage.cobertura.xml").write_text(COBERTURA_REPORT)

            plugin = DotnetCoveragePlugin()
            context = _make_context(project_root)
            result = plugin.measure_coverage(context, threshold=80.0)

            assert result.total_lines == 40
            assert result.covered_lines == 30
            assert result.tool == "dotnet_coverage"
