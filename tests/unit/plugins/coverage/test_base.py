"""Unit tests for coverage plugin base classes."""

from __future__ import annotations

from pathlib import Path
from typing import List


from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.coverage.base import (
    CoveragePlugin,
    CoverageResult,
    FileCoverage,
    TestStatistics,
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

    def test_passed_false_when_tests_failed(self) -> None:
        """Test passed is False when tests have failures, even if coverage is above threshold."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=90,
            threshold=80.0,
        )
        result.test_stats = TestStatistics(total=10, passed=9, failed=1)
        assert result.passed is False

    def test_passed_false_when_tests_have_errors(self) -> None:
        """Test passed is False when tests have errors."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=90,
            threshold=80.0,
        )
        result.test_stats = TestStatistics(total=10, passed=9, errors=1)
        assert result.passed is False

    def test_passed_true_when_tests_pass(self) -> None:
        """Test passed is True when tests all pass and coverage meets threshold."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=85,
            threshold=80.0,
        )
        result.test_stats = TestStatistics(total=10, passed=10)
        assert result.passed is True

    def test_passed_ignores_test_stats_when_none(self) -> None:
        """Test passed only checks threshold when test_stats is None."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=85,
            threshold=80.0,
        )
        assert result.test_stats is None
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


class TestCoverageResultFilterToChangedFiles:
    """Tests for CoverageResult.filter_to_changed_files method."""

    def test_filter_to_single_changed_file(self, tmp_path: Path) -> None:
        """Test filtering to a single changed file."""
        result = CoverageResult(
            total_lines=300,
            covered_lines=240,
            missing_lines=60,
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                    missing_lines=[10, 20, 30],
                ),
                "src/utils.py": FileCoverage(
                    file_path=Path("src/utils.py"),
                    total_lines=100,
                    covered_lines=90,
                    missing_lines=[5],
                ),
                "src/models.py": FileCoverage(
                    file_path=Path("src/models.py"),
                    total_lines=100,
                    covered_lines=70,
                    missing_lines=[1, 2, 3, 4, 5],
                ),
            },
        )

        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        assert len(filtered.files) == 1
        assert "src/app.py" in filtered.files
        assert filtered.total_lines == 100
        assert filtered.covered_lines == 80
        assert filtered.percentage == 80.0

    def test_filter_to_multiple_changed_files(self, tmp_path: Path) -> None:
        """Test filtering to multiple changed files."""
        result = CoverageResult(
            total_lines=300,
            covered_lines=240,
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
                "src/utils.py": FileCoverage(
                    file_path=Path("src/utils.py"),
                    total_lines=100,
                    covered_lines=90,
                ),
                "src/models.py": FileCoverage(
                    file_path=Path("src/models.py"),
                    total_lines=100,
                    covered_lines=70,
                ),
            },
        )

        changed_files = [
            tmp_path / "src" / "app.py",
            tmp_path / "src" / "utils.py",
        ]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        assert len(filtered.files) == 2
        assert "src/app.py" in filtered.files
        assert "src/utils.py" in filtered.files
        assert "src/models.py" not in filtered.files
        assert filtered.total_lines == 200
        assert filtered.covered_lines == 170
        assert filtered.percentage == 85.0

    def test_filter_no_matching_files(self, tmp_path: Path) -> None:
        """Test filtering when no files match."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
            },
        )

        changed_files = [tmp_path / "src" / "other.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        assert len(filtered.files) == 0
        assert filtered.total_lines == 0
        assert filtered.covered_lines == 0
        assert filtered.percentage == 100.0  # No lines = 100%

    def test_filter_empty_changed_files(self, tmp_path: Path) -> None:
        """Test filtering with empty changed files list."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
            },
        )

        filtered = result.filter_to_changed_files([], tmp_path)

        assert len(filtered.files) == 0
        assert filtered.total_lines == 0

    def test_filter_preserves_test_stats(self, tmp_path: Path) -> None:
        """Test that filtering preserves test statistics."""
        test_stats = TestStatistics(total=10, passed=10, failed=0)
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            threshold=80.0,
            test_stats=test_stats,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
            },
        )

        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        assert filtered.test_stats is not None
        assert filtered.test_stats.total == 10
        assert filtered.test_stats.passed == 10

    def test_filter_preserves_threshold(self, tmp_path: Path) -> None:
        """Test that filtering preserves threshold."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            threshold=75.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
            },
        )

        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        assert filtered.threshold == 75.0

    def test_filter_preserves_tool_name(self, tmp_path: Path) -> None:
        """Test that filtering preserves tool name."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            tool="coverage_py",
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
            },
        )

        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        assert filtered.tool == "coverage_py"

    def test_filter_recalculates_missing_lines(self, tmp_path: Path) -> None:
        """Test that missing lines count is recalculated from filtered files."""
        result = CoverageResult(
            total_lines=200,
            covered_lines=150,
            missing_lines=50,
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                    missing_lines=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],  # 10 missing
                ),
                "src/utils.py": FileCoverage(
                    file_path=Path("src/utils.py"),
                    total_lines=100,
                    covered_lines=70,
                    missing_lines=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],  # 15 missing
                ),
            },
        )

        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        # Only count missing lines from filtered files
        assert filtered.missing_lines == 10

    def test_filter_clears_issues(self, tmp_path: Path) -> None:
        """Test that filtering clears old issues (to be regenerated if needed)."""
        from lucidshark.core.models import Severity, UnifiedIssue

        mock_issue = UnifiedIssue(
            id="cov-1",
            title="Coverage below threshold",
            description="Coverage is below the configured threshold",
            domain=ToolDomain.COVERAGE,
            source_tool="coverage_py",
            severity=Severity.MEDIUM,
            rule_id="coverage_below_threshold",
        )
        result = CoverageResult(
            total_lines=100,
            covered_lines=70,
            threshold=80.0,
            issues=[mock_issue],
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=70,
                ),
            },
        )

        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        # Issues are cleared (will be regenerated based on new threshold check)
        assert filtered.issues == []

    def test_filter_with_path_suffix_matching(self, tmp_path: Path) -> None:
        """Test path matching works with different path formats."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
            },
        )

        # Changed file with full absolute path
        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        assert len(filtered.files) == 1
        assert "src/app.py" in filtered.files

    def test_filter_threshold_applies_to_filtered_result(self, tmp_path: Path) -> None:
        """Test that threshold check applies to filtered coverage percentage."""
        result = CoverageResult(
            total_lines=300,
            covered_lines=270,  # 90% overall
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=50,  # 50% for this file
                ),
                "src/utils.py": FileCoverage(
                    file_path=Path("src/utils.py"),
                    total_lines=100,
                    covered_lines=100,  # 100% for this file
                ),
                "src/models.py": FileCoverage(
                    file_path=Path("src/models.py"),
                    total_lines=100,
                    covered_lines=100,  # 100% for this file - not changed
                ),
            },
        )

        # Only changed files: app.py (50%) and utils.py (100%)
        changed_files = [
            tmp_path / "src" / "app.py",
            tmp_path / "src" / "utils.py",
        ]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        # Filtered coverage: (50 + 100) / 200 = 75%
        assert filtered.total_lines == 200
        assert filtered.covered_lines == 150
        assert filtered.percentage == 75.0
        # 75% is below 80% threshold
        assert filtered.passed is False

    def test_filter_returns_new_instance(self, tmp_path: Path) -> None:
        """Test that filter returns a new CoverageResult instance."""
        result = CoverageResult(
            total_lines=100,
            covered_lines=80,
            threshold=80.0,
            files={
                "src/app.py": FileCoverage(
                    file_path=Path("src/app.py"),
                    total_lines=100,
                    covered_lines=80,
                ),
            },
        )

        changed_files = [tmp_path / "src" / "app.py"]
        filtered = result.filter_to_changed_files(changed_files, tmp_path)

        # Should be a new instance
        assert filtered is not result
        assert filtered.files is not result.files
