"""Unit tests for Scoverage coverage plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.coverage.scoverage import ScoveragePlugin


class TestScoveragePlugin:
    """Tests for ScoveragePlugin class."""

    def test_name(self) -> None:
        plugin = ScoveragePlugin()
        assert plugin.name == "scoverage"

    def test_languages(self) -> None:
        plugin = ScoveragePlugin()
        assert "scala" in plugin.languages

    def test_domain(self) -> None:
        plugin = ScoveragePlugin()
        assert plugin.domain == ToolDomain.COVERAGE

    def test_get_version(self) -> None:
        plugin = ScoveragePlugin()
        assert plugin.get_version() == "integrated"


class TestScoverageBuildDetection:
    """Tests for build system detection."""

    def test_detect_sbt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = ScoveragePlugin(project_root=project_root)
                binary, build_system = plugin._detect_build_system()
                assert build_system == "sbt"

    def test_detect_maven(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = ScoveragePlugin(project_root=project_root)
            binary, build_system = plugin._detect_build_system()
            assert build_system == "maven"

    def test_no_build_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = ScoveragePlugin(project_root=project_root)
                with pytest.raises(FileNotFoundError):
                    plugin._detect_build_system()


class TestScoverageEnsureBinary:
    """Tests for ensure_binary."""

    def test_ensure_binary_sbt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = ScoveragePlugin(project_root=project_root)
                binary = plugin.ensure_binary()
                assert binary == Path("/usr/local/bin/sbt")


class TestScoverageMeasureCoverage:
    """Tests for measure_coverage flow."""

    def test_measure_coverage_no_build_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = ScoveragePlugin(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root

                result = plugin.measure_coverage(context, threshold=80.0)
                assert result.threshold == 80.0
                assert result.tool == "scoverage"
                assert result.total_lines == 0

    def test_measure_coverage_no_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = ScoveragePlugin(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root

                result = plugin.measure_coverage(context, threshold=80.0)
                assert result.total_lines == 0
                assert len(result.issues) == 1
                assert result.issues[0].rule_id == "no_coverage_data"

    def test_measure_coverage_existing_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            report_dir = project_root / "target" / "scala-2.13" / "scoverage-report"
            report_dir.mkdir(parents=True)
            (report_dir / "scoverage.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<scoverage statement-count="100" statements-invoked="85" statement-rate="85.0"
           branch-count="20" branches-invoked="15" branch-rate="75.0">
    <packages>
        <package name="com.example">
            <classes>
                <class name="com.example.Service" filename="com/example/Service.scala"
                       statement-count="60" statements-invoked="50" statement-rate="83.33">
                    <methods/>
                </class>
                <class name="com.example.Utils" filename="com/example/Utils.scala"
                       statement-count="40" statements-invoked="35" statement-rate="87.5">
                    <methods/>
                </class>
            </classes>
        </package>
    </packages>
</scoverage>"""
            )

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = ScoveragePlugin(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.ignore_patterns = None

                result = plugin.measure_coverage(context, threshold=80.0)
                assert result.total_lines == 100
                assert result.covered_lines == 85
                assert result.percentage == 85.0
                assert result.passed is True
                assert len(result.issues) == 0
                assert len(result.files) == 2


class TestScoverageReportLocations:
    """Tests for finding Scoverage reports."""

    def test_find_sbt_report_standard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "target" / "scala-2.13" / "scoverage-report"
            report_dir.mkdir(parents=True)
            (report_dir / "scoverage.xml").touch()

            plugin = ScoveragePlugin()
            report = plugin._find_scoverage_report(project_root, "sbt")
            assert report is not None

    def test_find_sbt_report_scala3(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "target" / "scala-3" / "scoverage-report"
            report_dir.mkdir(parents=True)
            (report_dir / "scoverage.xml").touch()

            plugin = ScoveragePlugin()
            report = plugin._find_scoverage_report(project_root, "sbt")
            assert report is not None

    def test_find_maven_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            target_dir = project_root / "target"
            target_dir.mkdir(parents=True)
            (target_dir / "scoverage.xml").touch()

            plugin = ScoveragePlugin()
            report = plugin._find_scoverage_report(project_root, "maven")
            assert report is not None

    def test_find_gradle_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "build" / "reports" / "scoverage"
            report_dir.mkdir(parents=True)
            (report_dir / "scoverage.xml").touch()

            plugin = ScoveragePlugin()
            report = plugin._find_scoverage_report(project_root, "gradle")
            assert report is not None

    def test_no_report_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = ScoveragePlugin()
            report = plugin._find_scoverage_report(project_root, "sbt")
            assert report is None


class TestScoverageXmlParsing:
    """Tests for Scoverage XML report parsing."""

    def test_parse_report(self) -> None:
        plugin = ScoveragePlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<scoverage statement-count="200" statements-invoked="160" statement-rate="80.0"
           branch-count="40" branches-invoked="30" branch-rate="75.0">
    <packages>
        <package name="com.example">
            <classes>
                <class name="com.example.App" filename="com/example/App.scala"
                       statement-count="120" statements-invoked="100" statement-rate="83.33">
                    <methods/>
                </class>
                <class name="com.example.Config" filename="com/example/Config.scala"
                       statement-count="80" statements-invoked="60" statement-rate="75.0">
                    <methods/>
                </class>
            </classes>
        </package>
    </packages>
</scoverage>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "scoverage.xml"
            report_file.write_text(xml_content)

            result = plugin._parse_scoverage_report(
                report_file, project_root, threshold=80.0
            )

            assert result.total_lines == 200
            assert result.covered_lines == 160
            assert result.percentage == 80.0
            assert result.passed is True
            assert len(result.files) == 2

    def test_parse_report_below_threshold(self) -> None:
        plugin = ScoveragePlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<scoverage statement-count="100" statements-invoked="50" statement-rate="50.0">
    <packages/>
</scoverage>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "scoverage.xml"
            report_file.write_text(xml_content)

            result = plugin._parse_scoverage_report(
                report_file, project_root, threshold=80.0
            )

            assert result.total_lines == 100
            assert result.covered_lines == 50
            assert result.percentage == 50.0
            assert result.passed is False
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert issue.domain == ToolDomain.COVERAGE
            assert issue.source_tool == "scoverage"
            assert "50.0%" in issue.title
            assert "80.0%" in issue.title

    def test_parse_report_invalid_xml(self) -> None:
        plugin = ScoveragePlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "scoverage.xml"
            report_file.write_text("not valid xml")

            result = plugin._parse_scoverage_report(
                report_file, project_root, threshold=80.0
            )
            assert result.total_lines == 0

    def test_parse_report_per_file_coverage(self) -> None:
        plugin = ScoveragePlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<scoverage statement-count="50" statements-invoked="40" statement-rate="80.0">
    <packages>
        <package name="com.example">
            <classes>
                <class name="com.example.Service" filename="com/example/Service.scala"
                       statement-count="30" statements-invoked="25" statement-rate="83.33">
                    <methods/>
                </class>
                <class name="com.example.Repo" filename="com/example/Repo.scala"
                       statement-count="20" statements-invoked="15" statement-rate="75.0">
                    <methods/>
                </class>
            </classes>
        </package>
    </packages>
</scoverage>"""

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "scoverage.xml"
            report_file.write_text(xml_content)

            # Create source files
            src_dir = project_root / "src" / "main" / "scala" / "com" / "example"
            src_dir.mkdir(parents=True)
            (src_dir / "Service.scala").touch()
            (src_dir / "Repo.scala").touch()

            result = plugin._parse_scoverage_report(
                report_file, project_root, threshold=80.0
            )

            assert len(result.files) == 2
            # Check per-file coverage
            for file_cov in result.files.values():
                assert file_cov.total_lines > 0
                assert file_cov.covered_lines > 0


class TestScoverageSourcePathResolution:
    """Tests for source file path resolution."""

    def test_resolve_standard_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src" / "main" / "scala" / "com" / "example"
            src_dir.mkdir(parents=True)
            (src_dir / "App.scala").touch()

            plugin = ScoveragePlugin()
            resolved = plugin._resolve_source_path(
                project_root, "com/example/App.scala"
            )
            assert resolved == src_dir / "App.scala"

    def test_resolve_test_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_dir = project_root / "src" / "test" / "scala" / "com" / "example"
            test_dir.mkdir(parents=True)
            (test_dir / "AppSpec.scala").touch()

            plugin = ScoveragePlugin()
            resolved = plugin._resolve_source_path(
                project_root, "com/example/AppSpec.scala"
            )
            assert resolved == test_dir / "AppSpec.scala"

    def test_resolve_fallback_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = ScoveragePlugin()
            resolved = plugin._resolve_source_path(
                project_root, "com/example/Missing.scala"
            )
            # Should return best guess
            expected = project_root / "src" / "main" / "scala" / "com" / "example" / "Missing.scala"
            assert resolved == expected


class TestScoverageNoDataIssue:
    """Tests for _create_no_data_issue."""

    def test_no_data_issue_fields(self) -> None:
        plugin = ScoveragePlugin()
        issue = plugin._create_no_data_issue()
        assert issue.id == "no-coverage-data-scoverage"
        assert issue.rule_id == "no_coverage_data"
        assert issue.source_tool == "scoverage"
        assert issue.severity == Severity.HIGH
        assert issue.domain == ToolDomain.COVERAGE


class TestScoverageCoverageIssue:
    """Tests for coverage issue creation."""

    def test_create_coverage_issue_below_50(self) -> None:
        plugin = ScoveragePlugin()
        issue = plugin._create_coverage_issue(
            percentage=30.0, threshold=80.0, total_lines=100, covered_lines=30
        )
        assert issue.severity == Severity.HIGH
        assert "30.0%" in issue.title

    def test_create_coverage_issue_moderately_below(self) -> None:
        plugin = ScoveragePlugin()
        issue = plugin._create_coverage_issue(
            percentage=60.0, threshold=80.0, total_lines=100, covered_lines=60
        )
        assert issue.severity == Severity.MEDIUM

    def test_create_coverage_issue_slightly_below(self) -> None:
        plugin = ScoveragePlugin()
        issue = plugin._create_coverage_issue(
            percentage=75.0, threshold=80.0, total_lines=100, covered_lines=75
        )
        assert issue.severity == Severity.LOW
