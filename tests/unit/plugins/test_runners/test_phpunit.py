"""Unit tests for PHPUnit test runner plugin.

These tests mock subprocess calls to test the parsing logic without
requiring actual PHPUnit installation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.test_runners.phpunit import (
    PhpunitRunner,
    _find_phpunit,
)


class TestPhpunitRunner:
    """Unit tests for PhpunitRunner."""

    def test_name(self) -> None:
        runner = PhpunitRunner()
        assert runner.name == "phpunit"

    def test_languages(self) -> None:
        runner = PhpunitRunner()
        assert runner.languages == ["php"]

    def test_domain(self) -> None:
        runner = PhpunitRunner()
        assert runner.domain == ToolDomain.TESTING

    def test_ensure_binary_vendor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            vendor_bin = tmpdir_path / "vendor" / "bin"
            vendor_bin.mkdir(parents=True)
            phpunit_path = vendor_bin / "phpunit"
            phpunit_path.touch()

            runner = PhpunitRunner(project_root=tmpdir_path)
            binary = runner.ensure_binary()
            assert binary == phpunit_path

    def test_ensure_binary_system_path(self) -> None:
        runner = PhpunitRunner()
        with patch("shutil.which", return_value="/usr/local/bin/phpunit"):
            binary = runner.ensure_binary()
            assert binary == Path("/usr/local/bin/phpunit")

    def test_ensure_binary_not_found(self) -> None:
        runner = PhpunitRunner()
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError) as exc_info:
                runner.ensure_binary()
            assert "PHPUnit is not installed" in str(exc_info.value)

    def test_run_tests_no_binary(self) -> None:
        runner = PhpunitRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )
            with patch.object(
                runner, "ensure_binary", side_effect=FileNotFoundError("not found")
            ):
                result = runner.run_tests(context)
                assert result.tool == "phpunit"
                assert result.passed == 0

    def test_run_tests_timeout(self) -> None:
        runner = PhpunitRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )
            with patch.object(
                runner, "ensure_binary", return_value=Path("/usr/bin/phpunit")
            ):
                with patch.object(
                    runner,
                    "_run_test_subprocess",
                    return_value=None,
                ):
                    result = runner.run_tests(context)
                    assert result.tool == "phpunit"
                    assert result.passed == 0


class TestJunitXmlParsing:
    """Tests for PHPUnit JUnit XML parsing."""

    def test_parse_passing_tests(self) -> None:
        runner = PhpunitRunner()

        xml_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<testsuites>\n"
            '  <testsuite name="Tests" tests="3" assertions="5" errors="0" failures="0" skipped="0" time="0.123">\n'
            '    <testcase name="testAdd" classname="Tests\\MathTest" file="/app/tests/MathTest.php" line="10" assertions="2" time="0.05"/>\n'
            '    <testcase name="testSubtract" classname="Tests\\MathTest" file="/app/tests/MathTest.php" line="20" assertions="2" time="0.03"/>\n'
            '    <testcase name="testMultiply" classname="Tests\\MathTest" file="/app/tests/MathTest.php" line="30" assertions="1" time="0.04"/>\n'
            "  </testsuite>\n"
            "</testsuites>\n"
        )

        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(xml_content)
            junit_path = Path(f.name)

        try:
            result = runner._parse_junit_xml(junit_path, Path("/app"))
            assert result.tool == "phpunit"
            assert result.passed == 3
            assert result.failed == 0
            assert result.errors == 0
            assert result.skipped == 0
        finally:
            junit_path.unlink()

    def test_parse_nested_testsuites_no_double_counting(self) -> None:
        """Nested testsuites must not inflate counts."""
        runner = PhpunitRunner()

        xml_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<testsuites>\n"
            '  <testsuite name="All" tests="5" assertions="8" errors="0" failures="1" skipped="0" time="0.2">\n'
            '    <testsuite name="Tests\\Unit" tests="3" assertions="5" errors="0" failures="1" skipped="0" time="0.1">\n'
            '      <testcase name="testA" classname="Tests\\Unit\\FooTest" file="/app/tests/Unit/FooTest.php" line="10" time="0.03"/>\n'
            '      <testcase name="testB" classname="Tests\\Unit\\FooTest" file="/app/tests/Unit/FooTest.php" line="20" time="0.03">\n'
            '        <failure type="PHPUnit\\Framework\\ExpectationFailedException" message="Failed">Failed</failure>\n'
            "      </testcase>\n"
            '      <testcase name="testC" classname="Tests\\Unit\\FooTest" file="/app/tests/Unit/FooTest.php" line="30" time="0.04"/>\n'
            "    </testsuite>\n"
            '    <testsuite name="Tests\\Feature" tests="2" assertions="3" errors="0" failures="0" skipped="0" time="0.1">\n'
            '      <testcase name="testD" classname="Tests\\Feature\\BarTest" file="/app/tests/Feature/BarTest.php" line="10" time="0.05"/>\n'
            '      <testcase name="testE" classname="Tests\\Feature\\BarTest" file="/app/tests/Feature/BarTest.php" line="20" time="0.05"/>\n'
            "    </testsuite>\n"
            "  </testsuite>\n"
            "</testsuites>\n"
        )

        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(xml_content)
            junit_path = Path(f.name)

        try:
            result = runner._parse_junit_xml(junit_path, Path("/app"))
            # Should count only the top-level testsuite (tests=5, failures=1)
            # NOT 5+3+2=10 tests and 1+1+0=2 failures from all levels
            assert result.passed == 4
            assert result.failed == 1
            assert result.errors == 0
            assert result.skipped == 0
        finally:
            junit_path.unlink()

    def test_parse_failing_tests(self) -> None:
        runner = PhpunitRunner()

        xml_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<testsuites>\n"
            '  <testsuite name="Tests" tests="2" assertions="3" errors="0" failures="1" skipped="0" time="0.1">\n'
            '    <testcase name="testPass" classname="Tests\\FooTest" file="/app/tests/FooTest.php" line="10" assertions="1" time="0.05"/>\n'
            '    <testcase name="testFail" classname="Tests\\FooTest" file="/app/tests/FooTest.php" line="20" assertions="2" time="0.05">\n'
            '      <failure type="PHPUnit\\Framework\\ExpectationFailedException" message="Failed asserting that 2 matches expected 3.">'
            "Failed asserting that 2 matches expected 3.\n/app/tests/FooTest.php:25"
            "</failure>\n"
            "    </testcase>\n"
            "  </testsuite>\n"
            "</testsuites>\n"
        )

        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(xml_content)
            junit_path = Path(f.name)

        try:
            result = runner._parse_junit_xml(junit_path, Path("/app"))
            assert result.failed == 1
            assert len(result.issues) == 1
            assert result.issues[0].source_tool == "phpunit"
            assert result.issues[0].severity == Severity.HIGH
            assert "testFail" in result.issues[0].title
        finally:
            junit_path.unlink()

    def test_parse_error_tests(self) -> None:
        runner = PhpunitRunner()

        xml_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<testsuites>\n"
            '  <testsuite name="Tests" tests="1" assertions="0" errors="1" failures="0" skipped="0" time="0.01">\n'
            '    <testcase name="testBroken" classname="Tests\\BrokenTest" file="/app/tests/BrokenTest.php" line="5" time="0.01">\n'
            "      <error type=\"Error\" message=\"Class 'Foo' not found\">Error: Class 'Foo' not found</error>\n"
            "    </testcase>\n"
            "  </testsuite>\n"
            "</testsuites>\n"
        )

        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(xml_content)
            junit_path = Path(f.name)

        try:
            result = runner._parse_junit_xml(junit_path, Path("/app"))
            assert len(result.issues) == 1
            assert "BrokenTest" in result.issues[0].title
        finally:
            junit_path.unlink()

    def test_parse_skipped_tests(self) -> None:
        runner = PhpunitRunner()

        xml_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<testsuites>\n"
            '  <testsuite name="Tests" tests="2" assertions="1" errors="0" failures="0" skipped="1" time="0.05">\n'
            '    <testcase name="testPass" classname="Tests\\FooTest" assertions="1" time="0.03"/>\n'
            '    <testcase name="testSkipped" classname="Tests\\FooTest" time="0.02">\n'
            "      <skipped/>\n"
            "    </testcase>\n"
            "  </testsuite>\n"
            "</testsuites>\n"
        )

        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(xml_content)
            junit_path = Path(f.name)

        try:
            result = runner._parse_junit_xml(junit_path, Path("/app"))
            assert result.skipped >= 1
        finally:
            junit_path.unlink()

    def test_parse_missing_file(self) -> None:
        runner = PhpunitRunner()
        result = runner._parse_junit_xml(Path("/nonexistent.xml"), Path("/app"))
        assert result.passed == 0
        assert result.failed == 0

    def test_parse_invalid_xml(self) -> None:
        runner = PhpunitRunner()

        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write("not valid xml <<<<")
            junit_path = Path(f.name)

        try:
            result = runner._parse_junit_xml(junit_path, Path("/app"))
            assert result.passed == 0
        finally:
            junit_path.unlink()


class TestPhpunitIssueId:
    """Tests for issue ID generation."""

    def test_deterministic(self) -> None:
        runner = PhpunitRunner()
        id1 = runner._generate_phpunit_issue_id("FooTest", "testBar")
        id2 = runner._generate_phpunit_issue_id("FooTest", "testBar")
        assert id1 == id2

    def test_different_inputs(self) -> None:
        runner = PhpunitRunner()
        id1 = runner._generate_phpunit_issue_id("FooTest", "testBar")
        id2 = runner._generate_phpunit_issue_id("FooTest", "testBaz")
        assert id1 != id2

    def test_prefix(self) -> None:
        runner = PhpunitRunner()
        issue_id = runner._generate_phpunit_issue_id("FooTest", "testBar")
        assert issue_id.startswith("phpunit-")


class TestFindPhpunit:
    """Tests for _find_phpunit helper."""

    def test_find_in_vendor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            vendor_bin = tmpdir_path / "vendor" / "bin"
            vendor_bin.mkdir(parents=True)
            (vendor_bin / "phpunit").touch()

            result = _find_phpunit(tmpdir_path)
            assert result == vendor_bin / "phpunit"

    def test_find_in_path(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/phpunit"):
            result = _find_phpunit()
            assert result == Path("/usr/bin/phpunit")

    def test_not_found(self) -> None:
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError):
                _find_phpunit()
