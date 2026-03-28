"""Unit tests for Sorbet type checker plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.type_checkers.sorbet import (
    SorbetChecker,
    _get_severity_for_code,
)


class TestSorbetCheckerProperties:
    """Tests for SorbetChecker basic properties."""

    def test_name(self) -> None:
        checker = SorbetChecker()
        assert checker.name == "sorbet"

    def test_languages(self) -> None:
        checker = SorbetChecker()
        assert checker.languages == ["ruby"]

    def test_domain(self) -> None:
        checker = SorbetChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        checker = SorbetChecker()
        assert checker.supports_strict_mode is True

    def test_init_with_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = SorbetChecker(project_root=Path(tmpdir))
            assert checker._project_root == Path(tmpdir)


class TestSorbetSeverityMapping:
    """Tests for error code severity mapping."""

    def test_parse_errors_medium(self) -> None:
        assert _get_severity_for_code(1001) == Severity.MEDIUM

    def test_resolver_errors_high(self) -> None:
        assert _get_severity_for_code(2001) == Severity.HIGH

    def test_type_errors_high(self) -> None:
        assert _get_severity_for_code(7003) == Severity.HIGH

    def test_namer_errors_medium(self) -> None:
        assert _get_severity_for_code(3001) == Severity.MEDIUM

    def test_unknown_code_medium(self) -> None:
        assert _get_severity_for_code(9999) == Severity.MEDIUM


class TestSorbetBinaryFinding:
    """Tests for binary finding logic."""

    def test_find_in_binstubs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            bin_dir = project_root / "bin"
            bin_dir.mkdir()
            srb_bin = bin_dir / "srb"
            srb_bin.touch()
            srb_bin.chmod(0o755)

            checker = SorbetChecker(project_root=project_root)
            binary = checker.ensure_binary()
            assert binary == srb_bin

    @patch("shutil.which")
    def test_find_in_system_path(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/local/bin/srb"
        checker = SorbetChecker()
        binary = checker.ensure_binary()
        assert binary == Path("/usr/local/bin/srb")

    @patch("shutil.which")
    def test_not_found_raises_error(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        checker = SorbetChecker()
        with pytest.raises(FileNotFoundError) as exc:
            checker.ensure_binary()
        assert "Sorbet is not installed" in str(exc.value)


class TestSorbetParseOutput:
    """Tests for Sorbet text output parsing."""

    def test_parse_empty_output(self) -> None:
        checker = SorbetChecker()
        issues = checker._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_no_errors(self) -> None:
        checker = SorbetChecker()
        output = "No errors! Great job."
        issues = checker._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_error_with_url(self) -> None:
        checker = SorbetChecker()
        output = "lib/example.rb:10: Method `foo` does not exist on `String` https://srb.help/7003"
        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1
        issue = issues[0]
        assert issue.rule_id == "7003"
        assert issue.source_tool == "sorbet"
        assert issue.severity == Severity.HIGH
        assert issue.line_start == 10
        assert "foo" in issue.title

    def test_parse_multiple_errors(self) -> None:
        checker = SorbetChecker()
        output = (
            "lib/a.rb:5: Type error https://srb.help/7002\n"
            "lib/b.rb:15: Resolver error https://srb.help/2001\n"
        )
        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 2

    def test_skips_summary_lines(self) -> None:
        checker = SorbetChecker()
        output = (
            "lib/a.rb:5: Type error https://srb.help/7002\n"
            "Errors: 1\n"
        )
        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1

    def test_skips_indented_context_lines(self) -> None:
        checker = SorbetChecker()
        output = (
            "lib/a.rb:5: Type error https://srb.help/7002\n"
            "     5 |    foo.bar\n"
            "              ^^^\n"
        )
        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1


class TestSorbetCheck:
    """Tests for check() method."""

    def test_check_skips_when_not_installed(self) -> None:
        checker = SorbetChecker()
        context = ScanContext(
            project_root=Path("/project"),
            paths=[],
            enabled_domains=[ToolDomain.TYPE_CHECKING],
        )
        with patch.object(
            checker, "ensure_binary", side_effect=FileNotFoundError("not installed")
        ):
            issues = checker.check(context)
            assert issues == []
            assert len(context.tool_skips) == 1

    def test_check_skips_without_sorbet_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            checker = SorbetChecker(project_root=project_root)
            context = ScanContext(
                project_root=project_root,
                paths=[],
                enabled_domains=[ToolDomain.TYPE_CHECKING],
            )
            with patch.object(
                checker, "ensure_binary", return_value=Path("/usr/bin/srb")
            ):
                issues = checker.check(context)
                assert issues == []
                assert len(context.tool_skips) == 1


class TestSorbetIssueId:
    """Tests for deterministic issue ID generation."""

    def test_id_starts_with_sorbet(self) -> None:
        checker = SorbetChecker()
        issue_id = checker._generate_issue_id(7003, "test.rb", 10, "msg")
        assert issue_id.startswith("sorbet-7003-")

    def test_id_is_deterministic(self) -> None:
        checker = SorbetChecker()
        id1 = checker._generate_issue_id(7003, "test.rb", 10, "msg")
        id2 = checker._generate_issue_id(7003, "test.rb", 10, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        checker = SorbetChecker()
        id1 = checker._generate_issue_id(7003, "a.rb", 10, "msg")
        id2 = checker._generate_issue_id(7002, "a.rb", 10, "msg")
        assert id1 != id2
