"""Integration tests for pytest runner plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext, ToolDomain
from lucidscan.plugins.test_runners.pytest import PytestRunner

from tests.integration.conftest import pytest_runner_available


@pytest_runner_available
class TestPytestBinaryManagement:
    """Integration tests for pytest binary finding."""

    def test_ensure_binary_returns_path(self, py_test_runner: PytestRunner) -> None:
        """Test that ensure_binary returns a valid path."""
        binary = py_test_runner.ensure_binary()
        assert binary.exists()
        assert binary.is_file()

    def test_get_version_returns_string(self, py_test_runner: PytestRunner) -> None:
        """Test that get_version returns a version string."""
        version = py_test_runner.get_version()
        assert version != "unknown"
        # Version should be like "8.0.0"
        assert "." in version


@pytest_runner_available
class TestPytestFunctional:
    """Functional integration tests for pytest runner."""

    def test_run_tests_all_pass(self, py_test_runner: PytestRunner) -> None:
        """Test running tests where all tests pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple test file
            test_file = project_root / "test_example.py"
            test_file.write_text("""
def test_pass():
    assert True

def test_pass_2():
    assert 1 + 1 == 2
""")

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            result = py_test_runner.run_tests(context)

            assert result.passed >= 2
            assert result.failed == 0
            assert result.success is True
            assert len(result.issues) == 0

    def test_run_tests_with_failures(self, py_test_runner: PytestRunner) -> None:
        """Test running tests with some failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create test file with a failure
            test_file = project_root / "test_example.py"
            test_file.write_text("""
def test_pass():
    assert True

def test_fail():
    assert False, "This should fail"
""")

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            result = py_test_runner.run_tests(context)

            assert result.passed == 1
            assert result.failed == 1
            assert result.success is False
            assert len(result.issues) >= 1

            # Check the failure issue
            issue = result.issues[0]
            assert issue.scanner == ToolDomain.TESTING
            assert issue.source_tool == "pytest"
            assert "test_fail" in issue.title

    def test_run_tests_empty_project(self, py_test_runner: PytestRunner) -> None:
        """Test running tests in project with no tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            result = py_test_runner.run_tests(context)

            # No tests found should result in 0 passed/failed
            assert result.total == 0 or result.passed == 0
            assert result.success is True


@pytest_runner_available
class TestPytestIssueGeneration:
    """Tests for issue generation from test failures."""

    def test_issue_has_correct_fields(self, py_test_runner: PytestRunner) -> None:
        """Test that generated issues have all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create test file with assertion failure
            test_file = project_root / "test_assertion.py"
            test_file.write_text("""
def test_assertion_failure():
    expected = 10
    actual = 5
    assert actual == expected, f"Expected {expected}, got {actual}"
""")

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            result = py_test_runner.run_tests(context)

            assert len(result.issues) == 1
            issue = result.issues[0]

            # Check required fields
            assert issue.id is not None
            assert issue.id.startswith("pytest-")
            assert issue.scanner == ToolDomain.TESTING
            assert issue.source_tool == "pytest"
            assert issue.severity is not None
            assert issue.title is not None
            assert issue.description is not None

            # Check metadata
            assert "test_name" in issue.scanner_metadata
            assert "outcome" in issue.scanner_metadata
