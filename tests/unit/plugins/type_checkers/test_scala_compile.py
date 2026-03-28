"""Unit tests for Scala compiler type checker plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.type_checkers.scala_compile import ScalaCompileChecker


class TestScalaCompileChecker:
    """Tests for ScalaCompileChecker class."""

    def test_name(self) -> None:
        plugin = ScalaCompileChecker()
        assert plugin.name == "scala_compile"

    def test_languages(self) -> None:
        plugin = ScalaCompileChecker()
        assert plugin.languages == ["scala"]

    def test_domain(self) -> None:
        plugin = ScalaCompileChecker()
        assert plugin.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        plugin = ScalaCompileChecker()
        assert plugin.supports_strict_mode is False


class TestScalaCompileBuildDetection:
    """Tests for build system detection."""

    def test_detect_sbt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = ScalaCompileChecker(project_root=project_root)
                binary, build_system = plugin._detect_build_system()
                assert build_system == "sbt"

    def test_detect_maven_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "pom.xml").write_text("<project/>")
            mvnw = project_root / "mvnw"
            mvnw.touch()

            plugin = ScalaCompileChecker(project_root=project_root)
            binary, build_system = plugin._detect_build_system()
            assert build_system == "maven"

    def test_no_build_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = ScalaCompileChecker(project_root=project_root)
                with pytest.raises(FileNotFoundError):
                    plugin._detect_build_system()


class TestScalaCompileEnsureBinary:
    """Tests for ensure_binary."""

    def test_ensure_binary_returns_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "build.sbt").write_text('scalaVersion := "3.3.1"')

            with patch("shutil.which", return_value="/usr/local/bin/sbt"):
                plugin = ScalaCompileChecker(project_root=project_root)
                binary = plugin.ensure_binary()
                assert binary == Path("/usr/local/bin/sbt")


class TestScalaCompileParseOutput:
    """Tests for compiler output parsing."""

    def test_parse_sbt_error(self) -> None:
        plugin = ScalaCompileChecker()
        output = "[error] /project/src/main/scala/App.scala:10:5: type mismatch"
        issues = plugin._parse_scala_compiler_output(output, Path("/project"))

        assert len(issues) == 1
        issue = issues[0]
        assert issue.domain == ToolDomain.TYPE_CHECKING
        assert issue.source_tool == "scala_compile"
        assert issue.severity == Severity.HIGH
        assert issue.rule_id == "compile_error"
        assert issue.line_start == 10
        assert issue.column_start == 5
        assert "type mismatch" in issue.title

    def test_parse_sbt_warning(self) -> None:
        plugin = ScalaCompileChecker()
        output = "[warn] /project/src/main/scala/App.scala:20:3: unused import"
        issues = plugin._parse_scala_compiler_output(output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM
        assert issues[0].rule_id == "compile_warning"

    def test_parse_sbt_error_without_column(self) -> None:
        plugin = ScalaCompileChecker()
        output = "[error] /project/src/App.scala:15: not found: value foo"
        issues = plugin._parse_scala_compiler_output(output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].line_start == 15
        assert issues[0].column_start is None

    def test_parse_scalac_direct_error(self) -> None:
        plugin = ScalaCompileChecker()
        output = "/project/src/App.scala:10:5: error: not found: type Foo"
        issues = plugin._parse_scala_compiler_output(output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.HIGH
        assert issues[0].line_start == 10

    def test_parse_scalac_direct_warning(self) -> None:
        plugin = ScalaCompileChecker()
        output = "/project/src/App.scala:5:1: warning: unused import"
        issues = plugin._parse_scala_compiler_output(output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_parse_empty_output(self) -> None:
        plugin = ScalaCompileChecker()
        issues = plugin._parse_scala_compiler_output("", Path("/project"))
        assert issues == []

    def test_parse_multiple_issues(self) -> None:
        plugin = ScalaCompileChecker()
        output = (
            "[error] /project/src/A.scala:1:1: not found: value x\n"
            "[warn] /project/src/B.scala:5:3: unused import\n"
            "[error] /project/src/C.scala:10:7: type mismatch\n"
        )
        issues = plugin._parse_scala_compiler_output(output, Path("/project"))

        assert len(issues) == 3
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.MEDIUM
        assert issues[2].severity == Severity.HIGH

    def test_parse_ignores_non_diagnostic_lines(self) -> None:
        plugin = ScalaCompileChecker()
        output = (
            "[info] Compiling 5 Scala sources...\n"
            "[error] /project/src/App.scala:10:5: type mismatch\n"
            "[info] Total time: 3 s\n"
        )
        issues = plugin._parse_scala_compiler_output(output, Path("/project"))
        assert len(issues) == 1


class TestScalaCompileCheck:
    """Tests for check method."""

    def test_check_skips_when_no_build_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch("shutil.which", return_value=None):
                plugin = ScalaCompileChecker(project_root=project_root)
                context = MagicMock()
                context.project_root = project_root

                issues = plugin.check(context)
                assert issues == []
                context.record_skip.assert_called_once()


class TestScalaCompileIssueId:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        plugin = ScalaCompileChecker()
        id1 = plugin._generate_issue_id("file.scala", 10, "msg")
        id2 = plugin._generate_issue_id("file.scala", 10, "msg")
        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        plugin = ScalaCompileChecker()
        id1 = plugin._generate_issue_id("file.scala", 10, "msg1")
        id2 = plugin._generate_issue_id("file.scala", 20, "msg2")
        assert id1 != id2

    def test_id_format(self) -> None:
        plugin = ScalaCompileChecker()
        issue_id = plugin._generate_issue_id("file.scala", 10, "msg")
        assert issue_id.startswith("scala-compile-")
