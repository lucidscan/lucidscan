"""Unit tests for test runner base classes."""

from __future__ import annotations

from pathlib import Path
from typing import List


from lucidscan.core.models import ScanContext, ToolDomain
from lucidscan.plugins.test_runners.base import TestRunnerPlugin, TestResult


class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_default_values(self) -> None:
        """Test default TestResult values."""
        result = TestResult()
        assert result.passed == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.errors == 0
        assert result.duration_ms == 0
        assert result.issues == []

    def test_total_property(self) -> None:
        """Test total property calculates sum correctly."""
        result = TestResult(passed=10, failed=2, skipped=3, errors=1)
        assert result.total == 16

    def test_success_property_all_passed(self) -> None:
        """Test success is True when no failures or errors."""
        result = TestResult(passed=10, failed=0, skipped=5, errors=0)
        assert result.success is True

    def test_success_property_with_failures(self) -> None:
        """Test success is False with failures."""
        result = TestResult(passed=10, failed=2, skipped=0, errors=0)
        assert result.success is False

    def test_success_property_with_errors(self) -> None:
        """Test success is False with errors."""
        result = TestResult(passed=10, failed=0, skipped=0, errors=1)
        assert result.success is False


class ConcreteTestRunner(TestRunnerPlugin):
    """Concrete implementation of TestRunnerPlugin for testing."""

    @property
    def name(self) -> str:
        return "test_runner"

    @property
    def languages(self) -> List[str]:
        return ["python"]

    def get_version(self) -> str:
        return "1.0.0"

    def ensure_binary(self) -> Path:
        return Path("/usr/bin/test")

    def run_tests(self, context: ScanContext) -> TestResult:
        return TestResult(passed=5, failed=0)


class TestTestRunnerPlugin:
    """Tests for TestRunnerPlugin abstract base class."""

    def test_domain_is_testing(self) -> None:
        """Test domain property returns TESTING."""
        runner = ConcreteTestRunner()
        assert runner.domain == ToolDomain.TESTING

    def test_name_property(self) -> None:
        """Test name property."""
        runner = ConcreteTestRunner()
        assert runner.name == "test_runner"

    def test_languages_property(self) -> None:
        """Test languages property."""
        runner = ConcreteTestRunner()
        assert runner.languages == ["python"]

    def test_get_version(self) -> None:
        """Test get_version method."""
        runner = ConcreteTestRunner()
        assert runner.get_version() == "1.0.0"

    def test_ensure_binary(self) -> None:
        """Test ensure_binary method."""
        runner = ConcreteTestRunner()
        assert runner.ensure_binary() == Path("/usr/bin/test")

    def test_run_tests(self) -> None:
        """Test run_tests method."""
        runner = ConcreteTestRunner()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        result = runner.run_tests(context)
        assert result.passed == 5
        assert result.failed == 0
        assert result.success is True
