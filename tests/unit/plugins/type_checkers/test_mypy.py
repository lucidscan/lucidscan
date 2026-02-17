"""Unit tests for mypy type checker plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.type_checkers.mypy import (
    MypyChecker,
    SEVERITY_MAP,
    _glob_to_regex,
)


def make_completed_process(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestMypyCheckerProperties:
    """Tests for MypyChecker basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        checker = MypyChecker()
        assert checker.name == "mypy"

    def test_languages(self) -> None:
        """Test supported languages."""
        checker = MypyChecker()
        assert checker.languages == ["python"]

    def test_domain(self) -> None:
        """Test domain is TYPE_CHECKING."""
        checker = MypyChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        """Test strict mode is supported."""
        checker = MypyChecker()
        assert checker.supports_strict_mode is True

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = MypyChecker(project_root=Path(tmpdir))
            assert checker._project_root == Path(tmpdir)


class TestMypySeverityMapping:
    """Tests for mypy severity mapping."""

    def test_error_maps_to_high(self) -> None:
        """Test error maps to HIGH."""
        assert SEVERITY_MAP["error"] == Severity.HIGH

    def test_warning_maps_to_medium(self) -> None:
        """Test warning maps to MEDIUM."""
        assert SEVERITY_MAP["warning"] == Severity.MEDIUM

    def test_note_maps_to_low(self) -> None:
        """Test note maps to LOW."""
        assert SEVERITY_MAP["note"] == Severity.LOW


class TestGlobToRegex:
    """Tests for _glob_to_regex conversion function."""

    def test_double_star_slash_pattern(self) -> None:
        """Test **/.venv/** pattern conversion."""
        regex = _glob_to_regex("**/.venv/**")
        assert "(^|/)" in regex
        assert "\\.venv" in regex
        assert "(/|$)" in regex

    def test_leading_double_star(self) -> None:
        """Test **/foo pattern conversion."""
        regex = _glob_to_regex("**/foo")
        assert "(^|/)" in regex
        assert "foo$" in regex

    def test_trailing_double_star(self) -> None:
        """Test foo/** pattern conversion."""
        regex = _glob_to_regex("foo/**")
        assert "^foo" in regex
        assert "(/|$)" in regex

    def test_directory_slash_pattern(self) -> None:
        """Test .venv/ directory pattern."""
        regex = _glob_to_regex(".venv/")
        assert "(^|/)" in regex
        assert "\\.venv" in regex
        assert "(/|$)" in regex

    def test_wildcard_pattern(self) -> None:
        """Test *.pyc wildcard pattern."""
        regex = _glob_to_regex("*.pyc")
        assert "[^/]*" in regex
        assert "\\.pyc" in regex

    def test_double_star_wildcard(self) -> None:
        """Test **/*.pyc pattern - leading **/ is stripped, then wildcard converted."""
        regex = _glob_to_regex("**/*.pyc")
        # After stripping **/, we get "*.pyc" which has * converted to [^/]*
        assert "[^/]*" in regex
        assert "\\.pyc" in regex

    def test_question_mark_pattern(self) -> None:
        """Test ? single character pattern."""
        regex = _glob_to_regex("test?.py")
        assert "[^/]" in regex


class TestMypyEnsureBinary:
    """Tests for ensure_binary method."""

    def test_finds_venv_mypy_unix(self) -> None:
        """Test finding mypy in project .venv on Unix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_mypy = project_root / ".venv" / "bin" / "mypy"
            venv_mypy.parent.mkdir(parents=True)
            venv_mypy.touch()

            checker = MypyChecker(project_root=project_root)
            with patch("sys.platform", "linux"):
                binary = checker.ensure_binary()
                assert binary == venv_mypy

    def test_finds_system_mypy(self) -> None:
        """Test finding mypy in system PATH."""
        checker = MypyChecker()

        with patch("shutil.which", return_value="/usr/local/bin/mypy"):
            binary = checker.ensure_binary()
            assert binary == Path("/usr/local/bin/mypy")

    def test_raises_when_not_found(self) -> None:
        """Test raises FileNotFoundError when mypy not found."""
        checker = MypyChecker()

        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="mypy is not installed"):
                checker.ensure_binary()

    def test_get_version_success(self) -> None:
        """Test get_version with successful call."""
        checker = MypyChecker()

        with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
            with patch("lucidshark.plugins.type_checkers.mypy.get_cli_version", return_value="1.8.0"):
                version = checker.get_version()
                assert version == "1.8.0"

    def test_get_version_not_found(self) -> None:
        """Test get_version returns unknown when mypy not found."""
        checker = MypyChecker()

        with patch.object(checker, "ensure_binary", side_effect=FileNotFoundError()):
            version = checker.get_version()
            assert version == "unknown"


class TestMypyCheck:
    """Tests for check method."""

    def test_check_binary_not_found(self) -> None:
        """Test check returns empty when binary not found."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(checker, "ensure_binary", side_effect=FileNotFoundError("not found")):
                issues = checker.check(context)
                assert issues == []

    def test_check_success(self) -> None:
        """Test successful type checking."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            mypy_output = json.dumps({
                "file": "src/app.py",
                "severity": "error",
                "message": "Incompatible types in assignment",
                "line": 10,
                "column": 5,
                "code": "assignment",
            })

            mock_result = make_completed_process(1, mypy_output)

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
                with patch("lucidshark.plugins.type_checkers.mypy.run_with_streaming", return_value=mock_result):
                    issues = checker.check(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "mypy"
                    assert issues[0].domain == ToolDomain.TYPE_CHECKING
                    assert issues[0].severity == Severity.HIGH
                    assert issues[0].rule_id == "assignment"

    def test_check_timeout(self) -> None:
        """Test check handles timeout."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
                with patch(
                    "lucidshark.plugins.type_checkers.mypy.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("mypy", 180),
                ):
                    issues = checker.check(context)
                    assert issues == []

    def test_check_subprocess_error(self) -> None:
        """Test check handles subprocess errors."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
                with patch(
                    "lucidshark.plugins.type_checkers.mypy.run_with_streaming",
                    side_effect=OSError("command failed"),
                ):
                    issues = checker.check(context)
                    assert issues == []

    def test_check_no_python_files(self) -> None:
        """Test check returns empty when no Python files in paths."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            js_file = tmpdir_path / "app.js"
            js_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[js_file],
                enabled_domains=[],
            )

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
                issues = checker.check(context)
                assert issues == []

    def test_check_uses_mypy_ini_if_present(self) -> None:
        """Test check uses mypy.ini config file if present."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mypy_ini = tmpdir_path / "mypy.ini"
            mypy_ini.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, "")

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
                with patch("lucidshark.plugins.type_checkers.mypy.run_with_streaming", return_value=mock_result) as mock_run:
                    checker.check(context)
                    cmd = mock_run.call_args.kwargs.get("cmd") or mock_run.call_args[1].get("cmd")
                    assert "--config-file" in cmd
                    assert str(mypy_ini) in cmd

    def test_check_uses_dot_for_project_root_path(self) -> None:
        """Test check uses '.' when single path is project root."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, "")

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
                with patch("lucidshark.plugins.type_checkers.mypy.run_with_streaming", return_value=mock_result) as mock_run:
                    checker.check(context)
                    cmd = mock_run.call_args.kwargs.get("cmd") or mock_run.call_args[1].get("cmd")
                    assert "." in cmd

    def test_check_uses_stderr_as_fallback(self) -> None:
        """Test check uses stderr when stdout is empty."""
        checker = MypyChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            mypy_error = json.dumps({
                "file": "app.py",
                "severity": "error",
                "message": "test error",
                "line": 1,
                "column": 1,
                "code": "misc",
            })

            mock_result = make_completed_process(1, "", mypy_error)

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/mypy")):
                with patch("lucidshark.plugins.type_checkers.mypy.run_with_streaming", return_value=mock_result):
                    issues = checker.check(context)
                    assert len(issues) == 1


class TestMypyParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        checker = MypyChecker()
        issues = checker._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_none_output(self) -> None:
        """Test parsing None-like empty output."""
        checker = MypyChecker()
        issues = checker._parse_output("   ", Path("/project"))
        assert issues == []

    def test_parse_single_line_json(self) -> None:
        """Test parsing single JSON line (mypy 1.x format)."""
        checker = MypyChecker()
        output = json.dumps({
            "file": "app.py",
            "severity": "error",
            "message": "Incompatible types",
            "line": 5,
            "column": 3,
            "code": "assignment",
        })

        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "assignment"
        assert issues[0].line_start == 5

    def test_parse_multiline_json(self) -> None:
        """Test parsing multiple JSON lines."""
        checker = MypyChecker()
        line1 = json.dumps({
            "file": "a.py", "severity": "error", "message": "Error 1",
            "line": 1, "column": 1, "code": "misc",
        })
        line2 = json.dumps({
            "file": "b.py", "severity": "warning", "message": "Warning 1",
            "line": 5, "column": 2, "code": "override",
        })
        output = f"{line1}\n{line2}"

        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 2

    def test_parse_messages_array_format(self) -> None:
        """Test parsing mypy 2.x format with messages array."""
        checker = MypyChecker()
        output = json.dumps({
            "messages": [
                {
                    "file": "a.py", "severity": "error", "message": "Error 1",
                    "line": 1, "column": 1, "code": "misc",
                },
                {
                    "file": "b.py", "severity": "error", "message": "Error 2",
                    "line": 5, "column": 1, "code": "attr-defined",
                },
            ]
        })

        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 2

    def test_parse_non_json_lines_skipped(self) -> None:
        """Test that non-JSON lines are skipped."""
        checker = MypyChecker()
        valid_line = json.dumps({
            "file": "a.py", "severity": "error", "message": "Error",
            "line": 1, "column": 1, "code": "misc",
        })
        output = f"Some non-JSON output\n{valid_line}\nAnother non-JSON line"

        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1


class TestMypyErrorToIssue:
    """Tests for _error_to_issue method."""

    def test_converts_error_correctly(self) -> None:
        """Test basic error conversion."""
        checker = MypyChecker()
        error = {
            "file": "src/app.py",
            "severity": "error",
            "message": "Name 'x' is not defined",
            "line": 10,
            "column": 5,
            "code": "name-defined",
        }

        issue = checker._error_to_issue(error, Path("/project"))

        assert issue is not None
        assert issue.source_tool == "mypy"
        assert issue.severity == Severity.HIGH
        assert issue.rule_id == "name-defined"
        assert issue.line_start == 10
        assert issue.column_start == 5
        assert issue.file_path == Path("/project/src/app.py")

    def test_error_with_absolute_path(self) -> None:
        """Test error with absolute file path."""
        checker = MypyChecker()
        error = {
            "file": "/abs/path/file.py",
            "severity": "error",
            "message": "msg",
            "line": 1,
            "column": 1,
            "code": "misc",
        }

        issue = checker._error_to_issue(error, Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/abs/path/file.py")

    def test_error_without_code(self) -> None:
        """Test error without code field."""
        checker = MypyChecker()
        error = {
            "file": "file.py",
            "severity": "error",
            "message": "Parse error",
            "line": 1,
            "column": 1,
        }

        issue = checker._error_to_issue(error, Path("/project"))
        assert issue is not None
        assert issue.rule_id == "unknown"
        assert issue.title == "Parse error"

    def test_error_with_none_line(self) -> None:
        """Test error with None line number."""
        checker = MypyChecker()
        error = {
            "file": "file.py",
            "severity": "error",
            "message": "msg",
            "line": None,
            "column": None,
            "code": "misc",
        }

        issue = checker._error_to_issue(error, Path("/project"))
        assert issue is not None
        assert issue.line_start is None

    def test_error_unknown_severity(self) -> None:
        """Test error with unknown severity defaults to MEDIUM."""
        checker = MypyChecker()
        error = {
            "file": "file.py",
            "severity": "unknown",
            "message": "msg",
            "line": 1,
            "column": 1,
            "code": "misc",
        }

        issue = checker._error_to_issue(error, Path("/project"))
        assert issue is not None
        assert issue.severity == Severity.MEDIUM


class TestMypyIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        checker = MypyChecker()
        id1 = checker._generate_issue_id("misc", "file.py", 10, 5, "msg")
        id2 = checker._generate_issue_id("misc", "file.py", 10, 5, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        checker = MypyChecker()
        id1 = checker._generate_issue_id("misc", "file.py", 10, 5, "msg")
        id2 = checker._generate_issue_id("attr-defined", "file.py", 10, 5, "msg")
        assert id1 != id2

    def test_id_format_with_code(self) -> None:
        """Test ID format includes code."""
        checker = MypyChecker()
        issue_id = checker._generate_issue_id("assignment", "f.py", 1, 1, "msg")
        assert issue_id.startswith("mypy-assignment-")

    def test_id_format_without_code(self) -> None:
        """Test ID format without code."""
        checker = MypyChecker()
        issue_id = checker._generate_issue_id("", "f.py", 1, 1, "msg")
        assert issue_id.startswith("mypy-")
        assert "mypy--" not in issue_id

    def test_id_handles_none_values(self) -> None:
        """Test ID handles None line/column."""
        checker = MypyChecker()
        issue_id = checker._generate_issue_id("misc", "f.py", None, None, "msg")
        assert issue_id.startswith("mypy-misc-")
