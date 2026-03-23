"""Unit tests for JaCoCo coverage plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.coverage.jacoco import JaCoCoPlugin


class TestJaCoCoPlugin:
    """Tests for JaCoCoPlugin class."""

    def test_name(self) -> None:
        """Test plugin name."""
        plugin = JaCoCoPlugin()
        assert plugin.name == "jacoco"

    def test_languages(self) -> None:
        """Test supported languages."""
        plugin = JaCoCoPlugin()
        assert "java" in plugin.languages
        assert "kotlin" in plugin.languages

    def test_domain(self) -> None:
        """Test domain is COVERAGE."""
        plugin = JaCoCoPlugin()
        assert plugin.domain == ToolDomain.COVERAGE

    def test_get_version(self) -> None:
        """Test version returns 'integrated'."""
        plugin = JaCoCoPlugin()
        assert plugin.get_version() == "integrated"


class TestJaCoCoBuildSystemDetection:
    """Tests for build system detection logic."""

    def test_detect_maven_wrapper(self) -> None:
        """Test detecting Maven wrapper (mvnw)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            binary, build_system = plugin._detect_build_system()

            assert binary == mvnw
            assert build_system == "maven"

    def test_detect_gradle_wrapper(self) -> None:
        """Test detecting Gradle wrapper (gradlew)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            binary, build_system = plugin._detect_build_system()

            assert binary == gradlew
            assert build_system == "gradle"

    def test_no_build_system_raises_error(self) -> None:
        """Test FileNotFoundError when no build system found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None
                plugin = JaCoCoPlugin(project_root=project_root)

                with pytest.raises(FileNotFoundError) as exc:
                    plugin._detect_build_system()

                assert "No build system found" in str(exc.value)


class TestJaCoCoEnsureBinary:
    """Tests for ensure_binary."""

    def test_ensure_binary_returns_path(self) -> None:
        """Test ensure_binary returns detected binary path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            binary = plugin.ensure_binary()
            assert binary == mvnw

    def test_ensure_binary_raises_when_not_found(self) -> None:
        """Test ensure_binary raises when no build tool found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = JaCoCoPlugin(project_root=project_root)
                with pytest.raises(FileNotFoundError):
                    plugin.ensure_binary()


class TestJaCoCoMeasureCoverage:
    """Tests for measure_coverage flow."""

    def test_measure_coverage_no_build_system(self) -> None:
        """Test measure_coverage when no build system found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = JaCoCoPlugin(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.stream_handler = None
                context.config = None

                result = plugin.measure_coverage(context, threshold=80.0)
                assert result.threshold == 80.0
                assert result.tool == "jacoco"
                assert result.total_lines == 0

    def test_measure_coverage_existing_report(self) -> None:
        """Test measure_coverage uses existing JaCoCo report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            # Create existing report
            report_dir = project_root / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (
                report_dir / "jacoco.xml"
            ).write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <report name="test">
                <counter type="LINE" missed="20" covered="80"/>
            </report>""")

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None
            context.ignore_patterns = None  # No exclude patterns

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 100
            assert result.covered_lines == 80

    def test_measure_coverage_no_report_returns_no_data_issue(self) -> None:
        """Test measure_coverage with no existing report returns no-data issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None

            result = plugin.measure_coverage(context, threshold=80.0)
            assert result.total_lines == 0
            assert len(result.issues) == 1
            assert result.issues[0].rule_id == "no_coverage_data"
            assert result.issues[0].source_tool == "jacoco"


class TestJaCoCoReportExists:
    """Tests for report existence checking."""

    def test_maven_report_exists_standard(self) -> None:
        """Test detecting standard Maven JaCoCo report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (report_dir / "jacoco.xml").touch()

            plugin = JaCoCoPlugin()
            assert plugin._jacoco_report_exists(project_root, "maven") is True

    def test_maven_report_exists_target(self) -> None:
        """Test detecting Maven JaCoCo report in target root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            target_dir = project_root / "target"
            target_dir.mkdir(parents=True)
            (target_dir / "jacoco.xml").touch()

            plugin = JaCoCoPlugin()
            assert plugin._jacoco_report_exists(project_root, "maven") is True

    def test_gradle_report_exists(self) -> None:
        """Test detecting Gradle JaCoCo report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "build" / "reports" / "jacoco" / "test"
            report_dir.mkdir(parents=True)
            (report_dir / "jacocoTestReport.xml").touch()

            plugin = JaCoCoPlugin()
            assert plugin._jacoco_report_exists(project_root, "gradle") is True

    def test_no_report_exists(self) -> None:
        """Test when no JaCoCo report exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = JaCoCoPlugin()
            assert plugin._jacoco_report_exists(project_root, "maven") is False
            assert plugin._jacoco_report_exists(project_root, "gradle") is False


class TestJaCoCoXmlParsing:
    """Tests for JaCoCo XML report parsing."""

    def test_parse_xml_report(self) -> None:
        """Test parsing JaCoCo XML report."""
        plugin = JaCoCoPlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">
<report name="user-service">
    <counter type="INSTRUCTION" missed="100" covered="400"/>
    <counter type="BRANCH" missed="10" covered="30"/>
    <counter type="LINE" missed="50" covered="200"/>
    <counter type="COMPLEXITY" missed="20" covered="80"/>
    <counter type="METHOD" missed="5" covered="45"/>
    <counter type="CLASS" missed="1" covered="9"/>
    <package name="com/example/service">
        <sourcefile name="UserService.java">
            <line nr="10" mi="0" ci="5" mb="0" cb="2"/>
            <line nr="15" mi="2" ci="0" mb="1" cb="0"/>
            <counter type="LINE" missed="5" covered="25"/>
        </sourcefile>
    </package>
</report>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "jacoco.xml"
            report_file.write_text(xml_content)

            result = plugin._parse_xml_report(report_file, project_root, threshold=80.0)

            assert result.total_lines == 250  # 50 + 200
            assert result.covered_lines == 200
            assert result.missing_lines == 50
            assert result.threshold == 80.0

            # 200/250 = 80%, should pass at 80% threshold
            assert result.percentage == 80.0
            assert result.passed is True
            assert len(result.issues) == 0

    def test_parse_xml_report_below_threshold(self) -> None:
        """Test parsing report with coverage below threshold."""
        plugin = JaCoCoPlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="LINE" missed="60" covered="40"/>
</report>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "jacoco.xml"
            report_file.write_text(xml_content)

            result = plugin._parse_xml_report(report_file, project_root, threshold=80.0)

            assert result.total_lines == 100
            assert result.covered_lines == 40
            assert result.percentage == 40.0
            assert result.passed is False
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert issue.domain == ToolDomain.COVERAGE
            assert issue.source_tool == "jacoco"
            assert issue.rule_id == "coverage_below_threshold"
            assert "40.0%" in issue.title
            assert "80.0%" in issue.title

    def test_parse_xml_report_per_file_coverage(self) -> None:
        """Test parsing per-file coverage data."""
        plugin = JaCoCoPlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="LINE" missed="20" covered="80"/>
    <package name="com/example">
        <sourcefile name="Service.java">
            <line nr="10" mi="2" ci="0"/>
            <line nr="20" mi="0" ci="5"/>
            <counter type="LINE" missed="10" covered="40"/>
        </sourcefile>
    </package>
</report>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "jacoco.xml"
            report_file.write_text(xml_content)

            # Create source file
            src_dir = project_root / "src" / "main" / "java" / "com" / "example"
            src_dir.mkdir(parents=True)
            (src_dir / "Service.java").touch()

            result = plugin._parse_xml_report(report_file, project_root, threshold=80.0)

            assert len(result.files) == 1
            file_cov = list(result.files.values())[0]
            assert file_cov.total_lines == 50
            assert file_cov.covered_lines == 40
            # Line 10 has mi=2 so it should be in missing_lines
            assert 10 in file_cov.missing_lines

    def test_parse_xml_report_uses_relative_paths_as_keys(self) -> None:
        """Test that JaCoCo stores files with relative paths as dictionary keys."""
        plugin = JaCoCoPlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="LINE" missed="20" covered="80"/>
    <package name="com/example/service">
        <sourcefile name="UserService.java">
            <line nr="10" mi="0" ci="5"/>
            <line nr="20" mi="2" ci="0"/>
            <counter type="LINE" missed="2" covered="18"/>
        </sourcefile>
    </package>
    <package name="com/example/controller">
        <sourcefile name="ApiController.java">
            <line nr="15" mi="0" ci="10"/>
            <counter type="LINE" missed="5" covered="15"/>
        </sourcefile>
    </package>
</report>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "jacoco.xml"
            report_file.write_text(xml_content)

            # Create source files
            service_dir = (
                project_root / "src" / "main" / "java" / "com" / "example" / "service"
            )
            service_dir.mkdir(parents=True)
            (service_dir / "UserService.java").touch()

            controller_dir = (
                project_root
                / "src"
                / "main"
                / "java"
                / "com"
                / "example"
                / "controller"
            )
            controller_dir.mkdir(parents=True)
            (controller_dir / "ApiController.java").touch()

            result = plugin._parse_xml_report(report_file, project_root, threshold=80.0)

            # Verify we have 2 files
            assert len(result.files) == 2

            # Verify keys are RELATIVE paths, not absolute
            expected_keys = {
                "src/main/java/com/example/service/UserService.java",
                "src/main/java/com/example/controller/ApiController.java",
            }
            assert set(result.files.keys()) == expected_keys

            # Verify filtering to changed files works
            changed_files = [
                project_root
                / "src"
                / "main"
                / "java"
                / "com"
                / "example"
                / "service"
                / "UserService.java"
            ]
            filtered_result = result.filter_to_changed_files(
                changed_files, project_root
            )

            # Should only have UserService.java
            assert len(filtered_result.files) == 1
            assert (
                "src/main/java/com/example/service/UserService.java"
                in filtered_result.files
            )

            # Verify coverage is recalculated for filtered files only
            assert filtered_result.total_lines == 20  # Only UserService lines
            assert filtered_result.covered_lines == 18
            assert filtered_result.percentage == 90.0  # 18/20

    def test_parse_xml_report_invalid_xml(self) -> None:
        """Test parsing invalid XML returns empty result."""
        plugin = JaCoCoPlugin()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "jacoco.xml"
            report_file.write_text("not valid xml")

            result = plugin._parse_xml_report(report_file, project_root, threshold=80.0)
            assert result.total_lines == 0
            assert result.threshold == 80.0

    def test_parse_xml_report_no_line_counter(self) -> None:
        """Test parsing XML without LINE counter."""
        plugin = JaCoCoPlugin()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<report name="test">
    <counter type="INSTRUCTION" missed="10" covered="90"/>
</report>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "jacoco.xml"
            report_file.write_text(xml_content)

            result = plugin._parse_xml_report(report_file, project_root, threshold=80.0)
            assert result.total_lines == 0  # No LINE counter


class TestJaCoCoParseJacocoReport:
    """Tests for the _parse_jacoco_report method that finds and parses reports."""

    def test_find_maven_report(self) -> None:
        """Test finding Maven JaCoCo report in standard location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (
                report_dir / "jacoco.xml"
            ).write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <report name="test">
                <counter type="LINE" missed="10" covered="90"/>
            </report>""")

            plugin = JaCoCoPlugin()
            result = plugin._parse_jacoco_report(project_root, 80.0, "maven")
            assert result.total_lines == 100
            assert result.covered_lines == 90

    def test_find_gradle_report(self) -> None:
        """Test finding Gradle JaCoCo report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "build" / "reports" / "jacoco" / "test"
            report_dir.mkdir(parents=True)
            (
                report_dir / "jacocoTestReport.xml"
            ).write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <report name="test">
                <counter type="LINE" missed="30" covered="70"/>
            </report>""")

            plugin = JaCoCoPlugin()
            result = plugin._parse_jacoco_report(project_root, 80.0, "gradle")
            assert result.total_lines == 100
            assert result.covered_lines == 70

    def test_no_report_found(self) -> None:
        """Test when no JaCoCo report is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = JaCoCoPlugin()
            result = plugin._parse_jacoco_report(project_root, 80.0, "maven")
            assert result.total_lines == 0
            assert result.threshold == 80.0

    def test_find_multi_module_report(self) -> None:
        """Test finding report in multi-module project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Create module with report
            module_dir = project_root / "core" / "target" / "site" / "jacoco"
            module_dir.mkdir(parents=True)
            (
                module_dir / "jacoco.xml"
            ).write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <report name="core">
                <counter type="LINE" missed="5" covered="95"/>
            </report>""")

            plugin = JaCoCoPlugin()
            result = plugin._parse_jacoco_report(project_root, 80.0, "maven")
            assert result.total_lines == 100
            assert result.covered_lines == 95


class TestJaCoCoCoverageIssue:
    """Tests for coverage issue creation."""

    def test_create_coverage_issue_below_50(self) -> None:
        """Test HIGH severity when coverage below 50%."""
        plugin = JaCoCoPlugin()

        issue = plugin._create_coverage_issue(
            percentage=30.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=30,
        )

        assert issue.severity == Severity.HIGH
        assert "30.0%" in issue.title
        assert "80.0%" in issue.title

    def test_create_coverage_issue_moderately_below(self) -> None:
        """Test MEDIUM severity when coverage moderately below threshold."""
        plugin = JaCoCoPlugin()

        issue = plugin._create_coverage_issue(
            percentage=60.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=60,
        )

        assert issue.severity == Severity.MEDIUM

    def test_create_coverage_issue_slightly_below(self) -> None:
        """Test LOW severity when coverage slightly below threshold."""
        plugin = JaCoCoPlugin()

        issue = plugin._create_coverage_issue(
            percentage=75.0,
            threshold=80.0,
            total_lines=100,
            covered_lines=75,
        )

        assert issue.severity == Severity.LOW


class TestJaCoCoSourcePathResolution:
    """Tests for source file path resolution."""

    def test_resolve_source_path_standard(self) -> None:
        """Test resolving standard Maven/Gradle source path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src" / "main" / "java" / "com" / "example"
            src_dir.mkdir(parents=True)
            (src_dir / "Service.java").touch()

            plugin = JaCoCoPlugin()
            resolved = plugin._resolve_source_path(
                project_root, "com/example", "Service.java"
            )

            assert resolved == src_dir / "Service.java"

    def test_resolve_source_path_test_directory(self) -> None:
        """Test resolving test source path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_dir = project_root / "src" / "test" / "java" / "com" / "example"
            test_dir.mkdir(parents=True)
            (test_dir / "ServiceTest.java").touch()

            plugin = JaCoCoPlugin()
            resolved = plugin._resolve_source_path(
                project_root, "com/example", "ServiceTest.java"
            )

            assert resolved == test_dir / "ServiceTest.java"

    def test_resolve_source_path_fallback(self) -> None:
        """Test fallback path when source file not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = JaCoCoPlugin()
            resolved = plugin._resolve_source_path(
                project_root, "com/example", "Missing.java"
            )

            # Should return best guess path
            assert (
                resolved
                == project_root
                / "src"
                / "main"
                / "java"
                / "com"
                / "example"
                / "Missing.java"
            )


class TestJaCoCoNoDataIssue:
    """Tests for _create_no_data_issue."""

    def test_no_data_issue_fields(self) -> None:
        """Test no-data issue has correct fields."""
        plugin = JaCoCoPlugin()
        issue = plugin._create_no_data_issue()
        assert issue.id == "no-coverage-data-jacoco"
        assert issue.rule_id == "no_coverage_data"
        assert issue.source_tool == "jacoco"
        assert issue.severity == Severity.HIGH
        assert issue.domain == ToolDomain.COVERAGE
        assert "jacoco" in issue.description.lower()
