"""Unit tests for Swift test runner plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.test_runners.swift_test import SwiftTestRunner


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _make_context(
    project_root: Path,
    paths: list[Path] | None = None,
    enabled_domains: list | None = None,
) -> ScanContext:
    """Create a minimal ScanContext for testing."""
    return ScanContext(
        project_root=project_root,
        paths=paths or [],
        enabled_domains=enabled_domains or [ToolDomain.TESTING],
    )


FAKE_BINARY = Path("/usr/bin/swift")


class TestSwiftTestRunnerProperties:
    """Tests for SwiftTestRunner basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        runner = SwiftTestRunner()
        assert runner.name == "swift_test"

    def test_languages(self) -> None:
        """Test supported languages."""
        runner = SwiftTestRunner()
        assert runner.languages == ["swift"]

    def test_domain(self) -> None:
        """Test domain is TESTING."""
        runner = SwiftTestRunner()
        assert runner.domain == ToolDomain.TESTING

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = SwiftTestRunner(project_root=Path(tmpdir))
            assert runner._project_root == Path(tmpdir)


class TestSwiftTestRunnerEnsureBinary:
    """Tests for ensure_binary method."""

    def test_found(self) -> None:
        """Test finding swift in system PATH."""
        runner = SwiftTestRunner()
        with patch(
            "lucidshark.plugins.swift_utils.shutil.which",
            return_value="/usr/bin/swift",
        ):
            binary = runner.ensure_binary()
            assert binary == Path("/usr/bin/swift")

    def test_not_found(self) -> None:
        """Test FileNotFoundError when swift not found."""
        runner = SwiftTestRunner()
        with patch(
            "lucidshark.plugins.swift_utils.shutil.which",
            return_value=None,
        ):
            with pytest.raises(FileNotFoundError, match="swift is not installed"):
                runner.ensure_binary()


class TestSwiftTestRunnerGetVersion:
    """Tests for get_version method."""

    def test_returns_version(self) -> None:
        """Test get_version returns a version string."""
        runner = SwiftTestRunner()
        mock_result = subprocess.CompletedProcess(
            args=["swift", "--version"],
            returncode=0,
            stdout="Swift version 5.9.0 (swift-5.9-RELEASE)",
            stderr="",
        )
        with patch(
            "lucidshark.plugins.swift_utils.subprocess.run",
            return_value=mock_result,
        ):
            version = runner.get_version()
            assert version == "5.9.0"

    def test_returns_unknown_on_error(self) -> None:
        """Test get_version returns 'unknown' when binary not found."""
        runner = SwiftTestRunner()
        with patch(
            "lucidshark.plugins.swift_utils.subprocess.run",
            side_effect=FileNotFoundError("not found"),
        ):
            version = runner.get_version()
            assert version == "unknown"


class TestSwiftTestRunTests:
    """Tests for run_tests method."""

    def _setup_swift_project(self, project_root: Path) -> None:
        """Write a minimal Package.swift so the project is detected."""
        (project_root / "Package.swift").write_text(
            "// swift-tools-version:5.9\nimport PackageDescription\n"
        )

    def test_no_package_swift(self) -> None:
        """Test run_tests returns empty when no Package.swift exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            runner = SwiftTestRunner(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with patch.object(runner, "ensure_binary", return_value=FAKE_BINARY):
                result = runner.run_tests(context)
                assert result.tool == "swift_test"
                assert result.passed == 0
                assert result.failed == 0

    def test_binary_not_found(self) -> None:
        """Test run_tests returns empty when binary not found."""
        runner = SwiftTestRunner()
        context = _make_context(Path("/tmp"))
        with patch.object(
            runner, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = runner.run_tests(context)
            assert result.tool == "swift_test"
            assert result.passed == 0
            assert result.failed == 0

    def test_timeout(self) -> None:
        """Test run_tests handles timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            self._setup_swift_project(project_root)

            runner = SwiftTestRunner(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with (
                patch(
                    "lucidshark.plugins.test_runners.swift_test.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(
                        cmd="swift test", timeout=600
                    ),
                ),
                patch.object(runner, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = runner.run_tests(context)
                assert result.tool == "swift_test"
                assert result.passed == 0
                assert result.failed == 0

    def test_all_passing(self) -> None:
        """Test run_tests with all tests passing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            self._setup_swift_project(project_root)

            runner = SwiftTestRunner(project_root=project_root)
            context = _make_context(project_root, [project_root])

            stdout = (
                "Test Suite 'All tests' started at 2024-01-01 12:00:00.000.\n"
                "Test Case '-[MyTests.CalculatorTests testAdd]' passed (0.001 seconds).\n"
                "Test Case '-[MyTests.CalculatorTests testSubtract]' passed (0.001 seconds).\n"
                "Test Case '-[MyTests.CalculatorTests testMultiply]' passed (0.001 seconds).\n"
                "Test Suite 'All tests' passed at 2024-01-01 12:00:00.005.\n"
                "     Executed 3 tests, with 0 failures (0 unexpected) in 0.003 (0.005) seconds\n"
            )
            mock_result = make_completed_process(0, stdout)
            with (
                patch(
                    "lucidshark.plugins.test_runners.swift_test.run_with_streaming",
                    return_value=mock_result,
                ),
                patch.object(runner, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = runner.run_tests(context)
                assert result.passed == 3
                assert result.failed == 0

    def test_with_failures(self) -> None:
        """Test run_tests with test failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            self._setup_swift_project(project_root)

            runner = SwiftTestRunner(project_root=project_root)
            context = _make_context(project_root, [project_root])

            stdout = (
                "Test Suite 'All tests' started at 2024-01-01 12:00:00.000.\n"
                "Test Case '-[MyTests.CalculatorTests testAdd]' passed (0.001 seconds).\n"
                "Test Case '-[MyTests.CalculatorTests testDivide]' failed (0.002 seconds).\n"
                "Test Suite 'All tests' failed at 2024-01-01 12:00:00.005.\n"
                "     Executed 2 tests, with 1 failure (0 unexpected) in 0.003 (0.005) seconds\n"
            )
            mock_result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.test_runners.swift_test.run_with_streaming",
                    return_value=mock_result,
                ),
                patch.object(runner, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = runner.run_tests(context)
                assert result.passed == 1
                assert result.failed == 1
                assert len(result.issues) >= 1
                assert result.issues[0].domain == ToolDomain.TESTING

    def test_coverage_flag_added_when_domain_enabled(self) -> None:
        """Test that --enable-code-coverage is added when COVERAGE domain is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            self._setup_swift_project(project_root)

            runner = SwiftTestRunner(project_root=project_root)
            context = _make_context(
                project_root,
                [project_root],
                enabled_domains=[ToolDomain.TESTING, ToolDomain.COVERAGE],
            )

            stdout = "     Executed 1 test, with 0 failures (0 unexpected) in 0.001 (0.002) seconds\n"
            mock_result = make_completed_process(0, stdout)
            with (
                patch(
                    "lucidshark.plugins.test_runners.swift_test.run_with_streaming",
                    return_value=mock_result,
                ) as mock_run,
                patch.object(runner, "ensure_binary", return_value=FAKE_BINARY),
            ):
                runner.run_tests(context)
                call_args = mock_run.call_args
                cmd = (
                    call_args.kwargs.get("cmd")
                    or call_args[1].get("cmd")
                    or call_args[0][0]
                )
                assert "--enable-code-coverage" in cmd

    def test_no_coverage_flag_when_domain_not_enabled(self) -> None:
        """Test that --enable-code-coverage is NOT added when COVERAGE is not enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            self._setup_swift_project(project_root)

            runner = SwiftTestRunner(project_root=project_root)
            context = _make_context(
                project_root,
                [project_root],
                enabled_domains=[ToolDomain.TESTING],
            )

            stdout = "     Executed 1 test, with 0 failures (0 unexpected) in 0.001 (0.002) seconds\n"
            mock_result = make_completed_process(0, stdout)
            with (
                patch(
                    "lucidshark.plugins.test_runners.swift_test.run_with_streaming",
                    return_value=mock_result,
                ) as mock_run,
                patch.object(runner, "ensure_binary", return_value=FAKE_BINARY),
            ):
                runner.run_tests(context)
                call_args = mock_run.call_args
                cmd = (
                    call_args.kwargs.get("cmd")
                    or call_args[1].get("cmd")
                    or call_args[0][0]
                )
                assert "--enable-code-coverage" not in cmd


class TestParseTestOutput:
    """Tests for _parse_test_output."""

    def test_parse_passing_output(self) -> None:
        """Test parsing output where all tests pass."""
        runner = SwiftTestRunner()
        output = (
            "Test Suite 'All tests' started at 2024-01-01 12:00:00.000.\n"
            "Test Case '-[MyTests.CalculatorTests testAdd]' passed (0.001 seconds).\n"
            "Test Case '-[MyTests.CalculatorTests testSubtract]' passed (0.001 seconds).\n"
            "Test Case '-[MyTests.CalculatorTests testMultiply]' passed (0.001 seconds).\n"
            "Test Suite 'All tests' passed at 2024-01-01 12:00:00.005.\n"
            "     Executed 3 tests, with 0 failures (0 unexpected) in 0.003 (0.005) seconds\n"
        )
        result = runner._parse_test_output(output, Path("/tmp"))
        assert result.passed == 3
        assert result.failed == 0
        assert result.skipped == 0

    def test_parse_failed_output(self) -> None:
        """Test parsing output with test failures."""
        runner = SwiftTestRunner()
        output = (
            "Test Suite 'All tests' started at 2024-01-01 12:00:00.000.\n"
            "Test Case '-[MyTests.CalculatorTests testAdd]' passed (0.001 seconds).\n"
            "Test Case '-[MyTests.CalculatorTests testDivide]' failed (0.002 seconds).\n"
            "Test Suite 'All tests' failed at 2024-01-01 12:00:00.005.\n"
            "     Executed 2 tests, with 1 failure (0 unexpected) in 0.003 (0.005) seconds\n"
        )
        result = runner._parse_test_output(output, Path("/tmp"))
        assert result.passed == 1
        assert result.failed == 1
        assert len(result.issues) >= 1
        assert result.issues[0].domain == ToolDomain.TESTING

    def test_parse_summary_line_with_multiple_failures(self) -> None:
        """Test parsing summary line with multiple failures."""
        runner = SwiftTestRunner()
        output = (
            "Test Case '-[MyTests.CalculatorTests testAdd]' passed (0.001 seconds).\n"
            "Test Case '-[MyTests.CalculatorTests testDivide]' failed (0.002 seconds).\n"
            "Test Case '-[MyTests.CalculatorTests testModulo]' failed (0.002 seconds).\n"
            "     Executed 5 tests, with 2 failures (0 unexpected) in 0.005 (0.006) seconds\n"
        )
        result = runner._parse_test_output(output, Path("/tmp"))
        assert result.passed == 3
        assert result.failed == 2

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output returns zero counts."""
        runner = SwiftTestRunner()
        result = runner._parse_test_output("", Path("/tmp"))
        assert result.passed == 0
        assert result.failed == 0
        assert result.skipped == 0

    def test_parse_output_with_no_summary_line(self) -> None:
        """Test parsing output without summary line uses pattern counts."""
        runner = SwiftTestRunner()
        output = (
            "Test Case '-[MyTests.TestA testFoo]' passed (0.001 seconds).\n"
            "Test Case '-[MyTests.TestA testBar]' failed (0.001 seconds).\n"
        )
        result = runner._parse_test_output(output, Path("/tmp"))
        assert result.passed == 1
        assert result.failed == 1

    def test_parse_swift_testing_format(self) -> None:
        """Test parsing Swift Testing framework format."""
        runner = SwiftTestRunner()
        output = (
            'Test "testAdd" failed (0.001 seconds).\n'
            "     Executed 2 tests, with 1 failure (0 unexpected) in 0.002 (0.003) seconds\n"
        )
        result = runner._parse_test_output(output, Path("/tmp"))
        assert result.passed == 1
        assert result.failed == 1


class TestExtractFailedTests:
    """Tests for _extract_failed_tests method."""

    def test_extracts_xctest_failures(self) -> None:
        """Test extracting XCTest-style test failures."""
        runner = SwiftTestRunner()
        output = "Test Case '-[MyTests.CalculatorTests testDivide]' failed (0.002 seconds).\n"
        failures = runner._extract_failed_tests(output)
        assert len(failures) == 1
        assert "MyTests.CalculatorTests testDivide" in failures[0][0]

    def test_extracts_swift_testing_failures(self) -> None:
        """Test extracting Swift Testing format failures."""
        runner = SwiftTestRunner()
        output = 'Test "testDivide" failed (0.002 seconds).\n'
        failures = runner._extract_failed_tests(output)
        assert len(failures) == 1
        assert "testDivide" in failures[0][0]

    def test_no_failures_returns_empty(self) -> None:
        """Test no failures returns empty list."""
        runner = SwiftTestRunner()
        output = (
            "Test Case '-[MyTests.CalculatorTests testAdd]' passed (0.001 seconds).\n"
        )
        failures = runner._extract_failed_tests(output)
        assert failures == []


class TestFailureToIssue:
    """Tests for _failure_to_issue method."""

    def test_creates_issue(self) -> None:
        """Test creating UnifiedIssue from failure."""
        runner = SwiftTestRunner()
        issue = runner._failure_to_issue(
            "MyTests.CalculatorTests testDivide",
            'XCTAssertEqual failed: ("1") is not equal to ("0")',
            Path("/project"),
        )
        assert issue is not None
        assert issue.domain == ToolDomain.TESTING
        assert issue.source_tool == "swift_test"
        assert issue.severity == Severity.HIGH
        assert issue.rule_id == "test_failed"
        assert "FAILED" in issue.title
        assert issue.fixable is False

    def test_issue_metadata(self) -> None:
        """Test issue contains correct metadata."""
        runner = SwiftTestRunner()
        issue = runner._failure_to_issue(
            "MyTests.CalculatorTests testDivide",
            "Test failed",
            Path("/project"),
        )
        assert issue is not None
        assert issue.metadata["test_name"] == "MyTests.CalculatorTests testDivide"
        assert issue.metadata["outcome"] == "failed"


class TestSwiftTestIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        runner = SwiftTestRunner()
        id1 = runner._generate_swift_issue_id("testFoo", "msg")
        id2 = runner._generate_swift_issue_id("testFoo", "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        runner = SwiftTestRunner()
        id1 = runner._generate_swift_issue_id("testFoo", "msg")
        id2 = runner._generate_swift_issue_id("testBar", "msg")
        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID starts with swift-test-."""
        runner = SwiftTestRunner()
        issue_id = runner._generate_swift_issue_id("testFoo", "msg")
        assert issue_id.startswith("swift-test-")
