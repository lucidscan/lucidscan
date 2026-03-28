"""Unit tests for clang-format formatter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.formatters.clang_format import ClangFormatFormatter


class TestClangFormatProperties:
    """Basic property tests for ClangFormatFormatter."""

    def test_name(self) -> None:
        formatter = ClangFormatFormatter()
        assert formatter.name == "clang_format"

    def test_languages(self) -> None:
        formatter = ClangFormatFormatter()
        assert formatter.languages == ["c", "c++"]

    def test_supports_fix(self) -> None:
        formatter = ClangFormatFormatter()
        assert formatter.supports_fix is True

    def test_domain(self) -> None:
        formatter = ClangFormatFormatter()
        assert formatter.domain == ToolDomain.FORMATTING


class TestParseCheckOutput:
    """Tests for _parse_check_output."""

    def test_parse_empty_output(self) -> None:
        formatter = ClangFormatFormatter()
        issues = formatter._parse_check_output("", Path("/tmp"))
        assert issues == []

    def test_parse_single_warning(self) -> None:
        formatter = ClangFormatFormatter()
        output = "/tmp/main.cpp:10:5: warning: code should be clang-formatted [-Wclang-format-violations]\n"
        issues = formatter._parse_check_output(output, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].domain == ToolDomain.FORMATTING
        assert issues[0].source_tool == "clang-format"
        assert issues[0].severity == Severity.LOW
        assert issues[0].fixable is True

    def test_parse_multiple_files(self) -> None:
        formatter = ClangFormatFormatter()
        output = (
            "/tmp/main.cpp:10:5: warning: code should be clang-formatted [-Wclang-format-violations]\n"
            "/tmp/utils.cpp:20:3: warning: code should be clang-formatted [-Wclang-format-violations]\n"
        )
        issues = formatter._parse_check_output(output, Path("/tmp"))
        assert len(issues) == 2

    def test_deduplicates_same_file(self) -> None:
        formatter = ClangFormatFormatter()
        output = (
            "/tmp/main.cpp:10:5: warning: code should be clang-formatted [-Wclang-format-violations]\n"
            "/tmp/main.cpp:20:3: warning: code should be clang-formatted [-Wclang-format-violations]\n"
        )
        issues = formatter._parse_check_output(output, Path("/tmp"))
        # Same file should produce only one issue
        assert len(issues) == 1

    def test_handles_various_extensions(self) -> None:
        formatter = ClangFormatFormatter()
        output = (
            "/tmp/main.cpp:1:1: warning: format\n"
            "/tmp/utils.cc:1:1: warning: format\n"
            "/tmp/lib.hpp:1:1: warning: format\n"
            "/tmp/header.h:1:1: warning: format\n"
        )
        issues = formatter._parse_check_output(output, Path("/tmp"))
        assert len(issues) == 4


class TestCheck:
    """Tests for check method."""

    @patch.object(ClangFormatFormatter, "ensure_binary")
    def test_check_binary_not_found(self, mock_binary) -> None:
        mock_binary.side_effect = FileNotFoundError("clang-format not found")
        formatter = ClangFormatFormatter()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        issues = formatter.check(context)
        assert issues == []

    def test_check_no_cpp_files(self) -> None:
        formatter = ClangFormatFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "script.py").write_text("print('hello')")
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            with patch.object(
                ClangFormatFormatter,
                "ensure_binary",
                return_value=Path("/usr/bin/clang-format"),
            ):
                issues = formatter.check(context)
                assert issues == []

    @patch("lucidshark.plugins.formatters.clang_format.run_with_streaming")
    @patch.object(ClangFormatFormatter, "ensure_binary")
    def test_check_timeout(self, mock_binary, mock_run) -> None:
        mock_binary.return_value = Path("/usr/bin/clang-format")
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="clang-format", timeout=120
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "main.cpp").write_text("int main() {}")
            formatter = ClangFormatFormatter()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            issues = formatter.check(context)
            assert issues == []

    @patch("lucidshark.plugins.formatters.clang_format.run_with_streaming")
    @patch.object(ClangFormatFormatter, "ensure_binary")
    def test_check_clean_output(self, mock_binary, mock_run) -> None:
        mock_binary.return_value = Path("/usr/bin/clang-format")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "main.cpp").write_text("int main() {}")
            formatter = ClangFormatFormatter()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            issues = formatter.check(context)
            assert issues == []


class TestFix:
    """Tests for fix method."""

    @patch.object(ClangFormatFormatter, "ensure_binary")
    def test_fix_binary_not_found(self, mock_binary) -> None:
        mock_binary.side_effect = FileNotFoundError("clang-format not found")
        formatter = ClangFormatFormatter()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        result = formatter.fix(context)
        assert result.files_modified == 0

    @patch("lucidshark.plugins.formatters.clang_format.run_with_streaming")
    @patch.object(ClangFormatFormatter, "ensure_binary")
    def test_fix_runs_with_inplace_flag(self, mock_binary, mock_run) -> None:
        mock_binary.return_value = Path("/usr/bin/clang-format")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "main.cpp").write_text("int main() {}")
            formatter = ClangFormatFormatter()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            formatter.fix(context)

            # Verify -i flag was used
            call_args = mock_run.call_args
            cmd = (
                call_args.kwargs.get("cmd")
                or call_args[1].get("cmd")
                or call_args[0][0]
            )
            assert "-i" in cmd

    def test_fix_no_cpp_files(self) -> None:
        formatter = ClangFormatFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            with patch.object(
                ClangFormatFormatter,
                "ensure_binary",
                return_value=Path("/usr/bin/clang-format"),
            ):
                result = formatter.fix(context)
                assert result.files_modified == 0


class TestResolvePaths:
    """Tests for path resolution with C++ extensions."""

    def test_resolve_cpp_files_only(self) -> None:
        formatter = ClangFormatFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "main.cpp").write_text("int main() {}")
            (tmpdir_path / "utils.hpp").write_text("#pragma once")
            (tmpdir_path / "script.py").write_text("x = 1")
            (tmpdir_path / "readme.md").write_text("# readme")

            from lucidshark.plugins.cpp_utils import CPP_EXTENSIONS

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            paths = formatter._resolve_paths(
                context, CPP_EXTENSIONS, fallback_to_cwd=False
            )
            assert any("main.cpp" in p for p in paths)
            assert any("utils.hpp" in p for p in paths)
            assert not any("script.py" in p for p in paths)
            assert not any("readme.md" in p for p in paths)

    def test_resolve_individual_file(self) -> None:
        formatter = ClangFormatFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cpp_file = tmpdir_path / "main.cpp"
            cpp_file.write_text("int main() {}")

            from lucidshark.plugins.cpp_utils import CPP_EXTENSIONS

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[cpp_file],
                enabled_domains=[],
            )
            paths = formatter._resolve_paths(
                context, CPP_EXTENSIONS, fallback_to_cwd=False
            )
            assert len(paths) == 1
            assert paths[0] == str(cpp_file)
