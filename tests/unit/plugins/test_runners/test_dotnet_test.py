"""Unit tests for dotnet test runner plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.test_runners.dotnet_test import DotnetTestRunner


class TestDotnetTestRunnerProperties:
    """Basic property tests for DotnetTestRunner."""

    def test_name(self) -> None:
        runner = DotnetTestRunner()
        assert runner.name == "dotnet_test"

    def test_languages(self) -> None:
        runner = DotnetTestRunner()
        assert runner.languages == ["csharp"]

    def test_domain(self) -> None:
        runner = DotnetTestRunner()
        assert runner.domain == ToolDomain.TESTING


def _make_context(
    project_root: Path,
    enabled_domains: list | None = None,
) -> ScanContext:
    return ScanContext(
        project_root=project_root,
        paths=[project_root],
        enabled_domains=enabled_domains or [ToolDomain.TESTING],
    )


FAKE_BINARY = Path("/usr/bin/dotnet")

# Minimal TRX XML for testing
TRX_PASSING = """\
<?xml version="1.0" encoding="utf-8"?>
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <ResultSummary outcome="Completed">
    <Counters total="3" executed="3" passed="3" failed="0" error="0" timeout="0"
              aborted="0" inconclusive="0" passedButRunAborted="0" notRunnable="0"
              notExecuted="0" disconnected="0" warning="0" completed="0" inProgress="0"
              pending="0" />
  </ResultSummary>
  <Results />
</TestRun>
"""

TRX_FAILING = """\
<?xml version="1.0" encoding="utf-8"?>
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <ResultSummary outcome="Failed">
    <Counters total="3" executed="3" passed="1" failed="2" error="0" timeout="0"
              aborted="0" inconclusive="0" passedButRunAborted="0" notRunnable="0"
              notExecuted="0" disconnected="0" warning="0" completed="0" inProgress="0"
              pending="0" />
  </ResultSummary>
  <Results>
    <UnitTestResult testName="MyTest.TestAdd" outcome="Failed">
      <Output>
        <ErrorInfo>
          <Message>Expected: 4, But was: 5</Message>
          <StackTrace>   at MyTest.TestAdd() in /src/Tests.cs:line 42</StackTrace>
        </ErrorInfo>
      </Output>
    </UnitTestResult>
    <UnitTestResult testName="MyTest.TestSubtract" outcome="Failed">
      <Output>
        <ErrorInfo>
          <Message>Assert.Equal() Failure</Message>
          <StackTrace>   at MyTest.TestSubtract() in /src/Tests.cs:line 55</StackTrace>
        </ErrorInfo>
      </Output>
    </UnitTestResult>
  </Results>
</TestRun>
"""


class TestParseTrxReports:
    """Tests for TRX report parsing."""

    def test_parse_passing_trx(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            results_dir = project_root / "TestResults"
            results_dir.mkdir()
            trx_file = results_dir / "test.trx"
            trx_file.write_text(TRX_PASSING)

            runner = DotnetTestRunner()
            result = runner._parse_trx_reports(results_dir, project_root)

            assert result is not None
            assert result.passed == 3
            assert result.failed == 0
            assert result.skipped == 0
            assert result.issues == []
            assert result.tool == "dotnet_test"

    def test_parse_failing_trx(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            results_dir = project_root / "TestResults"
            results_dir.mkdir()
            trx_file = results_dir / "test.trx"
            trx_file.write_text(TRX_FAILING)

            runner = DotnetTestRunner()
            result = runner._parse_trx_reports(results_dir, project_root)

            assert result is not None
            assert result.passed == 1
            assert result.failed == 2
            assert len(result.issues) == 2
            assert result.issues[0].domain == ToolDomain.TESTING
            assert result.issues[0].source_tool == "dotnet_test"
            assert "TestAdd" in result.issues[0].title
            assert "Expected: 4" in result.issues[0].description

    def test_parse_no_results_dir(self) -> None:
        runner = DotnetTestRunner()
        result = runner._parse_trx_reports(Path("/nonexistent"), Path("/tmp"))
        assert result is None

    def test_parse_empty_results_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "TestResults"
            results_dir.mkdir()

            runner = DotnetTestRunner()
            result = runner._parse_trx_reports(results_dir, Path(tmpdir))
            assert result is None


class TestParseConsoleOutput:
    """Tests for console output parsing."""

    def test_parse_passing_output(self) -> None:
        runner = DotnetTestRunner()
        output = "Passed! - Failed: 0, Passed: 5, Skipped: 0, Total: 5\n"
        result = runner._parse_console_output(output, Path("/tmp"))
        assert result.passed == 5
        assert result.failed == 0
        assert result.skipped == 0
        assert result.tool == "dotnet_test"

    def test_parse_failed_output(self) -> None:
        runner = DotnetTestRunner()
        output = "Failed! - Failed: 2, Passed: 3, Skipped: 1, Total: 6\n"
        result = runner._parse_console_output(output, Path("/tmp"))
        assert result.passed == 3
        assert result.failed == 2
        assert result.skipped == 1

    def test_parse_empty_output(self) -> None:
        runner = DotnetTestRunner()
        result = runner._parse_console_output("", Path("/tmp"))
        assert result.passed == 0
        assert result.failed == 0


class TestExtractLocation:
    """Tests for _extract_location method."""

    def test_extracts_from_stack_trace(self) -> None:
        runner = DotnetTestRunner()
        trace = "   at MyTest.TestAdd() in /src/Tests.cs:line 42"
        file_path, line_num = runner._extract_location(trace, Path("/project"))
        assert file_path == Path("/src/Tests.cs")
        assert line_num == 42

    def test_relative_path(self) -> None:
        runner = DotnetTestRunner()
        trace = "   at MyTest.TestAdd() in src/Tests.cs:line 10"
        file_path, line_num = runner._extract_location(trace, Path("/project"))
        assert file_path == Path("/project/src/Tests.cs")
        assert line_num == 10

    def test_no_match(self) -> None:
        runner = DotnetTestRunner()
        file_path, line_num = runner._extract_location("no match here", Path("/tmp"))
        assert file_path is None
        assert line_num is None

    def test_empty_trace(self) -> None:
        runner = DotnetTestRunner()
        file_path, line_num = runner._extract_location("", Path("/tmp"))
        assert file_path is None
        assert line_num is None


class TestRunTests:
    """Tests for run_tests method."""

    def test_no_project_file_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = DotnetTestRunner()
            context = _make_context(Path(tmpdir))
            with patch.object(runner, "ensure_binary", return_value=FAKE_BINARY):
                result = runner.run_tests(context)
                assert result.passed == 0
                assert result.tool == "dotnet_test"

    def test_binary_not_found(self) -> None:
        runner = DotnetTestRunner()
        context = _make_context(Path("/tmp"))
        with patch.object(
            runner, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = runner.run_tests(context)
            assert result.tool == "dotnet_test"

    @patch("lucidshark.plugins.test_runners.dotnet_test.run_with_streaming")
    @patch.object(DotnetTestRunner, "ensure_binary")
    def test_uses_trx_logger(
        self, mock_binary: MagicMock, mock_run: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()
            mock_binary.return_value = FAKE_BINARY

            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="Passed! - Failed: 0, Passed: 3, Skipped: 0, Total: 3\n",
                stderr="",
            )

            runner = DotnetTestRunner()
            context = _make_context(project_root)
            runner.run_tests(context)

            # Check that --logger trx was in the command
            call_args = mock_run.call_args
            cmd = (
                call_args.kwargs.get("cmd")
                or call_args[1].get("cmd")
                or call_args[0][0]
            )
            assert "--logger" in cmd
            assert "trx" in cmd

    @patch("lucidshark.plugins.test_runners.dotnet_test.run_with_streaming")
    @patch.object(DotnetTestRunner, "ensure_binary")
    def test_adds_coverage_when_domain_enabled(
        self, mock_binary: MagicMock, mock_run: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()
            mock_binary.return_value = FAKE_BINARY

            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="Passed! - Failed: 0, Passed: 1, Skipped: 0, Total: 1\n",
                stderr="",
            )

            runner = DotnetTestRunner()
            context = _make_context(
                project_root,
                enabled_domains=[ToolDomain.TESTING, ToolDomain.COVERAGE],
            )
            runner.run_tests(context)

            call_args = mock_run.call_args
            cmd = (
                call_args.kwargs.get("cmd")
                or call_args[1].get("cmd")
                or call_args[0][0]
            )
            assert any("XPlat Code Coverage" in arg for arg in cmd)

    def test_timeout_returns_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            runner = DotnetTestRunner()
            context = _make_context(project_root)

            with (
                patch(
                    "lucidshark.plugins.test_runners.dotnet_test.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(cmd="dotnet", timeout=600),
                ),
                patch.object(runner, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = runner.run_tests(context)
                assert result.tool == "dotnet_test"
                assert result.passed == 0
