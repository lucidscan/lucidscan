"""Unit tests for JaCoCo coverage plugin."""

from __future__ import annotations

import subprocess
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
            (report_dir / "jacoco.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <report name="test">
                <counter type="LINE" missed="20" covered="80"/>
            </report>""")

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None

            result = plugin.measure_coverage(context, threshold=80.0, run_tests=True)
            assert result.total_lines == 100
            assert result.covered_lines == 80

    def test_measure_coverage_run_tests_false_no_report(self) -> None:
        """Test measure_coverage with run_tests=False and no existing report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None

            result = plugin.measure_coverage(context, threshold=80.0, run_tests=False)
            # No report exists, so result should have 0 lines
            assert result.total_lines == 0

    def test_measure_coverage_run_maven_fails(self) -> None:
        """Test measure_coverage when Maven run fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None

            with patch.object(plugin, "_run_maven_with_jacoco", return_value=(False, None)):
                result = plugin.measure_coverage(context, threshold=80.0, run_tests=True)
                assert result.threshold == 80.0
                assert result.tool == "jacoco"


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


class TestJaCoCoRunMavenWithJaCoCo:
    """Tests for Maven JaCoCo execution."""

    def test_run_maven_with_jacoco_success(self) -> None:
        """Test successful Maven JaCoCo run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            # Create report that appears after running
            report_dir = project_root / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (report_dir / "jacoco.xml").touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None

            mock_result = MagicMock()
            mock_result.stdout = "Tests run: 5, Failures: 0, Errors: 0, Skipped: 0"
            mock_result.stderr = ""

            with patch("lucidshark.plugins.coverage.jacoco.run_with_streaming", return_value=mock_result):
                success, stats = plugin._run_maven_with_jacoco(mvnw, context)
                assert success is True
                assert stats is not None
                assert stats.total == 5

    def test_run_maven_with_jacoco_timeout(self) -> None:
        """Test Maven JaCoCo timeout handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None

            with patch("lucidshark.plugins.coverage.jacoco.run_with_streaming",
                       side_effect=subprocess.TimeoutExpired("mvn", 600)):
                success, stats = plugin._run_maven_with_jacoco(mvnw, context)
                assert success is False
                assert stats is None

    def test_run_maven_with_jacoco_extra_args(self) -> None:
        """Test that extra args from config are included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            # Create report
            report_dir = project_root / "target" / "site" / "jacoco"
            report_dir.mkdir(parents=True)
            (report_dir / "jacoco.xml").touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config.pipeline.coverage.extra_args = ["-DskipITs"]

            mock_result = MagicMock()
            mock_result.stdout = ""
            mock_result.stderr = ""

            with patch("lucidshark.plugins.coverage.jacoco.run_with_streaming", return_value=mock_result) as mock_run:
                plugin._run_maven_with_jacoco(mvnw, context)
                cmd = mock_run.call_args[1]["cmd"] if "cmd" in mock_run.call_args[1] else mock_run.call_args[0][0]
                assert "-DskipITs" in cmd

    def test_run_maven_verify_fallback(self) -> None:
        """Test fallback to verify phase when test phase doesn't generate report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None
            context.config = None

            call_count = [0]

            def fake_run(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call (test phase) - no report generated
                    raise Exception("test failed")
                # Second call (verify phase)
                result = MagicMock()
                result.stdout = "Tests run: 3, Failures: 0, Errors: 0, Skipped: 0"
                result.stderr = ""
                return result

            with patch("lucidshark.plugins.coverage.jacoco.run_with_streaming", side_effect=fake_run):
                success, stats = plugin._run_maven_with_jacoco(mvnw, context)
                assert success is True
                assert call_count[0] == 2  # Both test and verify were called


class TestJaCoCoRunGradleWithJaCoCo:
    """Tests for Gradle JaCoCo execution."""

    def test_run_gradle_with_jacoco_success(self) -> None:
        """Test successful Gradle JaCoCo run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            mock_result = MagicMock()
            mock_result.stdout = "10 tests completed, 2 failed, 1 skipped"
            mock_result.stderr = ""

            with patch("lucidshark.plugins.coverage.jacoco.run_with_streaming", return_value=mock_result):
                success, stats = plugin._run_gradle_with_jacoco(gradlew, context)
                assert success is True
                assert stats is not None
                assert stats.total == 10
                assert stats.failed == 2

    def test_run_gradle_with_jacoco_timeout(self) -> None:
        """Test Gradle JaCoCo timeout handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("lucidshark.plugins.coverage.jacoco.run_with_streaming",
                       side_effect=subprocess.TimeoutExpired("gradle", 600)):
                success, stats = plugin._run_gradle_with_jacoco(gradlew, context)
                assert success is False
                assert stats is None

    def test_run_gradle_with_jacoco_exception(self) -> None:
        """Test Gradle JaCoCo general exception handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            plugin = JaCoCoPlugin(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("lucidshark.plugins.coverage.jacoco.run_with_streaming",
                       side_effect=Exception("build failed")):
                success, stats = plugin._run_gradle_with_jacoco(gradlew, context)
                assert success is True  # Still true (we want the coverage report)


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
            (report_dir / "jacoco.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
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
            (report_dir / "jacocoTestReport.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
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
            (module_dir / "jacoco.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
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
            missing_lines=70,
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
            missing_lines=40,
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
            missing_lines=25,
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
            assert resolved == project_root / "src" / "main" / "java" / "com" / "example" / "Missing.java"


class TestJaCoCoTestStatsParsing:
    """Tests for parsing test statistics from build output."""

    def test_parse_maven_test_output(self) -> None:
        """Test parsing Maven test output."""
        plugin = JaCoCoPlugin()

        output = """
[INFO] --- maven-surefire-plugin:3.0.0:test (default-test) @ user-service ---
[INFO] Tests run: 10, Failures: 1, Errors: 0, Skipped: 2
        """

        stats = plugin._parse_maven_test_output(output)

        assert stats.total == 10
        assert stats.failed == 1
        assert stats.errors == 0
        assert stats.skipped == 2
        assert stats.passed == 7

    def test_parse_maven_test_output_multiple_modules(self) -> None:
        """Test parsing Maven output with multiple module summaries."""
        plugin = JaCoCoPlugin()

        output = """
[INFO] Tests run: 5, Failures: 0, Errors: 0, Skipped: 1
[INFO] Tests run: 3, Failures: 1, Errors: 0, Skipped: 0
        """

        stats = plugin._parse_maven_test_output(output)
        assert stats.total == 8
        assert stats.failed == 1
        assert stats.skipped == 1
        assert stats.passed == 6

    def test_parse_maven_test_output_no_match(self) -> None:
        """Test parsing Maven output with no test summary."""
        plugin = JaCoCoPlugin()

        output = "[INFO] BUILD SUCCESS"

        stats = plugin._parse_maven_test_output(output)
        assert stats.total == 0
        assert stats.passed == 0

    def test_parse_gradle_test_output(self) -> None:
        """Test parsing Gradle test output."""
        plugin = JaCoCoPlugin()

        output = """
> Task :test
10 tests completed, 2 failed, 1 skipped
        """

        stats = plugin._parse_gradle_test_output(output)

        assert stats.total == 10
        assert stats.failed == 2
        assert stats.skipped == 1

    def test_parse_gradle_test_output_all_passed(self) -> None:
        """Test parsing Gradle output with all tests passed."""
        plugin = JaCoCoPlugin()

        output = """
> Task :test
5 tests completed
        """

        stats = plugin._parse_gradle_test_output(output)
        assert stats.total == 5
        assert stats.failed == 0
        assert stats.skipped == 0

    def test_parse_gradle_test_output_no_match(self) -> None:
        """Test parsing Gradle output with no test summary."""
        plugin = JaCoCoPlugin()

        output = "BUILD SUCCESSFUL"

        stats = plugin._parse_gradle_test_output(output)
        assert stats.total == 0
