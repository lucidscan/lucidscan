"""Unit tests for clang-tidy linter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.clang_tidy import (
    CATEGORY_SEVERITY,
    ClangTidyLinter,
    _DIAG_RE,
)


class TestClangTidyProperties:
    """Basic property tests for ClangTidyLinter."""

    def test_name(self) -> None:
        linter = ClangTidyLinter()
        assert linter.name == "clang_tidy"

    def test_languages(self) -> None:
        linter = ClangTidyLinter()
        assert linter.languages == ["c", "c++"]

    def test_supports_fix(self) -> None:
        linter = ClangTidyLinter()
        assert linter.supports_fix is True

    def test_domain(self) -> None:
        linter = ClangTidyLinter()
        assert linter.domain == ToolDomain.LINTING


class TestDiagRegex:
    """Tests for the diagnostic output regex."""

    def test_matches_warning_with_check(self) -> None:
        line = "/path/to/file.cpp:42:15: warning: use of 'auto' is discouraged [modernize-use-auto]"
        match = _DIAG_RE.match(line)
        assert match is not None
        assert match.group(1) == "/path/to/file.cpp"
        assert match.group(2) == "42"
        assert match.group(3) == "15"
        assert match.group(4) == "warning"
        assert match.group(5) == "use of 'auto' is discouraged"
        assert match.group(6) == "modernize-use-auto"

    def test_matches_error_with_check(self) -> None:
        line = "main.cpp:10:5: error: null pointer dereference [clang-analyzer-core.NullDereference]"
        match = _DIAG_RE.match(line)
        assert match is not None
        assert match.group(4) == "error"
        assert match.group(6) == "clang-analyzer-core.NullDereference"

    def test_matches_warning_without_check(self) -> None:
        line = "file.cpp:1:1: warning: some compiler warning"
        match = _DIAG_RE.match(line)
        assert match is not None
        assert match.group(6) is None

    def test_does_not_match_note(self) -> None:
        line = "file.cpp:1:1: note: this is a note"
        match = _DIAG_RE.match(line)
        assert match is not None
        assert match.group(4) == "note"


class TestParseOutput:
    """Tests for _parse_output."""

    def test_parse_empty_output(self) -> None:
        linter = ClangTidyLinter()
        issues = linter._parse_output("", Path("/tmp"))
        assert issues == []

    def test_parse_single_warning(self) -> None:
        linter = ClangTidyLinter()
        output = "/tmp/main.cpp:10:5: warning: variable 'x' is not initialized [cppcoreguidelines-init-variables]\n"
        issues = linter._parse_output(output, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].domain == ToolDomain.LINTING
        assert issues[0].source_tool == "clang-tidy"
        assert issues[0].rule_id == "cppcoreguidelines-init-variables"
        assert issues[0].line_start == 10
        assert issues[0].column_start == 5

    def test_parse_multiple_warnings(self) -> None:
        linter = ClangTidyLinter()
        output = (
            "/tmp/main.cpp:10:5: warning: msg1 [bugprone-use-after-move]\n"
            "/tmp/main.cpp:20:3: warning: msg2 [performance-unnecessary-copy-initialization]\n"
            "/tmp/main.cpp:15:1: note: this is a note\n"
        )
        issues = linter._parse_output(output, Path("/tmp"))
        # Notes should be skipped
        assert len(issues) == 2

    def test_parse_deduplicates(self) -> None:
        linter = ClangTidyLinter()
        output = (
            "/tmp/main.cpp:10:5: warning: same message [bugprone-test]\n"
            "/tmp/main.cpp:10:5: warning: same message [bugprone-test]\n"
        )
        issues = linter._parse_output(output, Path("/tmp"))
        assert len(issues) == 1

    def test_severity_mapping_bugprone(self) -> None:
        linter = ClangTidyLinter()
        severity = linter._get_severity("bugprone-use-after-move", "warning")
        assert severity == Severity.HIGH

    def test_severity_mapping_readability(self) -> None:
        linter = ClangTidyLinter()
        severity = linter._get_severity(
            "readability-braces-around-statements", "warning"
        )
        assert severity == Severity.LOW

    def test_severity_mapping_performance(self) -> None:
        linter = ClangTidyLinter()
        severity = linter._get_severity(
            "performance-unnecessary-copy-initialization", "warning"
        )
        assert severity == Severity.MEDIUM

    def test_severity_mapping_fallback_to_diag_level(self) -> None:
        linter = ClangTidyLinter()
        severity = linter._get_severity("unknown-check", "error")
        assert severity == Severity.HIGH

    def test_severity_mapping_unknown_defaults_to_medium(self) -> None:
        linter = ClangTidyLinter()
        severity = linter._get_severity("", "unknown")
        assert severity == Severity.MEDIUM


class TestLint:
    """Tests for lint method."""

    @patch.object(ClangTidyLinter, "ensure_binary")
    def test_lint_binary_not_found(self, mock_binary) -> None:
        mock_binary.side_effect = FileNotFoundError("clang-tidy not found")
        linter = ClangTidyLinter()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        issues = linter.lint(context)
        assert issues == []

    @patch("lucidshark.plugins.linters.clang_tidy.run_with_streaming")
    @patch.object(ClangTidyLinter, "ensure_binary")
    def test_lint_timeout(self, mock_binary, mock_run) -> None:
        mock_binary.return_value = Path("/usr/bin/clang-tidy")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="clang-tidy", timeout=300)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "main.cpp").write_text("int main() {}")
            linter = ClangTidyLinter()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            issues = linter.lint(context)
            assert issues == []

    @patch("lucidshark.plugins.linters.clang_tidy.run_with_streaming")
    @patch.object(ClangTidyLinter, "ensure_binary")
    def test_lint_parses_output(self, mock_binary, mock_run) -> None:
        mock_binary.return_value = Path("/usr/bin/clang-tidy")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="/tmp/test/main.cpp:5:3: warning: use nullptr [modernize-use-nullptr]\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "main.cpp").write_text("int main() {}")
            linter = ClangTidyLinter()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            issues = linter.lint(context)
            assert len(issues) == 1
            assert issues[0].rule_id == "modernize-use-nullptr"

    def test_collect_files_with_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cpp_file = tmpdir_path / "main.cpp"
            cpp_file.write_text("int main() {}")
            py_file = tmpdir_path / "script.py"
            py_file.write_text("print('hello')")

            linter = ClangTidyLinter()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            files = linter._collect_files(context)
            assert any("main.cpp" in f for f in files)
            assert not any("script.py" in f for f in files)

    def test_collect_files_individual_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cpp_file = tmpdir_path / "main.cpp"
            cpp_file.write_text("int main() {}")

            linter = ClangTidyLinter()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[cpp_file],
                enabled_domains=[],
            )
            files = linter._collect_files(context)
            assert len(files) == 1
            assert files[0] == str(cpp_file)


class TestCategorySeverityMapping:
    """Tests for category severity constants."""

    def test_bugprone_is_high(self) -> None:
        assert CATEGORY_SEVERITY["bugprone"] == Severity.HIGH

    def test_cert_is_high(self) -> None:
        assert CATEGORY_SEVERITY["cert"] == Severity.HIGH

    def test_clang_analyzer_is_high(self) -> None:
        assert CATEGORY_SEVERITY["clang-analyzer"] == Severity.HIGH

    def test_modernize_is_medium(self) -> None:
        assert CATEGORY_SEVERITY["modernize"] == Severity.MEDIUM

    def test_readability_is_low(self) -> None:
        assert CATEGORY_SEVERITY["readability"] == Severity.LOW

    def test_performance_is_medium(self) -> None:
        assert CATEGORY_SEVERITY["performance"] == Severity.MEDIUM
