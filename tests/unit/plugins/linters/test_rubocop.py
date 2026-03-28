"""Unit tests for RuboCop linter plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.rubocop import (
    RubocopLinter,
    SEVERITY_MAP,
    DEPARTMENT_SEVERITY,
    RUBY_EXTENSIONS,
    _find_rubocop,
)


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestRubocopLinterProperties:
    """Tests for RubocopLinter basic properties."""

    def test_name(self) -> None:
        linter = RubocopLinter()
        assert linter.name == "rubocop"

    def test_languages(self) -> None:
        linter = RubocopLinter()
        assert linter.languages == ["ruby"]

    def test_domain(self) -> None:
        linter = RubocopLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        linter = RubocopLinter()
        assert linter.supports_fix is True

    def test_init_with_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = RubocopLinter(project_root=Path(tmpdir))
            assert linter.name == "rubocop"

    def test_ruby_extensions(self) -> None:
        assert ".rb" in RUBY_EXTENSIONS
        assert ".rake" in RUBY_EXTENSIONS
        assert ".gemspec" in RUBY_EXTENSIONS


class TestRubocopSeverityMapping:
    """Tests for RuboCop severity mapping."""

    def test_convention_maps_to_low(self) -> None:
        assert SEVERITY_MAP["convention"] == Severity.LOW

    def test_refactor_maps_to_low(self) -> None:
        assert SEVERITY_MAP["refactor"] == Severity.LOW

    def test_warning_maps_to_medium(self) -> None:
        assert SEVERITY_MAP["warning"] == Severity.MEDIUM

    def test_error_maps_to_high(self) -> None:
        assert SEVERITY_MAP["error"] == Severity.HIGH

    def test_fatal_maps_to_high(self) -> None:
        assert SEVERITY_MAP["fatal"] == Severity.HIGH


class TestRubocopDepartmentSeverity:
    """Tests for department-based severity."""

    def test_security_department_high(self) -> None:
        assert DEPARTMENT_SEVERITY["Security"] == Severity.HIGH

    def test_lint_department_medium(self) -> None:
        assert DEPARTMENT_SEVERITY["Lint"] == Severity.MEDIUM

    def test_layout_department_low(self) -> None:
        assert DEPARTMENT_SEVERITY["Layout"] == Severity.LOW

    def test_style_department_low(self) -> None:
        assert DEPARTMENT_SEVERITY["Style"] == Severity.LOW


class TestRubocopGetSeverity:
    """Tests for _get_severity method."""

    def test_security_cop_uses_department(self) -> None:
        linter = RubocopLinter()
        severity = linter._get_severity("warning", "Security/Open")
        assert severity == Severity.HIGH

    def test_error_severity_overrides_low_department(self) -> None:
        linter = RubocopLinter()
        severity = linter._get_severity("error", "Style/SomeRule")
        assert severity == Severity.HIGH

    def test_convention_with_lint_department(self) -> None:
        linter = RubocopLinter()
        severity = linter._get_severity("convention", "Lint/UselessAssignment")
        assert severity == Severity.MEDIUM

    def test_unknown_department_uses_base(self) -> None:
        linter = RubocopLinter()
        severity = linter._get_severity("warning", "CustomDept/SomeRule")
        assert severity == Severity.MEDIUM


class TestFindRubocop:
    """Tests for _find_rubocop binary discovery."""

    def test_find_in_binstubs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            bin_dir = project_root / "bin"
            bin_dir.mkdir()
            rubocop_bin = bin_dir / "rubocop"
            rubocop_bin.touch()
            rubocop_bin.chmod(0o755)

            binary = _find_rubocop(project_root)
            assert binary == rubocop_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/local/bin/rubocop"
        binary = _find_rubocop()
        assert binary == Path("/usr/local/bin/rubocop")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        with pytest.raises(FileNotFoundError) as exc:
            _find_rubocop()
        assert "RuboCop is not installed" in str(exc.value)


class TestRubocopParseOutput:
    """Tests for RuboCop JSON output parsing."""

    def test_parse_empty_output(self) -> None:
        linter = RubocopLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_no_offenses(self) -> None:
        linter = RubocopLinter()
        output = json.dumps({
            "files": [
                {"path": "lib/example.rb", "offenses": []}
            ],
            "summary": {"offense_count": 0}
        })
        issues = linter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_with_offenses(self) -> None:
        linter = RubocopLinter()
        output = json.dumps({
            "files": [
                {
                    "path": "lib/example.rb",
                    "offenses": [
                        {
                            "severity": "convention",
                            "message": "Line is too long. [120/80]",
                            "cop_name": "Layout/LineLength",
                            "corrected": False,
                            "correctable": True,
                            "location": {
                                "start_line": 10,
                                "start_column": 1,
                                "last_line": 10,
                                "last_column": 120,
                                "line": 10,
                                "column": 1,
                            },
                        }
                    ],
                }
            ],
            "summary": {"offense_count": 1}
        })
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        issue = issues[0]
        assert issue.rule_id == "Layout/LineLength"
        assert issue.source_tool == "rubocop"
        assert issue.domain == ToolDomain.LINTING
        assert issue.severity == Severity.LOW
        assert issue.fixable is True
        assert issue.line_start == 10

    def test_parse_multiple_files_and_offenses(self) -> None:
        linter = RubocopLinter()
        output = json.dumps({
            "files": [
                {
                    "path": "lib/a.rb",
                    "offenses": [
                        {
                            "severity": "warning",
                            "message": "Unused variable",
                            "cop_name": "Lint/UselessAssignment",
                            "corrected": False,
                            "correctable": False,
                            "location": {"line": 5, "column": 1},
                        }
                    ],
                },
                {
                    "path": "lib/b.rb",
                    "offenses": [
                        {
                            "severity": "error",
                            "message": "Syntax error",
                            "cop_name": "Lint/Syntax",
                            "corrected": False,
                            "correctable": False,
                            "location": {"line": 1, "column": 1},
                        }
                    ],
                },
            ],
            "summary": {"offense_count": 2}
        })
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 2

    def test_parse_invalid_json(self) -> None:
        linter = RubocopLinter()
        issues = linter._parse_output("not json", Path("/project"))
        assert issues == []


class TestRubocopIssueId:
    """Tests for deterministic issue ID generation."""

    def test_id_starts_with_rubocop(self) -> None:
        linter = RubocopLinter()
        issue_id = linter._generate_issue_id(
            "Style/StringLiterals", "test.rb", {"line": 1, "column": 1}, "msg"
        )
        assert issue_id.startswith("rubocop-")

    def test_id_is_deterministic(self) -> None:
        linter = RubocopLinter()
        id1 = linter._generate_issue_id(
            "Style/StringLiterals", "test.rb", {"line": 1, "column": 1}, "msg"
        )
        id2 = linter._generate_issue_id(
            "Style/StringLiterals", "test.rb", {"line": 1, "column": 1}, "msg"
        )
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        linter = RubocopLinter()
        id1 = linter._generate_issue_id(
            "Style/A", "test.rb", {"line": 1, "column": 1}, "msg"
        )
        id2 = linter._generate_issue_id(
            "Style/B", "test.rb", {"line": 1, "column": 1}, "msg"
        )
        assert id1 != id2


class TestRubocopLint:
    """Tests for lint() method."""

    def test_lint_skips_when_not_installed(self) -> None:
        linter = RubocopLinter()
        context = ScanContext(
            project_root=Path("/project"),
            paths=[],
            enabled_domains=[ToolDomain.LINTING],
        )
        with patch.object(linter, "_ensure_binary_safe", return_value=None):
            issues = linter.lint(context)
            assert issues == []
            assert len(context.tool_skips) == 1

    def test_lint_skips_when_no_ruby_files(self) -> None:
        linter = RubocopLinter()
        context = ScanContext(
            project_root=Path("/project"),
            paths=[Path("/project/readme.md")],
            enabled_domains=[ToolDomain.LINTING],
        )
        with patch.object(
            linter, "_ensure_binary_safe", return_value=Path("/usr/bin/rubocop")
        ):
            issues = linter.lint(context)
            assert issues == []

    def test_lint_runs_rubocop(self) -> None:
        output = json.dumps({
            "files": [
                {
                    "path": "test.rb",
                    "offenses": [
                        {
                            "severity": "convention",
                            "message": "test offense",
                            "cop_name": "Style/Test",
                            "corrected": False,
                            "correctable": True,
                            "location": {"line": 1, "column": 1},
                        }
                    ],
                }
            ],
            "summary": {"offense_count": 1}
        })
        linter = RubocopLinter()
        context = ScanContext(
            project_root=Path("/project"),
            paths=[],
            enabled_domains=[ToolDomain.LINTING],
        )
        with (
            patch.object(
                linter, "_ensure_binary_safe", return_value=Path("/usr/bin/rubocop")
            ),
            patch.object(linter, "_run_linter_command", return_value=output),
        ):
            issues = linter.lint(context)
            assert len(issues) == 1
            assert issues[0].rule_id == "Style/Test"


class TestRubocopPathFiltering:
    """Tests for path filtering logic."""

    def test_filter_ruby_files(self) -> None:
        linter = RubocopLinter()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "app.rb").touch()
            (root / "task.rake").touch()
            (root / "readme.md").touch()
            (root / "lib").mkdir()

            paths = [root / "app.rb", root / "task.rake", root / "readme.md", root / "lib"]
            filtered = linter._filter_paths(paths)
            assert str(root / "app.rb") in filtered
            assert str(root / "task.rake") in filtered
            assert str(root / "readme.md") not in filtered
            assert str(root / "lib") in filtered  # directories pass through
