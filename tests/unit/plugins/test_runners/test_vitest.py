"""Unit tests for Vitest runner plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.test_runners.vitest import VitestRunner


class TestVitestRunner:
    """Tests for VitestRunner class."""

    def test_name(self) -> None:
        runner = VitestRunner()
        assert runner.name == "vitest"

    def test_languages(self) -> None:
        runner = VitestRunner()
        assert runner.languages == ["javascript", "typescript"]

    def test_domain(self) -> None:
        runner = VitestRunner()
        assert runner.domain == ToolDomain.TESTING


class TestVitestRunnerBinaryFinding:
    """Tests for binary finding logic."""

    def test_find_in_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            binary = runner.ensure_binary()
            assert binary == vitest_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/local/bin/vitest"
        runner = VitestRunner()
        binary = runner.ensure_binary()
        assert binary == Path("/usr/local/bin/vitest")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        runner = VitestRunner()
        with pytest.raises(FileNotFoundError) as exc:
            runner.ensure_binary()
        assert "Vitest is not installed" in str(exc.value)


class TestVitestGetVersion:
    """Tests for version detection."""

    def test_get_version_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            with patch(
                "lucidshark.plugins.test_runners.base.get_cli_version",
                return_value="3.0.4",
            ):
                version = runner.get_version()
                assert version == "3.0.4"

    @patch("shutil.which", return_value=None)
    def test_get_version_unknown_when_not_found(self, mock_which: MagicMock) -> None:
        runner = VitestRunner()
        version = runner.get_version()
        assert version == "unknown"


class TestVitestRunTests:
    """Tests for test execution flow."""

    @patch("shutil.which", return_value=None)
    def test_run_tests_binary_not_found(self, mock_which: MagicMock) -> None:
        runner = VitestRunner()
        context = MagicMock()
        context.project_root = Path("/project")
        context.paths = []
        context.stream_handler = None

        result = runner.run_tests(context)
        assert result.passed == 0
        assert result.failed == 0

    def test_run_tests_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = []

            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("vitest", 600),
            ):
                result = runner.run_tests(context)
                assert result.passed == 0

    def test_run_tests_general_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = []

            with patch("subprocess.run", side_effect=OSError("cannot execute")):
                result = runner.run_tests(context)
                assert result.passed == 0

    def test_run_tests_always_includes_coverage_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = []

            mock_result = MagicMock()
            mock_result.stdout = "{}"

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                runner.run_tests(context)
                cmd = mock_run.call_args[0][0]
                assert "--coverage" in cmd

    def test_run_tests_with_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = [Path("src/tests")]

            mock_result = MagicMock()
            mock_result.stdout = "{}"

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                runner.run_tests(context)
                cmd = mock_run.call_args[0][0]
                assert "src/tests" in cmd

    def test_run_tests_uses_run_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = []

            mock_result = MagicMock()
            mock_result.stdout = "{}"

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                runner.run_tests(context)
                cmd = mock_run.call_args[0][0]
                assert "run" in cmd

    def test_run_tests_uses_json_reporter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = []

            mock_result = MagicMock()
            mock_result.stdout = "{}"

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                runner.run_tests(context)
                cmd = mock_run.call_args[0][0]
                assert "--reporter=json" in cmd

    def test_run_tests_parses_json_report_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            node_bin = project_root / "node_modules" / ".bin"
            node_bin.mkdir(parents=True)
            vitest_bin = node_bin / "vitest"
            vitest_bin.touch()
            vitest_bin.chmod(0o755)

            runner = VitestRunner(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = []

            def fake_run(cmd, **kwargs):
                for arg in cmd:
                    if arg.startswith("--outputFile="):
                        report_path = Path(arg.split("=", 1)[1])
                        report = {
                            "numPassedTests": 3,
                            "numFailedTests": 0,
                            "numPendingTests": 0,
                            "numTodoTests": 0,
                            "testResults": [],
                        }
                        report_path.write_text(json.dumps(report))
                        break
                result = MagicMock()
                result.stdout = ""
                return result

            with patch("subprocess.run", side_effect=fake_run):
                result = runner.run_tests(context)
                assert result.passed == 3
                assert result.failed == 0


class TestVitestReportProcessing:
    """Tests for Vitest report processing (via base class)."""

    def test_process_report_with_failures(self) -> None:
        runner = VitestRunner()

        report = {
            "numPassedTests": 5,
            "numFailedTests": 2,
            "numPendingTests": 1,
            "numTodoTests": 0,
            "startTime": 1000,
            "testResults": [
                {
                    "name": "/project/tests/example.test.ts",
                    "status": "failed",
                    "startTime": 1000,
                    "endTime": 1500,
                    "assertionResults": [
                        {
                            "fullName": "Example test should pass",
                            "status": "passed",
                            "title": "should pass",
                            "ancestorTitles": ["Example test"],
                        },
                        {
                            "fullName": "Example test should fail",
                            "status": "failed",
                            "title": "should fail",
                            "ancestorTitles": ["Example test"],
                            "failureMessages": ["expect(1).toBe(2)"],
                            "location": {"line": 10},
                        },
                    ],
                },
            ],
        }

        project_root = Path("/project")
        result = runner._process_report(report, project_root)

        assert result.passed == 5
        assert result.failed == 2
        assert result.skipped == 1
        assert len(result.issues) == 1

        issue = result.issues[0]
        assert "should fail" in issue.title
        assert issue.source_tool == "vitest"

    def test_process_report_all_passed(self) -> None:
        runner = VitestRunner()

        report = {
            "numPassedTests": 10,
            "numFailedTests": 0,
            "numPendingTests": 0,
            "numTodoTests": 0,
            "testResults": [],
        }

        project_root = Path("/project")
        result = runner._process_report(report, project_root)

        assert result.passed == 10
        assert result.failed == 0
        assert result.success is True
        assert len(result.issues) == 0

    def test_process_report_with_todo_tests(self) -> None:
        runner = VitestRunner()

        report = {
            "numPassedTests": 5,
            "numFailedTests": 0,
            "numPendingTests": 2,
            "numTodoTests": 3,
            "testResults": [],
        }

        result = runner._process_report(report, Path("/project"))
        assert result.skipped == 5  # 2 pending + 3 todo

    def test_process_report_duration_calculation(self) -> None:
        runner = VitestRunner()

        report = {
            "numPassedTests": 2,
            "numFailedTests": 0,
            "numPendingTests": 0,
            "numTodoTests": 0,
            "testResults": [
                {
                    "name": "a.test.ts",
                    "status": "passed",
                    "startTime": 1000,
                    "endTime": 1500,
                    "assertionResults": [],
                },
                {
                    "name": "b.test.ts",
                    "status": "passed",
                    "startTime": 1500,
                    "endTime": 2500,
                    "assertionResults": [],
                },
            ],
        }

        result = runner._process_report(report, Path("/project"))
        assert result.duration_ms == 1500  # 500 + 1000


class TestVitestJsonOutput:
    """Tests for JSON output parsing (via base class)."""

    def test_parse_json_output_empty(self) -> None:
        runner = VitestRunner()
        result = runner._parse_json_output("", Path("/project"))
        assert result.passed == 0

    def test_parse_json_output_whitespace_only(self) -> None:
        runner = VitestRunner()
        result = runner._parse_json_output("   \n  ", Path("/project"))
        assert result.passed == 0

    def test_parse_json_output_invalid_json(self) -> None:
        runner = VitestRunner()
        result = runner._parse_json_output("not json {", Path("/project"))
        assert result.passed == 0

    def test_parse_json_output_valid(self) -> None:
        runner = VitestRunner()
        output = json.dumps(
            {
                "numPassedTests": 5,
                "numFailedTests": 0,
                "numPendingTests": 0,
                "numTodoTests": 0,
                "testResults": [],
            }
        )
        result = runner._parse_json_output(output, Path("/project"))
        assert result.passed == 5

    def test_parse_json_report_file_not_readable(self) -> None:
        runner = VitestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            report_file = Path(tmpdir) / "report.json"
            report_file.write_text("invalid json")

            result = runner._parse_json_report(report_file, Path("/project"))
            assert result.passed == 0


class TestVitestAssertionToIssue:
    """Tests for assertion to issue conversion (via base class)."""

    def test_assertion_with_location(self) -> None:
        runner = VitestRunner()

        assertion = {
            "fullName": "Suite should work",
            "title": "should work",
            "ancestorTitles": ["Suite"],
            "status": "failed",
            "failureMessages": ["Expected 1 to be 2"],
            "location": {"line": 15},
        }
        test_file = {
            "name": "/project/tests/app.test.ts",
            "status": "failed",
        }

        issue = runner._assertion_to_issue(assertion, test_file, Path("/project"))
        assert issue is not None
        assert issue.line_start == 15
        assert issue.file_path == Path("/project/tests/app.test.ts")
        assert "Suite > should work" in issue.title
        assert issue.severity == Severity.HIGH

    def test_assertion_without_location(self) -> None:
        runner = VitestRunner()

        assertion = {
            "fullName": "should work",
            "title": "should work",
            "ancestorTitles": [],
            "status": "failed",
            "failureMessages": ["Test failed"],
            "location": {},
        }
        test_file = {
            "name": "tests/app.test.ts",
            "status": "failed",
        }

        issue = runner._assertion_to_issue(assertion, test_file, Path("/project"))
        assert issue is not None
        assert issue.line_start is None

    def test_assertion_relative_file_path(self) -> None:
        runner = VitestRunner()

        assertion = {
            "fullName": "Test",
            "title": "Test",
            "ancestorTitles": [],
            "status": "failed",
            "failureMessages": ["fail"],
        }
        test_file = {
            "name": "tests/app.test.ts",
            "status": "failed",
        }

        issue = runner._assertion_to_issue(assertion, test_file, Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/project/tests/app.test.ts")

    def test_assertion_no_failure_messages(self) -> None:
        runner = VitestRunner()

        assertion = {
            "fullName": "Test",
            "title": "Test",
            "ancestorTitles": [],
            "status": "failed",
            "failureMessages": [],
        }
        test_file = {"name": "test.ts", "status": "failed"}

        issue = runner._assertion_to_issue(assertion, test_file, Path("/project"))
        assert issue is not None
        assert "Test failed" in issue.description


class TestVitestAssertionExtraction:
    """Tests for assertion message extraction (via base class)."""

    def test_extract_expect_pattern(self) -> None:
        runner = VitestRunner()
        message = "expect(received).toBe(expected)\n\nExpected: 2\nReceived: 1"
        result = runner._extract_assertion(message)
        assert "Expected:" in result or "expect" in result.lower()

    def test_extract_expected_received_pattern(self) -> None:
        runner = VitestRunner()
        message = "\nExpected: 42\nReceived: 0\n"
        result = runner._extract_assertion(message)
        assert "Expected:" in result

    def test_extract_first_meaningful_line(self) -> None:
        runner = VitestRunner()
        message = "\nTypeError: Cannot read property 'foo' of undefined\n    at Object.<anonymous> (test.ts:5:1)\n"
        result = runner._extract_assertion(message)
        assert "TypeError" in result

    def test_empty_message(self) -> None:
        runner = VitestRunner()
        result = runner._extract_assertion("")
        assert result == ""

    def test_extract_skips_short_lines(self) -> None:
        runner = VitestRunner()
        message = "\nat Object.test\nSome meaningful error message here\n"
        result = runner._extract_assertion(message)
        assert len(result) > 5


class TestVitestIssueIdGeneration:
    """Tests for deterministic issue ID generation (via base class)."""

    def test_same_input_same_id(self) -> None:
        runner = VitestRunner()
        id1 = runner._generate_issue_id("Test > should work", "expect")
        id2 = runner._generate_issue_id("Test > should work", "expect")
        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        runner = VitestRunner()
        id1 = runner._generate_issue_id("Test > should work", "expect 1")
        id2 = runner._generate_issue_id("Test > should fail", "expect 2")
        assert id1 != id2

    def test_id_format(self) -> None:
        runner = VitestRunner()
        issue_id = runner._generate_issue_id("Test > should work", "expect")
        assert issue_id.startswith("vitest-")
        assert len(issue_id) == len("vitest-") + 12
