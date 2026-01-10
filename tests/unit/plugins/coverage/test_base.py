"""Unit tests for coverage plugin base classes."""

from __future__ import annotations

from pathlib import Path
from typing import List


from lucidscan.core.models import ScanContext, ToolDomain
from lucidscan.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
)


class TestFileCoverage:
    """Tests for FileCoverage dataclass."""

    def test_default_values(self) -> None:
        """Test default FileCoverage values."""
        fc = FileCoverage(file_path=Path("/test.py"))
        assert fc.total_lines == 0
        assert fc.covered_lines == 0
        assert fc.missing_lines == []
        assert fc.excluded_lines == 0

    def test_percentage_calculation(self) -> None:
        """Test coverage percentage calculation."""
        fc = FileCoverage(
            file_path=Path("/test.py"),
            total_lines=100,
            covered_lines=75,
        )
        assert fc.percentage == 75.0

    def test_percentage_zero_lines(self) -> None:
        """Test percentage is 100% when no lines."""
        fc = FileCoverage(file_path=Path("/test.py"))
        assert fc.percentage == 100.0


class TestCoverageResult:
    """Tests for CoverageResult dataclass."""

    def test_default_values(self) -> None:
        """Test default CoverageResult values."""
        result = CoverageResult()
        assert result.total_lines == 0
        assert result.covered_lines == 0
        assert result.missing_lines == 0
        assert result.excluded_lines == 0
        assert result.threshold == 0.0
        assert result.files == {}
        assert result.issues == []

    def test_percentage_calculation(self) -> None:
        """Test coverage percentage calculation."""
        result = CoverageResult(
            total_lines=200,
            covered_lines=160,
        )
        assert result.percentage == 80.0

    def test_percentage_zero_lines(self) -> None:
        """Test percentage is 100% when no lines."""
        result = CoverageResult()
        assert result.percentage == 100.0

    def test_passed_above_threshold(self) -> None:
        """Test passed is True when above threshold."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=85,
            threshold=80.0,
        )
        assert result.passed is True

    def test_passed_below_threshold(self) -> None:
        """Test passed is False when below threshold."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=75,
            threshold=80.0,
        )
        assert result.passed is False

    def test_passed_at_threshold(self) -> None:
        """Test passed is True when exactly at threshold."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            threshold=80.0,
        )
        assert result.passed is True


class ConcreteCoveragePlugin(CoveragePlugin):
    """Concrete implementation of CoveragePlugin for testing."""

    @property
    def name(self) -> str:
        return "test_coverage"

    @property
    def languages(self) -> List[str]:
        return ["python"]

    def get_version(self) -> str:
        return "1.0.0"

    def ensure_binary(self) -> Path:
        return Path("/usr/bin/coverage")

    def measure_coverage(
        self,
        context: ScanContext,
        threshold: float = 80.0,
        run_tests: bool = True,
    ) -> CoverageResult:
        return CoverageResult(
            total_lines=100,
            covered_lines=85,
            threshold=threshold,
        )


class TestCoveragePlugin:
    """Tests for CoveragePlugin abstract base class."""

    def test_domain_is_coverage(self) -> None:
        """Test domain property returns COVERAGE."""
        plugin = ConcreteCoveragePlugin()
        assert plugin.domain == ToolDomain.COVERAGE

    def test_name_property(self) -> None:
        """Test name property."""
        plugin = ConcreteCoveragePlugin()
        assert plugin.name == "test_coverage"

    def test_languages_property(self) -> None:
        """Test languages property."""
        plugin = ConcreteCoveragePlugin()
        assert plugin.languages == ["python"]

    def test_get_version(self) -> None:
        """Test get_version method."""
        plugin = ConcreteCoveragePlugin()
        assert plugin.get_version() == "1.0.0"

    def test_ensure_binary(self) -> None:
        """Test ensure_binary method."""
        plugin = ConcreteCoveragePlugin()
        assert plugin.ensure_binary() == Path("/usr/bin/coverage")

    def test_measure_coverage(self) -> None:
        """Test measure_coverage method."""
        plugin = ConcreteCoveragePlugin()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        result = plugin.measure_coverage(context, threshold=80.0)
        assert result.total_lines == 100
        assert result.covered_lines == 85
        assert result.passed is True
