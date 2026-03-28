"""Unit tests for CTest test runner plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch


from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.test_runners.ctest import CTestRunner


SAMPLE_CTEST_OUTPUT = """\
Test project /tmp/build
    Start  1: test_basic
1/4 Test  #1: test_basic ...................   Passed    0.01 sec
    Start  2: test_advanced
2/4 Test  #2: test_advanced ................   Passed    0.02 sec
    Start  3: test_failing
3/4 Test  #3: test_failing .................***Failed    0.01 sec
    Start  4: test_skipped
4/4 Test  #4: test_skipped .................   Not Run   0.00 sec

75% tests passed, 1 tests failed out of 4

Total Test time (real) =   0.04 sec

The following tests FAILED:
          3 - test_failing (Failed)
Errors while running CTest
"""


class TestCTestProperties:
    """Basic property tests for CTestRunner."""

    def test_name(self) -> None:
        runner = CTestRunner()
        assert runner.name == "ctest"

    def test_languages(self) -> None:
        runner = CTestRunner()
        assert runner.languages == ["c++"]

    def test_domain(self) -> None:
        runner = CTestRunner()
        assert runner.domain == ToolDomain.TESTING


class TestParseCTestOutput:
    """Tests for _parse_ctest_output."""

    def test_parse_mixed_results(self) -> None:
        runner = CTestRunner()
        result = runner._parse_ctest_output(SAMPLE_CTEST_OUTPUT, Path("/tmp"))
        assert result.passed == 2
        assert result.failed == 1
        assert result.skipped == 1
        assert result.tool == "ctest"

    def test_parse_all_passing(self) -> None:
        runner = CTestRunner()
        output = """\
Test project /tmp/build
    Start  1: test_one
1/2 Test  #1: test_one .....................   Passed    0.01 sec
    Start  2: test_two
2/2 Test  #2: test_two .....................   Passed    0.02 sec

100% tests passed, 0 tests failed out of 2
"""
        result = runner._parse_ctest_output(output, Path("/tmp"))
        assert result.passed == 2
        assert result.failed == 0
        assert result.skipped == 0

    def test_parse_empty_output(self) -> None:
        runner = CTestRunner()
        result = runner._parse_ctest_output("", Path("/tmp"))
        assert result.passed == 0
        assert result.failed == 0
        assert result.tool == "ctest"

    def test_parse_all_failing(self) -> None:
        runner = CTestRunner()
        output = """\
Test project /tmp/build
    Start  1: test_a
1/2 Test  #1: test_a .......................***Failed    0.01 sec
    Start  2: test_b
2/2 Test  #2: test_b .......................***Failed    0.01 sec

0% tests passed, 2 tests failed out of 2
"""
        result = runner._parse_ctest_output(output, Path("/tmp"))
        assert result.passed == 0
        assert result.failed == 2
        assert len(result.issues) == 2

    def test_failure_creates_issue(self) -> None:
        runner = CTestRunner()
        result = runner._parse_ctest_output(SAMPLE_CTEST_OUTPUT, Path("/tmp"))
        assert len(result.issues) == 1
        assert result.issues[0].domain == ToolDomain.TESTING
        assert result.issues[0].severity == Severity.HIGH
        assert "test_failing" in result.issues[0].title

    def test_duration_calculated(self) -> None:
        runner = CTestRunner()
        result = runner._parse_ctest_output(SAMPLE_CTEST_OUTPUT, Path("/tmp"))
        assert result.duration_ms > 0

    def test_parse_summary_fallback(self) -> None:
        runner = CTestRunner()
        output = "80% tests passed, 1 tests failed out of 5\n"
        result = runner._parse_ctest_output(output, Path("/tmp"))
        assert result.passed == 4
        assert result.failed == 1

    def test_timeout_counted_as_failure(self) -> None:
        runner = CTestRunner()
        output = """\
Test project /tmp/build
    Start  1: test_slow
1/1 Test  #1: test_slow ....................   Timeout   30.00 sec
"""
        result = runner._parse_ctest_output(output, Path("/tmp"))
        assert result.failed == 1


class TestFailureToIssue:
    """Tests for _failure_to_issue."""

    def test_creates_issue(self) -> None:
        runner = CTestRunner()
        issue = runner._failure_to_issue(
            "test_basic", "assertion failed at line 42", Path("/tmp")
        )
        assert issue is not None
        assert issue.domain == ToolDomain.TESTING
        assert issue.source_tool == "ctest"
        assert "test_basic" in issue.title
        assert issue.severity == Severity.HIGH

    def test_truncates_long_title(self) -> None:
        runner = CTestRunner()
        long_output = "x" * 500
        issue = runner._failure_to_issue("test_name", long_output, Path("/tmp"))
        assert issue is not None
        assert len(issue.title) <= 200

    def test_empty_output(self) -> None:
        runner = CTestRunner()
        issue = runner._failure_to_issue("test_name", "", Path("/tmp"))
        assert issue is not None
        assert "Test failed" in issue.title


class TestExtractLocation:
    """Tests for _extract_location."""

    def test_extracts_cpp_file_location(self) -> None:
        runner = CTestRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_main.cpp"
            test_file.write_text("int main() {}")
            output = f"{test_file}:42: FAILED\n"
            file_path, line_num = runner._extract_location(output, Path(tmpdir))
            assert file_path == test_file
            assert line_num == 42

    def test_extracts_parenthesis_format(self) -> None:
        runner = CTestRunner()
        output = "test_main.cpp(15): assertion failed\n"
        file_path, line_num = runner._extract_location(output, Path("/tmp"))
        assert line_num == 15

    def test_returns_none_for_no_location(self) -> None:
        runner = CTestRunner()
        output = "Some generic output\n"
        file_path, line_num = runner._extract_location(output, Path("/tmp"))
        assert file_path is None
        assert line_num is None


class TestExtractShortMessage:
    """Tests for _extract_short_message."""

    def test_extracts_assertion_message(self) -> None:
        runner = CTestRunner()
        output = "some setup output\nEXPECT_EQ(a, b) failed\nmore output\n"
        msg = runner._extract_short_message(output)
        assert "EXPECT_EQ" in msg

    def test_extracts_catch2_require(self) -> None:
        runner = CTestRunner()
        output = "REQUIRE( x == 5 ) failed\n"
        msg = runner._extract_short_message(output)
        assert "REQUIRE" in msg

    def test_empty_output_returns_default(self) -> None:
        runner = CTestRunner()
        msg = runner._extract_short_message("")
        assert msg == "Test failed"


class TestRunTests:
    """Tests for run_tests method."""

    @patch.object(CTestRunner, "ensure_binary")
    def test_binary_not_found(self, mock_binary) -> None:
        mock_binary.side_effect = FileNotFoundError("ctest not found")
        runner = CTestRunner()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        result = runner.run_tests(context)
        assert result.tool == "ctest"
        assert result.passed == 0

    def test_no_cmake_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = CTestRunner()
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )
            with patch.object(
                CTestRunner, "ensure_binary", return_value=Path("/usr/bin/ctest")
            ):
                result = runner.run_tests(context)
                assert result.tool == "ctest"
                assert result.passed == 0

    def test_no_build_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "CMakeLists.txt").write_text("project(test)")
            runner = CTestRunner()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            with patch.object(
                CTestRunner, "ensure_binary", return_value=Path("/usr/bin/ctest")
            ):
                result = runner.run_tests(context)
                assert result.errors == 1
                assert any(
                    "build directory" in str(i.title).lower() for i in result.issues
                )


class TestGenerateIssueId:
    """Tests for _generate_ctest_issue_id."""

    def test_deterministic(self) -> None:
        runner = CTestRunner()
        id1 = runner._generate_ctest_issue_id("test_basic")
        id2 = runner._generate_ctest_issue_id("test_basic")
        assert id1 == id2

    def test_different_tests_different_ids(self) -> None:
        runner = CTestRunner()
        id1 = runner._generate_ctest_issue_id("test_one")
        id2 = runner._generate_ctest_issue_id("test_two")
        assert id1 != id2

    def test_starts_with_ctest(self) -> None:
        runner = CTestRunner()
        issue_id = runner._generate_ctest_issue_id("test_basic")
        assert issue_id.startswith("ctest-")
