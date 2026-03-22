"""Unit tests for Prettier formatter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.formatters.prettier import (
    PrettierFormatter,
    PRETTIER_EXTENSIONS,
)


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _make_context(project_root: Path, paths: list[Path] | None = None) -> ScanContext:
    """Helper to create a ScanContext with sensible defaults."""
    return ScanContext(
        project_root=project_root,
        paths=paths or [],
        enabled_domains=[ToolDomain.FORMATTING],
    )


class TestPrettierFormatterProperties:
    def test_name(self) -> None:
        formatter = PrettierFormatter()
        assert formatter.name == "prettier"

    def test_languages(self) -> None:
        formatter = PrettierFormatter()
        assert "javascript" in formatter.languages
        assert "typescript" in formatter.languages

    def test_domain(self) -> None:
        formatter = PrettierFormatter()
        assert formatter.domain == ToolDomain.FORMATTING

    def test_supports_fix(self) -> None:
        formatter = PrettierFormatter()
        assert formatter.supports_fix is True

    def test_extensions(self) -> None:
        assert ".js" in PRETTIER_EXTENSIONS
        assert ".ts" in PRETTIER_EXTENSIONS
        assert ".tsx" in PRETTIER_EXTENSIONS
        assert ".css" in PRETTIER_EXTENSIONS
        assert ".json" in PRETTIER_EXTENSIONS
        assert ".md" in PRETTIER_EXTENSIONS
        assert ".jsx" in PRETTIER_EXTENSIONS


class TestPrettierFormatterCheck:
    def test_check_no_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x = 1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_with_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x=1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            stdout = "[warn] test.js\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert issues[0].domain == ToolDomain.FORMATTING
                assert issues[0].source_tool == "prettier"
                assert issues[0].severity == Severity.LOW
                assert issues[0].fixable is True

    def test_check_skips_non_matching_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.py").write_text("x = 1\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.py"])

            issues = formatter.check(context)
            assert issues == []

    def test_check_binary_not_found(self) -> None:
        formatter = PrettierFormatter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = formatter.check(context)
            assert issues == []

    def test_check_skips_info_lines(self) -> None:
        """Test that info/summary lines from prettier are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x=1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            stdout = "Checking formatting...\n[warn] test.js\nAll matched files use Prettier code style!\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1

    def test_check_timeout_expired(self) -> None:
        """Test that TimeoutExpired is caught and returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x = 1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(cmd="prettier", timeout=120),
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_generic_exception(self) -> None:
        """Test that a generic Exception from subprocess is caught."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x = 1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    side_effect=OSError("Permission denied"),
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_paths_falsy_falls_back_to_dot(self) -> None:
        """When context.paths is empty, check should fall back to ['.']."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, paths=[])

            result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ) as mock_run,
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert issues == []
                # The command should include "." as the path
                call_args = mock_run.call_args
                cmd = (
                    call_args.kwargs.get("cmd") or call_args[1].get("cmd")
                    if call_args[1]
                    else call_args[0][0]
                )
                assert "." in cmd

    def test_check_empty_stdout_on_nonzero_returncode(self) -> None:
        """Non-zero returncode with empty stdout should produce no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("x\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            result = make_completed_process(1, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_none_stdout_on_nonzero_returncode(self) -> None:
        """Non-zero returncode with None stdout should produce no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("x\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            result = make_completed_process(1, "")
            result.stdout = None
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_bare_file_paths_in_output(self) -> None:
        """File paths without [warn] prefix should still be parsed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "app.ts").write_text("x\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "app.ts"])

            stdout = "app.ts\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert "app.ts" in issues[0].title

    def test_check_multiple_files_in_output(self) -> None:
        """Multiple file paths in output should produce multiple issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "a.js").write_text("x\n")
            (project_root / "b.css").write_text("x\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(
                project_root, [project_root / "a.js", project_root / "b.css"]
            )

            stdout = "[warn] a.js\n[warn] b.css\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                issues = formatter.check(context)
                assert len(issues) == 2
                titles = {i.title for i in issues}
                assert "File needs formatting: a.js" in titles
                assert "File needs formatting: b.css" in titles


class TestPrettierCheckOutputFiltering:
    """Tests for check() output filtering  -  verifies known info/summary lines are skipped."""

    def _run_check_with_stdout(self, stdout: str, stderr: str = "") -> list:
        """Helper: run check() with fake prettier output and return issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x=1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            result = make_completed_process(1, stdout, stderr)
            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                return formatter.check(context)

    def test_valid_file_paths_produce_issues(self) -> None:
        issues = self._run_check_with_stdout("[warn] src/app.js\n")
        assert len(issues) == 1
        assert "src/app.js" in issues[0].title

    def test_bare_file_path_produces_issue(self) -> None:
        issues = self._run_check_with_stdout("test.tsx\n")
        assert len(issues) == 1
        assert "test.tsx" in issues[0].title

    def test_info_summary_lines_skipped(self) -> None:
        """Info/summary lines from prettier output are not treated as issues."""
        stdout = (
            "Checking formatting...\n"
            "[warn] test.js\n"
            "All matched files use Prettier code style!\n"
            "Code style issues found in 1 file.\n"
        )
        issues = self._run_check_with_stdout(stdout)
        assert len(issues) == 1
        assert "test.js" in issues[0].title

    def test_empty_and_whitespace_lines_skipped(self) -> None:
        stdout = "\n   \n[warn] test.js\n\n"
        issues = self._run_check_with_stdout(stdout)
        assert len(issues) == 1
        assert "test.js" in issues[0].title

    def test_warn_prefix_stripped(self) -> None:
        """The [warn] prefix should be stripped, leaving just the file path."""
        issues = self._run_check_with_stdout("[warn] test.js\n")
        assert len(issues) == 1
        assert "test.js" in issues[0].title
        assert "[warn]" not in issues[0].title

    def test_stderr_warn_lines_also_parsed(self) -> None:
        """Prettier v3+ writes [warn] to stderr; check() reads both streams."""
        issues = self._run_check_with_stdout("", stderr="[warn] test.js\n")
        assert len(issues) == 1
        assert "test.js" in issues[0].title


class TestPrettierFormatterEnsureBinary:
    def test_ensure_binary_not_found(self) -> None:
        formatter = PrettierFormatter(project_root=Path("/nonexistent"))
        with (
            patch(
                "lucidshark.plugins.formatters.prettier.resolve_node_bin",
                return_value=None,
            ),
            patch(
                "lucidshark.plugins.formatters.prettier.shutil.which", return_value=None
            ),
        ):
            with pytest.raises(FileNotFoundError):
                formatter.ensure_binary()

    def test_ensure_binary_from_node_modules(self) -> None:
        formatter = PrettierFormatter(project_root=Path("/project"))
        with patch(
            "lucidshark.plugins.formatters.prettier.resolve_node_bin",
            return_value=Path("/project/node_modules/.bin/prettier"),
        ):
            binary = formatter.ensure_binary()
            assert binary == Path("/project/node_modules/.bin/prettier")

    def test_ensure_binary_from_system(self) -> None:
        formatter = PrettierFormatter(project_root=Path("/project"))
        with (
            patch(
                "lucidshark.plugins.formatters.prettier.resolve_node_bin",
                return_value=None,
            ),
            patch(
                "lucidshark.plugins.formatters.prettier.shutil.which",
                return_value="/usr/bin/prettier",
            ),
        ):
            binary = formatter.ensure_binary()
            assert binary == Path("/usr/bin/prettier")

    def test_ensure_binary_project_root_none_skips_node_modules(self) -> None:
        """When project_root is None, node_modules check should be skipped."""
        formatter = PrettierFormatter(project_root=None)
        with (
            patch(
                "lucidshark.plugins.formatters.prettier.resolve_node_bin"
            ) as mock_resolve,
            patch(
                "lucidshark.plugins.formatters.prettier.shutil.which",
                return_value="/usr/bin/prettier",
            ),
        ):
            binary = formatter.ensure_binary()
            assert binary == Path("/usr/bin/prettier")
            mock_resolve.assert_not_called()


class TestPrettierFormatterResolvePaths:
    def test_directories_included(self) -> None:
        """Directories should always pass through the filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            subdir = project_root / "src"
            subdir.mkdir()

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [subdir])
            result = formatter._resolve_paths(
                context, PRETTIER_EXTENSIONS, fallback_to_cwd=True
            )
            assert str(subdir) in result

    def test_correct_extensions_included(self) -> None:
        """Files with prettier-supported extensions should be included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            js_file = project_root / "app.js"
            ts_file = project_root / "index.ts"
            css_file = project_root / "style.css"
            json_file = project_root / "data.json"
            md_file = project_root / "README.md"
            for f in [js_file, ts_file, css_file, json_file, md_file]:
                f.write_text("")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(
                project_root, [js_file, ts_file, css_file, json_file, md_file]
            )
            result = formatter._resolve_paths(
                context, PRETTIER_EXTENSIONS, fallback_to_cwd=True
            )
            assert len(result) == 5

    def test_wrong_extensions_excluded(self) -> None:
        """Files with non-prettier extensions should be excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            rs_file = project_root / "lib.rs"
            go_file = project_root / "main.go"
            for f in [py_file, rs_file, go_file]:
                f.write_text("")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [py_file, rs_file, go_file])
            result = formatter._resolve_paths(
                context, PRETTIER_EXTENSIONS, fallback_to_cwd=True
            )
            assert result == []

    def test_mixed_paths(self) -> None:
        """Mix of valid, invalid extensions and directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            subdir = project_root / "components"
            subdir.mkdir()
            js_file = project_root / "app.js"
            py_file = project_root / "main.py"
            js_file.write_text("")
            py_file.write_text("")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [subdir, js_file, py_file])
            result = formatter._resolve_paths(
                context, PRETTIER_EXTENSIONS, fallback_to_cwd=True
            )
            assert len(result) == 2
            assert str(subdir) in result
            assert str(js_file) in result


class TestPrettierFormatterGetVersion:
    def test_get_version_success(self) -> None:
        formatter = PrettierFormatter(project_root=Path("/project"))
        with (
            patch.object(
                formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
            ),
            patch(
                "lucidshark.plugins.formatters.prettier.get_cli_version",
                return_value="3.2.1",
            ),
        ):
            version = formatter.get_version()
            assert version == "3.2.1"

    def test_get_version_binary_not_found(self) -> None:
        formatter = PrettierFormatter(project_root=Path("/project"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            version = formatter.get_version()
            assert version == "unknown"


class TestPrettierFormatterFix:
    def test_fix_success(self) -> None:
        """Fix should run --write without pre-check (runner does post-check)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x=1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            write_result = make_completed_process(0, "")

            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=write_result,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                result = formatter.fix(context)
                assert result.files_modified == 0
                assert result.issues_fixed == 0
                assert result.issues_remaining == 0

    def test_fix_binary_not_found(self) -> None:
        """Fix should return empty FixResult when binary is not found."""
        formatter = PrettierFormatter()
        context = _make_context(Path("/tmp"))

        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = formatter.fix(context)
            assert result.files_modified == 0
            assert result.issues_fixed == 0
            assert result.issues_remaining == 0

    def test_fix_no_matching_paths(self) -> None:
        """Fix should return empty FixResult when no paths match prettier extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "main.py").write_text("x = 1\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "main.py"])

            with patch.object(
                formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
            ):
                result = formatter.fix(context)
                assert result.files_modified == 0
                assert result.issues_fixed == 0
                assert result.issues_remaining == 0

    def test_fix_subprocess_exception(self) -> None:
        """Fix should return empty FixResult when --write subprocess fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("const x=1;\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    side_effect=OSError("disk full"),
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                result = formatter.fix(context)
                assert result.files_modified == 0
                assert result.issues_fixed == 0
                assert result.issues_remaining == 0

    def test_fix_runs_write_only(self) -> None:
        """Fix runs --write only; runner does post-check separately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "test.js").write_text("x\n")

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, [project_root / "test.js"])

            write_result = make_completed_process(0, "")

            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    return_value=write_result,
                ) as mock_run,
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                formatter.fix(context)
                # Only one subprocess call (--write), no pre-check
                assert mock_run.call_count == 1
                cmd = mock_run.call_args[1].get("cmd") or mock_run.call_args[0][0]
                assert "--write" in cmd

    def test_fix_with_empty_paths_falls_back_to_dot(self) -> None:
        """Fix with no context.paths should fall back to ['.']."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            formatter = PrettierFormatter(project_root=project_root)
            context = _make_context(project_root, paths=[])

            write_result = make_completed_process(0, "")

            def mock_run_streaming(cmd, **kwargs):
                assert "." in cmd, "Expected '.' in command when paths is empty"
                return write_result

            with (
                patch(
                    "lucidshark.plugins.formatters.prettier.run_with_streaming",
                    side_effect=mock_run_streaming,
                ),
                patch.object(
                    formatter, "ensure_binary", return_value=Path("/usr/bin/prettier")
                ),
            ):
                result = formatter.fix(context)
                assert result.files_modified == 0
                assert result.issues_remaining == 0
