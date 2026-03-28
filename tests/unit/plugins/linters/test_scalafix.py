"""Unit tests for Scalafix linter plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.linters.scalafix import ScalafixLinter


class TestScalafixLinter:
    """Tests for ScalafixLinter class."""

    def test_name(self) -> None:
        plugin = ScalafixLinter()
        assert plugin.name == "scalafix"

    def test_languages(self) -> None:
        plugin = ScalafixLinter()
        assert plugin.languages == ["scala"]

    def test_domain(self) -> None:
        plugin = ScalafixLinter()
        assert plugin.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        plugin = ScalafixLinter()
        assert plugin.supports_fix is True


class TestScalafixEnsureBinary:
    """Tests for ensure_binary."""

    def test_ensure_binary_found_on_path(self) -> None:
        with patch("shutil.which", return_value="/usr/local/bin/scalafix"):
            plugin = ScalafixLinter()
            binary = plugin.ensure_binary()
            assert binary == Path("/usr/local/bin/scalafix")

    def test_ensure_binary_not_found(self) -> None:
        with patch("shutil.which", return_value=None):
            plugin = ScalafixLinter()
            with pytest.raises(FileNotFoundError, match="scalafix is not installed"):
                plugin.ensure_binary()


class TestScalafixFindScalaFiles:
    """Tests for _find_scala_files."""

    def test_find_scala_files_in_src(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src" / "main" / "scala" / "com" / "example"
            src_dir.mkdir(parents=True)
            (src_dir / "App.scala").write_text("object App")
            (src_dir / "Utils.scala").write_text("object Utils")

            plugin = ScalafixLinter(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = None
            context.ignore_patterns = None

            files = plugin._find_scala_files(context)
            assert len(files) == 2
            assert any("App.scala" in f for f in files)
            assert any("Utils.scala" in f for f in files)

    def test_find_scala_files_empty_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            plugin = ScalafixLinter(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = None
            context.ignore_patterns = None

            files = plugin._find_scala_files(context)
            assert len(files) == 0

    def test_find_sc_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "script.sc").write_text("println('hello')")

            plugin = ScalafixLinter(project_root=project_root)
            context = MagicMock()
            context.project_root = project_root
            context.paths = None
            context.ignore_patterns = None

            files = plugin._find_scala_files(context)
            assert len(files) == 1
            assert any("script.sc" in f for f in files)


class TestScalafixParseOutput:
    """Tests for output parsing."""

    def test_parse_output_with_rule(self) -> None:
        plugin = ScalafixLinter()

        output = "src/main/scala/App.scala:10:5: error: [DisableSyntax] var is disabled"
        issues = plugin._parse_output(output, Path("/project"))

        assert len(issues) == 1
        issue = issues[0]
        assert issue.domain == ToolDomain.LINTING
        assert issue.source_tool == "scalafix"
        assert issue.severity == Severity.HIGH
        assert issue.rule_id == "DisableSyntax"
        assert issue.line_start == 10
        assert issue.column_start == 5
        assert "var is disabled" in issue.title

    def test_parse_output_warning(self) -> None:
        plugin = ScalafixLinter()

        output = "src/App.scala:20:1: warning: [RemoveUnused] unused import"
        issues = plugin._parse_output(output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_parse_output_without_column(self) -> None:
        plugin = ScalafixLinter()

        output = "src/App.scala:15: error: [OrganizeImports] unsorted imports"
        issues = plugin._parse_output(output, Path("/project"))

        assert len(issues) == 1
        issue = issues[0]
        assert issue.line_start == 15
        assert issue.column_start is None

    def test_parse_empty_output(self) -> None:
        plugin = ScalafixLinter()
        issues = plugin._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_output_multiple_issues(self) -> None:
        plugin = ScalafixLinter()

        output = (
            "src/A.scala:1:1: error: [DisableSyntax] null is disabled\n"
            "src/B.scala:5:3: warning: [RemoveUnused] unused variable\n"
            "src/C.scala:10:1: info: [LeakingImplicitClassVal] consider val\n"
        )
        issues = plugin._parse_output(output, Path("/project"))

        assert len(issues) == 3
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.MEDIUM
        assert issues[2].severity == Severity.LOW


class TestScalafixLint:
    """Tests for lint method."""

    def test_lint_skips_when_not_installed(self) -> None:
        with patch("shutil.which", return_value=None):
            plugin = ScalafixLinter()
            context = MagicMock()
            context.project_root = Path("/project")
            context.paths = None

            issues = plugin.lint(context)
            assert issues == []
            context.record_skip.assert_called_once()

    def test_lint_no_scala_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value="/usr/local/bin/scalafix"):
                plugin = ScalafixLinter(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root
                context.paths = None
                context.ignore_patterns = None

                issues = plugin.lint(context)
                assert issues == []


class TestScalafixIssueId:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        plugin = ScalafixLinter()
        id1 = plugin._generate_issue_id("rule", "file.scala", 10, "msg")
        id2 = plugin._generate_issue_id("rule", "file.scala", 10, "msg")
        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        plugin = ScalafixLinter()
        id1 = plugin._generate_issue_id("rule1", "file.scala", 10, "msg")
        id2 = plugin._generate_issue_id("rule2", "file.scala", 10, "msg")
        assert id1 != id2

    def test_id_format(self) -> None:
        plugin = ScalafixLinter()
        issue_id = plugin._generate_issue_id("rule", "file.scala", 10, "msg")
        assert issue_id.startswith("scalafix-")
