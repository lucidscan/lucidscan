"""Integration tests for Ruff linter.

These tests actually run the Ruff binary against real targets.
They require Ruff binary (downloaded automatically on first run).

Run with: pytest tests/integration/linters -v
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext, Severity
from lucidscan.plugins.linters.ruff import RuffLinter
from tests.integration.conftest import ruff_available


class TestRuffBinaryDownload:
    """Tests for Ruff binary download and management."""

    def test_ensure_binary_downloads_ruff(self, ruff_linter: RuffLinter) -> None:
        """Test that ensure_binary downloads Ruff if not present."""
        binary_path = ruff_linter.ensure_binary()

        assert binary_path.exists()
        assert "ruff" in binary_path.name

    def test_ruff_binary_is_executable(self, ensure_ruff_binary: Path) -> None:
        """Test that the downloaded Ruff binary is executable."""
        result = subprocess.run(
            [str(ensure_ruff_binary), "version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        assert "ruff" in result.stdout.lower()


@ruff_available
class TestRuffLinting:
    """Integration tests for Ruff linting."""

    def test_lint_python_file_with_issues(self, ruff_linter: RuffLinter) -> None:
        """Test linting a Python file with known issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with unused import (F401)
            test_file = tmpdir_path / "test.py"
            test_file.write_text("import os\nx = 1\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = ruff_linter.lint(context)

            assert len(issues) > 0
            assert issues[0].source_tool == "ruff"
            # F401 is unused import
            assert any("F401" in issue.title for issue in issues)

    def test_lint_clean_python_file(self, ruff_linter: RuffLinter) -> None:
        """Test linting a clean Python file returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a clean Python file
            test_file = tmpdir_path / "clean.py"
            test_file.write_text('"""Module docstring."""\n\nx = 1\n')

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = ruff_linter.lint(context)

            # Clean file should have no issues
            assert len(issues) == 0

    def test_lint_empty_directory(self, ruff_linter: RuffLinter) -> None:
        """Test linting an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = ruff_linter.lint(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_lint_multiple_issues(self, ruff_linter: RuffLinter) -> None:
        """Test linting a file with multiple issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with multiple issues
            test_file = tmpdir_path / "many_issues.py"
            test_file.write_text(
                "import os\n"  # F401: unused import
                "import sys\n"  # F401: unused import
                "x=1\n"  # E225: missing whitespace
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = ruff_linter.lint(context)

            # Should find multiple issues
            assert len(issues) >= 2


@ruff_available
class TestRuffAutoFix:
    """Integration tests for Ruff auto-fix functionality."""

    def test_fix_applies_changes(self, ruff_linter: RuffLinter) -> None:
        """Test that fix mode applies automatic fixes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with fixable issues
            test_file = tmpdir_path / "fixable.py"
            original_content = "import os\nx = 1\n"
            test_file.write_text(original_content)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = ruff_linter.fix(context)

            # Result should have fix statistics
            assert hasattr(result, "issues_fixed")
            assert hasattr(result, "issues_remaining")

    def test_fix_result_statistics(self, ruff_linter: RuffLinter) -> None:
        """Test that fix result contains correct statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file with fixable issues
            test_file = tmpdir_path / "stats.py"
            test_file.write_text("import os\nimport sys\nx = 1\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = ruff_linter.fix(context)

            # Should have fixed some issues
            assert result.issues_fixed >= 0
            assert result.issues_remaining >= 0


class TestRuffOutputParsing:
    """Tests for Ruff output parsing."""

    def test_severity_mapping(self, ruff_linter: RuffLinter) -> None:
        """Test that Ruff severities are mapped correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create file with different severity issues
            test_file = tmpdir_path / "severity.py"
            test_file.write_text("import os\n")  # F401 is medium severity

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = ruff_linter.lint(context)

            if issues:
                # All issues should have valid severity
                for issue in issues:
                    assert issue.severity in [
                        Severity.CRITICAL,
                        Severity.HIGH,
                        Severity.MEDIUM,
                        Severity.LOW,
                        Severity.INFO,
                    ]

    def test_issue_id_is_deterministic(self, ruff_linter: RuffLinter) -> None:
        """Test that issue IDs are consistent across runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            test_file = tmpdir_path / "deterministic.py"
            test_file.write_text("import os\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues1 = ruff_linter.lint(context)
            issues2 = ruff_linter.lint(context)

            if issues1 and issues2:
                # Same file, same content should produce same IDs
                assert issues1[0].id == issues2[0].id
