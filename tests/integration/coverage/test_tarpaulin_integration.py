"""Integration tests for Tarpaulin coverage plugin.

These tests actually run cargo tarpaulin against real Rust targets.
They require Rust (cargo) and cargo-tarpaulin to be installed.

Run with: pytest tests/integration/coverage/test_tarpaulin_integration.py -v
"""

from __future__ import annotations

from pathlib import Path

from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.coverage.tarpaulin import TarpaulinPlugin
from tests.integration.conftest import cargo_available, tarpaulin_available


@cargo_available
@tarpaulin_available
class TestTarpaulinFunctional:
    """Functional integration tests for Tarpaulin plugin."""

    def test_measure_coverage_sample_project(
        self, tarpaulin_plugin: TarpaulinPlugin
    ) -> None:
        """Test measuring coverage in the rust-cli sample project."""
        project_path = Path(__file__).parent.parent / "projects" / "rust-cli"
        if not project_path.exists():
            import pytest
            pytest.skip("rust-cli sample project not found")

        context = ScanContext(
            project_root=project_path,
            paths=[project_path],
            enabled_domains=[],
        )

        result = tarpaulin_plugin.measure_coverage(
            context, threshold=50.0
        )

        # Should have some coverage data
        assert result.total_lines > 0
        assert result.covered_lines >= 0
        assert 0 <= result.percentage <= 100
        assert result.tool == "tarpaulin"

    def test_measure_coverage_returns_coverage_result(
        self, tarpaulin_plugin: TarpaulinPlugin
    ) -> None:
        """Test that measure_coverage returns proper CoverageResult."""
        project_path = Path(__file__).parent.parent / "projects" / "rust-cli"
        if not project_path.exists():
            import pytest
            pytest.skip("rust-cli sample project not found")

        context = ScanContext(
            project_root=project_path,
            paths=[project_path],
            enabled_domains=[],
        )

        result = tarpaulin_plugin.measure_coverage(
            context, threshold=0.0
        )

        # Check CoverageResult fields
        assert result.tool == "tarpaulin"
        assert result.total_lines >= 0
        assert result.covered_lines >= 0
        assert result.missing_lines >= 0
        assert isinstance(result.percentage, float)
        assert isinstance(result.passed, bool)
        assert isinstance(result.issues, list)


@cargo_available
@tarpaulin_available
class TestTarpaulinCoverageThresholds:
    """Tests for Tarpaulin coverage threshold checks."""

    def test_coverage_below_threshold_generates_issue(
        self, tarpaulin_plugin: TarpaulinPlugin
    ) -> None:
        """Test that coverage below threshold generates an issue."""
        project_path = Path(__file__).parent.parent / "projects" / "rust-cli"
        if not project_path.exists():
            import pytest
            pytest.skip("rust-cli sample project not found")

        context = ScanContext(
            project_root=project_path,
            paths=[project_path],
            enabled_domains=[],
        )

        # Set a very high threshold to ensure failure
        result = tarpaulin_plugin.measure_coverage(
            context, threshold=99.0
        )

        # Should fail the threshold check
        if result.total_lines > 0:
            if result.percentage < 99.0:
                assert result.passed is False
                assert len(result.issues) >= 1

                # Check the issue
                issue = result.issues[0]
                assert issue.domain == ToolDomain.COVERAGE
                assert issue.source_tool == "tarpaulin"

    def test_coverage_above_threshold_passes(
        self, tarpaulin_plugin: TarpaulinPlugin
    ) -> None:
        """Test that coverage above threshold passes."""
        project_path = Path(__file__).parent.parent / "projects" / "rust-cli"
        if not project_path.exists():
            import pytest
            pytest.skip("rust-cli sample project not found")

        context = ScanContext(
            project_root=project_path,
            paths=[project_path],
            enabled_domains=[],
        )

        # Set a very low threshold
        result = tarpaulin_plugin.measure_coverage(
            context, threshold=1.0
        )

        # Should pass the threshold check if we have any coverage
        if result.total_lines > 0 and result.percentage >= 1.0:
            assert result.passed is True


@cargo_available
@tarpaulin_available
class TestTarpaulinIssueGeneration:
    """Tests for Tarpaulin issue generation."""

    def test_issue_has_correct_metadata(
        self, tarpaulin_plugin: TarpaulinPlugin
    ) -> None:
        """Test that coverage issues have correct metadata."""
        project_path = Path(__file__).parent.parent / "projects" / "rust-cli"
        if not project_path.exists():
            import pytest
            pytest.skip("rust-cli sample project not found")

        context = ScanContext(
            project_root=project_path,
            paths=[project_path],
            enabled_domains=[],
        )

        # Use high threshold to ensure we get an issue
        result = tarpaulin_plugin.measure_coverage(
            context, threshold=99.0
        )

        # Should generate an issue due to low coverage
        if len(result.issues) > 0:
            issue = result.issues[0]
            metadata = issue.metadata

            assert "coverage_percentage" in metadata
            assert "threshold" in metadata
            assert "total_lines" in metadata
            assert "covered_lines" in metadata
            assert "missing_lines" in metadata
