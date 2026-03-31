"""Unit tests for dotnet format linter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.dotnet_utils import find_dotnet, find_project_file
from lucidshark.plugins.linters.dotnet_format import DotnetFormatLinter


class TestDotnetFormatLinterProperties:
    """Basic property tests for DotnetFormatLinter."""

    def test_name(self) -> None:
        linter = DotnetFormatLinter()
        assert linter.name == "dotnet_format"

    def test_languages(self) -> None:
        linter = DotnetFormatLinter()
        assert linter.languages == ["csharp"]

    def test_domain(self) -> None:
        linter = DotnetFormatLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        linter = DotnetFormatLinter()
        assert linter.supports_fix is True


class TestFindDotnet:
    """Tests for find_dotnet helper."""

    @patch("shutil.which", return_value="/usr/bin/dotnet")
    def test_found(self, mock_which: MagicMock) -> None:
        result = find_dotnet()
        assert result == Path("/usr/bin/dotnet")

    @patch("shutil.which", return_value=None)
    def test_not_found(self, mock_which: MagicMock) -> None:
        with pytest.raises(FileNotFoundError, match="dotnet is not installed"):
            find_dotnet()


class TestFindProjectFile:
    """Tests for find_project_file helper."""

    def test_finds_sln(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.sln").touch()
            result = find_project_file(project_root)
            assert result is not None
            assert result.suffix == ".sln"

    def test_finds_csproj(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()
            result = find_project_file(project_root)
            assert result is not None
            assert result.suffix == ".csproj"

    def test_prefers_sln_over_csproj(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.sln").touch()
            (project_root / "MyApp.csproj").touch()
            result = find_project_file(project_root)
            assert result is not None
            assert result.suffix == ".sln"

    def test_finds_nested_csproj(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            subdir = project_root / "src"
            subdir.mkdir()
            (subdir / "MyApp.csproj").touch()
            result = find_project_file(project_root)
            assert result is not None
            assert result.suffix == ".csproj"

    def test_returns_none_when_nothing_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            result = find_project_file(project_root)
            assert result is None


def _make_context(project_root: Path) -> ScanContext:
    return ScanContext(
        project_root=project_root,
        paths=[project_root],
        enabled_domains=[ToolDomain.LINTING],
    )


FAKE_BINARY = Path("/usr/bin/dotnet")


class TestDotnetFormatLinterLint:
    """Tests for lint method."""

    def test_no_project_file_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = DotnetFormatLinter()
            context = _make_context(Path(tmpdir))
            with patch.object(linter, "ensure_binary", return_value=FAKE_BINARY):
                issues = linter.lint(context)
                assert issues == []

    def test_binary_not_found_returns_empty(self) -> None:
        linter = DotnetFormatLinter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            linter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = linter.lint(context)
            assert issues == []

    def test_parses_diagnostic_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            linter = DotnetFormatLinter()
            context = _make_context(project_root)

            stdout = (
                "src/Program.cs(10,5): warning IDE0055: Fix formatting [MyApp.csproj]\n"
                "src/Utils.cs(20,1): info IDE0003: Remove this qualification [MyApp.csproj]\n"
            )
            result = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=stdout, stderr=""
            )

            with (
                patch(
                    "lucidshark.plugins.linters.dotnet_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert len(issues) == 2
                assert issues[0].severity == Severity.MEDIUM
                assert issues[0].rule_id == "IDE0055"
                assert issues[0].domain == ToolDomain.LINTING
                assert issues[0].source_tool == "dotnet_format"
                assert issues[1].severity == Severity.LOW
                assert issues[1].rule_id == "IDE0003"

    def test_parses_error_severity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            linter = DotnetFormatLinter()
            context = _make_context(project_root)

            stdout = (
                "src/Broken.cs(5,10): error IDE0001: Simplify name [MyApp.csproj]\n"
            )
            result = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=stdout, stderr=""
            )

            with (
                patch(
                    "lucidshark.plugins.linters.dotnet_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert len(issues) == 1
                assert issues[0].severity == Severity.HIGH

    def test_deduplicates_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            linter = DotnetFormatLinter()
            context = _make_context(project_root)

            # Same diagnostic twice
            stdout = (
                "src/Program.cs(10,5): warning IDE0055: Fix formatting [MyApp.csproj]\n"
                "src/Program.cs(10,5): warning IDE0055: Fix formatting [MyApp.csproj]\n"
            )
            result = subprocess.CompletedProcess(
                args=[], returncode=1, stdout=stdout, stderr=""
            )

            with (
                patch(
                    "lucidshark.plugins.linters.dotnet_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert len(issues) == 1

    def test_timeout_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            linter = DotnetFormatLinter()
            context = _make_context(project_root)

            with (
                patch(
                    "lucidshark.plugins.linters.dotnet_format.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(cmd="dotnet", timeout=300),
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_clean_code_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            linter = DotnetFormatLinter()
            context = _make_context(project_root)

            result = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

            with (
                patch(
                    "lucidshark.plugins.linters.dotnet_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(linter, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = linter.lint(context)
                assert issues == []


class TestDotnetFormatLinterParseOutput:
    """Tests for _parse_output method."""

    def test_empty_output(self) -> None:
        linter = DotnetFormatLinter()
        assert linter._parse_output("", Path("/tmp")) == []

    def test_no_diagnostics(self) -> None:
        linter = DotnetFormatLinter()
        output = "Build succeeded.\n0 Error(s), 0 Warning(s)\n"
        assert linter._parse_output(output, Path("/tmp")) == []

    def test_extracts_file_path_and_line(self) -> None:
        linter = DotnetFormatLinter()
        output = "src/App.cs(42,8): warning IDE0055: Fix formatting [MyApp.csproj]\n"
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].line_start == 42
        assert issues[0].column_start == 8
        assert issues[0].file_path == Path("/project/src/App.cs")

    def test_without_column(self) -> None:
        linter = DotnetFormatLinter()
        output = "src/App.cs(42): warning IDE0055: Fix formatting [MyApp.csproj]\n"
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].line_start == 42
        assert issues[0].column_start is None
