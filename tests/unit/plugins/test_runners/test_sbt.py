"""Unit tests for sbt test runner plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.test_runners.sbt import SbtTestRunner


class TestSbtTestRunner:
    """Tests for SbtTestRunner class."""

    def test_name(self) -> None:
        plugin = SbtTestRunner()
        assert plugin.name == "sbt"

    def test_languages(self) -> None:
        plugin = SbtTestRunner()
        assert plugin.languages == ["scala"]

    def test_domain(self) -> None:
        plugin = SbtTestRunner()
        assert plugin.domain == ToolDomain.TESTING


class TestSbtBuildDetection:
    """Tests for build system detection."""

    def test_detect_sbt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = SbtTestRunner(project_root=project_root)
                binary, build_system = plugin._detect_build_system()
                assert build_system == "sbt"

    def test_detect_maven_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = SbtTestRunner(project_root=project_root)
            binary, build_system = plugin._detect_build_system()
            assert build_system == "maven"

    def test_detect_gradle_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            gradlew = project_root / "gradlew"
            gradlew.touch()

            plugin = SbtTestRunner(project_root=project_root)
            binary, build_system = plugin._detect_build_system()
            assert build_system == "gradle"

    def test_no_build_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = SbtTestRunner(project_root=project_root)
                with pytest.raises(FileNotFoundError):
                    plugin._detect_build_system()


class TestSbtEnsureBinary:
    """Tests for ensure_binary."""

    def test_ensure_binary_sbt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = SbtTestRunner(project_root=project_root)
                binary = plugin.ensure_binary()
                assert binary == Path("/usr/local/bin/sbt")

    def test_ensure_binary_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = SbtTestRunner(project_root=project_root)
                with pytest.raises(FileNotFoundError):
                    plugin.ensure_binary()


class TestSbtJunitParsing:
    """Tests for JUnit XML report parsing."""

    def test_parse_sbt_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "target" / "test-reports"
            report_dir.mkdir(parents=True)

            xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.MySpec" tests="3" failures="1" errors="0" skipped="0" time="1.5">
    <testcase classname="com.example.MySpec" name="should add numbers" time="0.5"/>
    <testcase classname="com.example.MySpec" name="should subtract" time="0.3"/>
    <testcase classname="com.example.MySpec" name="should divide" time="0.7">
        <failure type="org.scalatest.exceptions.TestFailedException" message="2 did not equal 3">
            at com.example.MySpec.should divide(MySpec.scala:15)
        </failure>
    </testcase>
</testsuite>"""
            (report_dir / "TEST-com.example.MySpec.xml").write_text(xml_content)

            plugin = SbtTestRunner(project_root=project_root)
            result = plugin._parse_sbt_reports(project_root)

            assert result.passed == 2
            assert result.failed == 1
            assert result.skipped == 0
            assert result.errors == 0
            assert result.tool == "sbt"
            assert len(result.issues) == 1

            issue = result.issues[0]
            assert issue.domain == ToolDomain.TESTING
            assert issue.source_tool == "sbt"
            assert issue.severity == Severity.HIGH
            assert "should divide" in issue.title

    def test_parse_sbt_reports_versioned_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "target" / "scala-2.13" / "test-reports"
            report_dir.mkdir(parents=True)

            xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="MySpec" tests="2" failures="0" errors="0" skipped="0" time="0.5">
    <testcase classname="MySpec" name="test1" time="0.3"/>
    <testcase classname="MySpec" name="test2" time="0.2"/>
</testsuite>"""
            (report_dir / "TEST-MySpec.xml").write_text(xml_content)

            plugin = SbtTestRunner(project_root=project_root)
            result = plugin._parse_sbt_reports(project_root)

            assert result.passed == 2
            assert result.failed == 0

    def test_parse_no_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = SbtTestRunner(project_root=project_root)
            result = plugin._parse_sbt_reports(project_root)

            assert result.passed == 0
            assert result.failed == 0
            assert result.total == 0

    def test_parse_surefire_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "target" / "surefire-reports"
            report_dir.mkdir(parents=True)

            xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.ScalaSpec" tests="1" failures="0" errors="0" skipped="0" time="0.1">
    <testcase classname="com.example.ScalaSpec" name="test" time="0.1"/>
</testsuite>"""
            (report_dir / "TEST-com.example.ScalaSpec.xml").write_text(xml_content)

            plugin = SbtTestRunner(project_root=project_root)
            result = plugin._parse_surefire_reports(project_root)

            assert result.passed == 1
            assert result.failed == 0

    def test_parse_gradle_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            report_dir = project_root / "build" / "test-results" / "test"
            report_dir.mkdir(parents=True)

            xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="ScalaSpec" tests="2" failures="1" errors="0" skipped="1" time="0.3">
    <testcase classname="ScalaSpec" name="passing" time="0.1"/>
    <testcase classname="ScalaSpec" name="failing" time="0.1">
        <failure message="assertion failed"/>
    </testcase>
    <testcase classname="ScalaSpec" name="skipped" time="0.0">
        <skipped/>
    </testcase>
</testsuite>"""
            (report_dir / "TEST-ScalaSpec.xml").write_text(xml_content)

            plugin = SbtTestRunner(project_root=project_root)
            result = plugin._parse_gradle_reports(project_root)

            assert result.passed == 0  # 2 total - 1 failure - 0 errors - 1 skipped
            assert result.failed == 1
            assert result.skipped == 1


class TestSbtTestcaseToIssue:
    """Tests for test failure to issue conversion."""

    def test_testcase_resolves_scala_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            test_dir = project_root / "src" / "test" / "scala" / "com" / "example"
            test_dir.mkdir(parents=True)
            (test_dir / "MySpec.scala").touch()

            import defusedxml.ElementTree as ET

            testcase_xml = '<testcase classname="com.example.MySpec" name="test" time="0.1"/>'
            failure_xml = '<failure type="TestFailed" message="oops">stacktrace</failure>'
            testcase = ET.fromstring(testcase_xml)
            failure = ET.fromstring(failure_xml)

            plugin = SbtTestRunner(project_root=project_root)
            issue = plugin._testcase_to_issue(testcase, failure, project_root, "failed")

            assert issue is not None
            assert issue.file_path == test_dir / "MySpec.scala"


class TestSbtRunTests:
    """Tests for run_tests method."""

    def test_run_tests_no_build_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = SbtTestRunner(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root

                result = plugin.run_tests(context)
                assert result.tool == "sbt"
                assert result.total == 0
                context.record_skip.assert_called_once()


class TestSbtMergeResults:
    """Tests for result merging."""

    def test_merge_results(self) -> None:
        from lucidshark.plugins.test_runners.base import TestResult

        plugin = SbtTestRunner()
        r1 = TestResult(passed=5, failed=1, skipped=2, errors=0, duration_ms=100, tool="sbt")
        r2 = TestResult(passed=3, failed=2, skipped=0, errors=1, duration_ms=200, tool="sbt")

        merged = plugin._merge_results(r1, r2)
        assert merged.passed == 8
        assert merged.failed == 3
        assert merged.skipped == 2
        assert merged.errors == 1
        assert merged.duration_ms == 300
        assert merged.tool == "sbt"


class TestSbtExtractLine:
    """Tests for stacktrace line extraction."""

    def test_extract_line_scala_style(self) -> None:
        plugin = SbtTestRunner()
        stacktrace = "at com.example.MySpec.should work(MySpec.scala:42)"
        line = plugin._extract_line_from_stacktrace(stacktrace, "com.example.MySpec")
        assert line == 42

    def test_extract_line_inner_class(self) -> None:
        plugin = SbtTestRunner()
        stacktrace = "at com.example.MySpec$Inner.test(MySpec.scala:10)"
        line = plugin._extract_line_from_stacktrace(stacktrace, "com.example.MySpec")
        assert line == 10

    def test_extract_line_no_match(self) -> None:
        plugin = SbtTestRunner()
        stacktrace = "at org.other.Class.method(Class.java:10)"
        line = plugin._extract_line_from_stacktrace(stacktrace, "com.example.MySpec")
        assert line is None
