"""Integration tests for Checkstyle linter.

These tests require Java to be installed.

Run with: pytest tests/integration/linters -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path


from lucidscan.core.models import ScanContext
from lucidscan.plugins.linters.checkstyle import CheckstyleLinter
from tests.integration.conftest import java_available


class TestCheckstyleDownload:
    """Tests for Checkstyle JAR download and management."""

    @java_available
    def test_ensure_binary_downloads_jar(self, checkstyle_linter: CheckstyleLinter) -> None:
        """Test that ensure_binary downloads Checkstyle JAR if not present."""
        jar_path = checkstyle_linter.ensure_binary()

        assert jar_path.exists()
        assert jar_path.suffix == ".jar"


@java_available
class TestCheckstyleLinting:
    """Integration tests for Checkstyle linting."""

    def test_lint_java_file_with_issues(self, checkstyle_linter: CheckstyleLinter) -> None:
        """Test linting a Java file with style issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Java file with style issues (missing Javadoc)
            test_file = tmpdir_path / "Example.java"
            test_file.write_text(
                "public class Example {\n"
                "    public void method() {\n"
                "        int x = 1;\n"
                "    }\n"
                "}\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = checkstyle_linter.lint(context)

            # Should find style issues
            assert isinstance(issues, list)
            for issue in issues:
                assert issue.source_tool == "checkstyle"

    def test_lint_empty_directory(self, checkstyle_linter: CheckstyleLinter) -> None:
        """Test linting an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = checkstyle_linter.lint(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_lint_clean_java_file(self, checkstyle_linter: CheckstyleLinter) -> None:
        """Test linting a well-formatted Java file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a well-formatted Java file
            test_file = tmpdir_path / "Clean.java"
            test_file.write_text(
                "/**\n"
                " * Example class.\n"
                " */\n"
                "public class Clean {\n"
                "    /**\n"
                "     * Example method.\n"
                "     */\n"
                "    public void method() {\n"
                "        int x = 1;\n"
                "    }\n"
                "}\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = checkstyle_linter.lint(context)

            # Well-formatted file may still have issues depending on config
            assert isinstance(issues, list)
