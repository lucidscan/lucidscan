"""Tests for parallel scanner execution."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from lucidscan.core.models import ScanContext, ScanDomain, Severity, UnifiedIssue
from lucidscan.pipeline.parallel import (
    DEFAULT_MAX_WORKERS,
    ParallelScannerExecutor,
    ScannerResult,
)


class MockScanner:
    """Mock scanner for testing."""

    def __init__(
        self,
        name: str,
        delay: float = 0,
        issues: int = 1,
        should_fail: bool = False,
    ):
        self._name = name
        self._delay = delay
        self._issues = issues
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    @property
    def domains(self) -> List[ScanDomain]:
        return [ScanDomain.SCA]

    def get_version(self) -> str:
        return "1.0.0"

    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        if self._should_fail:
            raise RuntimeError(f"Scanner {self._name} failed")
        time.sleep(self._delay)
        return [
            UnifiedIssue(
                id=f"{self._name}-{i}",
                scanner=ScanDomain.SCA,
                source_tool=self._name,
                severity=Severity.MEDIUM,
                title=f"Issue {i}",
                description="Test issue",
            )
            for i in range(self._issues)
        ]


class TestScannerResult:
    """Tests for ScannerResult dataclass."""

    def test_default_values(self) -> None:
        """Test default values for ScannerResult."""
        result = ScannerResult(
            scanner_name="test",
            scanner_version="1.0.0",
            domains=["sca"],
        )
        assert result.issues == []
        assert result.error is None
        assert result.success is True

    def test_error_result(self) -> None:
        """Test error result creation."""
        result = ScannerResult(
            scanner_name="test",
            scanner_version="1.0.0",
            domains=[],
            error="Something went wrong",
            success=False,
        )
        assert result.success is False
        assert result.error == "Something went wrong"


class TestParallelScannerExecutor:
    """Tests for ParallelScannerExecutor."""

    @pytest.fixture
    def context(self, tmp_path: Path) -> ScanContext:
        """Create a test scan context."""
        return ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[ScanDomain.SCA],
        )

    def test_default_max_workers(self) -> None:
        """Test default max workers value."""
        executor = ParallelScannerExecutor()
        assert executor._max_workers == DEFAULT_MAX_WORKERS

    def test_custom_max_workers(self) -> None:
        """Test custom max workers value."""
        executor = ParallelScannerExecutor(max_workers=8)
        assert executor._max_workers == 8

    def test_sequential_mode_flag(self) -> None:
        """Test sequential mode flag."""
        executor = ParallelScannerExecutor(sequential=True)
        assert executor._sequential is True

    def test_empty_scanner_list(self, context: ScanContext) -> None:
        """Test execution with no scanners."""
        executor = ParallelScannerExecutor()
        issues, results = executor.execute([], context)
        assert issues == []
        assert results == []

    def test_parallel_execution_aggregates_results(
        self, context: ScanContext
    ) -> None:
        """Test that parallel execution aggregates all scanner results."""
        with patch(
            "lucidscan.pipeline.parallel.get_scanner_plugin"
        ) as mock_get:
            mock_get.side_effect = lambda name, **kwargs: MockScanner(name, issues=2)

            executor = ParallelScannerExecutor(max_workers=2)
            issues, results = executor.execute(
                ["scanner1", "scanner2"], context
            )

            assert len(issues) == 4  # 2 scanners x 2 issues each
            assert len(results) == 2

    def test_sequential_mode_runs_in_order(self, context: ScanContext) -> None:
        """Test that sequential mode runs scanners one at a time."""
        call_order = []

        def mock_scanner(name: str, **kwargs) -> MockScanner:
            scanner = MockScanner(name)
            original_scan = scanner.scan

            def tracked_scan(ctx: ScanContext) -> List[UnifiedIssue]:
                call_order.append(name)
                return original_scan(ctx)

            scanner.scan = tracked_scan  # type: ignore
            return scanner

        with patch(
            "lucidscan.pipeline.parallel.get_scanner_plugin",
            side_effect=mock_scanner,
        ):
            executor = ParallelScannerExecutor(sequential=True)
            executor.execute(["a", "b", "c"], context)

            assert call_order == ["a", "b", "c"]

    def test_handles_scanner_not_found(self, context: ScanContext) -> None:
        """Test handling of missing scanner plugin."""
        with patch(
            "lucidscan.pipeline.parallel.get_scanner_plugin", return_value=None
        ):
            executor = ParallelScannerExecutor()
            issues, results = executor.execute(["missing"], context)

            assert len(issues) == 0
            assert len(results) == 1
            assert results[0].success is False
            assert "not found" in (results[0].error or "")

    def test_handles_scanner_exception(self, context: ScanContext) -> None:
        """Test handling of scanner that raises exception."""
        with patch(
            "lucidscan.pipeline.parallel.get_scanner_plugin"
        ) as mock_get:
            mock_get.return_value = MockScanner("failing", should_fail=True)

            executor = ParallelScannerExecutor()
            issues, results = executor.execute(["failing"], context)

            assert len(issues) == 0
            assert results[0].success is False
            assert "failed" in (results[0].error or "")

    def test_scanner_result_includes_version(
        self, context: ScanContext
    ) -> None:
        """Test that scanner results include version info."""
        with patch(
            "lucidscan.pipeline.parallel.get_scanner_plugin"
        ) as mock_get:
            mock_get.return_value = MockScanner("test")

            executor = ParallelScannerExecutor()
            _, results = executor.execute(["test"], context)

            assert results[0].scanner_version == "1.0.0"
            assert results[0].domains == ["sca"]

    def test_scanner_result_includes_domains(
        self, context: ScanContext
    ) -> None:
        """Test that scanner results include domain info."""
        with patch(
            "lucidscan.pipeline.parallel.get_scanner_plugin"
        ) as mock_get:
            mock_get.return_value = MockScanner("test")

            executor = ParallelScannerExecutor()
            _, results = executor.execute(["test"], context)

            assert "sca" in results[0].domains
