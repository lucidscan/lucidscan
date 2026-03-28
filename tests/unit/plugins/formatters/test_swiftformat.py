"""Unit tests for SwiftFormat formatter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.formatters.swiftformat import (
    SwiftFormatFormatter,
    SWIFT_EXTENSIONS,
)
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
        enabled_domains=enabled_domains or [ToolDomain.FORMATTING],
    )


FAKE_BINARY = Path("/usr/bin/swiftformat")


class TestSwiftFormatProperties:
    """Tests for SwiftFormatFormatter basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        formatter = SwiftFormatFormatter()
        assert formatter.name == "swiftformat"

    def test_languages(self) -> None:
        """Test supported languages."""
        formatter = SwiftFormatFormatter()
        assert formatter.languages == ["swift"]

    def test_domain(self) -> None:
        """Test domain is FORMATTING."""
        formatter = SwiftFormatFormatter()
        assert formatter.domain == ToolDomain.FORMATTING

    def test_supports_fix(self) -> None:
        """Test supports_fix returns True."""
        formatter = SwiftFormatFormatter()
        assert formatter.supports_fix is True

    def test_extensions(self) -> None:
        """Test .swift is in SWIFT_EXTENSIONS."""
        assert ".swift" in SWIFT_EXTENSIONS


class TestSwiftFormatEnsureBinary:
    """Tests for ensure_binary method."""

    def test_found(self) -> None:
        """Test finding swiftformat in system PATH."""
        formatter = SwiftFormatFormatter()
        with patch(
            "lucidshark.plugins.formatters.swiftformat.shutil.which",
            return_value="/usr/local/bin/swiftformat",
        ):
            binary = formatter.ensure_binary()
            assert binary == Path("/usr/local/bin/swiftformat")

    def test_not_found(self) -> None:
        """Test FileNotFoundError when swiftformat not found."""
        formatter = SwiftFormatFormatter()
        with patch(
            "lucidshark.plugins.formatters.swiftformat.shutil.which",
            return_value=None,
        ):
            with pytest.raises(FileNotFoundError, match="swiftformat is not installed"):
                formatter.ensure_binary()


class TestSwiftFormatGetVersion:
    """Tests for get_version method."""

    def test_returns_version(self) -> None:
        """Test get_version returns a version string."""
        formatter = SwiftFormatFormatter()
        with (
            patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            patch(
                "lucidshark.plugins.formatters.swiftformat.get_cli_version",
                return_value="0.53.0",
            ),
        ):
            version = formatter.get_version()
            assert version == "0.53.0"

    def test_returns_unknown_on_error(self) -> None:
        """Test get_version returns 'unknown' when binary not found."""
        formatter = SwiftFormatFormatter()
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            version = formatter.get_version()
            assert version == "unknown"


class TestSwiftFormatCheck:
    """Tests for check method."""

    def test_no_issues_returncode_zero(self) -> None:
        """Test check returns empty when returncode is 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_with_issues(self) -> None:
        """Test check parses lint output with formatting issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            stderr = f"warning: {swift_file}:1:1: (indent) Indent code in accordance with the scope level\n"
            result = make_completed_process(1, "", stderr)
            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert issues[0].domain == ToolDomain.FORMATTING
                assert issues[0].source_tool == "swiftformat"
                assert issues[0].severity == Severity.LOW
                assert issues[0].fixable is True

    def test_multiple_files_with_issues(self) -> None:
        """Test check with issues in multiple files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file_a = project_root / "a.swift"
            swift_file_a.write_text("")
            swift_file_b = project_root / "b.swift"
            swift_file_b.write_text("")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file_a, swift_file_b])

            stderr = (
                f"warning: {swift_file_a}:1:1: (indent) formatting issue\n"
                f"warning: {swift_file_b}:1:1: (indent) formatting issue\n"
            )
            result = make_completed_process(1, "", stderr)
            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert len(issues) == 2

    def test_binary_not_found_returns_empty(self) -> None:
        """Test check returns empty when binary not found."""
        formatter = SwiftFormatFormatter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = formatter.check(context)
            assert issues == []

    def test_timeout_returns_empty(self) -> None:
        """Test check returns empty on timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(
                        cmd="swiftformat", timeout=120
                    ),
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_no_paths_returns_empty(self) -> None:
        """Test check returns empty when no matching paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("x = 1\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [py_file])

            with patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY):
                issues = formatter.check(context)
                assert issues == []

    def test_generic_exception_returns_empty(self) -> None:
        """Test check returns empty on generic exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    side_effect=RuntimeError("unexpected error"),
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_deduplicates_same_file(self) -> None:
        """Test that multiple warnings for the same file produce one issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            stderr = (
                f"warning: {swift_file}:1:1: (indent) issue one\n"
                f"warning: {swift_file}:5:1: (braces) issue two\n"
            )
            result = make_completed_process(1, "", stderr)
            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1

    def test_empty_stdout_and_stderr_nonzero_exit(self) -> None:
        """Test non-zero return code with empty stdout and stderr produces no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            result = make_completed_process(1, "", "")
            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert issues == []


class TestSwiftFormatFix:
    """Tests for fix method."""

    def test_fix_success(self) -> None:
        """Test fix applies formatting and returns FixResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            fix_run_result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    return_value=fix_run_result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 1
                assert result.issues_remaining == 0

    def test_fix_binary_not_found(self) -> None:
        """Test fix returns empty FixResult when binary not found."""
        formatter = SwiftFormatFormatter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = formatter.fix(context)
            assert isinstance(result, FixResult)
            assert result.files_modified == 0
            assert result.issues_fixed == 0

    def test_fix_no_matching_paths(self) -> None:
        """Test fix returns empty FixResult when no .swift files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("x = 1\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [py_file])

            with patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 0
                assert result.issues_fixed == 0

    def test_fix_subprocess_exception(self) -> None:
        """Test fix returns empty FixResult when subprocess raises exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])

            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    side_effect=RuntimeError("swiftformat crashed"),
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 0
                assert result.issues_fixed == 0

    def test_fix_multiple_swift_files(self) -> None:
        """Test fix reports correct files_modified for multiple Swift files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file_a = project_root / "a.swift"
            swift_file_a.write_text("")
            swift_file_b = project_root / "b.swift"
            swift_file_b.write_text("")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file_a, swift_file_b])

            fix_run_result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.swiftformat.run_with_streaming",
                    return_value=fix_run_result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 2


class TestSwiftFormatResolvePaths:
    """Tests for _resolve_paths via the formatter."""

    def test_directories_expanded_to_swift_files(self) -> None:
        """Test directories are expanded to .swift files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            subdir = project_root / "Sources"
            subdir.mkdir()
            swift_file = subdir / "App.swift"
            swift_file.touch()

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [subdir])
            result = formatter._resolve_paths(
                context, SWIFT_EXTENSIONS, fallback_to_cwd=False
            )
            assert result == [str(swift_file)]

    def test_skips_non_swift_files(self) -> None:
        """Test non-Swift files are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("x = 1\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [py_file])
            result = formatter._resolve_paths(
                context, SWIFT_EXTENSIONS, fallback_to_cwd=False
            )
            assert result == []

    def test_includes_swift_files(self) -> None:
        """Test .swift files are included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("import Foundation\n")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file])
            result = formatter._resolve_paths(
                context, SWIFT_EXTENSIONS, fallback_to_cwd=False
            )
            assert result == [str(swift_file)]

    def test_mixed_valid_and_invalid_files(self) -> None:
        """Test filtering with mixed file types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            swift_file = project_root / "App.swift"
            swift_file.write_text("")
            py_file = project_root / "script.py"
            py_file.write_text("")
            txt_file = project_root / "notes.txt"
            txt_file.write_text("")

            formatter = SwiftFormatFormatter(project_root=project_root)
            context = _make_context(project_root, [swift_file, py_file, txt_file])
            result = formatter._resolve_paths(
                context, SWIFT_EXTENSIONS, fallback_to_cwd=False
            )
            assert result == [str(swift_file)]
