"""Integration tests for JaCoCo coverage plugin.

These tests require Java and Maven to be installed.
The JaCoCo coverage plugin now parses existing reports, so tests
must first run Maven to generate JaCoCo XML data.

Run with: pytest tests/integration/coverage/test_jacoco_integration.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lucidshark.core.models import ScanContext, ToolDomain
from lucidshark.plugins.coverage.jacoco import JaCoCoPlugin
from tests.integration.conftest import maven_available


_JAVA_WEBAPP_PROJECT = Path(__file__).parent.parent / "projects" / "java-webapp"


@pytest.fixture(scope="session")
def _run_maven_tests() -> None:
    """Run mvn test once to generate JaCoCo coverage reports."""
    subprocess.run(
        ["mvn", "test", "-q"],
        cwd=_JAVA_WEBAPP_PROJECT,
        capture_output=True,
        timeout=120,
    )


@maven_available
class TestJaCoCoFunctional:
    """Functional integration tests for JaCoCo plugin."""

    def test_measure_coverage_java_webapp(
        self, jacoco_plugin: JaCoCoPlugin, java_webapp_project: Path,
        _run_maven_tests: None,
    ) -> None:
        """Test measuring coverage in the java-webapp project."""
        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        result = jacoco_plugin.measure_coverage(
            context, threshold=50.0
        )

        # Should have some coverage data
        assert result.total_lines > 0
        assert result.covered_lines >= 0
        assert 0 <= result.percentage <= 100
        assert result.tool == "jacoco"

    def test_measure_coverage_returns_coverage_result(
        self, jacoco_plugin: JaCoCoPlugin, java_webapp_project: Path,
        _run_maven_tests: None,
    ) -> None:
        """Test that measure_coverage returns proper CoverageResult."""
        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        result = jacoco_plugin.measure_coverage(
            context, threshold=0.0
        )

        # Check CoverageResult fields
        assert result.tool == "jacoco"
        assert result.total_lines >= 0
        assert result.covered_lines >= 0
        assert result.missing_lines >= 0
        assert isinstance(result.percentage, float)
        assert isinstance(result.passed, bool)
        assert isinstance(result.issues, list)

    def test_jacoco_reports_generated(
        self, jacoco_plugin: JaCoCoPlugin, java_webapp_project: Path,
        _run_maven_tests: None,
    ) -> None:
        """Test that JaCoCo generates coverage reports."""
        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        result = jacoco_plugin.measure_coverage(
            context, threshold=0.0
        )

        # After running, JaCoCo report should exist
        jacoco_dir = java_webapp_project / "target" / "site" / "jacoco"

        # Only check if coverage was measured
        if result.total_lines > 0:
            assert jacoco_dir.exists(), "JaCoCo should create report directory"

            # Check for jacoco.xml
            jacoco_xml = jacoco_dir / "jacoco.xml"
            assert jacoco_xml.exists(), "JaCoCo should generate XML report"


@maven_available
class TestJaCoCoCoverageThresholds:
    """Tests for JaCoCo coverage threshold checks."""

    def test_coverage_below_threshold_generates_issue(
        self, jacoco_plugin: JaCoCoPlugin, java_webapp_project: Path,
        _run_maven_tests: None,
    ) -> None:
        """Test that coverage below threshold generates an issue."""
        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        # Set a very high threshold to ensure failure
        result = jacoco_plugin.measure_coverage(
            context, threshold=99.0
        )

        # Should fail the threshold check
        if result.total_lines > 0:
            # If we have any coverage data, 99% threshold should fail
            if result.percentage < 99.0:
                assert result.passed is False
                assert len(result.issues) >= 1

                # Check the issue
                issue = result.issues[0]
                assert issue.domain == ToolDomain.COVERAGE
                assert issue.source_tool == "jacoco"

    def test_coverage_above_threshold_passes(
        self, jacoco_plugin: JaCoCoPlugin, java_webapp_project: Path,
        _run_maven_tests: None,
    ) -> None:
        """Test that coverage above threshold passes."""
        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        # Set a very low threshold
        result = jacoco_plugin.measure_coverage(
            context, threshold=1.0
        )

        # Should pass the threshold check if we have any coverage
        if result.total_lines > 0 and result.percentage >= 1.0:
            assert result.passed is True


@maven_available
class TestJaCoCoIssueGeneration:
    """Tests for JaCoCo issue generation."""

    def test_issue_has_correct_metadata(
        self, jacoco_plugin: JaCoCoPlugin, java_webapp_project: Path,
        _run_maven_tests: None,
    ) -> None:
        """Test that coverage issues have correct metadata."""
        context = ScanContext(
            project_root=java_webapp_project,
            paths=[java_webapp_project],
            enabled_domains=[],
        )

        # Use high threshold to ensure we get an issue
        result = jacoco_plugin.measure_coverage(
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
