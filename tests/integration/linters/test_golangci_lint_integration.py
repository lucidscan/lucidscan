"""Integration tests for golangci-lint linter plugin.

These tests require golangci-lint and Go to be installed.

Run with: pytest tests/integration/linters/test_golangci_lint_integration.py -v
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.base import FixResult
from lucidshark.plugins.linters.golangci_lint import (
    LINTER_SEVERITY,
    GoLangCILintLinter,
)
from tests.integration.conftest import go_available, golangci_lint_available


def _create_temp_go_project(
    tmp_path: Path, module_name: str = "example.com/testproject"
) -> Path:
    """Create a minimal Go project in tmp_path."""
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(f"module {module_name}\n\ngo 1.21\n")
    return tmp_path


class TestGoLangCILintAvailability:
    """Tests for golangci-lint availability."""

    @golangci_lint_available
    def test_ensure_binary_finds_golangci_lint(
        self, golangci_lint_linter: GoLangCILintLinter
    ) -> None:
        """Test that ensure_binary finds golangci-lint."""
        binary_path = golangci_lint_linter.ensure_binary()
        assert binary_path.exists()
        assert "golangci-lint" in binary_path.name

    @golangci_lint_available
    def test_get_version(self, golangci_lint_linter: GoLangCILintLinter) -> None:
        """Test that get_version returns a version string."""
        version = golangci_lint_linter.get_version()
        assert version != "unknown"

    def test_ensure_binary_raises_when_not_installed(self) -> None:
        """Test that ensure_binary raises FileNotFoundError when not installed."""
        linter = GoLangCILintLinter(project_root=Path("/nonexistent"))
        try:
            binary_path = linter.ensure_binary()
            # If installed globally, verify it exists
            assert binary_path.exists()
        except FileNotFoundError as e:
            assert "golangci-lint" in str(e).lower()


@golangci_lint_available
@go_available
class TestGoLangCILintLinting:
    """Integration tests for golangci-lint linting."""

    def test_lint_clean_project(self, golangci_lint_linter: GoLangCILintLinter) -> None:
        """Test linting a clean Go project returns 0 issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            # Create a clean Go file
            main_go = tmpdir_path / "main.go"
            main_go.write_text(
                'package main\n\nimport "fmt"\n\nfunc main() {\n'
                '\tfmt.Println("hello")\n}\n'
            )

            # Run go mod tidy
            subprocess.run(
                ["go", "mod", "tidy"],
                cwd=tmpdir_path,
                capture_output=True,
                timeout=60,
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = golangci_lint_linter.lint(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_lint_detects_issues(
        self, golangci_lint_linter: GoLangCILintLinter
    ) -> None:
        """Test linting a Go project with known issues finds them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            _create_temp_go_project(tmpdir_path)

            # Create a file with an unused variable
            main_go = tmpdir_path / "main.go"
            main_go.write_text(
                'package main\n\nimport "fmt"\n\nfunc main() {\n'
                "\tx := 42\n"
                '\tfmt.Println("hello")\n}\n'
            )

            subprocess.run(
                ["go", "mod", "tidy"],
                cwd=tmpdir_path,
                capture_output=True,
                timeout=60,
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = golangci_lint_linter.lint(context)

            assert isinstance(issues, list)
            assert len(issues) > 0

            for issue in issues:
                assert issue.source_tool == "golangci-lint"
                assert issue.domain == ToolDomain.LINTING
                assert issue.severity is not None

    def test_lint_skips_without_go_mod(
        self, golangci_lint_linter: GoLangCILintLinter
    ) -> None:
        """Test that linting returns empty when no go.mod is present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Go file but no go.mod
            main_go = tmpdir_path / "main.go"
            main_go.write_text("package main\n\nfunc main() {}\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = golangci_lint_linter.lint(context)

            assert isinstance(issues, list)
            assert len(issues) == 0


class TestGoLangCILintOutputParsing:
    """Tests for golangci-lint output parsing (no binary required)."""

    def test_parse_output_with_issues(self) -> None:
        """Test _parse_output with sample JSON output."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        sample_output = json.dumps(
            {
                "Issues": [
                    {
                        "FromLinter": "unused",
                        "Text": "'x' is unused",
                        "Severity": "warning",
                        "SourceLines": ["    x := 42"],
                        "Pos": {
                            "Filename": "main.go",
                            "Line": 6,
                            "Column": 2,
                        },
                    },
                    {
                        "FromLinter": "errcheck",
                        "Text": "Error return value of `fmt.Println` is not checked",
                        "Severity": "error",
                        "SourceLines": ['    fmt.Println("hello")'],
                        "Pos": {
                            "Filename": "main.go",
                            "Line": 7,
                            "Column": 2,
                        },
                    },
                ]
            }
        )

        issues = linter._parse_output(sample_output, Path("/tmp"))

        assert len(issues) == 2
        assert issues[0].source_tool == "golangci-lint"
        assert issues[0].domain == ToolDomain.LINTING
        assert issues[0].rule_id == "unused"
        assert issues[0].line_start == 6
        assert issues[1].rule_id == "errcheck"
        assert issues[1].line_start == 7

    def test_parse_output_empty(self) -> None:
        """Test _parse_output with empty output."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        issues = linter._parse_output("", Path("/tmp"))

        assert issues == []

    def test_parse_output_no_issues(self) -> None:
        """Test _parse_output when Issues array is empty."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        sample_output = json.dumps({"Issues": []})
        issues = linter._parse_output(sample_output, Path("/tmp"))

        assert issues == []

    def test_parse_output_invalid_json(self) -> None:
        """Test _parse_output with invalid JSON."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        issues = linter._parse_output("not valid json", Path("/tmp"))

        assert issues == []

    def test_severity_mapping_from_linter_name(self) -> None:
        """Test that severity is correctly mapped from linter name."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        # govet should be HIGH severity
        severity = linter._get_severity("govet", "warning")
        assert severity == Severity.HIGH

        # gosimple should be LOW severity
        severity = linter._get_severity("gosimple", "error")
        assert severity == Severity.LOW

        # errcheck should be HIGH severity
        severity = linter._get_severity("errcheck", "")
        assert severity == Severity.HIGH

    def test_severity_mapping_fallback_to_field(self) -> None:
        """Test that severity falls back to the severity field."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        # Unknown linter, falls back to severity field
        severity = linter._get_severity("unknown_linter", "error")
        assert severity == Severity.HIGH

        severity = linter._get_severity("unknown_linter", "warning")
        assert severity == Severity.MEDIUM

    def test_severity_mapping_default(self) -> None:
        """Test that severity defaults to MEDIUM for unknown linters."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        severity = linter._get_severity("unknown_linter", "")
        assert severity == Severity.MEDIUM

    def test_issue_id_is_deterministic(self) -> None:
        """Test that issue IDs are consistent across runs."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        sample_output = json.dumps(
            {
                "Issues": [
                    {
                        "FromLinter": "unused",
                        "Text": "'x' is unused",
                        "Severity": "warning",
                        "SourceLines": ["    x := 42"],
                        "Pos": {
                            "Filename": "main.go",
                            "Line": 6,
                            "Column": 2,
                        },
                    }
                ]
            }
        )

        issues1 = linter._parse_output(sample_output, Path("/tmp"))
        issues2 = linter._parse_output(sample_output, Path("/tmp"))

        assert len(issues1) == 1
        assert len(issues2) == 1
        assert issues1[0].id == issues2[0].id
        assert issues1[0].id.startswith("golangci-lint-")

    def test_parse_output_deduplicates(self) -> None:
        """Test that duplicate issues are deduplicated."""
        linter = GoLangCILintLinter(project_root=Path("/tmp"))

        issue_data = {
            "FromLinter": "unused",
            "Text": "'x' is unused",
            "Severity": "warning",
            "SourceLines": ["    x := 42"],
            "Pos": {
                "Filename": "main.go",
                "Line": 6,
                "Column": 2,
            },
        }

        sample_output = json.dumps({"Issues": [issue_data, issue_data]})
        issues = linter._parse_output(sample_output, Path("/tmp"))

        assert len(issues) == 1


# ---------------------------------------------------------------------------
# New test classes below — no golangci-lint or Go binary required
# ---------------------------------------------------------------------------


def _make_context(tmp_path: Path, has_go_mod: bool = True) -> MagicMock:
    """Create a minimal ScanContext-like mock for unit tests."""
    if has_go_mod:
        (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    ctx = MagicMock()
    ctx.project_root = tmp_path
    ctx.stream_handler = None
    ctx.record_skip = MagicMock()
    return ctx


class TestGoLangCILintProperties:
    """Tests for basic linter properties (no binary needed)."""

    def test_name_property(self):
        linter = GoLangCILintLinter()
        assert linter.name == "golangci_lint"

    def test_languages_property(self):
        linter = GoLangCILintLinter()
        assert linter.languages == ["go"]

    def test_supports_fix_property(self):
        linter = GoLangCILintLinter()
        assert linter.supports_fix is True

    def test_domain_property(self):
        from lucidshark.core.models import ToolDomain

        linter = GoLangCILintLinter()
        assert linter.domain == ToolDomain.LINTING


class TestGoLangCILintParsingEdgeCases:
    """Tests for _parse_output and _issue_to_unified edge cases (no binary needed)."""

    def _make_linter(self):
        return GoLangCILintLinter(project_root=Path("/tmp"))

    # -- _parse_output edge cases --

    def test_parse_output_null_issues(self):
        linter = self._make_linter()
        issues = linter._parse_output('{"Issues": null}', Path("/tmp"))
        assert issues == []

    def test_parse_output_missing_issues_key(self):
        linter = self._make_linter()
        issues = linter._parse_output('{"Report": {}}', Path("/tmp"))
        assert issues == []

    def test_parse_output_whitespace_only(self):
        linter = self._make_linter()
        issues = linter._parse_output("   \n\t  ", Path("/tmp"))
        assert issues == []

    def test_parse_output_extra_json_fields(self):
        linter = self._make_linter()
        output = json.dumps(
            {
                "Issues": [
                    {
                        "FromLinter": "govet",
                        "Text": "test issue",
                        "Severity": "error",
                        "SourceLines": ["x := 1"],
                        "Pos": {"Filename": "main.go", "Line": 1, "Column": 1},
                    }
                ],
                "Report": {"Linters": []},
                "ExtraField": True,
            }
        )
        issues = linter._parse_output(output, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].rule_id == "govet"

    # -- _issue_to_unified edge cases --

    def test_issue_missing_filename_returns_none(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is None

    def test_issue_missing_pos_key(self):
        linter = self._make_linter()
        raw = {"FromLinter": "govet", "Text": "issue"}
        # No "Pos" key -> Filename will be "" -> returns None
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is None

    def test_issue_null_line_and_column(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "f.go", "Line": None, "Column": None},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.line_start is None
        assert result.column_start is None

    def test_issue_sourcelines_none(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
            "SourceLines": None,
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.code_snippet is None

    def test_issue_sourcelines_empty(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
            "SourceLines": [],
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.code_snippet is None

    def test_issue_sourcelines_multiple(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
            "SourceLines": ["line1", "line2"],
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.code_snippet == "line1\nline2"

    def test_issue_absolute_file_path(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "/abs/path/main.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/project"))
        assert result is not None
        assert result.file_path == Path("/abs/path/main.go")
        assert result.file_path.is_absolute()

    def test_issue_relative_file_path_resolved(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "pkg/handler.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/project"))
        assert result is not None
        assert result.file_path == Path("/project/pkg/handler.go")

    def test_issue_empty_text(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.description == ""

    def test_issue_missing_fromlinter(self):
        linter = self._make_linter()
        raw = {
            "Text": "some issue",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.rule_id == "unknown"
        assert "unknown" in result.title

    def test_issue_documentation_url(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert "#govet" in result.documentation_url

    def test_issue_metadata_fields(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Severity": "error",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert "from_linter" in result.metadata
        assert "severity_field" in result.metadata
        assert result.metadata["from_linter"] == "govet"
        assert result.metadata["severity_field"] == "error"

    def test_issue_title_format(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "errcheck",
            "Text": "unchecked error",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.title == "[errcheck] unchecked error"

    def test_issue_fixable_true(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "f.go", "Line": 1, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.fixable is True

    def test_issue_line_end_equals_line_start(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": {"Filename": "f.go", "Line": 42, "Column": 1},
        }
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is not None
        assert result.line_end == result.line_start
        assert result.line_end == 42

    def test_issue_malformed_pos_value_caught(self):
        linter = self._make_linter()
        raw = {
            "FromLinter": "govet",
            "Text": "issue",
            "Pos": "not_a_dict",
        }
        # "not_a_dict".get(...) raises AttributeError, caught by except block
        result = linter._issue_to_unified(raw, Path("/tmp"))
        assert result is None


class TestGoLangCILintSeverityComplete:
    """Thorough tests for _get_severity (no binary needed)."""

    def _make_linter(self):
        return GoLangCILintLinter(project_root=Path("/tmp"))

    def test_severity_medium_linter(self):
        linter = self._make_linter()
        severity = linter._get_severity("ineffassign", "error")
        assert severity == Severity.MEDIUM

    def test_severity_empty_fromlinter_falls_to_field(self):
        linter = self._make_linter()
        severity = linter._get_severity("", "warning")
        assert severity == Severity.MEDIUM

    def test_severity_unknown_field_value(self):
        linter = self._make_linter()
        severity = linter._get_severity("unknown_linter", "info")
        assert severity == Severity.MEDIUM

    def test_severity_all_high_linters(self):
        linter = self._make_linter()
        high_linters = [k for k, v in LINTER_SEVERITY.items() if v == Severity.HIGH]
        assert len(high_linters) > 0, "Expected at least one HIGH linter"
        for name in high_linters:
            assert linter._get_severity(name, "") == Severity.HIGH, (
                f"Expected HIGH for linter {name}"
            )

    def test_severity_all_medium_linters(self):
        linter = self._make_linter()
        medium_linters = [k for k, v in LINTER_SEVERITY.items() if v == Severity.MEDIUM]
        assert len(medium_linters) > 0, "Expected at least one MEDIUM linter"
        for name in medium_linters:
            assert linter._get_severity(name, "") == Severity.MEDIUM, (
                f"Expected MEDIUM for linter {name}"
            )

    def test_severity_all_low_linters(self):
        linter = self._make_linter()
        low_linters = [k for k, v in LINTER_SEVERITY.items() if v == Severity.LOW]
        assert len(low_linters) > 0, "Expected at least one LOW linter"
        for name in low_linters:
            assert linter._get_severity(name, "") == Severity.LOW, (
                f"Expected LOW for linter {name}"
            )


class TestGoLangCILintErrorHandling:
    """Tests for error paths in lint() and fix() using mocks (no binary needed)."""

    @patch("lucidshark.plugins.linters.golangci_lint.find_golangci_lint")
    def test_lint_returns_empty_on_binary_not_found(self, mock_find, tmp_path):
        mock_find.side_effect = FileNotFoundError("golangci-lint not found")
        linter = GoLangCILintLinter()
        ctx = _make_context(tmp_path)
        result = linter.lint(ctx)
        assert result == []

    @patch("lucidshark.plugins.linters.golangci_lint.run_with_streaming")
    @patch("lucidshark.plugins.linters.golangci_lint.find_golangci_lint")
    def test_lint_returns_empty_on_timeout(self, mock_find, mock_run, tmp_path):
        mock_find.return_value = Path("/usr/bin/golangci-lint")
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="golangci-lint", timeout=300
        )
        linter = GoLangCILintLinter()
        ctx = _make_context(tmp_path)
        result = linter.lint(ctx)
        assert result == []
        ctx.record_skip.assert_called_once()

    @patch("lucidshark.plugins.linters.golangci_lint.run_with_streaming")
    @patch("lucidshark.plugins.linters.golangci_lint.find_golangci_lint")
    def test_lint_returns_empty_on_generic_exception(
        self, mock_find, mock_run, tmp_path
    ):
        mock_find.return_value = Path("/usr/bin/golangci-lint")
        mock_run.side_effect = RuntimeError("something broke")
        linter = GoLangCILintLinter()
        ctx = _make_context(tmp_path)
        result = linter.lint(ctx)
        assert result == []
        ctx.record_skip.assert_called_once()

    @patch("lucidshark.plugins.linters.golangci_lint.find_golangci_lint")
    def test_fix_returns_empty_on_binary_not_found(self, mock_find, tmp_path):
        mock_find.side_effect = FileNotFoundError("golangci-lint not found")
        linter = GoLangCILintLinter()
        ctx = _make_context(tmp_path)
        result = linter.fix(ctx)
        assert isinstance(result, FixResult)
        assert result.files_modified == 0
        assert result.issues_fixed == 0

    @patch("lucidshark.plugins.linters.golangci_lint.has_go_mod")
    @patch("lucidshark.plugins.linters.golangci_lint.find_golangci_lint")
    def test_fix_returns_empty_on_no_go_mod(self, mock_find, mock_has_go_mod, tmp_path):
        mock_find.return_value = Path("/usr/bin/golangci-lint")
        mock_has_go_mod.return_value = False
        linter = GoLangCILintLinter()
        ctx = _make_context(tmp_path, has_go_mod=False)
        result = linter.fix(ctx)
        assert isinstance(result, FixResult)
        assert result.files_modified == 0
        assert result.issues_fixed == 0

    @patch("lucidshark.plugins.linters.golangci_lint.run_with_streaming")
    @patch("lucidshark.plugins.linters.golangci_lint.find_golangci_lint")
    def test_fix_returns_empty_on_timeout(self, mock_find, mock_run, tmp_path):
        mock_find.return_value = Path("/usr/bin/golangci-lint")
        # fix() calls self.lint() first (which calls run_with_streaming),
        # then calls run_with_streaming again for the fix command.
        # First call (lint pre-check) returns empty issues,
        # second call (fix) raises timeout.
        mock_run_result = MagicMock()
        mock_run_result.stdout = '{"Issues": []}'

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return mock_run_result
            raise subprocess.TimeoutExpired(cmd="golangci-lint", timeout=300)

        mock_run.side_effect = side_effect
        linter = GoLangCILintLinter()
        ctx = _make_context(tmp_path)
        result = linter.fix(ctx)
        assert isinstance(result, FixResult)
        assert result.files_modified == 0
