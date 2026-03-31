"""Unit tests for Scalafmt formatter plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.formatters.scalafmt import ScalafmtFormatter


class TestScalafmtFormatter:
    """Tests for ScalafmtFormatter class."""

    def test_name(self) -> None:
        plugin = ScalafmtFormatter()
        assert plugin.name == "scalafmt"

    def test_languages(self) -> None:
        plugin = ScalafmtFormatter()
        assert plugin.languages == ["scala"]

    def test_domain(self) -> None:
        plugin = ScalafmtFormatter()
        assert plugin.domain == ToolDomain.FORMATTING

    def test_supports_fix(self) -> None:
        plugin = ScalafmtFormatter()
        assert plugin.supports_fix is True


class TestScalafmtEnsureBinary:
    """Tests for ensure_binary."""

    def test_ensure_binary_found_on_path(self) -> None:
        with patch("shutil.which", return_value="/usr/local/bin/scalafmt"):
            plugin = ScalafmtFormatter()
            binary = plugin.ensure_binary()
            assert binary == Path("/usr/local/bin/scalafmt")

    def test_ensure_binary_not_found(self) -> None:
        with patch("shutil.which", return_value=None):
            plugin = ScalafmtFormatter()
            with pytest.raises(FileNotFoundError, match="scalafmt is not installed"):
                plugin.ensure_binary()


class TestScalafmtCheck:
    """Tests for check method."""

    def test_check_skips_when_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            plugin = ScalafmtFormatter()
            context = MagicMock()
            context.project_root = Path("/project")
            context.paths = None

            issues = plugin.check(context)
            assert issues == []
            context.record_skip.assert_called_once()

    def test_check_no_scala_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value="/usr/local/bin/scalafmt"):
                plugin = ScalafmtFormatter(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.paths = None
                context.ignore_patterns = None

                issues = plugin.check(context)
                assert issues == []

    def test_check_parses_unformatted_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "App.scala").write_text("object App {}")

            with patch("shutil.which", return_value="/usr/local/bin/scalafmt"):
                plugin = ScalafmtFormatter(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.paths = [src_dir / "App.scala"]
                context.ignore_patterns = None

                # Mock run_with_streaming to simulate unformatted output
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stdout = "src/App.scala\n"
                mock_result.stderr = ""

                with patch(
                    "lucidshark.plugins.formatters.scalafmt.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = plugin.check(context)
                    assert len(issues) == 1
                    assert issues[0].source_tool == "scalafmt"
                    assert issues[0].severity == Severity.LOW
                    assert issues[0].rule_id == "format"
                    assert issues[0].fixable is True

    def test_check_clean_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "App.scala").write_text("object App {}")

            with patch("shutil.which", return_value="/usr/local/bin/scalafmt"):
                plugin = ScalafmtFormatter(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.paths = [src_dir / "App.scala"]
                context.ignore_patterns = None

                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""

                with patch(
                    "lucidshark.plugins.formatters.scalafmt.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = plugin.check(context)
                    assert issues == []


class TestScalafmtFix:
    """Tests for fix method."""

    def test_fix_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            plugin = ScalafmtFormatter()
            context = MagicMock()
            context.project_root = Path("/project")
            context.paths = None

            result = plugin.fix(context)
            assert result.files_modified == 0

    def test_fix_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value="/usr/local/bin/scalafmt"):
                plugin = ScalafmtFormatter(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.paths = None
                context.ignore_patterns = None

                result = plugin.fix(context)
                assert result.files_modified == 0

    def test_fix_reports_correct_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "App.scala").write_text("object App {}")

            with patch("shutil.which", return_value="/usr/local/bin/scalafmt"):
                plugin = ScalafmtFormatter(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.paths = [src_dir / "App.scala"]
                context.ignore_patterns = None

                # First check: 1 issue, second check (after fix): 0 issues
                mock_check_result = MagicMock()
                mock_check_result.returncode = 1
                mock_check_result.stdout = "src/App.scala\n"
                mock_check_result.stderr = ""

                mock_clean_result = MagicMock()
                mock_clean_result.returncode = 0
                mock_clean_result.stdout = ""
                mock_clean_result.stderr = ""

                mock_fix_result = MagicMock()
                mock_fix_result.returncode = 0

                call_count = 0

                def mock_run(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    cmd = args[0] if args else kwargs.get("cmd", [])
                    if "--check" in cmd:
                        # Pre-fix check returns issues, post-fix returns clean
                        if call_count <= 1:
                            return mock_check_result
                        return mock_clean_result
                    return mock_fix_result

                with patch(
                    "lucidshark.plugins.formatters.scalafmt.run_with_streaming",
                    side_effect=mock_run,
                ):
                    result = plugin.fix(context)
                    assert result.issues_fixed == 1
                    assert result.files_modified == 1
                    assert result.issues_remaining == 0
