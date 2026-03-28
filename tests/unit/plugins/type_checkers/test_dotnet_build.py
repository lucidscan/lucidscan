"""Unit tests for dotnet build type checker plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.type_checkers.dotnet_build import DotnetBuildChecker


def _make_context(project_root: Path) -> ScanContext:
    return ScanContext(
        project_root=project_root,
        paths=[project_root],
        enabled_domains=[ToolDomain.TYPE_CHECKING],
    )


FAKE_BINARY = Path("/usr/bin/dotnet")


class TestDotnetBuildCheckerProperties:
    """Basic property tests."""

    def test_name(self) -> None:
        checker = DotnetBuildChecker()
        assert checker.name == "dotnet_build"

    def test_languages(self) -> None:
        checker = DotnetBuildChecker()
        assert checker.languages == ["csharp"]

    def test_domain(self) -> None:
        checker = DotnetBuildChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        checker = DotnetBuildChecker()
        assert checker.supports_strict_mode is True


class TestDotnetBuildCheckerEnsureBinary:
    def test_found(self) -> None:
        checker = DotnetBuildChecker()
        with patch("shutil.which", return_value="/usr/bin/dotnet"):
            binary = checker.ensure_binary()
            assert binary == Path("/usr/bin/dotnet")

    def test_not_found(self) -> None:
        checker = DotnetBuildChecker()
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError):
                checker.ensure_binary()


class TestDotnetBuildCheckerCheck:
    """Tests for check method."""

    def test_no_project_file_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = DotnetBuildChecker()
            context = _make_context(Path(tmpdir))
            with patch.object(checker, "ensure_binary", return_value=FAKE_BINARY):
                issues = checker.check(context)
                assert issues == []

    def test_binary_not_found(self) -> None:
        checker = DotnetBuildChecker()
        context = _make_context(Path("/tmp"))
        with patch.object(
            checker, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = checker.check(context)
            assert issues == []

    def test_parses_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            checker = DotnetBuildChecker()
            context = _make_context(project_root)

            stderr = (
                "src/Program.cs(10,5): error CS0103: The name 'x' does not exist "
                "in the current context [MyApp.csproj]\n"
            )
            result = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=stderr
            )

            with (
                patch(
                    "lucidshark.plugins.type_checkers.dotnet_build.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert len(issues) == 1
                assert issues[0].severity == Severity.HIGH
                assert issues[0].rule_id == "CS0103"
                assert issues[0].domain == ToolDomain.TYPE_CHECKING
                assert issues[0].source_tool == "dotnet_build"
                assert issues[0].line_start == 10
                assert issues[0].column_start == 5

    def test_parses_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            checker = DotnetBuildChecker()
            context = _make_context(project_root)

            stderr = (
                "src/Utils.cs(20,15): warning CS8600: Converting null literal "
                "or possible null value to non-nullable type [MyApp.csproj]\n"
            )
            result = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=stderr
            )

            with (
                patch(
                    "lucidshark.plugins.type_checkers.dotnet_build.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert len(issues) == 1
                assert issues[0].severity == Severity.HIGH  # CS8600 is high severity
                assert issues[0].rule_id == "CS8600"

    def test_parses_multiple_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            checker = DotnetBuildChecker()
            context = _make_context(project_root)

            stderr = (
                "src/A.cs(1,1): error CS0103: The name 'x' does not exist [A.csproj]\n"
                "src/B.cs(2,2): warning CS0168: Variable declared but never used [B.csproj]\n"
            )
            result = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=stderr
            )

            with (
                patch(
                    "lucidshark.plugins.type_checkers.dotnet_build.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert len(issues) == 2

    def test_timeout_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            checker = DotnetBuildChecker()
            context = _make_context(project_root)

            with (
                patch(
                    "lucidshark.plugins.type_checkers.dotnet_build.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(cmd="dotnet", timeout=300),
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert issues == []

    def test_clean_build_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            checker = DotnetBuildChecker()
            context = _make_context(project_root)

            result = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="Build succeeded.\n", stderr=""
            )

            with (
                patch(
                    "lucidshark.plugins.type_checkers.dotnet_build.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert issues == []

    def test_deduplicates_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "MyApp.csproj").touch()

            checker = DotnetBuildChecker()
            context = _make_context(project_root)

            stderr = (
                "src/A.cs(1,1): error CS0103: The name 'x' does not exist [A.csproj]\n"
                "src/A.cs(1,1): error CS0103: The name 'x' does not exist [A.csproj]\n"
            )
            result = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr=stderr
            )

            with (
                patch(
                    "lucidshark.plugins.type_checkers.dotnet_build.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert len(issues) == 1


class TestDotnetBuildParseOutput:
    """Tests for _parse_output method."""

    def test_empty_output(self) -> None:
        checker = DotnetBuildChecker()
        assert checker._parse_output("", Path("/tmp")) == []

    def test_no_cs_diagnostics(self) -> None:
        checker = DotnetBuildChecker()
        output = "Build succeeded.\n0 Error(s), 0 Warning(s)\n"
        assert checker._parse_output(output, Path("/tmp")) == []

    def test_severity_mapping_error(self) -> None:
        checker = DotnetBuildChecker()
        output = "src/A.cs(1,1): error CS9999: Unknown error [A.csproj]\n"
        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.HIGH  # errors are HIGH

    def test_severity_mapping_warning(self) -> None:
        checker = DotnetBuildChecker()
        output = "src/A.cs(1,1): warning CS9999: Unknown warning [A.csproj]\n"
        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM  # generic warnings are MEDIUM
