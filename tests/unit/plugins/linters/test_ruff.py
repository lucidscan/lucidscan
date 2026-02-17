"""Unit tests for Ruff linter plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.ruff import (
    RuffLinter,
    SEVERITY_MAP,
    PYTHON_EXTENSIONS,
)


def make_completed_process(returncode: int, stdout: str, stderr: str = "") -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestRuffLinterProperties:
    """Tests for RuffLinter basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        linter = RuffLinter()
        assert linter.name == "ruff"

    def test_languages(self) -> None:
        """Test supported languages."""
        linter = RuffLinter()
        assert linter.languages == ["python"]

    def test_domain(self) -> None:
        """Test domain is LINTING."""
        linter = RuffLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        """Test supports_fix returns True."""
        linter = RuffLinter()
        assert linter.supports_fix is True

    def test_get_version(self) -> None:
        """Test get_version returns configured version."""
        linter = RuffLinter(version="0.5.0")
        assert linter.get_version() == "0.5.0"

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = RuffLinter(project_root=Path(tmpdir))
            assert linter.name == "ruff"


class TestRuffSeverityMapping:
    """Tests for Ruff severity mapping."""

    def test_error_code_medium(self) -> None:
        """Test E codes map to MEDIUM."""
        assert SEVERITY_MAP["E"] == Severity.MEDIUM

    def test_warning_code_low(self) -> None:
        """Test W codes map to LOW."""
        assert SEVERITY_MAP["W"] == Severity.LOW

    def test_security_code_high(self) -> None:
        """Test S (bandit) codes map to HIGH."""
        assert SEVERITY_MAP["S"] == Severity.HIGH

    def test_debugger_code_high(self) -> None:
        """Test T10 (debugger) codes map to HIGH."""
        assert SEVERITY_MAP["T10"] == Severity.HIGH

    def test_isort_code_low(self) -> None:
        """Test I (isort) codes map to LOW."""
        assert SEVERITY_MAP["I"] == Severity.LOW


class TestRuffGetSeverity:
    """Tests for _get_severity method."""

    def test_extracts_single_letter_prefix(self) -> None:
        """Test extracting single letter prefix from code."""
        linter = RuffLinter()
        assert linter._get_severity("E501") == Severity.MEDIUM
        assert linter._get_severity("F401") == Severity.MEDIUM
        assert linter._get_severity("W292") == Severity.LOW

    def test_extracts_multi_letter_prefix(self) -> None:
        """Test extracting multi-letter prefix from code."""
        linter = RuffLinter()
        assert linter._get_severity("UP001") == Severity.LOW
        assert linter._get_severity("SIM101") == Severity.LOW

    def test_unknown_code_defaults_to_medium(self) -> None:
        """Test unknown codes default to MEDIUM."""
        linter = RuffLinter()
        assert linter._get_severity("UNKNOWN001") == Severity.MEDIUM

    def test_security_code_high(self) -> None:
        """Test security codes are HIGH."""
        linter = RuffLinter()
        assert linter._get_severity("S101") == Severity.HIGH


class TestRuffPythonExtensions:
    """Tests for PYTHON_EXTENSIONS constant."""

    def test_includes_py(self) -> None:
        """Test .py is included."""
        assert ".py" in PYTHON_EXTENSIONS

    def test_includes_pyi(self) -> None:
        """Test .pyi is included."""
        assert ".pyi" in PYTHON_EXTENSIONS

    def test_includes_pyw(self) -> None:
        """Test .pyw is included."""
        assert ".pyw" in PYTHON_EXTENSIONS


class TestRuffFilterPaths:
    """Tests for _filter_paths method."""

    def test_filter_python_files(self) -> None:
        """Test that Python files are included."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "test.py"
            py_file.touch()

            result = linter._filter_paths([py_file], Path(tmpdir))
            assert len(result) == 1

    def test_filter_excludes_non_python(self) -> None:
        """Test that non-Python files are excluded."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            js_file = Path(tmpdir) / "test.js"
            js_file.touch()

            result = linter._filter_paths([js_file], Path(tmpdir))
            assert len(result) == 0

    def test_filter_includes_directories(self) -> None:
        """Test that directories are passed through."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()

            result = linter._filter_paths([src_dir], Path(tmpdir))
            assert len(result) == 1

    def test_filter_mixed_files(self) -> None:
        """Test filtering with mixed file types."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "app.py"
            js_file = Path(tmpdir) / "app.js"
            pyi_file = Path(tmpdir) / "types.pyi"
            py_file.touch()
            js_file.touch()
            pyi_file.touch()

            result = linter._filter_paths([py_file, js_file, pyi_file], Path(tmpdir))
            assert len(result) == 2  # py and pyi


class TestRuffSimplifyExcludePattern:
    """Tests for _simplify_exclude_pattern static method."""

    def test_strip_double_star_prefix_and_suffix(self) -> None:
        """Test **/.venv/** -> .venv."""
        result = RuffLinter._simplify_exclude_pattern("**/.venv/**")
        assert result == ".venv"

    def test_strip_double_star_prefix(self) -> None:
        """Test **/foo -> foo."""
        result = RuffLinter._simplify_exclude_pattern("**/foo")
        assert result == "foo"

    def test_strip_double_star_suffix(self) -> None:
        """Test foo/** -> foo."""
        result = RuffLinter._simplify_exclude_pattern("foo/**")
        assert result == "foo"

    def test_no_double_stars(self) -> None:
        """Test pattern without ** is kept as-is."""
        result = RuffLinter._simplify_exclude_pattern(".git")
        assert result == ".git"

    def test_backslash_normalization(self) -> None:
        """Test backslashes are normalized to forward slashes."""
        result = RuffLinter._simplify_exclude_pattern("**\\.venv\\**")
        assert result == ".venv"

    def test_complex_pattern(self) -> None:
        """Test complex pattern simplification."""
        result = RuffLinter._simplify_exclude_pattern("**/node_modules/**")
        assert result == "node_modules"


class TestRuffGetExcludePatterns:
    """Tests for _get_ruff_exclude_patterns method."""

    def test_simplifies_patterns(self) -> None:
        """Test that patterns are simplified for Ruff."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            with patch.object(context, "get_exclude_patterns", return_value=["**/.venv/**", "**/node_modules/**"]):
                patterns = linter._get_ruff_exclude_patterns(context)
                assert ".venv" in patterns
                assert "node_modules" in patterns

    def test_deduplicates_patterns(self) -> None:
        """Test that duplicate patterns are removed."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            with patch.object(context, "get_exclude_patterns", return_value=["**/.venv/**", ".venv"]):
                patterns = linter._get_ruff_exclude_patterns(context)
                assert patterns.count(".venv") == 1


class TestRuffLint:
    """Tests for lint method."""

    def test_lint_success(self) -> None:
        """Test successful linting."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            ruff_output = json.dumps([
                {
                    "code": "F401",
                    "message": "'os' imported but unused",
                    "filename": "src/app.py",
                    "location": {"row": 1, "column": 1},
                    "end_location": {"row": 1, "column": 10},
                    "fix": {"applicability": "safe", "edits": [], "message": "Remove import"},
                    "url": "https://docs.astral.sh/ruff/rules/unused-import",
                }
            ])

            mock_result = make_completed_process(1, ruff_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                with patch("lucidshark.plugins.linters.ruff.run_with_streaming", return_value=mock_result):
                    issues = linter.lint(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "ruff"
                    assert issues[0].domain == ToolDomain.LINTING
                    assert issues[0].rule_id == "F401"
                    assert issues[0].severity == Severity.MEDIUM
                    assert issues[0].fixable is True
                    assert issues[0].line_start == 1

    def test_lint_timeout(self) -> None:
        """Test lint handles timeout."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                with patch(
                    "lucidshark.plugins.linters.ruff.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("ruff", 120),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_subprocess_error(self) -> None:
        """Test lint handles subprocess errors."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                with patch(
                    "lucidshark.plugins.linters.ruff.run_with_streaming",
                    side_effect=OSError("command failed"),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_no_python_files(self) -> None:
        """Test lint returns empty when no Python files."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            js_file = tmpdir_path / "test.js"
            js_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[js_file],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_uses_dot_when_no_paths(self) -> None:
        """Test lint uses '.' when no paths specified."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, "[]")

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                with patch("lucidshark.plugins.linters.ruff.run_with_streaming", return_value=mock_result) as mock_run:
                    linter.lint(context)
                    cmd = mock_run.call_args.kwargs.get("cmd") or mock_run.call_args[1].get("cmd")
                    assert "." in cmd


class TestRuffFix:
    """Tests for fix method."""

    def test_fix_success(self) -> None:
        """Test successful fix operation."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            # Pre-fix: 2 issues
            pre_output = json.dumps([
                {"code": "F401", "message": "unused import", "filename": "a.py",
                 "location": {"row": 1, "column": 1}},
                {"code": "F401", "message": "unused import 2", "filename": "a.py",
                 "location": {"row": 2, "column": 1}},
            ])
            # Post-fix: 1 issue remaining
            post_output = json.dumps([
                {"code": "F401", "message": "unused import 2", "filename": "a.py",
                 "location": {"row": 2, "column": 1}},
            ])

            pre_result = make_completed_process(1, pre_output)
            post_result = make_completed_process(1, post_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                with patch("lucidshark.plugins.linters.ruff.run_with_streaming") as mock_run:
                    mock_run.side_effect = [pre_result, post_result]
                    result = linter.fix(context)
                    assert result.issues_fixed == 1
                    assert result.issues_remaining == 1

    def test_fix_timeout(self) -> None:
        """Test fix handles timeout."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            pre_output = json.dumps([
                {"code": "F401", "message": "msg", "filename": "a.py",
                 "location": {"row": 1, "column": 1}},
            ])
            pre_result = make_completed_process(1, pre_output)

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                with patch("lucidshark.plugins.linters.ruff.run_with_streaming") as mock_run:
                    mock_run.side_effect = [
                        pre_result,
                        subprocess.TimeoutExpired("ruff", 120),
                    ]
                    result = linter.fix(context)
                    assert result.issues_fixed == 0

    def test_fix_no_python_files(self) -> None:
        """Test fix returns empty when no Python files."""
        linter = RuffLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            js_file = tmpdir_path / "test.js"
            js_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[js_file],
                enabled_domains=[],
            )

            with patch.object(linter, "ensure_binary", return_value=Path("/usr/bin/ruff")):
                result = linter.fix(context)
                assert result.issues_fixed == 0
                assert result.files_modified == 0


class TestRuffParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        linter = RuffLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        linter = RuffLinter()
        issues = linter._parse_output("not json", Path("/project"))
        assert issues == []

    def test_parse_non_list_json(self) -> None:
        """Test parsing non-list JSON output."""
        linter = RuffLinter()
        issues = linter._parse_output('{"key": "value"}', Path("/project"))
        assert issues == []

    def test_parse_empty_list(self) -> None:
        """Test parsing empty JSON list."""
        linter = RuffLinter()
        issues = linter._parse_output("[]", Path("/project"))
        assert issues == []

    def test_parse_single_violation(self) -> None:
        """Test parsing single violation."""
        linter = RuffLinter()
        output = json.dumps([{
            "code": "E501",
            "message": "Line too long",
            "filename": "test.py",
            "location": {"row": 5, "column": 80},
            "end_location": {"row": 5, "column": 120},
        }])

        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "E501"
        assert issues[0].line_start == 5

    def test_parse_multiple_violations(self) -> None:
        """Test parsing multiple violations."""
        linter = RuffLinter()
        output = json.dumps([
            {"code": "F401", "message": "unused", "filename": "a.py",
             "location": {"row": 1, "column": 1}},
            {"code": "E501", "message": "too long", "filename": "b.py",
             "location": {"row": 10, "column": 80}},
        ])

        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 2

    def test_parse_skips_non_dict_violations(self) -> None:
        """Test that non-dict violations are skipped."""
        linter = RuffLinter()
        output = json.dumps([
            "not a dict",
            {"code": "F401", "message": "msg", "filename": "a.py",
             "location": {"row": 1, "column": 1}},
        ])

        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1


class TestRuffViolationToIssue:
    """Tests for _violation_to_issue method."""

    def test_converts_violation_correctly(self) -> None:
        """Test basic violation conversion."""
        linter = RuffLinter()
        violation = {
            "code": "F401",
            "message": "'os' imported but unused",
            "filename": "src/app.py",
            "location": {"row": 1, "column": 1},
            "end_location": {"row": 1, "column": 10},
            "source": "import os",
            "fix": {"applicability": "safe", "edits": [{"content": ""}], "message": "Remove import"},
            "url": "https://docs.astral.sh/ruff/rules/unused-import",
            "noqa_row": 1,
        }

        issue = linter._violation_to_issue(violation, Path("/project"))

        assert issue is not None
        assert issue.source_tool == "ruff"
        assert issue.rule_id == "F401"
        assert issue.severity == Severity.MEDIUM
        assert issue.file_path == Path("/project/src/app.py")
        assert issue.line_start == 1
        assert issue.column_start == 1
        assert issue.code_snippet == "import os"
        assert issue.fixable is True
        assert issue.suggested_fix == "Remove import"
        assert issue.metadata["noqa_row"] == 1

    def test_violation_with_absolute_path(self) -> None:
        """Test violation with absolute file path."""
        linter = RuffLinter()
        violation = {
            "code": "E501",
            "message": "Line too long",
            "filename": "/abs/path/file.py",
            "location": {"row": 1, "column": 80},
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/abs/path/file.py")

    def test_violation_without_fix(self) -> None:
        """Test violation without fix info."""
        linter = RuffLinter()
        violation = {
            "code": "E501",
            "message": "Line too long",
            "filename": "file.py",
            "location": {"row": 1, "column": 80},
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        assert issue.fixable is False

    def test_violation_without_source(self) -> None:
        """Test violation without source line."""
        linter = RuffLinter()
        violation = {
            "code": "F401",
            "message": "unused",
            "filename": "file.py",
            "location": {"row": 1, "column": 1},
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        assert issue.code_snippet is None


class TestRuffIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        linter = RuffLinter()
        id1 = linter._generate_issue_id("F401", "file.py", {"row": 1, "column": 1}, "msg")
        id2 = linter._generate_issue_id("F401", "file.py", {"row": 1, "column": 1}, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        linter = RuffLinter()
        id1 = linter._generate_issue_id("F401", "a.py", {"row": 1, "column": 1}, "msg")
        id2 = linter._generate_issue_id("E501", "a.py", {"row": 1, "column": 1}, "msg")
        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID format starts with ruff-CODE-."""
        linter = RuffLinter()
        issue_id = linter._generate_issue_id("F401", "f.py", {"row": 1, "column": 1}, "msg")
        assert issue_id.startswith("ruff-F401-")
