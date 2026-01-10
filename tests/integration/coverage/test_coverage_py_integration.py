"""Integration tests for coverage.py plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext, ToolDomain
from lucidscan.plugins.coverage.coverage_py import CoveragePyPlugin

from tests.integration.conftest import coverage_py_available, pytest_runner_available


@coverage_py_available
class TestCoveragePyBinaryManagement:
    """Integration tests for coverage.py binary finding."""

    def test_ensure_binary_returns_path(
        self, coverage_py_plugin: CoveragePyPlugin
    ) -> None:
        """Test that ensure_binary returns a valid path."""
        binary = coverage_py_plugin.ensure_binary()
        assert binary.exists()
        assert binary.is_file()

    def test_get_version_returns_string(
        self, coverage_py_plugin: CoveragePyPlugin
    ) -> None:
        """Test that get_version returns a version string."""
        version = coverage_py_plugin.get_version()
        assert version != "unknown"
        # Version should be like "7.4.0"
        assert "." in version


@coverage_py_available
@pytest_runner_available
class TestCoveragePyFunctional:
    """Functional integration tests for coverage.py plugin."""

    def test_measure_coverage_high_coverage(
        self, coverage_py_plugin: CoveragePyPlugin
    ) -> None:
        """Test measuring coverage with high coverage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple module
            module_file = project_root / "mymodule.py"
            module_file.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
""")

            # Create test that covers all code
            test_file = project_root / "test_mymodule.py"
            test_file.write_text("""
from mymodule import add, subtract

def test_add():
    assert add(1, 2) == 3

def test_subtract():
    assert subtract(5, 3) == 2
""")

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            result = coverage_py_plugin.measure_coverage(
                context, threshold=80.0, run_tests=True
            )

            # Should have high coverage
            assert result.total_lines > 0
            assert result.covered_lines > 0
            assert result.percentage >= 80.0
            assert result.passed is True
            assert len(result.issues) == 0

    def test_measure_coverage_below_threshold(
        self, coverage_py_plugin: CoveragePyPlugin
    ) -> None:
        """Test measuring coverage when below threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a module with uncovered code
            module_file = project_root / "mymodule.py"
            module_file.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        return None
    return a / b

def power(a, b):
    return a ** b
""")

            # Create test that only covers add
            test_file = project_root / "test_mymodule.py"
            test_file.write_text("""
from mymodule import add

def test_add():
    assert add(1, 2) == 3
""")

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            result = coverage_py_plugin.measure_coverage(
                context, threshold=80.0, run_tests=True
            )

            # Should be below 80% threshold
            assert result.total_lines > 0
            assert result.percentage < 80.0
            assert result.passed is False
            assert len(result.issues) == 1

            # Check the issue
            issue = result.issues[0]
            assert issue.scanner == ToolDomain.COVERAGE
            assert issue.source_tool == "coverage.py"
            assert "below threshold" in issue.title.lower()


@coverage_py_available
class TestCoveragePyIssueGeneration:
    """Tests for coverage issue generation."""

    def test_issue_has_correct_metadata(
        self, coverage_py_plugin: CoveragePyPlugin
    ) -> None:
        """Test that coverage issues have correct metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create module with no tests
            module_file = project_root / "mymodule.py"
            module_file.write_text("""
def uncovered_function():
    return "never tested"
""")

            # Create empty test file so pytest doesn't fail
            test_file = project_root / "test_empty.py"
            test_file.write_text("""
def test_nothing():
    pass
""")

            context = ScanContext(
                project_root=project_root,
                paths=[project_root],
                enabled_domains=[],
            )

            result = coverage_py_plugin.measure_coverage(
                context, threshold=80.0, run_tests=True
            )

            # Should generate an issue due to low coverage
            if len(result.issues) > 0:
                issue = result.issues[0]
                metadata = issue.scanner_metadata

                assert "coverage_percentage" in metadata
                assert "threshold" in metadata
                assert "total_lines" in metadata
                assert "covered_lines" in metadata
                assert "missing_lines" in metadata
