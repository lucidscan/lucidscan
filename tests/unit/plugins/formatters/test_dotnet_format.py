"""Unit tests for dotnet format formatter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.formatters.dotnet_format import (
    CS_EXTENSIONS,
    DotnetFormatFormatter,
)
from lucidshark.plugins.linters.base import FixResult


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _make_context(project_root: Path, paths: list[Path] | None = None) -> ScanContext:
    return ScanContext(
        project_root=project_root,
        paths=paths or [],
        enabled_domains=[ToolDomain.FORMATTING],
    )


FAKE_BINARY = Path("/usr/bin/dotnet")


class TestDotnetFormatFormatterProperties:
    def test_name(self) -> None:
        formatter = DotnetFormatFormatter()
        assert formatter.name == "dotnet_format_whitespace"

    def test_languages(self) -> None:
        formatter = DotnetFormatFormatter()
        assert formatter.languages == ["csharp"]

    def test_domain(self) -> None:
        formatter = DotnetFormatFormatter()
        assert formatter.domain == ToolDomain.FORMATTING

    def test_extensions(self) -> None:
        assert ".cs" in CS_EXTENSIONS

    def test_supports_fix(self) -> None:
        formatter = DotnetFormatFormatter()
        assert formatter.supports_fix is True


class TestDotnetFormatFormatterGetVersion:
    def test_get_version_success(self) -> None:
        formatter = DotnetFormatFormatter()
        with (
            patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            patch(
                "lucidshark.plugins.formatters.dotnet_format.get_cli_version",
                return_value="8.0.100",
            ),
        ):
            version = formatter.get_version()
            assert version == "8.0.100"

    def test_get_version_binary_not_found(self) -> None:
        formatter = DotnetFormatFormatter()
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            version = formatter.get_version()
            assert version == "unknown"


class TestDotnetFormatFormatterEnsureBinary:
    def test_not_found(self) -> None:
        formatter = DotnetFormatFormatter()
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError):
                formatter.ensure_binary()

    def test_found(self) -> None:
        formatter = DotnetFormatFormatter()
        with patch("shutil.which", return_value="/usr/bin/dotnet"):
            binary = formatter.ensure_binary()
            assert binary == Path("/usr/bin/dotnet")


class TestDotnetFormatFormatterCheck:
    def test_check_no_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            formatter = DotnetFormatFormatter()
            context = _make_context(project_root)

            result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.dotnet_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_with_formatting_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            formatter = DotnetFormatFormatter()
            context = _make_context(project_root)

            stdout = "Formatted code file 'src/Program.cs'.\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.dotnet_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert issues[0].domain == ToolDomain.FORMATTING
                assert issues[0].source_tool == "dotnet_format_whitespace"
                assert issues[0].severity == Severity.LOW
                assert issues[0].fixable is True

    def test_check_no_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            formatter = DotnetFormatFormatter()
            context = _make_context(Path(tmpdir))

            with patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY):
                issues = formatter.check(context)
                assert issues == []

    def test_check_binary_not_found(self) -> None:
        formatter = DotnetFormatFormatter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = formatter.check(context)
            assert issues == []

    def test_check_timeout_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            formatter = DotnetFormatFormatter()
            context = _make_context(project_root)

            with (
                patch(
                    "lucidshark.plugins.formatters.dotnet_format.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(cmd="dotnet", timeout=120),
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_deduplicates_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            formatter = DotnetFormatFormatter()
            context = _make_context(project_root)

            stdout = (
                "Formatted code file 'src/Program.cs'.\n"
                "Formatted code file 'src/Program.cs'.\n"
            )
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.dotnet_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1


class TestDotnetFormatFormatterFix:
    def test_fix_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            formatter = DotnetFormatFormatter()
            context = _make_context(project_root)

            fix_run_result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.dotnet_format.run_with_streaming",
                    return_value=fix_run_result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)

    def test_fix_binary_not_found(self) -> None:
        formatter = DotnetFormatFormatter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = formatter.fix(context)
            assert isinstance(result, FixResult)
            assert result.files_modified == 0

    def test_fix_no_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            formatter = DotnetFormatFormatter()
            context = _make_context(Path(tmpdir))
            with patch.object(formatter, "ensure_binary", return_value=FAKE_BINARY):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 0
