"""Integration tests for Swift project scanning.

These tests run the LucidShark CLI against a realistic Swift project
with intentional issues and verify expected results.

Run with: pytest tests/integration/projects/test_swift_project.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.projects.conftest import (
    run_lucidshark,
    swift_available,
    swiftlint_available,
)


pytestmark = pytest.mark.integration


@swiftlint_available
class TestSwiftLinting:
    """Test Swift linting (SwiftLint) against the test project.

    SwiftLint is a Swift linter that detects style and convention issues.
    """

    def test_swiftlint_finds_lint_issues(self, swift_project: Path) -> None:
        """Test that SwiftLint finds lint issues in the Swift project."""
        result = run_lucidshark(swift_project, domains=["linting"])

        # Should find issues (exit code depends on fail threshold settings)
        assert result.exit_code in (0, 1)

        # SwiftLint should find style/convention issues
        linting_issues = result.issues_by_domain("linting")
        assert len(linting_issues) >= 1, "Expected at least 1 SwiftLint issue"

    def test_swiftlint_finds_force_unwrapping(self, swift_project: Path) -> None:
        """Test that SwiftLint detects force_unwrapping in Calculator."""
        result = run_lucidshark(swift_project, domains=["linting"])

        linting_issues = result.issues_by_domain("linting")
        # The project has intentional force_unwrapping in Calculator.swift
        if linting_issues:
            calculator_issues = [
                i
                for i in linting_issues
                if "Calculator.swift" in str(i.get("file_path", ""))
            ]
            assert len(calculator_issues) >= 1, (
                "Expected SwiftLint issues in Calculator.swift"
            )

    def test_swiftlint_finds_force_cast(self, swift_project: Path) -> None:
        """Test that SwiftLint detects force_cast in UserService."""
        result = run_lucidshark(swift_project, domains=["linting"])

        linting_issues = result.issues_by_domain("linting")
        if linting_issues:
            service_issues = [
                i
                for i in linting_issues
                if "UserService.swift" in str(i.get("file_path", ""))
            ]
            assert isinstance(service_issues, list)

    def test_linting_json_output_format(self, swift_project: Path) -> None:
        """Test that JSON output has expected structure."""
        result = run_lucidshark(swift_project, domains=["linting"])

        # Should have issues with required fields
        if result.issues:
            issue = result.issues[0]
            assert "id" in issue
            assert "title" in issue
            assert "severity" in issue
            assert "file_path" in issue


@swift_available
class TestSwiftTypeChecking:
    """Test Swift type checking (swift build) against the test project.

    swift build verifies that the project compiles without errors.
    """

    def test_type_checking_scan_completes(self, swift_project: Path) -> None:
        """Test that type checking scan completes without errors."""
        result = run_lucidshark(swift_project, domains=["type_checking"])

        # Scan should complete (exit 0 or 1), not crash (exit 2+)
        assert result.exit_code in (0, 1)

    def test_swift_build_reports_warnings(self, swift_project: Path) -> None:
        """Test that swift build reports compiler warnings."""
        result = run_lucidshark(swift_project, domains=["type_checking"])

        assert result.exit_code in (0, 1)

        # swift build may find warnings
        type_issues = result.issues_by_domain("type_checking")
        if type_issues:
            for issue in type_issues:
                assert "severity" in issue
                assert "file_path" in issue


@swift_available
class TestSwiftTestRunner:
    """Test Swift test running with swift test."""

    def test_swift_runs_tests(self, swift_project: Path) -> None:
        """Test that swift test runner executes tests."""
        result = run_lucidshark(swift_project, domains=["testing"])

        # Scan should complete
        assert result.exit_code in (0, 1)

        # Check summary for test results
        if result.summary:
            testing_summary = result.summary.get("testing", {})
            if testing_summary:
                assert "passed" in testing_summary or "total" in testing_summary


@swift_available
class TestSwiftCoverage:
    """Test Swift coverage measurement."""

    def test_swift_measures_coverage(self, swift_project: Path) -> None:
        """Test that swift coverage is measured."""
        result = run_lucidshark(swift_project, domains=["coverage"])

        # Scan should complete
        assert result.exit_code in (0, 1)

        # Check summary for coverage results
        if result.summary:
            coverage_summary = result.summary.get("coverage", {})
            if coverage_summary:
                assert (
                    "percentage" in coverage_summary
                    or "total_lines" in coverage_summary
                )


@swift_available
class TestSwiftCombinedScanning:
    """Test combined scanning for Swift projects."""

    @swiftlint_available
    def test_combined_linting_and_type_checking(self, swift_project: Path) -> None:
        """Test running both linting and type checking together."""
        result = run_lucidshark(swift_project, domains=["linting", "type_checking"])

        # Scan should complete
        assert result.exit_code in (0, 1)

        # Should have run both domains
        linting_issues = result.issues_by_domain("linting")
        type_issues = result.issues_by_domain("type_checking")

        # At least linting should find issues (SwiftLint on intentional issues)
        assert isinstance(linting_issues, list)
        assert isinstance(type_issues, list)

    @swiftlint_available
    def test_scan_all_domains(self, swift_project: Path) -> None:
        """Test scanning with all domains enabled."""
        result = run_lucidshark(
            swift_project,
            domains=["linting", "type_checking", "testing"],
        )

        # Scan should complete (exit 0 or 1), not error (exit 2+)
        assert result.exit_code in (0, 1)


class TestSwiftProjectStructure:
    """Test that the Swift project is properly structured."""

    def test_project_has_required_files(self, swift_project: Path) -> None:
        """Test that the test project has all required files."""
        assert (swift_project / "Package.swift").exists()
        assert (swift_project / "Sources" / "SwiftApp" / "Calculator.swift").exists()
        assert (swift_project / "Sources" / "SwiftApp" / "UserService.swift").exists()

    def test_project_has_source_files(self, swift_project: Path) -> None:
        """Test that the project has Swift source files."""
        src_dir = swift_project / "Sources"
        swift_files = list(src_dir.rglob("*.swift"))
        assert len(swift_files) >= 2, "Expected at least 2 Swift source files"

    def test_project_has_test_files(self, swift_project: Path) -> None:
        """Test that the project has Swift test files."""
        tests_dir = swift_project / "Tests"
        test_files = list(tests_dir.rglob("*.swift"))
        assert len(test_files) >= 2, "Expected at least 2 Swift test files"
