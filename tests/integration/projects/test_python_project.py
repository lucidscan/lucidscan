"""Integration tests for Python project scanning.

These tests run the LucidScan CLI against a realistic Python project
with intentional issues and verify expected results.

Run with: pytest tests/integration/projects -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.projects.conftest import (
    run_lucidscan,
    ruff_available,
)


pytestmark = pytest.mark.integration


@ruff_available
class TestPythonLinting:
    """Test Python linting against the test project.

    Note: Ruff is auto-downloaded by LucidScan, so no fixture setup needed.
    """

    def test_ruff_finds_unused_imports(self, python_project: Path) -> None:
        """Test that Ruff finds unused imports (F401)."""
        result = run_lucidscan(python_project, domains=["linting"])

        # Should find issues (exit code depends on fail threshold settings)
        assert result.exit_code in (0, 1)
        assert result.issue_count >= 2

        # Should find F401 (unused imports) in app.py
        f401_issues = result.issues_by_rule("F401")
        assert len(f401_issues) >= 2, "Expected at least 2 unused import warnings"

    def test_ruff_finds_formatting_issues(self, python_project: Path) -> None:
        """Test that Ruff finds formatting issues."""
        result = run_lucidscan(python_project, domains=["linting"])

        assert result.issue_count >= 1
        # Should have linting domain issues
        linting_issues = result.issues_by_domain("linting")
        assert len(linting_issues) >= 1

    def test_linting_json_output_format(self, python_project: Path) -> None:
        """Test that JSON output has expected structure."""
        result = run_lucidscan(python_project, domains=["linting"])

        # Should have issues with required fields
        if result.issues:
            issue = result.issues[0]
            assert "id" in issue
            assert "title" in issue
            assert "severity" in issue
            assert "file_path" in issue


class TestPythonTypeChecking:
    """Test Python type checking against the test project.

    Note: mypy is installed in the project's venv by the fixture.
    """

    def test_type_checking_scan_completes(
        self, python_project_with_deps: Path
    ) -> None:
        """Test that type checking scan completes without errors."""
        result = run_lucidscan(python_project_with_deps, domains=["type_checking"])

        # Scan should complete (exit 0 or 1), not crash (exit 2+)
        assert result.exit_code in (0, 1)

        # If type checker is available and finds issues, verify them
        type_issues = result.issues_by_domain("type_checking")
        if type_issues:
            # Verify issues have expected fields
            for issue in type_issues:
                assert "severity" in issue
                assert "file_path" in issue

    def test_type_checking_detects_errors(
        self, python_project_with_deps: Path
    ) -> None:
        """Test that type errors are detected."""
        result = run_lucidscan(python_project_with_deps, domains=["type_checking"])

        # models.py has intentional type errors
        type_issues = result.issues_by_domain("type_checking")

        # Should find type errors since mypy is installed in project venv
        assert len(type_issues) >= 1, "Expected mypy to find type errors"

        # Verify errors are from expected files
        assert any(
            "models.py" in issue.get("file_path", "")
            for issue in type_issues
        ), "Expected type errors in models.py"


class TestPythonCombinedScanning:
    """Test combined linting and type checking."""

    @ruff_available
    def test_combined_linting_and_type_checking(
        self, python_project_with_deps: Path
    ) -> None:
        """Test running both linting and type checking together."""
        result = run_lucidscan(
            python_project_with_deps, domains=["linting", "type_checking"]
        )

        # Should have issues from both domains
        linting_issues = result.issues_by_domain("linting")
        type_issues = result.issues_by_domain("type_checking")

        assert len(linting_issues) >= 1, "Expected linting issues"
        assert len(type_issues) >= 1, "Expected type checking issues"

    @ruff_available
    def test_scan_completes_successfully(self, python_project: Path) -> None:
        """Test that scan completes and finds issues."""
        result = run_lucidscan(python_project, domains=["linting"])

        # Scan should complete (exit 0 or 1), not error (exit 2 or 3)
        assert result.exit_code in (0, 1)
        # Should find issues
        assert result.issue_count >= 1


class TestPythonProjectStructure:
    """Test that the Python project is properly structured."""

    def test_project_has_required_files(self, python_project: Path) -> None:
        """Test that the test project has all required files."""
        assert (python_project / "pyproject.toml").exists()
        assert (python_project / "requirements.txt").exists()
        assert (python_project / "src" / "app.py").exists()
        assert (python_project / "src" / "models.py").exists()
        assert (python_project / "src" / "utils.py").exists()
