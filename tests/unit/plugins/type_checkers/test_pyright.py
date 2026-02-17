"""Unit tests for pyright type checker plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.type_checkers.pyright import (
    PyrightChecker,
    SEVERITY_MAP,
)


def make_completed_process(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestPyrightCheckerProperties:
    """Tests for PyrightChecker basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        checker = PyrightChecker()
        assert checker.name == "pyright"

    def test_languages(self) -> None:
        """Test supported languages."""
        checker = PyrightChecker()
        assert checker.languages == ["python"]

    def test_domain(self) -> None:
        """Test domain is TYPE_CHECKING."""
        checker = PyrightChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        """Test strict mode is supported."""
        checker = PyrightChecker()
        assert checker.supports_strict_mode is True

    def test_get_version(self) -> None:
        """Test get_version returns configured version."""
        checker = PyrightChecker(version="1.2.3")
        assert checker.get_version() == "1.2.3"

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = PyrightChecker(project_root=Path(tmpdir))
            assert checker._project_root == Path(tmpdir)

    def test_init_without_project_root(self) -> None:
        """Test initialization without project root."""
        checker = PyrightChecker()
        assert checker._project_root is None


class TestPyrightSeverityMapping:
    """Tests for pyright severity mapping."""

    def test_error_maps_to_high(self) -> None:
        """Test error severity maps to HIGH."""
        assert SEVERITY_MAP["error"] == Severity.HIGH

    def test_warning_maps_to_medium(self) -> None:
        """Test warning severity maps to MEDIUM."""
        assert SEVERITY_MAP["warning"] == Severity.MEDIUM

    def test_information_maps_to_low(self) -> None:
        """Test information severity maps to LOW."""
        assert SEVERITY_MAP["information"] == Severity.LOW


class TestPyrightEnsureBinary:
    """Tests for ensure_binary method."""

    def test_finds_venv_pyright(self) -> None:
        """Test finding pyright in project .venv."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            venv_pyright = project_root / ".venv" / "bin" / "pyright"
            venv_pyright.parent.mkdir(parents=True)
            venv_pyright.touch()

            checker = PyrightChecker(project_root=project_root)
            binary = checker.ensure_binary()
            assert binary == venv_pyright

    def test_finds_node_modules_pyright(self) -> None:
        """Test finding pyright in node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            checker = PyrightChecker(project_root=project_root)

            with patch("lucidshark.plugins.type_checkers.pyright.resolve_node_bin", return_value=Path(tmpdir) / "node_modules/.bin/pyright"):
                binary = checker.ensure_binary()
                assert binary == Path(tmpdir) / "node_modules/.bin/pyright"

    def test_finds_system_pyright(self) -> None:
        """Test finding pyright in system PATH."""
        checker = PyrightChecker()

        with patch("shutil.which", return_value="/usr/local/bin/pyright"):
            binary = checker.ensure_binary()
            assert binary == Path("/usr/local/bin/pyright")

    def test_download_when_not_found(self) -> None:
        """Test _download_binary is called when pyright not found."""
        checker = PyrightChecker()

        with patch("shutil.which", return_value=None):
            with patch("lucidshark.plugins.type_checkers.pyright.resolve_node_bin", return_value=None):
                with patch.object(checker, "_download_binary", return_value=Path("/downloaded/pyright")) as mock_dl:
                    binary = checker.ensure_binary()
                    mock_dl.assert_called_once()
                    assert binary == Path("/downloaded/pyright")


class TestPyrightDownloadBinary:
    """Tests for _download_binary method."""

    def test_raises_when_pyright_not_available(self) -> None:
        """Test raises FileNotFoundError when pyright cannot be downloaded."""
        checker = PyrightChecker()

        with patch("shutil.which", return_value=None):
            with patch.object(checker, "_paths") as mock_paths:
                bin_dir = Path("/tmp/test_bin")
                mock_paths.plugin_bin_dir.return_value = bin_dir
                with patch("pathlib.Path.exists", return_value=False):
                    with patch("pathlib.Path.mkdir"):
                        with pytest.raises(FileNotFoundError, match="pyright is not installed"):
                            checker._download_binary()

    def test_returns_pip_pyright_if_available(self) -> None:
        """Test returns pip-installed pyright if available during download."""
        checker = PyrightChecker()

        with patch.object(checker, "_paths") as mock_paths:
            bin_dir = Path("/tmp/test_bin")
            mock_paths.plugin_bin_dir.return_value = bin_dir

            with patch("pathlib.Path.exists", return_value=False):
                with patch("pathlib.Path.mkdir"):
                    with patch("shutil.which", return_value="/usr/bin/pyright"):
                        result = checker._download_binary()
                        assert result == Path("/usr/bin/pyright")


class TestPyrightCheck:
    """Tests for check method."""

    def test_check_binary_not_found(self) -> None:
        """Test check returns empty when binary not found."""
        checker = PyrightChecker()

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
        checker = PyrightChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            pyright_output = json.dumps({
                "generalDiagnostics": [
                    {
                        "file": "src/app.py",
                        "severity": "error",
                        "message": "Cannot assign type \"str\" to type \"int\"",
                        "rule": "reportAssignmentType",
                        "range": {
                            "start": {"line": 9, "character": 0},
                            "end": {"line": 9, "character": 10},
                        },
                    }
                ]
            })

            mock_result = make_completed_process(1, pyright_output)

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/pyright")):
                with patch("subprocess.run", return_value=mock_result):
                    issues = checker.check(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "pyright"
                    assert issues[0].domain == ToolDomain.TYPE_CHECKING
                    assert issues[0].severity == Severity.HIGH
                    assert issues[0].rule_id == "reportAssignmentType"
                    assert issues[0].line_start == 10  # 0-based to 1-based

    def test_check_timeout(self) -> None:
        """Test check handles timeout."""
        checker = PyrightChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/pyright")):
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pyright", 180)):
                    issues = checker.check(context)
                    assert issues == []

    def test_check_subprocess_error(self) -> None:
        """Test check handles subprocess errors."""
        checker = PyrightChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/pyright")):
                with patch("subprocess.run", side_effect=OSError("command failed")):
                    issues = checker.check(context)
                    assert issues == []

    def test_check_uses_dot_when_no_paths(self) -> None:
        """Test check uses '.' when no paths specified."""
        checker = PyrightChecker()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, '{"generalDiagnostics": []}')

            with patch.object(checker, "ensure_binary", return_value=Path("/usr/bin/pyright")):
                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    checker.check(context)
                    cmd = mock_run.call_args[0][0]
                    assert "." in cmd


class TestPyrightParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        checker = PyrightChecker()
        issues = checker._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_whitespace_output(self) -> None:
        """Test parsing whitespace-only output."""
        checker = PyrightChecker()
        issues = checker._parse_output("   \n  ", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        checker = PyrightChecker()
        issues = checker._parse_output("not json", Path("/project"))
        assert issues == []

    def test_parse_no_diagnostics(self) -> None:
        """Test parsing output with no diagnostics."""
        checker = PyrightChecker()
        output = json.dumps({"generalDiagnostics": []})
        issues = checker._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_multiple_diagnostics(self) -> None:
        """Test parsing output with multiple diagnostics."""
        checker = PyrightChecker()
        output = json.dumps({
            "generalDiagnostics": [
                {
                    "file": "a.py",
                    "severity": "error",
                    "message": "Error 1",
                    "rule": "rule1",
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
                },
                {
                    "file": "b.py",
                    "severity": "warning",
                    "message": "Warning 1",
                    "rule": "rule2",
                    "range": {"start": {"line": 4, "character": 2}, "end": {"line": 4, "character": 10}},
                },
            ]
        })

        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 2
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.MEDIUM


class TestPyrightDiagnosticToIssue:
    """Tests for _diagnostic_to_issue method."""

    def test_converts_diagnostic_correctly(self) -> None:
        """Test basic diagnostic conversion."""
        checker = PyrightChecker()
        diagnostic = {
            "file": "src/app.py",
            "severity": "error",
            "message": "Type mismatch",
            "rule": "reportGeneralClassIssues",
            "range": {
                "start": {"line": 5, "character": 3},
                "end": {"line": 5, "character": 15},
            },
        }

        issue = checker._diagnostic_to_issue(diagnostic, Path("/project"))

        assert issue is not None
        assert issue.source_tool == "pyright"
        assert issue.severity == Severity.HIGH
        assert issue.rule_id == "reportGeneralClassIssues"
        assert issue.line_start == 6  # 0-based to 1-based
        assert issue.line_end == 6
        assert issue.column_start == 4  # 0-based to 1-based
        assert issue.file_path == Path("/project/src/app.py")

    def test_diagnostic_with_absolute_path(self) -> None:
        """Test diagnostic with absolute file path."""
        checker = PyrightChecker()
        diagnostic = {
            "file": "/absolute/path/file.py",
            "severity": "warning",
            "message": "Warning",
            "rule": "testRule",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
        }

        issue = checker._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/absolute/path/file.py")

    def test_diagnostic_without_rule(self) -> None:
        """Test diagnostic without rule field."""
        checker = PyrightChecker()
        diagnostic = {
            "file": "file.py",
            "severity": "error",
            "message": "Some error",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
        }

        issue = checker._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.rule_id == "unknown"
        assert issue.title == "Some error"

    def test_diagnostic_unknown_severity(self) -> None:
        """Test diagnostic with unknown severity defaults to MEDIUM."""
        checker = PyrightChecker()
        diagnostic = {
            "file": "file.py",
            "severity": "unknown_level",
            "message": "message",
            "rule": "rule",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
        }

        issue = checker._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.severity == Severity.MEDIUM

    def test_diagnostic_with_missing_range(self) -> None:
        """Test diagnostic handles missing range gracefully."""
        checker = PyrightChecker()
        diagnostic = {
            "file": "file.py",
            "severity": "error",
            "message": "error message",
            "rule": "rule1",
        }

        issue = checker._diagnostic_to_issue(diagnostic, Path("/project"))
        assert issue is not None
        assert issue.line_start == 1  # Default from empty dict


class TestPyrightIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        checker = PyrightChecker()
        id1 = checker._generate_issue_id("rule1", "file.py", 10, 5, "msg")
        id2 = checker._generate_issue_id("rule1", "file.py", 10, 5, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        checker = PyrightChecker()
        id1 = checker._generate_issue_id("rule1", "file.py", 10, 5, "msg")
        id2 = checker._generate_issue_id("rule2", "file.py", 10, 5, "msg")
        assert id1 != id2

    def test_id_format_with_rule(self) -> None:
        """Test ID format includes rule name."""
        checker = PyrightChecker()
        issue_id = checker._generate_issue_id("reportError", "f.py", 1, 1, "msg")
        assert issue_id.startswith("pyright-reportError-")

    def test_id_format_without_rule(self) -> None:
        """Test ID format without rule name."""
        checker = PyrightChecker()
        issue_id = checker._generate_issue_id("", "f.py", 1, 1, "msg")
        assert issue_id.startswith("pyright-")
        assert "pyright--" not in issue_id
