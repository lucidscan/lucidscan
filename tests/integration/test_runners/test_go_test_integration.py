"""Integration tests for go test runner plugin.

These tests require Go to be installed.

Run with: pytest tests/integration/test_runners/test_go_test_integration.py -v
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.test_runners.go_test import GoTestRunner
from tests.integration.conftest import go_available


def _create_temp_go_project(
    tmp_path: Path, module_name: str = "example.com/testproject"
) -> Path:
    """Create a minimal Go project in tmp_path."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(f"module {module_name}\n\ngo 1.21\n")
    return tmp_path


class TestGoTestAvailability:
    """Tests for go test availability."""

    @go_available
    def test_ensure_binary_finds_go(self, go_test_runner: GoTestRunner) -> None:
        """Test that ensure_binary finds the go binary."""
        binary_path = go_test_runner.ensure_binary()
        assert binary_path.exists()
        assert "go" in binary_path.name

    @go_available
    def test_get_version(self, go_test_runner: GoTestRunner) -> None:
        """Test that get_version returns a version string."""
        version = go_test_runner.get_version()
        assert version != "unknown"
        assert "go" in version.lower()


@go_available
class TestGoTestFunctional:
    """Functional integration tests for go test runner."""

    def test_run_passing_tests(self, go_test_runner: GoTestRunner) -> None:
        """Test running a Go project where all tests pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            # Create a file with a function and a passing test
            main_go = tmpdir_path / "main.go"
            main_go.write_text(
                "package main\n\n"
                "func Add(a, b int) int { return a + b }\n\n"
                "func main() {}\n"
            )

            test_go = tmpdir_path / "main_test.go"
            test_go.write_text(
                'package main\n\nimport "testing"\n\n'
                "func TestAdd(t *testing.T) {\n"
                "\tif Add(1, 2) != 3 {\n"
                '\t\tt.Error("expected 3")\n'
                "\t}\n}\n\n"
                "func TestAddNegative(t *testing.T) {\n"
                "\tif Add(-1, 1) != 0 {\n"
                '\t\tt.Error("expected 0")\n'
                "\t}\n}\n"
            )

            subprocess.run(
                ["go", "mod", "tidy"],
                cwd=tmpdir_path,
                capture_output=True,
                timeout=60,
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = go_test_runner.run_tests(context)

            assert result.passed >= 2
            assert result.failed == 0
            assert result.success is True
            assert result.tool == "go_test"

    def test_run_failing_tests(self, go_test_runner: GoTestRunner) -> None:
        """Test running a Go project with failing tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            test_go = tmpdir_path / "fail_test.go"
            test_go.write_text(
                'package main\n\nimport "testing"\n\n'
                "func TestFail(t *testing.T) {\n"
                '\tt.Error("intentional failure")\n'
                "}\n"
            )

            subprocess.run(
                ["go", "mod", "tidy"],
                cwd=tmpdir_path,
                capture_output=True,
                timeout=60,
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = go_test_runner.run_tests(context)

            assert result.failed >= 1
            assert result.success is False
            assert result.tool == "go_test"

            # Should have at least one issue for the failure
            assert len(result.issues) >= 1
            for issue in result.issues:
                assert issue.domain == ToolDomain.TESTING
                assert issue.source_tool == "go_test"

    def test_run_tests_skips_without_go_mod(self, go_test_runner: GoTestRunner) -> None:
        """Test that go test returns empty TestResult when no go.mod is present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a test file but no go.mod
            test_go = tmpdir_path / "main_test.go"
            test_go.write_text(
                'package main\n\nimport "testing"\n\nfunc TestOK(t *testing.T) {}\n'
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = go_test_runner.run_tests(context)

            assert result.total == 0
            assert result.tool == "go_test"

    def test_run_tests_with_coverage_flag(self, go_test_runner: GoTestRunner) -> None:
        """Test that coverage domain triggers -coverprofile flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            main_go = tmpdir_path / "main.go"
            main_go.write_text(
                "package main\n\n"
                "func Add(a, b int) int { return a + b }\n\n"
                "func main() {}\n"
            )

            test_go = tmpdir_path / "main_test.go"
            test_go.write_text(
                'package main\n\nimport "testing"\n\n'
                "func TestAdd(t *testing.T) {\n"
                "\tif Add(1, 2) != 3 {\n"
                '\t\tt.Error("expected 3")\n'
                "\t}\n}\n"
            )

            subprocess.run(
                ["go", "mod", "tidy"],
                cwd=tmpdir_path,
                capture_output=True,
                timeout=60,
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[ToolDomain.COVERAGE],
            )

            result = go_test_runner.run_tests(context)

            assert result.passed >= 1
            assert result.tool == "go_test"

            # Verify coverage.out was created
            coverage_file = tmpdir_path / "coverage.out"
            assert coverage_file.exists(), (
                "coverage.out should be created when coverage domain is enabled"
            )


class TestGoTestJsonParsing:
    """Tests for go test JSON output parsing (no binary required)."""

    def test_parse_json_output_passing(self) -> None:
        """Test _parse_json_output with passing test events."""
        runner = GoTestRunner(project_root=Path("/tmp"))

        events = [
            {"Action": "run", "Package": "example.com/pkg", "Test": "TestAdd"},
            {
                "Action": "output",
                "Package": "example.com/pkg",
                "Test": "TestAdd",
                "Output": "=== RUN   TestAdd\n",
            },
            {
                "Action": "output",
                "Package": "example.com/pkg",
                "Test": "TestAdd",
                "Output": "--- PASS: TestAdd (0.00s)\n",
            },
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestAdd",
                "Elapsed": 0.001,
            },
        ]

        output = "\n".join(json.dumps(e) for e in events)

        result = runner._parse_json_output(output, Path("/tmp"))

        assert result.passed == 1
        assert result.failed == 0
        assert result.tool == "go_test"
        assert result.success is True

    def test_parse_json_output_failing(self) -> None:
        """Test _parse_json_output with failing test events."""
        runner = GoTestRunner(project_root=Path("/tmp"))

        events = [
            {"Action": "run", "Package": "example.com/pkg", "Test": "TestFail"},
            {
                "Action": "output",
                "Package": "example.com/pkg",
                "Test": "TestFail",
                "Output": "=== RUN   TestFail\n",
            },
            {
                "Action": "output",
                "Package": "example.com/pkg",
                "Test": "TestFail",
                "Output": "    fail_test.go:6: intentional failure\n",
            },
            {
                "Action": "output",
                "Package": "example.com/pkg",
                "Test": "TestFail",
                "Output": "--- FAIL: TestFail (0.00s)\n",
            },
            {
                "Action": "fail",
                "Package": "example.com/pkg",
                "Test": "TestFail",
                "Elapsed": 0.001,
            },
        ]

        output = "\n".join(json.dumps(e) for e in events)

        result = runner._parse_json_output(output, Path("/tmp"))

        assert result.passed == 0
        assert result.failed == 1
        assert result.success is False
        assert len(result.issues) == 1
        assert result.issues[0].domain == ToolDomain.TESTING
        assert result.issues[0].source_tool == "go_test"

    def test_parse_json_output_mixed(self) -> None:
        """Test _parse_json_output with mixed pass/fail/skip events."""
        runner = GoTestRunner(project_root=Path("/tmp"))

        events = [
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestOK",
                "Elapsed": 0.001,
            },
            {
                "Action": "fail",
                "Package": "example.com/pkg",
                "Test": "TestBad",
                "Elapsed": 0.002,
            },
            {
                "Action": "skip",
                "Package": "example.com/pkg",
                "Test": "TestSkip",
                "Elapsed": 0.0,
            },
        ]

        output = "\n".join(json.dumps(e) for e in events)

        result = runner._parse_json_output(output, Path("/tmp"))

        assert result.passed == 1
        assert result.failed == 1
        assert result.skipped == 1
        assert result.total == 3

    def test_parse_json_output_empty(self) -> None:
        """Test _parse_json_output with empty output."""
        runner = GoTestRunner(project_root=Path("/tmp"))

        result = runner._parse_json_output("", Path("/tmp"))

        assert result.passed == 0
        assert result.failed == 0
        assert result.total == 0
        assert result.tool == "go_test"

    def test_parse_json_output_invalid_lines(self) -> None:
        """Test _parse_json_output with mixed valid and invalid JSON lines."""
        runner = GoTestRunner(project_root=Path("/tmp"))

        events = [
            "not valid json",
            json.dumps(
                {
                    "Action": "pass",
                    "Package": "example.com/pkg",
                    "Test": "TestOK",
                    "Elapsed": 0.001,
                }
            ),
            "another invalid line",
        ]

        output = "\n".join(events)

        result = runner._parse_json_output(output, Path("/tmp"))

        assert result.passed == 1
        assert result.failed == 0

    def test_issue_id_is_deterministic(self) -> None:
        """Test that issue IDs are consistent across parse runs."""
        runner = GoTestRunner(project_root=Path("/tmp"))

        events = [
            {
                "Action": "output",
                "Package": "example.com/pkg",
                "Test": "TestFail",
                "Output": "    fail_test.go:6: error\n",
            },
            {
                "Action": "fail",
                "Package": "example.com/pkg",
                "Test": "TestFail",
                "Elapsed": 0.001,
            },
        ]

        output = "\n".join(json.dumps(e) for e in events)

        result1 = runner._parse_json_output(output, Path("/tmp"))
        result2 = runner._parse_json_output(output, Path("/tmp"))

        assert len(result1.issues) == 1
        assert len(result2.issues) == 1
        assert result1.issues[0].id == result2.issues[0].id
        assert result1.issues[0].id.startswith("go-test-")


# =============================================================================
# New unit tests  -  NO Go binary required
# =============================================================================


class TestGoTestProperties:
    """Tests for GoTestRunner property accessors."""

    def test_name(self) -> None:
        """Test that plugin name is 'go_test'."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        assert runner.name == "go_test"

    def test_languages(self) -> None:
        """Test that supported languages includes 'go'."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        assert runner.languages == ["go"]

    def test_domain(self) -> None:
        """Test that domain is TESTING."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        assert runner.domain == ToolDomain.TESTING


class TestGoTestJsonParsingEdgeCases:
    """Edge-case tests for JSON parsing  -  no binary required."""

    def test_package_only_events_ignored(self) -> None:
        """Events with Package but no Test field are ignored."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        events = [
            {"Action": "pass", "Package": "example.com/pkg", "Elapsed": 0.5},
            {"Action": "fail", "Package": "example.com/pkg2", "Elapsed": 0.1},
        ]
        output = "\n".join(json.dumps(e) for e in events)
        result = runner._parse_json_output(output, Path("/tmp"))
        assert result.total == 0

    def test_output_events_without_test_ignored(self) -> None:
        """Action=output with no Test field does not crash."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        events = [
            {"Action": "output", "Package": "example.com/pkg", "Output": "some text\n"},
        ]
        output = "\n".join(json.dumps(e) for e in events)
        result = runner._parse_json_output(output, Path("/tmp"))
        assert result.total == 0

    def test_subtest_events(self) -> None:
        """Subtests like 'TestParent/SubTest' are counted as separate tests."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        events = [
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestParent",
                "Elapsed": 0.01,
            },
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestParent/SubTest",
                "Elapsed": 0.005,
            },
        ]
        output = "\n".join(json.dumps(e) for e in events)
        result = runner._parse_json_output(output, Path("/tmp"))
        assert result.passed == 2
        assert result.total == 2

    def test_last_action_wins(self) -> None:
        """If a test has pass then fail, the last action (fail) wins."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        events = [
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestFlaky",
                "Elapsed": 0.01,
            },
            {
                "Action": "fail",
                "Package": "example.com/pkg",
                "Test": "TestFlaky",
                "Elapsed": 0.02,
            },
        ]
        output = "\n".join(json.dumps(e) for e in events)
        result = runner._parse_json_output(output, Path("/tmp"))
        assert result.failed == 1
        assert result.passed == 0

    def test_whitespace_only_output(self) -> None:
        """Whitespace-only output results in an empty TestResult."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        result = runner._parse_json_output("   \n  ", Path("/tmp"))
        assert result.total == 0

    def test_events_with_missing_elapsed(self) -> None:
        """Events without Elapsed field default to 0."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        events = [
            {"Action": "pass", "Package": "example.com/pkg", "Test": "TestNoElapsed"},
        ]
        output = "\n".join(json.dumps(e) for e in events)
        result = runner._parse_json_output(output, Path("/tmp"))
        assert result.passed == 1
        assert result.duration_ms == 0

    def test_duration_accumulation(self) -> None:
        """3 tests with Elapsed 1.5, 0.25, 0.001 accumulate to 1751 ms."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        events = [
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestA",
                "Elapsed": 1.5,
            },
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestB",
                "Elapsed": 0.25,
            },
            {
                "Action": "pass",
                "Package": "example.com/pkg",
                "Test": "TestC",
                "Elapsed": 0.001,
            },
        ]
        output = "\n".join(json.dumps(e) for e in events)
        result = runner._parse_json_output(output, Path("/tmp"))
        assert result.duration_ms == 1751

    def test_skip_action_counted(self) -> None:
        """Action=skip increments the skipped count."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        events = [
            {
                "Action": "skip",
                "Package": "example.com/pkg",
                "Test": "TestSkipMe",
                "Elapsed": 0.0,
            },
        ]
        output = "\n".join(json.dumps(e) for e in events)
        result = runner._parse_json_output(output, Path("/tmp"))
        assert result.skipped == 1
        assert result.passed == 0
        assert result.failed == 0


class TestGoTestExtractLocation:
    """Tests for _extract_location  -  no binary required."""

    def test_extracts_test_file_line(self) -> None:
        """Output with 'main_test.go:15: expected 4' extracts line 15."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        output_lines = ["    main_test.go:15: expected 4, got 3\n"]
        file_path, line_number = runner._extract_location(output_lines, Path("/tmp"))
        assert line_number == 15

    def test_extracts_from_go_file(self) -> None:
        """Output with 'main.go:10:' extracts line 10."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        output_lines = ["    main.go:10: something wrong\n"]
        file_path, line_number = runner._extract_location(output_lines, Path("/tmp"))
        assert line_number == 10

    def test_no_match_returns_nones(self) -> None:
        """No file:line patterns returns (None, None)."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        output_lines = ["no file reference here\n", "=== RUN TestSomething\n"]
        file_path, line_number = runner._extract_location(output_lines, Path("/tmp"))
        assert file_path is None
        assert line_number is None

    def test_first_match_wins(self) -> None:
        """Multiple file:line patterns  -  the first one is returned."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        output_lines = [
            "    alpha_test.go:5: first error\n",
            "    beta_test.go:20: second error\n",
        ]
        file_path, line_number = runner._extract_location(output_lines, Path("/tmp"))
        assert line_number == 5

    def test_file_exists_resolved_to_path(self, tmp_path: Path) -> None:
        """If the file exists in project root, the full Path is returned."""
        test_file = tmp_path / "real_test.go"
        test_file.write_text("package main\n")
        runner = GoTestRunner(project_root=tmp_path)
        output_lines = ["    real_test.go:42: assertion failed\n"]
        file_path, line_number = runner._extract_location(output_lines, tmp_path)
        assert file_path == test_file
        assert line_number == 42


class TestGoTestExtractShortMessage:
    """Tests for _extract_short_message  -  no binary required."""

    def test_extracts_meaningful_line(self) -> None:
        """Lines with 'file.go:6: expected 3, got 4' extracts the message."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        lines = ["    file.go:6: expected 3, got 4\n"]
        msg = runner._extract_short_message(lines)
        assert "expected 3, got 4" in msg

    def test_skips_decorative_lines(self) -> None:
        """Only '--- FAIL:' and '=== RUN' lines result in fallback."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        lines = ["--- FAIL: TestSomething (0.00s)\n", "=== RUN   TestSomething\n"]
        msg = runner._extract_short_message(lines)
        assert msg == "Test failed"

    def test_empty_list(self) -> None:
        """Empty list of lines returns 'Test failed'."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        msg = runner._extract_short_message([])
        assert msg == "Test failed"

    def test_truncation_at_100_chars(self) -> None:
        """A 200-char line is truncated to 100 characters."""
        runner = GoTestRunner(project_root=Path("/tmp"))
        long_line = "    file.go:1: " + "x" * 200 + "\n"
        msg = runner._extract_short_message([long_line])
        assert len(msg) <= 100


class TestGoTestErrorHandling:
    """Tests for run_tests error handling  -  uses mocks, no binary required."""

    def test_run_tests_binary_not_found(self, tmp_path: Path) -> None:
        """FileNotFoundError from find_go results in empty TestResult."""
        from unittest.mock import patch

        runner = GoTestRunner(project_root=tmp_path)
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )

        with patch.object(
            runner, "ensure_binary", side_effect=FileNotFoundError("go not found")
        ):
            result = runner.run_tests(context)

        assert result.total == 0
        assert result.tool == "go_test"

    def test_run_tests_timeout(self, tmp_path: Path) -> None:
        """TimeoutExpired results in empty TestResult and record_skip."""
        from unittest.mock import MagicMock, patch

        _create_temp_go_project(tmp_path)
        runner = GoTestRunner(project_root=tmp_path)
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        context.record_skip = MagicMock()  # type: ignore[method-assign]

        with (
            patch.object(
                runner, "ensure_binary", return_value=Path("/usr/local/bin/go")
            ),
            patch(
                "lucidshark.plugins.test_runners.go_test.run_with_streaming",
                side_effect=subprocess.TimeoutExpired(cmd="go test", timeout=600),
            ),
        ):
            result = runner.run_tests(context)

        assert result.total == 0
        assert result.tool == "go_test"
        context.record_skip.assert_called_once()

    def test_run_tests_called_process_error_with_stdout(self, tmp_path: Path) -> None:
        """CalledProcessError with stdout is still parsed."""
        from unittest.mock import patch

        _create_temp_go_project(tmp_path)
        runner = GoTestRunner(project_root=tmp_path)
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )

        # Build a CalledProcessError with valid JSON stdout
        error = subprocess.CalledProcessError(returncode=1, cmd="go test")
        error.stdout = json.dumps(
            {
                "Action": "fail",
                "Package": "example.com/pkg",
                "Test": "TestBad",
                "Elapsed": 0.01,
            }
        )

        with (
            patch.object(
                runner, "ensure_binary", return_value=Path("/usr/local/bin/go")
            ),
            patch(
                "lucidshark.plugins.test_runners.go_test.run_with_streaming",
                side_effect=error,
            ),
        ):
            result = runner.run_tests(context)

        assert result.failed == 1
        assert result.tool == "go_test"

    def test_run_tests_called_process_error_no_stdout(self, tmp_path: Path) -> None:
        """CalledProcessError with stdout=None results in empty result."""
        from unittest.mock import patch

        _create_temp_go_project(tmp_path)
        runner = GoTestRunner(project_root=tmp_path)
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )

        error = subprocess.CalledProcessError(returncode=1, cmd="go test")
        error.stdout = None

        with (
            patch.object(
                runner, "ensure_binary", return_value=Path("/usr/local/bin/go")
            ),
            patch(
                "lucidshark.plugins.test_runners.go_test.run_with_streaming",
                side_effect=error,
            ),
        ):
            result = runner.run_tests(context)

        assert result.total == 0
        assert result.tool == "go_test"

    def test_run_tests_generic_exception(self, tmp_path: Path) -> None:
        """RuntimeError results in empty TestResult and record_skip."""
        from unittest.mock import MagicMock, patch

        _create_temp_go_project(tmp_path)
        runner = GoTestRunner(project_root=tmp_path)
        context = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        context.record_skip = MagicMock()  # type: ignore[method-assign]

        with (
            patch.object(
                runner, "ensure_binary", return_value=Path("/usr/local/bin/go")
            ),
            patch(
                "lucidshark.plugins.test_runners.go_test.run_with_streaming",
                side_effect=RuntimeError("unexpected"),
            ),
        ):
            result = runner.run_tests(context)

        assert result.total == 0
        assert result.tool == "go_test"
        context.record_skip.assert_called_once()
