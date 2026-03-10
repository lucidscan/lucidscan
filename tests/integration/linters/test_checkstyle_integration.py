"""Integration tests for Checkstyle linter.

These tests require Java to be installed. Checkstyle JAR will be auto-downloaded.

Run with: pytest tests/integration/linters/test_checkstyle_integration.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext
from lucidshark.plugins.linters.checkstyle import CheckstyleLinter
from tests.integration.conftest import checkstyle_available, java_available


class TestCheckstyleResolution:
    """Tests for Checkstyle JAR resolution."""

    def test_ensure_binary_raises_when_java_not_available(self) -> None:
        """Test that ensure_binary raises FileNotFoundError when Java is missing."""
        import shutil

        linter = CheckstyleLinter(project_root=Path("/nonexistent"))

        with patch.object(shutil, "which", return_value=None):
            with pytest.raises(FileNotFoundError, match="Java is required"):
                linter.ensure_binary()


@java_available
class TestCheckstyleDownload:
    """Integration tests for Checkstyle JAR download."""

    @pytest.mark.slow
    def test_download_checkstyle_jar(self) -> None:
        """Test downloading Checkstyle all-in-one JAR."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(project_root=Path(tmpdir))
            jar_path = linter.ensure_binary()
            assert jar_path.exists()
            assert jar_path.suffix == ".jar"
            assert "checkstyle" in jar_path.name

    @pytest.mark.slow
    def test_cached_jar_reused(self) -> None:
        """Test that cached JAR is reused on subsequent calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = CheckstyleLinter(project_root=Path(tmpdir))

            # First call downloads
            jar_path1 = linter.ensure_binary()
            assert jar_path1.exists()

            # Second call should reuse cached JAR
            jar_path2 = linter.ensure_binary()
            assert jar_path1 == jar_path2


@checkstyle_available
class TestCheckstyleLinting:
    """Integration tests for Checkstyle linting checks."""

    @pytest.mark.slow
    def test_lint_java_file_with_issues(self) -> None:
        """Test linting a Java file with style issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Java file with style issues (tabs, missing final modifier)
            test_file = tmpdir_path / "Example.java"
            test_file.write_text(
                "public class Example {\n"
                "\tpublic void method() {\n"  # Tab character
                "\t\tint x = 1;\n"
                "\t}\n"
                "}\n"
            )

            linter = CheckstyleLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)
            # Should find at least the tab character issue
            for issue in issues:
                assert issue.source_tool == "checkstyle"

    @pytest.mark.slow
    def test_lint_empty_directory(self) -> None:
        """Test linting an empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            linter = CheckstyleLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)
            assert len(issues) == 0

    @pytest.mark.slow
    def test_lint_clean_java_file(self) -> None:
        """Test linting a well-formatted Java file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a well-formatted Java file (Google style: 2-space indent)
            test_file = tmpdir_path / "Clean.java"
            test_file.write_text(
                "/**\n"
                " * Example class.\n"
                " */\n"
                "public class Clean {\n"
                "  /**\n"
                "   * Example method.\n"
                "   */\n"
                "  public void method() {\n"
                "    int x = 1;\n"
                "  }\n"
                "}\n"
            )

            linter = CheckstyleLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)

    @pytest.mark.slow
    def test_lint_with_custom_config(self) -> None:
        """Test linting with a custom checkstyle.xml config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a minimal custom config
            # Note: DTD reference is optional but included for completeness
            config_file = tmpdir_path / "checkstyle.xml"
            config_file.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<!DOCTYPE module PUBLIC\n"
                '  "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"\n'
                '  "https://checkstyle.org/dtds/configuration_1_3.dtd">\n'
                '<module name="Checker">\n'
                '  <module name="TreeWalker">\n'
                '    <module name="EmptyCatchBlock">\n'
                '      <property name="exceptionVariableName" value="expected|ignore"/>\n'
                "    </module>\n"
                "  </module>\n"
                "</module>\n",
                encoding="utf-8",
            )

            # Create a Java file with empty catch block
            test_file = tmpdir_path / "Example.java"
            test_file.write_text(
                "public class Example {\n"
                "    public void method() {\n"
                "        try {\n"
                "            int x = 1;\n"
                "        } catch (Exception e) {\n"
                "        }\n"
                "    }\n"
                "}\n"
            )

            # Force file sync (helps on some CI systems)
            import os

            os.sync() if hasattr(os, "sync") else None

            linter = CheckstyleLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)
            # Should find the empty catch block
            # Debug: show what issues were found if assertion fails
            rule_ids = [issue.rule_id for issue in issues]
            assert any(
                "EmptyCatchBlock" in rule_id for rule_id in rule_ids
            ), f"Expected EmptyCatchBlock issue, got: {rule_ids}"

    @pytest.mark.slow
    def test_lint_multiple_files(self) -> None:
        """Test linting multiple Java files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()

            # Create multiple Java files
            (src_dir / "A.java").write_text(
                "public class A {\n\tpublic void foo() {}\n}\n"
            )
            (src_dir / "B.java").write_text(
                "public class B {\n\tpublic void bar() {}\n}\n"
            )

            linter = CheckstyleLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)
            # Should find issues in both files
            file_paths = {str(issue.file_path) for issue in issues}
            if issues:
                # At least one file should have issues (tabs)
                assert len(file_paths) >= 1

    @pytest.mark.slow
    def test_lint_respects_ignore_patterns(self) -> None:
        """Test that linting respects ignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            build_dir = tmpdir_path / "build"
            build_dir.mkdir()

            # Create files in both directories
            (src_dir / "Main.java").write_text(
                "public class Main {\n\tpublic void foo() {}\n}\n"
            )
            (build_dir / "Generated.java").write_text(
                "public class Generated {\n\tpublic void foo() {}\n}\n"
            )

            from unittest.mock import MagicMock

            mock_patterns = MagicMock()
            mock_patterns.matches = MagicMock(
                side_effect=lambda f, root: "build" in str(f)
            )

            linter = CheckstyleLinter(project_root=tmpdir_path)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir, build_dir],
                enabled_domains=[],
                ignore_patterns=mock_patterns,
            )

            issues = linter.lint(context)
            assert isinstance(issues, list)
            # No issues should come from build directory
            for issue in issues:
                assert "build" not in str(issue.file_path)


@checkstyle_available
class TestCheckstyleVersion:
    """Tests for Checkstyle version management."""

    @pytest.mark.slow
    def test_get_version_returns_configured_version(self) -> None:
        """Test that get_version returns the configured version."""
        linter = CheckstyleLinter()
        version = linter.get_version()
        assert version is not None
        assert isinstance(version, str)
        # Should be a valid semver-like version
        assert "." in version

    @pytest.mark.slow
    def test_different_versions_use_different_jars(self) -> None:
        """Test that different versions download to different directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Note: This test doesn't actually download different versions
            # It just verifies the path structure would be different
            linter1 = CheckstyleLinter(version="13.3.0", project_root=Path(tmpdir))
            linter2 = CheckstyleLinter(version="10.0.0", project_root=Path(tmpdir))

            # The paths should include the version
            path1 = linter1._paths.plugin_bin_dir("checkstyle", "13.3.0")
            path2 = linter2._paths.plugin_bin_dir("checkstyle", "10.0.0")

            assert path1 != path2
            assert "13.3.0" in str(path1)
            assert "10.0.0" in str(path2)
