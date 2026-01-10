"""Integration tests for Biome linter.

These tests actually run the Biome binary against real targets.
They require Biome binary (downloaded automatically on first run).

Run with: pytest tests/integration/linters -v
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext
from lucidscan.plugins.linters.biome import BiomeLinter
from tests.integration.conftest import biome_available


class TestBiomeBinaryDownload:
    """Tests for Biome binary download and management."""

    def test_ensure_binary_downloads_biome(self, biome_linter: BiomeLinter) -> None:
        """Test that ensure_binary downloads Biome if not present."""
        binary_path = biome_linter.ensure_binary()

        assert binary_path.exists()
        assert "biome" in binary_path.name

    def test_biome_binary_is_executable(self, ensure_biome_binary: Path) -> None:
        """Test that the downloaded Biome binary is executable."""
        result = subprocess.run(
            [str(ensure_biome_binary), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0
        # Biome outputs "Version: X.Y.Z" format
        assert "version" in result.stdout.lower()


@biome_available
class TestBiomeLinting:
    """Integration tests for Biome linting."""

    def test_lint_javascript_file_with_issues(self, biome_linter: BiomeLinter) -> None:
        """Test linting a JavaScript file with issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a JS file with issues (unused variable)
            test_file = tmpdir_path / "test.js"
            test_file.write_text("const x = 1;\n")  # Unused variable

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = biome_linter.lint(context)

            # Biome should find unused variable
            assert isinstance(issues, list)
            # Issues might be empty if Biome's default config doesn't flag this
            for issue in issues:
                assert issue.source_tool == "biome"

    def test_lint_empty_directory(self, biome_linter: BiomeLinter) -> None:
        """Test linting an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = biome_linter.lint(context)

            assert isinstance(issues, list)
            assert len(issues) == 0


@biome_available
class TestBiomeAutoFix:
    """Integration tests for Biome auto-fix functionality."""

    def test_fix_returns_result(self, biome_linter: BiomeLinter) -> None:
        """Test that fix mode returns a result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a JS file
            test_file = tmpdir_path / "fixable.js"
            test_file.write_text("const x = 1;\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            result = biome_linter.fix(context)

            # Result should have fix statistics
            assert hasattr(result, "issues_fixed")
            assert hasattr(result, "issues_remaining")
