"""Unit tests for Maven/Gradle test runner plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.test_runners.base import TestResult
from lucidshark.plugins.test_runners.maven import MavenTestRunner


class TestMavenTestRunner:
    """Tests for MavenTestRunner class."""

    def test_name(self) -> None:
        """Test plugin name."""
        runner = MavenTestRunner()
        assert runner.name == "maven"

    def test_languages(self) -> None:
        """Test supported languages."""
        runner = MavenTestRunner()
        assert "java" in runner.languages
        assert "kotlin" in runner.languages

    def test_domain(self) -> None:
        """Test domain is TESTING."""
        runner = MavenTestRunner()
        assert runner.domain == ToolDomain.TESTING


class TestMavenBuildSystemDetection:
    """Tests for build system detection logic."""

    def test_detect_maven_wrapper(self) -> None:
        """Test detecting Maven wrapper (mvnw)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)
            binary, build_system = runner._detect_build_system()

            assert binary == mvnw
            assert build_system == "maven"

    def test_detect_gradle_wrapper(self) -> None:
        """Test detecting Gradle wrapper (gradlew)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            runner = MavenTestRunner(project_root=project_root)
            binary, build_system = runner._detect_build_system()

            assert binary == gradlew
            assert build_system == "gradle"

    def test_detect_pom_xml_with_mvn(self) -> None:
        """Test detecting Maven via pom.xml and mvn in PATH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            pom_xml = project_root / "pom.xml"
            pom_xml.write_text("<project></project>")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/mvn"
                runner = MavenTestRunner(project_root=project_root)
                binary, build_system = runner._detect_build_system()

                assert binary == Path("/usr/bin/mvn")
                assert build_system == "maven"

    def test_detect_build_gradle_with_gradle(self) -> None:
        """Test detecting Gradle via build.gradle and gradle in PATH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            build_gradle = project_root / "build.gradle"
            build_gradle.write_text("// Gradle build")

            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/gradle"
                runner = MavenTestRunner(project_root=project_root)
                binary, build_system = runner._detect_build_system()

                assert binary == Path("/usr/bin/gradle")
                assert build_system == "gradle"

    def test_no_build_system_raises_error(self) -> None:
        """Test FileNotFoundError when no build system found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which") as mock_which:
                mock_which.return_value = None
                runner = MavenTestRunner(project_root=project_root)

                with pytest.raises(FileNotFoundError) as exc:
                    runner._detect_build_system()

                assert "No build system found" in str(exc.value)


class TestMavenGetVersion:
    """Tests for version detection."""

    def test_get_maven_version(self) -> None:
        """Test getting Maven version string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Apache Maven 3.9.6\nMaven home: /usr/share/maven"

            with patch("subprocess.run", return_value=mock_result):
                version = runner.get_version()
                assert version == "maven-3.9.6"

    def test_get_gradle_version(self) -> None:
        """Test getting Gradle version string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            runner = MavenTestRunner(project_root=project_root)

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "Gradle 8.5\nBuild time: 2024-01-01"

            with patch("subprocess.run", return_value=mock_result):
                version = runner.get_version()
                assert version == "gradle-8.5"

    def test_get_version_unknown_on_failure(self) -> None:
        """Test version returns 'unknown' when detection fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                runner = MavenTestRunner(project_root=project_root)
                version = runner.get_version()
                assert version == "unknown"

    def test_get_version_unknown_on_nonzero_exit(self) -> None:
        """Test version returns 'unknown' when command exits non-zero."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)

            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""

            with patch("subprocess.run", return_value=mock_result):
                version = runner.get_version()
                assert version == "unknown"


class TestMavenEnsureBinary:
    """Tests for ensure_binary."""

    def test_ensure_binary_returns_path(self) -> None:
        """Test ensure_binary returns detected binary path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)
            binary = runner.ensure_binary()
            assert binary == mvnw

    def test_ensure_binary_raises_when_not_found(self) -> None:
        """Test ensure_binary raises when no build tool found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                runner = MavenTestRunner(project_root=project_root)
                with pytest.raises(FileNotFoundError):
                    runner.ensure_binary()


class TestMavenRunTests:
    """Tests for test execution flow."""

    def test_run_tests_no_build_system(self) -> None:
        """Test run_tests returns empty result when no build system found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                runner = MavenTestRunner(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.stream_handler = None

                result = runner.run_tests(context)
                assert result.passed == 0
                assert result.failed == 0
                assert result.tool == "maven"

    def test_run_maven_tests_dispatches_to_maven(self) -> None:
        """Test that Maven build system dispatches to _run_maven_tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch.object(runner, "_run_maven_tests", return_value=TestResult(passed=5, tool="maven")) as mock:
                result = runner.run_tests(context)
                mock.assert_called_once()
                assert result.passed == 5

    def test_run_gradle_tests_dispatches_to_gradle(self) -> None:
        """Test that Gradle build system dispatches to _run_gradle_tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            runner = MavenTestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch.object(runner, "_run_gradle_tests", return_value=TestResult(passed=3, tool="maven")) as mock:
                result = runner.run_tests(context)
                mock.assert_called_once()
                assert result.passed == 3

    def test_run_maven_tests_timeout(self) -> None:
        """Test Maven test timeout handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("lucidshark.plugins.test_runners.maven.run_with_streaming", side_effect=subprocess.TimeoutExpired("cmd", 600)):
                result = runner._run_maven_tests(mvnw, context, with_coverage=False)
                assert result.passed == 0
                assert result.tool == "maven"

    def test_run_gradle_tests_timeout(self) -> None:
        """Test Gradle test timeout handling."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            runner = MavenTestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("lucidshark.plugins.test_runners.maven.run_with_streaming", side_effect=subprocess.TimeoutExpired("cmd", 600)):
                result = runner._run_gradle_tests(gradlew, context, with_coverage=False)
                assert result.passed == 0
                assert result.tool == "maven"

    def test_run_maven_tests_with_coverage(self) -> None:
        """Test Maven tests with coverage flag adds JaCoCo skip=false."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            # Create surefire reports dir so parsing returns something
            surefire_dir = project_root / "target" / "surefire-reports"
            surefire_dir.mkdir(parents=True)

            with patch("lucidshark.plugins.test_runners.maven.run_with_streaming") as mock_run:
                runner._run_maven_tests(mvnw, context, with_coverage=True)
                cmd = mock_run.call_args[1]["cmd"] if "cmd" in mock_run.call_args[1] else mock_run.call_args[0][0]
                assert "-Djacoco.skip=false" in cmd

    def test_run_gradle_tests_with_coverage(self) -> None:
        """Test Gradle tests with coverage flag adds jacocoTestReport."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            runner = MavenTestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            with patch("lucidshark.plugins.test_runners.maven.run_with_streaming") as mock_run:
                runner._run_gradle_tests(gradlew, context, with_coverage=True)
                cmd = mock_run.call_args[1]["cmd"] if "cmd" in mock_run.call_args[1] else mock_run.call_args[0][0]
                assert "jacocoTestReport" in cmd

    def test_run_maven_tests_nonzero_exit_still_parses(self) -> None:
        """Test Maven test still parses reports on non-zero exit code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            runner = MavenTestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.stream_handler = None

            # Create surefire reports
            surefire_dir = project_root / "target" / "surefire-reports"
            surefire_dir.mkdir(parents=True)
            xml_file = surefire_dir / "TEST-com.example.MyTest.xml"
            xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <testsuite name="com.example.MyTest" tests="3" failures="1" errors="0" skipped="0" time="1.0">
                <testcase classname="com.example.MyTest" name="test1" time="0.1"/>
                <testcase classname="com.example.MyTest" name="test2" time="0.1"/>
                <testcase classname="com.example.MyTest" name="testFail" time="0.1">
                    <failure type="AssertionError" message="expected true">stack</failure>
                </testcase>
            </testsuite>""")

            with patch("lucidshark.plugins.test_runners.maven.run_with_streaming", side_effect=Exception("exit code 1")):
                result = runner._run_maven_tests(mvnw, context, with_coverage=False)
                assert result.passed == 2
                assert result.failed == 1


class TestMavenSurefireReportParsing:
    """Tests for Surefire report directory parsing."""

    def test_parse_surefire_reports_single_module(self) -> None:
        """Test parsing surefire reports from standard location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            surefire_dir = project_root / "target" / "surefire-reports"
            surefire_dir.mkdir(parents=True)

            xml = """<?xml version="1.0" encoding="UTF-8"?>
            <testsuite name="com.example.MyTest" tests="5" failures="0" errors="0" skipped="0" time="2.0">
                <testcase classname="com.example.MyTest" name="test1" time="0.1"/>
                <testcase classname="com.example.MyTest" name="test2" time="0.1"/>
                <testcase classname="com.example.MyTest" name="test3" time="0.1"/>
                <testcase classname="com.example.MyTest" name="test4" time="0.1"/>
                <testcase classname="com.example.MyTest" name="test5" time="0.1"/>
            </testsuite>"""
            (surefire_dir / "TEST-com.example.MyTest.xml").write_text(xml)

            runner = MavenTestRunner()
            result = runner._parse_surefire_reports(project_root)
            assert result.passed == 5
            assert result.failed == 0

    def test_parse_surefire_reports_multi_module(self) -> None:
        """Test parsing surefire reports from multi-module project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Module A
            surefire_a = project_root / "module-a" / "target" / "surefire-reports"
            surefire_a.mkdir(parents=True)
            (surefire_a / "TEST-com.example.ATest.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <testsuite tests="3" failures="0" errors="0" skipped="0" time="1.0">
                    <testcase classname="com.example.ATest" name="test1" time="0.1"/>
                    <testcase classname="com.example.ATest" name="test2" time="0.1"/>
                    <testcase classname="com.example.ATest" name="test3" time="0.1"/>
                </testsuite>"""
            )

            # Module B
            surefire_b = project_root / "module-b" / "target" / "surefire-reports"
            surefire_b.mkdir(parents=True)
            (surefire_b / "TEST-com.example.BTest.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <testsuite tests="2" failures="1" errors="0" skipped="0" time="0.5">
                    <testcase classname="com.example.BTest" name="test1" time="0.1"/>
                    <testcase classname="com.example.BTest" name="testFail" time="0.1">
                        <failure type="AssertionError" message="nope">stack</failure>
                    </testcase>
                </testsuite>"""
            )

            runner = MavenTestRunner()
            result = runner._parse_surefire_reports(project_root)
            assert result.passed == 4
            assert result.failed == 1

    def test_parse_surefire_reports_no_reports_dir(self) -> None:
        """Test parsing when no surefire-reports directory exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            runner = MavenTestRunner()
            result = runner._parse_surefire_reports(project_root)
            assert result.passed == 0
            assert result.failed == 0


class TestMavenGradleReportParsing:
    """Tests for Gradle report directory parsing."""

    def test_parse_gradle_reports_standard_location(self) -> None:
        """Test parsing Gradle reports from build/test-results/test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradle_dir = project_root / "build" / "test-results" / "test"
            gradle_dir.mkdir(parents=True)

            (gradle_dir / "TEST-com.example.GTest.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <testsuite tests="4" failures="0" errors="0" skipped="1" time="1.0">
                    <testcase classname="com.example.GTest" name="test1" time="0.1"/>
                    <testcase classname="com.example.GTest" name="test2" time="0.1"/>
                    <testcase classname="com.example.GTest" name="test3" time="0.1"/>
                    <testcase classname="com.example.GTest" name="test4" time="0.1"/>
                </testsuite>"""
            )

            runner = MavenTestRunner()
            result = runner._parse_gradle_reports(project_root)
            assert result.passed == 3
            assert result.skipped == 1

    def test_parse_gradle_reports_multi_module(self) -> None:
        """Test parsing Gradle reports from multi-module project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Module with tests
            module_dir = project_root / "app" / "build" / "test-results" / "test"
            module_dir.mkdir(parents=True)
            (module_dir / "TEST-com.example.AppTest.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <testsuite tests="2" failures="0" errors="0" skipped="0" time="0.5">
                    <testcase classname="com.example.AppTest" name="test1" time="0.1"/>
                    <testcase classname="com.example.AppTest" name="test2" time="0.1"/>
                </testsuite>"""
            )

            runner = MavenTestRunner()
            result = runner._parse_gradle_reports(project_root)
            assert result.passed == 2

    def test_parse_gradle_reports_no_reports(self) -> None:
        """Test parsing when no Gradle test reports exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            runner = MavenTestRunner()
            result = runner._parse_gradle_reports(project_root)
            assert result.passed == 0


class TestMavenJunitXmlParsing:
    """Tests for JUnit XML parsing."""

    def test_parse_junit_xml_with_failures(self) -> None:
        """Test parsing JUnit XML with test failures."""
        runner = MavenTestRunner()

        junit_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="com.example.MyTest" tests="3" failures="1" errors="0" skipped="0" time="1.5">
            <testcase classname="com.example.MyTest" name="testSuccess" time="0.1"/>
            <testcase classname="com.example.MyTest" name="testFailure" time="0.05">
                <failure type="java.lang.AssertionError" message="expected: true but was: false">
java.lang.AssertionError: expected: true but was: false
    at com.example.MyTest.testFailure(MyTest.java:25)
                </failure>
            </testcase>
            <testcase classname="com.example.MyTest" name="testAnother" time="0.02"/>
        </testsuite>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "junit.xml"
            report_file.write_text(junit_xml)

            result = runner._parse_junit_xml(report_file, project_root)

            assert result.passed == 2
            assert result.failed == 1
            assert result.errors == 0
            assert result.duration_ms == 1500
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert "testFailure" in issue.title
            assert issue.severity == Severity.HIGH
            assert issue.domain == ToolDomain.TESTING
            assert issue.source_tool == "maven"

    def test_parse_junit_xml_all_passed(self) -> None:
        """Test parsing JUnit XML with all tests passed."""
        runner = MavenTestRunner()

        junit_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="com.example.MyTest" tests="5" failures="0" errors="0" skipped="0" time="2.0">
            <testcase classname="com.example.MyTest" name="test1" time="0.1"/>
            <testcase classname="com.example.MyTest" name="test2" time="0.1"/>
            <testcase classname="com.example.MyTest" name="test3" time="0.1"/>
            <testcase classname="com.example.MyTest" name="test4" time="0.1"/>
            <testcase classname="com.example.MyTest" name="test5" time="0.1"/>
        </testsuite>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "junit.xml"
            report_file.write_text(junit_xml)

            result = runner._parse_junit_xml(report_file, project_root)

            assert result.passed == 5
            assert result.failed == 0
            assert result.success is True
            assert len(result.issues) == 0

    def test_parse_junit_xml_with_errors(self) -> None:
        """Test parsing JUnit XML with test errors."""
        runner = MavenTestRunner()

        junit_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="com.example.MyTest" tests="2" failures="0" errors="1" skipped="0" time="0.5">
            <testcase classname="com.example.MyTest" name="testSuccess" time="0.1"/>
            <testcase classname="com.example.MyTest" name="testError" time="0.05">
                <error type="java.lang.NullPointerException" message="NPE">
java.lang.NullPointerException
    at com.example.MyTest.testError(MyTest.java:30)
                </error>
            </testcase>
        </testsuite>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "junit.xml"
            report_file.write_text(junit_xml)

            result = runner._parse_junit_xml(report_file, project_root)

            assert result.passed == 1
            assert result.errors == 1
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert "testError" in issue.title
            assert issue.severity == Severity.MEDIUM

    def test_parse_junit_xml_invalid_file(self) -> None:
        """Test parsing an invalid XML file returns empty result."""
        runner = MavenTestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "junit.xml"
            report_file.write_text("not valid xml <<<<")

            result = runner._parse_junit_xml(report_file, project_root)
            assert result.passed == 0
            assert result.failed == 0
            assert result.tool == "maven"

    def test_parse_junit_xml_no_testsuite(self) -> None:
        """Test parsing XML without testsuite element."""
        runner = MavenTestRunner()

        junit_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <root>
            <something/>
        </root>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "junit.xml"
            report_file.write_text(junit_xml)

            result = runner._parse_junit_xml(report_file, project_root)
            assert result.passed == 0

    def test_parse_junit_xml_with_skipped(self) -> None:
        """Test parsing JUnit XML with skipped tests."""
        runner = MavenTestRunner()

        junit_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite tests="4" failures="0" errors="0" skipped="2" time="1.0">
            <testcase classname="com.example.MyTest" name="test1" time="0.1"/>
            <testcase classname="com.example.MyTest" name="test2" time="0.1"/>
            <testcase classname="com.example.MyTest" name="testSkip1" time="0.0"/>
            <testcase classname="com.example.MyTest" name="testSkip2" time="0.0"/>
        </testsuite>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_file = project_root / "junit.xml"
            report_file.write_text(junit_xml)

            result = runner._parse_junit_xml(report_file, project_root)
            assert result.passed == 2
            assert result.skipped == 2


class TestMavenTestcaseToIssue:
    """Tests for converting JUnit testcase elements to UnifiedIssue."""

    def test_testcase_with_source_file(self) -> None:
        """Test testcase conversion when source file exists."""
        import defusedxml.ElementTree as ET

        runner = MavenTestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Create the source file
            src_dir = project_root / "src" / "test" / "java" / "com" / "example"
            src_dir.mkdir(parents=True)
            (src_dir / "MyTest.java").touch()

            testcase = ET.fromstring(
                '<testcase classname="com.example.MyTest" name="testMethod" time="0.1"/>'
            )
            failure = ET.fromstring(
                '<failure type="AssertionError" message="expected true">'
                'java.lang.AssertionError: expected true\n'
                '    at com.example.MyTest.testMethod(MyTest.java:42)'
                '</failure>'
            )

            issue = runner._testcase_to_issue(testcase, failure, project_root, "failed")
            assert issue is not None
            assert issue.file_path == src_dir / "MyTest.java"
            assert issue.line_start == 42
            assert issue.severity == Severity.HIGH
            assert issue.metadata["test_method"] == "testMethod"
            assert issue.metadata["test_class"] == "com.example.MyTest"

    def test_testcase_error_outcome_medium_severity(self) -> None:
        """Test error outcome produces MEDIUM severity."""
        import defusedxml.ElementTree as ET

        runner = MavenTestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            testcase = ET.fromstring(
                '<testcase classname="com.example.MyTest" name="testMethod" time="0.1"/>'
            )
            error = ET.fromstring(
                '<error type="NullPointerException" message="NPE">stack</error>'
            )

            issue = runner._testcase_to_issue(testcase, error, project_root, "error")
            assert issue is not None
            assert issue.severity == Severity.MEDIUM
            assert issue.metadata["outcome"] == "error"

    def test_testcase_long_message_truncated_in_title(self) -> None:
        """Test that long failure messages are truncated in issue title."""
        import defusedxml.ElementTree as ET

        runner = MavenTestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            testcase = ET.fromstring(
                '<testcase classname="com.example.MyTest" name="testMethod" time="0.1"/>'
            )
            long_msg = "A" * 200
            failure = ET.fromstring(
                f'<failure type="AssertionError" message="{long_msg}">stack</failure>'
            )

            issue = runner._testcase_to_issue(testcase, failure, project_root, "failed")
            assert issue is not None
            assert len(issue.title) < 200  # Title should be truncated

    def test_testcase_no_classname(self) -> None:
        """Test handling testcase with no classname."""
        import defusedxml.ElementTree as ET

        runner = MavenTestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            testcase = ET.fromstring(
                '<testcase name="testMethod" time="0.1"/>'
            )
            failure = ET.fromstring(
                '<failure type="AssertionError" message="err">stack</failure>'
            )

            issue = runner._testcase_to_issue(testcase, failure, project_root, "failed")
            assert issue is not None
            assert issue.file_path is None


class TestMavenLineExtraction:
    """Tests for line number extraction from stacktrace."""

    def test_extract_line_from_stacktrace(self) -> None:
        """Test extracting line number from Java stacktrace."""
        runner = MavenTestRunner()

        stacktrace = """java.lang.AssertionError: expected: true but was: false
    at org.junit.Assert.fail(Assert.java:88)
    at com.example.service.UserServiceTest.testLogin(UserServiceTest.java:42)
    at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
        """

        line = runner._extract_line_from_stacktrace(
            stacktrace, "com.example.service.UserServiceTest"
        )

        assert line == 42

    def test_extract_line_no_match(self) -> None:
        """Test no line number when class not in stacktrace."""
        runner = MavenTestRunner()

        stacktrace = """java.lang.NullPointerException
    at java.util.HashMap.get(HashMap.java:100)
        """

        line = runner._extract_line_from_stacktrace(
            stacktrace, "com.example.MyTest"
        )

        assert line is None

    def test_extract_line_empty_stacktrace(self) -> None:
        """Test extraction with empty stacktrace."""
        runner = MavenTestRunner()
        line = runner._extract_line_from_stacktrace("", "com.example.MyTest")
        assert line is None


class TestMavenIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        """Test same input produces same ID."""
        runner = MavenTestRunner()

        id1 = runner._generate_issue_id("com.example.Test#testFoo", "expected true")
        id2 = runner._generate_issue_id("com.example.Test#testFoo", "expected true")

        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Test different input produces different ID."""
        runner = MavenTestRunner()

        id1 = runner._generate_issue_id("com.example.Test#testFoo", "expected true")
        id2 = runner._generate_issue_id("com.example.Test#testBar", "expected true")

        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID format starts with maven-test-."""
        runner = MavenTestRunner()

        issue_id = runner._generate_issue_id("com.example.Test#testFoo", "msg")

        assert issue_id.startswith("maven-test-")


class TestMavenResultMerging:
    """Tests for merging multiple TestResults."""

    def test_merge_results(self) -> None:
        """Test merging two TestResults."""
        runner = MavenTestRunner()

        result1 = TestResult(passed=5, failed=1, skipped=0, errors=0, duration_ms=1000)
        result2 = TestResult(passed=3, failed=2, skipped=1, errors=1, duration_ms=500)

        merged = runner._merge_results(result1, result2)

        assert merged.passed == 8
        assert merged.failed == 3
        assert merged.skipped == 1
        assert merged.errors == 1
        assert merged.duration_ms == 1500

    def test_merge_results_preserves_issues(self) -> None:
        """Test merging results preserves issues from both."""
        from lucidshark.core.models import UnifiedIssue

        runner = MavenTestRunner()

        issue1 = MagicMock(spec=UnifiedIssue)
        issue2 = MagicMock(spec=UnifiedIssue)

        result1 = TestResult(passed=1, issues=[issue1])
        result2 = TestResult(passed=1, issues=[issue2])

        merged = runner._merge_results(result1, result2)
        assert len(merged.issues) == 2
        assert merged.tool == "maven"


class TestMavenJunitXmlDirParsing:
    """Tests for parsing JUnit XML files from a directory."""

    def test_parse_multiple_xml_files(self) -> None:
        """Test parsing multiple JUnit XML files in a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir)
            project_root = reports_dir.parent

            (reports_dir / "TEST-TestA.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <testsuite tests="2" failures="0" errors="0" skipped="0" time="0.5">
                    <testcase classname="TestA" name="test1" time="0.1"/>
                    <testcase classname="TestA" name="test2" time="0.1"/>
                </testsuite>"""
            )
            (reports_dir / "TEST-TestB.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <testsuite tests="3" failures="1" errors="0" skipped="0" time="0.8">
                    <testcase classname="TestB" name="test1" time="0.1"/>
                    <testcase classname="TestB" name="test2" time="0.1"/>
                    <testcase classname="TestB" name="testFail" time="0.1">
                        <failure type="AssertionError" message="fail">stack</failure>
                    </testcase>
                </testsuite>"""
            )

            runner = MavenTestRunner()
            result = runner._parse_junit_xml_dir(reports_dir, project_root)
            assert result.passed == 4
            assert result.failed == 1

    def test_parse_xml_dir_with_invalid_file(self) -> None:
        """Test that invalid XML files are skipped gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir)
            project_root = reports_dir.parent

            (reports_dir / "TEST-Good.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <testsuite tests="1" failures="0" errors="0" skipped="0" time="0.1">
                    <testcase classname="Good" name="test1" time="0.1"/>
                </testsuite>"""
            )
            (reports_dir / "TEST-Bad.xml").write_text("not valid xml")

            runner = MavenTestRunner()
            result = runner._parse_junit_xml_dir(reports_dir, project_root)
            assert result.passed == 1

    def test_parse_empty_xml_dir(self) -> None:
        """Test parsing empty directory returns empty result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir)
            project_root = reports_dir.parent

            runner = MavenTestRunner()
            result = runner._parse_junit_xml_dir(reports_dir, project_root)
            assert result.passed == 0
            assert result.failed == 0
