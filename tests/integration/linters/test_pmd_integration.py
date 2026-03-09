"""Integration tests for PMD linter.

These tests require Java to be installed. PMD will be auto-downloaded.

Run with: pytest tests/integration/linters/test_pmd_integration.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lucidshark.core.models import ScanContext
from lucidshark.plugins.linters.pmd import PmdLinter
from tests.integration.conftest import java_available, pmd_available


class TestPmdResolution:
    """Tests for PMD binary resolution."""

    def test_ensure_binary_raises_when_java_not_available(self) -> None:
        """Test that ensure_binary raises FileNotFoundError when Java is missing."""
        import shutil
        from unittest.mock import patch

        linter = PmdLinter(project_root=Path("/nonexistent"))

        with patch.object(shutil, "which", return_value=None):
            with pytest.raises(FileNotFoundError, match="Java is required"):
                linter.ensure_binary()


@java_available
class TestPmdDownload:
    """Integration tests for PMD binary download."""

    @pytest.mark.slow
    def test_download_pmd_binary(self) -> None:
        """Test downloading and extracting PMD binary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = PmdLinter(project_root=Path(tmpdir))
            binary = linter.ensure_binary()
            assert binary.exists()
            assert binary.name == "pmd"


@pmd_available
class TestPmdLinting:
    """Integration tests for PMD linting checks."""

    @pytest.mark.slow
    def test_lint_java_file_with_issues(self) -> None:
        """Test linting a Java file with known violations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Java file with a known PMD violation (empty catch block)
            test_file = tmpdir_path / "Example.java"
            test_file.write_text(
                "public class Example {\n"
                "    public void method() {\n"
                "        try {\n"
                "            int x = 1;\n"
                "        } catch (Exception e) {\n"
                "            // empty\n"
                "        }\n"
                "    }\n"
                "}\n"
            )

            linter = PmdLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)
            for issue in issues:
                assert issue.source_tool == "pmd"

    @pytest.mark.slow
    def test_lint_empty_directory(self) -> None:
        """Test linting an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            linter = PmdLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)
            assert len(issues) == 0
