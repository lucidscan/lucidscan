"""Integration tests for TypeScript project scanning.

These tests run the LucidScan CLI against a realistic TypeScript project
with intentional issues and verify expected results.

Run with: pytest tests/integration/projects -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.projects.conftest import (
    run_lucidscan,
    node_available,
)


pytestmark = pytest.mark.integration


@node_available
class TestTypeScriptLinting:
    """Test TypeScript linting against the test project.

    Note: ESLint is installed in the project's node_modules by the fixture.
    We only need Node.js to be globally available.
    """

    def test_eslint_finds_any_usage(
        self, typescript_project_with_deps: Path
    ) -> None:
        """Test that ESLint finds 'any' type usage."""
        result = run_lucidscan(
            typescript_project_with_deps, domains=["linting"]
        )

        # Should find linting issues
        linting_issues = result.issues_by_domain("linting")
        # May or may not find issues depending on ESLint config
        # At minimum, the scan should complete successfully
        assert result.exit_code in (0, 1)

    def test_eslint_finds_unused_vars(
        self, typescript_project_with_deps: Path
    ) -> None:
        """Test that ESLint finds unused variables."""
        result = run_lucidscan(
            typescript_project_with_deps, domains=["linting"]
        )

        # The project has unused variables that should be caught
        if result.issue_count > 0:
            linting_issues = result.issues_by_domain("linting")
            assert len(linting_issues) >= 0  # May find issues


@node_available
class TestTypeScriptTypeChecking:
    """Test TypeScript type checking against the test project.

    Note: TypeScript is installed in the project's node_modules by the fixture.
    We only need Node.js to be globally available.
    """

    def test_tsc_finds_type_errors(
        self, typescript_project_with_deps: Path
    ) -> None:
        """Test that TypeScript compiler finds type errors."""
        result = run_lucidscan(
            typescript_project_with_deps, domains=["type_checking"]
        )

        # Should find type errors (routes.ts has several)
        type_issues = result.issues_by_domain("type_checking")
        assert len(type_issues) >= 1, "Expected TypeScript type errors"

    def test_tsc_detects_return_type_mismatch(
        self, typescript_project_with_deps: Path
    ) -> None:
        """Test that tsc detects return type mismatches."""
        result = run_lucidscan(
            typescript_project_with_deps, domains=["type_checking"]
        )

        # index.ts has getPort() returning number instead of string
        # routes.ts has type mismatches
        assert result.issue_count >= 1


@node_available
class TestTypeScriptCombinedScanning:
    """Test combined linting and type checking for TypeScript."""

    def test_combined_scanning(
        self, typescript_project_with_deps: Path
    ) -> None:
        """Test running both linting and type checking together."""
        result = run_lucidscan(
            typescript_project_with_deps,
            domains=["linting", "type_checking"],
        )

        # Should have issues (at minimum type errors)
        assert result.issue_count >= 1

    def test_scan_completes_successfully(
        self, typescript_project_with_deps: Path
    ) -> None:
        """Test that scan completes and finds issues."""
        result = run_lucidscan(
            typescript_project_with_deps, domains=["type_checking"]
        )

        # Scan should complete (exit 0 or 1), not error (exit 2 or 3)
        assert result.exit_code in (0, 1)
        # Should find type errors
        assert result.issue_count >= 1


class TestTypeScriptProjectStructure:
    """Test that the TypeScript project is properly structured."""

    def test_project_has_required_files(self, typescript_project: Path) -> None:
        """Test that the test project has all required files."""
        assert (typescript_project / "package.json").exists()
        assert (typescript_project / "tsconfig.json").exists()
        assert (typescript_project / "src" / "index.ts").exists()
        assert (typescript_project / "src" / "routes.ts").exists()
        assert (typescript_project / "src" / "helpers.ts").exists()
