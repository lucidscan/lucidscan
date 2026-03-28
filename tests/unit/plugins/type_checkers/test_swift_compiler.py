"""Unit tests for Swift compiler type checker plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.type_checkers.swift_compiler import (
    SwiftCompilerChecker,
    LEVEL_SEVERITY,
    _DIAGNOSTIC_RE,
)
from lucidshark.plugins.swift_utils import generate_issue_id


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
        enabled_domains=enabled_domains or [ToolDomain.TYPE_CHECKING],
    )


FAKE_BINARY = Path("/usr/bin/swift")


class TestSwiftCompilerProperties:
    """Tests for SwiftCompilerChecker basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        checker = SwiftCompilerChecker()
        assert checker.name == "swift_compiler"

    def test_languages(self) -> None:
        """Test supported languages."""
        checker = SwiftCompilerChecker()
        assert checker.languages == ["swift"]

    def test_domain(self) -> None:
        """Test domain is TYPE_CHECKING."""
        checker = SwiftCompilerChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        """Test strict mode is not supported."""
        checker = SwiftCompilerChecker()
        assert checker.supports_strict_mode is False

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            checker = SwiftCompilerChecker(project_root=Path(tmpdir))
            assert checker._project_root == Path(tmpdir)


class TestSwiftCompilerLevelSeverity:
    """Tests for level severity mapping."""

    def test_error_maps_to_high(self) -> None:
        """Test error maps to HIGH."""
        assert LEVEL_SEVERITY["error"] == Severity.HIGH

    def test_warning_maps_to_medium(self) -> None:
        """Test warning maps to MEDIUM."""
        assert LEVEL_SEVERITY["warning"] == Severity.MEDIUM

    def test_note_maps_to_low(self) -> None:
        """Test note maps to LOW."""
        assert LEVEL_SEVERITY["note"] == Severity.LOW


class TestSwiftCompilerDiagnosticRegex:
    """Tests for the diagnostic regex pattern."""

    def test_matches_error_line(self) -> None:
        """Test regex matches a compiler error line."""
        line = "/path/to/File.swift:10:5: error: cannot convert value of type 'Int' to 'String'"
        match = _DIAGNOSTIC_RE.match(line)
        assert match is not None
        assert match.group(1) == "/path/to/File.swift"
        assert match.group(2) == "10"
        assert match.group(3) == "5"
        assert match.group(4) == "error"
        assert match.group(5) == "cannot convert value of type 'Int' to 'String'"

    def test_matches_warning_line(self) -> None:
        """Test regex matches a compiler warning line."""
        line = "Sources/App.swift:20:1: warning: result of call is unused"
        match = _DIAGNOSTIC_RE.match(line)
        assert match is not None
        assert match.group(4) == "warning"

    def test_matches_note_line(self) -> None:
        """Test regex matches a compiler note line."""
        line = "File.swift:5:3: note: did you mean 'foo'?"
        match = _DIAGNOSTIC_RE.match(line)
        assert match is not None
        assert match.group(4) == "note"

    def test_does_not_match_non_diagnostic(self) -> None:
        """Test regex does not match non-diagnostic lines."""
        line = "Building for debugging..."
        match = _DIAGNOSTIC_RE.match(line)
        assert match is None


class TestSwiftCompilerEnsureBinary:
    """Tests for ensure_binary method."""

    def test_found(self) -> None:
        """Test finding swift in system PATH."""
        checker = SwiftCompilerChecker()
        with patch(
            "lucidshark.plugins.swift_utils.shutil.which",
            return_value="/usr/bin/swift",
        ):
            binary = checker.ensure_binary()
            assert binary == Path("/usr/bin/swift")

    def test_not_found(self) -> None:
        """Test FileNotFoundError when swift not found."""
        checker = SwiftCompilerChecker()
        with patch(
            "lucidshark.plugins.swift_utils.shutil.which",
            return_value=None,
        ):
            with pytest.raises(FileNotFoundError, match="swift is not installed"):
                checker.ensure_binary()


class TestSwiftCompilerGetVersion:
    """Tests for get_version method."""

    def test_returns_version(self) -> None:
        """Test get_version returns a version string."""
        checker = SwiftCompilerChecker()
        mock_result = subprocess.CompletedProcess(
            args=["swift", "--version"],
            returncode=0,
            stdout="Swift version 5.9.0 (swift-5.9-RELEASE)",
            stderr="",
        )
        with patch(
            "lucidshark.plugins.swift_utils.subprocess.run",
            return_value=mock_result,
        ):
            version = checker.get_version()
            assert version == "5.9.0"

    def test_returns_unknown_on_error(self) -> None:
        """Test get_version returns 'unknown' when binary not found."""
        checker = SwiftCompilerChecker()
        with patch(
            "lucidshark.plugins.swift_utils.subprocess.run",
            side_effect=FileNotFoundError("not found"),
        ):
            version = checker.get_version()
            assert version == "unknown"


class TestSwiftCompilerCheck:
    """Tests for check method."""

    def test_no_issues(self) -> None:
        """Test check returns empty when no compiler errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            checker = SwiftCompilerChecker(project_root=project_root)
            context = _make_context(project_root, [project_root])

            result = make_completed_process(0, "", "")
            with (
                patch(
                    "lucidshark.plugins.type_checkers.swift_compiler.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert issues == []

    def test_with_compiler_errors(self) -> None:
        """Test check parses compiler error output from stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            checker = SwiftCompilerChecker(project_root=project_root)
            context = _make_context(project_root, [project_root])

            stderr = (
                "/path/to/File.swift:10:5: error: cannot convert value of type 'Int' to 'String'\n"
                "/path/to/File.swift:20:3: warning: result of call is unused\n"
            )
            result = make_completed_process(1, "", stderr)
            with (
                patch(
                    "lucidshark.plugins.type_checkers.swift_compiler.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert len(issues) == 2
                # First issue: error
                assert issues[0].domain == ToolDomain.TYPE_CHECKING
                assert issues[0].source_tool == "swift_compiler"
                assert issues[0].severity == Severity.HIGH
                assert issues[0].rule_id == "error"
                assert issues[0].line_start == 10
                assert issues[0].column_start == 5
                assert "cannot convert" in issues[0].description
                # Second issue: warning
                assert issues[1].severity == Severity.MEDIUM
                assert issues[1].rule_id == "warning"
                assert issues[1].line_start == 20

    def test_no_package_swift_returns_empty(self) -> None:
        """Test check returns empty when no Package.swift exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            checker = SwiftCompilerChecker(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with patch.object(checker, "ensure_binary", return_value=FAKE_BINARY):
                issues = checker.check(context)
                assert issues == []

    def test_binary_not_found_returns_empty(self) -> None:
        """Test check returns empty when binary not found."""
        checker = SwiftCompilerChecker()
        context = _make_context(Path("/tmp"))
        with patch.object(
            checker, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = checker.check(context)
            assert issues == []

    def test_timeout_returns_empty(self) -> None:
        """Test check returns empty on timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            checker = SwiftCompilerChecker(project_root=project_root)
            context = _make_context(project_root, [project_root])

            with (
                patch(
                    "lucidshark.plugins.type_checkers.swift_compiler.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(
                        cmd="swift build", timeout=300
                    ),
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert issues == []

    def test_notes_are_filtered_out(self) -> None:
        """Test that note-level diagnostics are filtered out."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            checker = SwiftCompilerChecker(project_root=project_root)
            context = _make_context(project_root, [project_root])

            stderr = (
                "File.swift:10:5: error: type mismatch\n"
                "File.swift:10:5: note: did you mean to convert?\n"
            )
            result = make_completed_process(1, "", stderr)
            with (
                patch(
                    "lucidshark.plugins.type_checkers.swift_compiler.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                # Only the error should be included, note is filtered
                assert len(issues) == 1
                assert issues[0].rule_id == "error"

    def test_deduplicates_issues(self) -> None:
        """Test that duplicate diagnostics produce only one issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            checker = SwiftCompilerChecker(project_root=project_root)
            context = _make_context(project_root, [project_root])

            stderr = (
                "File.swift:10:5: error: type mismatch\n"
                "File.swift:10:5: error: type mismatch\n"
            )
            result = make_completed_process(1, "", stderr)
            with (
                patch(
                    "lucidshark.plugins.type_checkers.swift_compiler.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert len(issues) == 1

    def test_relative_paths_resolved(self) -> None:
        """Test that relative file paths are resolved against project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Package.swift").write_text(
                "// swift-tools-version:5.9\nimport PackageDescription\n"
            )

            checker = SwiftCompilerChecker(project_root=project_root)
            context = _make_context(project_root, [project_root])

            stderr = "Sources/App.swift:5:1: error: missing return\n"
            result = make_completed_process(1, "", stderr)
            with (
                patch(
                    "lucidshark.plugins.type_checkers.swift_compiler.run_with_streaming",
                    return_value=result,
                ),
                patch.object(checker, "ensure_binary", return_value=FAKE_BINARY),
            ):
                issues = checker.check(context)
                assert len(issues) == 1
                assert issues[0].file_path == project_root / "Sources" / "App.swift"


class TestSwiftCompilerParseOutput:
    """Tests for _parse_output method."""

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        checker = SwiftCompilerChecker()
        issues = checker._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_whitespace_output(self) -> None:
        """Test parsing whitespace-only output."""
        checker = SwiftCompilerChecker()
        issues = checker._parse_output("   \n  ", Path("/project"))
        assert issues == []

    def test_parse_mixed_output(self) -> None:
        """Test parsing output with non-diagnostic lines mixed in."""
        checker = SwiftCompilerChecker()
        output = (
            "Building for debugging...\n"
            "Compiling MyModule File.swift\n"
            "/project/File.swift:10:5: error: bad type\n"
            "Build complete!\n"
        )
        issues = checker._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "error"


class TestSwiftCompilerIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_deterministic_ids(self) -> None:
        """Test same input produces same ID."""
        id1 = generate_issue_id("swift-compiler", "error", "File.swift", 10, 5, "msg")
        id2 = generate_issue_id("swift-compiler", "error", "File.swift", 10, 5, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        """Test different inputs produce different IDs."""
        id1 = generate_issue_id("swift-compiler", "error", "a.swift", 1, 1, "msg")
        id2 = generate_issue_id("swift-compiler", "warning", "a.swift", 1, 1, "msg")
        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID starts with tool name."""
        issue_id = generate_issue_id("swift-compiler", "error", "f.swift", 1, 1, "msg")
        assert issue_id.startswith("swift-compiler-")
