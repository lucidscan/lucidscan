"""Unit tests for SwiftLint linter plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.swiftlint import (
    SwiftLintLinter,
    RULE_SEVERITY,
    LEVEL_SEVERITY,
)
from lucidshark.plugins.swift_utils import generate_issue_id
from lucidshark.plugins.linters.base import FixResult


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _make_context(
    project_root: Path,
    paths: list[Path] | None = None,
    enabled_domains: list | None = None,
) -> ScanContext:
    """Create a minimal ScanContext for testing."""
    return ScanContext(
        project_root=project_root,
        paths=paths or [],
        enabled_domains=enabled_domains or [ToolDomain.LINTING],
    )


FAKE_BINARY = Path("/usr/bin/swiftlint")


class TestSwiftLintLinterProperties:
    """Tests for SwiftLintLinter basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        linter = SwiftLintLinter()
        assert linter.name == "swiftlint"

    def test_languages(self) -> None:
        """Test supported languages."""
        linter = SwiftLintLinter()
        assert linter.languages == ["swift"]

    def test_domain(self) -> None:
        """Test domain is LINTING."""
        linter = SwiftLintLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        """Test supports_fix returns True."""
        linter = SwiftLintLinter()
        assert linter.supports_fix is True

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = SwiftLintLinter(project_root=Path(tmpdir))
            assert linter._project_root == Path(tmpdir)


class TestSwiftLintSeverityMapping:
    """Tests for SwiftLint severity mappings."""

    def test_rule_severity_has_force_cast(self) -> None:
        """Test force_cast maps to HIGH."""
        assert RULE_SEVERITY["force_cast"] == Severity.HIGH

    def test_rule_severity_has_force_try(self) -> None:
        """Test force_try maps to HIGH."""
        assert RULE_SEVERITY["force_try"] == Severity.HIGH

    def test_rule_severity_has_force_unwrapping(self) -> None:
        """Test force_unwrapping maps to HIGH."""
        assert RULE_SEVERITY["force_unwrapping"] == Severity.HIGH

    def test_rule_severity_has_cyclomatic_complexity(self) -> None:
        """Test cyclomatic_complexity maps to MEDIUM."""
        assert RULE_SEVERITY["cyclomatic_complexity"] == Severity.MEDIUM

    def test_rule_severity_has_line_length(self) -> None:
        """Test line_length maps to LOW."""
        assert RULE_SEVERITY["line_length"] == Severity.LOW

    def test_rule_severity_has_trailing_whitespace(self) -> None:
        """Test trailing_whitespace maps to LOW."""
        assert RULE_SEVERITY["trailing_whitespace"] == Severity.LOW

    def test_rule_severity_has_unused_import(self) -> None:
        """Test unused_import maps to LOW."""
        assert RULE_SEVERITY["unused_import"] == Severity.LOW

    def test_level_severity_error(self) -> None:
        """Test error level maps to HIGH."""
        assert LEVEL_SEVERITY["error"] == Severity.HIGH

    def test_level_severity_warning(self) -> None:
        """Test warning level maps to MEDIUM."""
        assert LEVEL_SEVERITY["warning"] == Severity.MEDIUM


class TestSwiftLintEnsureBinary:
    """Tests for ensure_binary method."""

    def test_found_via_which(self) -> None:
        """Test finding swiftlint in system PATH."""
        linter = SwiftLintLinter()
        with patch(
            "lucidshark.plugins.linters.swiftlint.shutil.which",
            return_value="/usr/local/bin/swiftlint",
        ):
            binary = linter.ensure_binary()
            assert binary == Path("/usr/local/bin/swiftlint")

    def test_not_found_raises_file_not_found(self) -> None:
        """Test FileNotFoundError when swiftlint not found."""
        linter = SwiftLintLinter()
        with patch(
            "lucidshark.plugins.linters.swiftlint.shutil.which",
            return_value=None,
        ):
            with pytest.raises(FileNotFoundError, match="swiftlint is not installed"):
                linter.ensure_binary()


class TestSwiftLintGetVersion:
    """Tests for get_version method."""

    def test_returns_version(self) -> None:
        """Test get_version returns a version string."""
        linter = SwiftLintLinter()
        with (
            patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            patch(
                "lucidshark.plugins.linters.swiftlint.get_cli_version",
                return_value="0.54.0",
            ),
        ):
            version = linter.get_version()
            assert version == "0.54.0"

    def test_returns_unknown_on_error(self) -> None:
        """Test get_version returns 'unknown' when binary not found."""
        linter = SwiftLintLinter()
        with patch.object(
            linter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            version = linter.get_version()
            assert version == "unknown"


class TestSwiftLintLint:
    """Tests for lint method."""

    def test_no_issues_empty_output(self) -> None:
        """Test lint returns empty when swiftlint produces empty output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            result = make_completed_process(0, "[]")
            with (
                patch(
                    "lucidshark.plugins.linters.swiftlint.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_with_violations(self) -> None:
        """Test lint parses JSON array output with violations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "File.swift"
            swift_file.write_text("let x = 1\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            violations = json.dumps(
                [
                    {
                        "file": str(swift_file),
                        "line": 10,
                        "character": 5,
                        "severity": "warning",
                        "rule_id": "line_length",
                        "reason": "Line should be 120 characters or less",
                    }
                ]
            )
            result = make_completed_process(1, violations)
            with (
                patch(
                    "lucidshark.plugins.linters.swiftlint.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert len(issues) == 1
                assert issues[0].domain == ToolDomain.LINTING
                assert issues[0].source_tool == "swiftlint"
                assert issues[0].rule_id == "line_length"
                assert issues[0].severity == Severity.LOW
                assert issues[0].line_start == 10
                assert issues[0].column_start == 5
                assert issues[0].fixable is True

    def test_multiple_violations(self) -> None:
        """Test lint correctly parses multiple violations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "File.swift"
            swift_file.write_text("let x = 1\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            violations = json.dumps(
                [
                    {
                        "file": str(swift_file),
                        "line": 1,
                        "character": 1,
                        "severity": "error",
                        "rule_id": "force_cast",
                        "reason": "Force casts should be avoided",
                    },
                    {
                        "file": str(swift_file),
                        "line": 5,
                        "character": 10,
                        "severity": "warning",
                        "rule_id": "trailing_whitespace",
                        "reason": "Lines should not have trailing whitespace",
                    },
                ]
            )
            result = make_completed_process(1, violations)
            with (
                patch(
                    "lucidshark.plugins.linters.swiftlint.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert len(issues) == 2
                assert issues[0].severity == Severity.HIGH
                assert issues[1].severity == Severity.LOW

    def test_binary_not_found_returns_empty(self) -> None:
        """Test lint returns empty when binary not found."""
        linter = SwiftLintLinter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            linter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = linter.lint(context)
            assert issues == []

    def test_timeout_returns_empty(self) -> None:
        """Test lint returns empty on timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("let x = 1\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            with (
                patch(
                    "lucidshark.plugins.linters.swiftlint.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(cmd="swiftlint", timeout=300),
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_no_swift_files_returns_empty(self) -> None:
        """Test lint returns empty when no Swift files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("x = 1\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [py_file])

            with patch.object(linter, "ensure_binary", return_value=FAKE_BINARY):
                issues = linter.lint(context)
                assert issues == []

    def test_generic_exception_returns_empty(self) -> None:
        """Test lint returns empty on generic exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("let x = 1\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            with (
                patch(
                    "lucidshark.plugins.linters.swiftlint.run_with_streaming",
                    side_effect=RuntimeError("unexpected error"),
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_invalid_json_returns_empty(self) -> None:
        """Test lint returns empty when output is invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("let x = 1\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            result = make_completed_process(1, "not valid json")
            with (
                patch(
                    "lucidshark.plugins.linters.swiftlint.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert issues == []


class TestSwiftLintFix:
    """Tests for fix method."""

    def test_fix_success(self) -> None:
        """Test fix resolves pre-existing issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("let x = 1  \n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            # Pre-fix: 1 issue
            pre_output = json.dumps(
                [
                    {
                        "file": str(swift_file),
                        "line": 1,
                        "character": 1,
                        "severity": "warning",
                        "rule_id": "trailing_whitespace",
                        "reason": "Lines should not have trailing whitespace",
                    }
                ]
            )
            # Post-fix: 0 issues
            post_output = json.dumps([])
            fix_result = make_completed_process(0, "")

            pre_result = make_completed_process(1, pre_output)
            post_result = make_completed_process(0, post_output)

            with (
                patch(
                    "lucidshark.plugins.linters.swiftlint.run_with_streaming"
                ) as mock_run,
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                # lint (pre), fix, lint (post)
                mock_run.side_effect = [pre_result, fix_result, post_result]
                result = linter.fix(context)
                assert isinstance(result, FixResult)
                assert result.issues_fixed == 1
                assert result.issues_remaining == 0

    def test_fix_binary_not_found(self) -> None:
        """Test fix returns empty FixResult when binary not found."""
        linter = SwiftLintLinter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            linter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = linter.fix(context)
            assert isinstance(result, FixResult)
            assert result.files_modified == 0
            assert result.issues_fixed == 0

    def test_fix_no_swift_files(self) -> None:
        """Test fix returns empty FixResult when no Swift files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("x = 1\n")

            linter = SwiftLintLinter(project_root=project_root)
            context = _make_context(project_root, [py_file])

            with patch.object(linter, "ensure_binary", return_value=FAKE_BINARY):
                result = linter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 0
                assert result.issues_fixed == 0


class TestSwiftLintParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        linter = SwiftLintLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_whitespace_output(self) -> None:
        """Test parsing whitespace-only output."""
        linter = SwiftLintLinter()
        issues = linter._parse_output("   \n  ", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        linter = SwiftLintLinter()
        issues = linter._parse_output("not json", Path("/project"))
        assert issues == []

    def test_parse_non_list_json(self) -> None:
        """Test parsing non-list JSON output."""
        linter = SwiftLintLinter()
        issues = linter._parse_output('{"key": "value"}', Path("/project"))
        assert issues == []

    def test_parse_empty_list(self) -> None:
        """Test parsing empty JSON list."""
        linter = SwiftLintLinter()
        issues = linter._parse_output("[]", Path("/project"))
        assert issues == []

    def test_parse_single_violation(self) -> None:
        """Test parsing single violation."""
        linter = SwiftLintLinter()
        output = json.dumps(
            [
                {
                    "file": "/project/File.swift",
                    "line": 10,
                    "character": 5,
                    "severity": "warning",
                    "rule_id": "line_length",
                    "reason": "Line should be 120 characters or less",
                }
            ]
        )

        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "line_length"
        assert issues[0].line_start == 10
        assert issues[0].column_start == 5

    def test_parse_deduplicates_same_issue(self) -> None:
        """Test that duplicate violations produce only one issue."""
        linter = SwiftLintLinter()
        violation = {
            "file": "/project/File.swift",
            "line": 10,
            "character": 5,
            "severity": "warning",
            "rule_id": "line_length",
            "reason": "Line should be 120 characters or less",
        }
        output = json.dumps([violation, violation])

        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1


class TestSwiftLintViolationToIssue:
    """Tests for _violation_to_issue method."""

    def test_converts_violation_correctly(self) -> None:
        """Test basic violation conversion."""
        linter = SwiftLintLinter()
        violation = {
            "file": "Sources/App.swift",
            "line": 10,
            "character": 5,
            "severity": "warning",
            "rule_id": "line_length",
            "reason": "Line should be 120 characters or less",
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        assert issue.source_tool == "swiftlint"
        assert issue.domain == ToolDomain.LINTING
        assert issue.rule_id == "line_length"
        assert issue.severity == Severity.LOW
        assert issue.file_path == Path("/project/Sources/App.swift")
        assert issue.line_start == 10
        assert issue.column_start == 5
        assert issue.fixable is True
        assert "[line_length]" in issue.title

    def test_violation_with_absolute_path(self) -> None:
        """Test violation with absolute file path."""
        linter = SwiftLintLinter()
        violation = {
            "file": "/abs/path/File.swift",
            "line": 1,
            "character": 1,
            "severity": "error",
            "rule_id": "force_cast",
            "reason": "Force casts should be avoided",
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        assert issue.file_path == Path("/abs/path/File.swift")

    def test_violation_without_file_returns_none(self) -> None:
        """Test violation without file path returns None."""
        linter = SwiftLintLinter()
        violation = {
            "file": "",
            "line": 1,
            "character": 1,
            "severity": "warning",
            "rule_id": "test",
            "reason": "test reason",
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is None

    def test_severity_from_rule_id(self) -> None:
        """Test severity is taken from RULE_SEVERITY when available."""
        linter = SwiftLintLinter()
        violation = {
            "file": "File.swift",
            "line": 1,
            "character": 1,
            "severity": "warning",  # level says warning
            "rule_id": "force_cast",  # but rule says HIGH
            "reason": "Force casts should be avoided",
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        # Rule severity should override level severity
        assert issue.severity == Severity.HIGH

    def test_severity_fallback_to_level(self) -> None:
        """Test severity falls back to LEVEL_SEVERITY for unknown rules."""
        linter = SwiftLintLinter()
        violation = {
            "file": "File.swift",
            "line": 1,
            "character": 1,
            "severity": "error",
            "rule_id": "some_unknown_rule",
            "reason": "Something went wrong",
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        assert issue.severity == Severity.HIGH  # from LEVEL_SEVERITY["error"]

    def test_documentation_url(self) -> None:
        """Test documentation URL is generated correctly."""
        linter = SwiftLintLinter()
        violation = {
            "file": "File.swift",
            "line": 1,
            "character": 1,
            "severity": "warning",
            "rule_id": "line_length",
            "reason": "test",
        }

        issue = linter._violation_to_issue(violation, Path("/project"))
        assert issue is not None
        assert (
            issue.documentation_url
            == "https://realm.github.io/SwiftLint/line_length.html"
        )


class TestSwiftLintIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        id1 = generate_issue_id("swiftlint", "line_length", "File.swift", 10, 5, "msg")
        id2 = generate_issue_id("swiftlint", "line_length", "File.swift", 10, 5, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        id1 = generate_issue_id("swiftlint", "line_length", "a.swift", 1, 1, "msg")
        id2 = generate_issue_id("swiftlint", "force_cast", "a.swift", 1, 1, "msg")
        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID starts with tool name."""
        issue_id = generate_issue_id("swiftlint", "rule", "f.swift", 1, 1, "msg")
        assert issue_id.startswith("swiftlint-")
