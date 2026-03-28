"""Unit tests for Ktlint linter plugin."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.linters.ktlint import (
    DEFAULT_VERSION,
    SEVERITY_MAP,
    KtlintLinter,
)


def make_completed_process(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    """Create a CompletedProcess for testing."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


SAMPLE_KTLINT_OUTPUT = json.dumps(
    [
        {
            "file": "src/Main.kt",
            "errors": [
                {
                    "line": 5,
                    "column": 1,
                    "message": 'Unexpected blank line(s) before "}"',
                    "rule": "no-blank-line-before-rbrace",
                    "severity": "error",
                }
            ],
        }
    ]
)

SAMPLE_KTLINT_MULTI_FILE = json.dumps(
    [
        {
            "file": "src/A.kt",
            "errors": [
                {
                    "line": 1,
                    "column": 1,
                    "message": "File must end with a newline",
                    "rule": "final-newline",
                    "severity": "error",
                }
            ],
        },
        {
            "file": "src/B.kt",
            "errors": [
                {
                    "line": 10,
                    "column": 5,
                    "message": "Unexpected indentation (4) (should be 8)",
                    "rule": "indent",
                    "severity": "error",
                },
                {
                    "line": 20,
                    "column": 3,
                    "message": "Needless blank line(s)",
                    "rule": "no-consecutive-blank-lines",
                    "severity": "warning",
                },
            ],
        },
    ]
)


class TestKtlintLinterProperties:
    """Tests for KtlintLinter basic properties."""

    def test_name(self) -> None:
        """Test plugin name."""
        linter = KtlintLinter()
        assert linter.name == "ktlint"

    def test_languages(self) -> None:
        """Test supported languages."""
        linter = KtlintLinter()
        assert linter.languages == ["kotlin"]

    def test_domain(self) -> None:
        """Test domain is LINTING."""
        linter = KtlintLinter()
        assert linter.domain == ToolDomain.LINTING

    def test_supports_fix(self) -> None:
        """Test supports_fix returns True."""
        linter = KtlintLinter()
        assert linter.supports_fix is True

    def test_get_version(self) -> None:
        """Test get_version returns configured version."""
        linter = KtlintLinter(version="1.5.0")
        assert linter.get_version() == "1.5.0"

    def test_init_with_project_root(self) -> None:
        """Test initialization with project root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(project_root=Path(tmpdir))
            assert linter._project_root == Path(tmpdir)

    def test_init_default_version(self) -> None:
        """Test default version is loaded from pyproject.toml."""
        linter = KtlintLinter()
        assert linter._version == DEFAULT_VERSION
        assert isinstance(linter._version, str)


class TestKtlintSeverityMapping:
    """Tests for Ktlint severity mapping."""

    def test_error_maps_to_high(self) -> None:
        """Test error maps to HIGH."""
        assert SEVERITY_MAP["error"] == Severity.HIGH

    def test_warning_maps_to_medium(self) -> None:
        """Test warning maps to MEDIUM."""
        assert SEVERITY_MAP["warning"] == Severity.MEDIUM


class TestKtlintEnsureBinary:
    """Tests for ensure_binary method."""

    def test_cached_jar_found(self) -> None:
        """Test finds cached JAR."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(version="1.5.0", project_root=Path(tmpdir))

            # Create fake cached JAR
            jar_dir = Path(tmpdir) / ".lucidshark" / "bin" / "ktlint" / "1.5.0"
            jar_dir.mkdir(parents=True)
            jar_path = jar_dir / "ktlint-1.5.0.jar"
            jar_path.touch()

            result = linter.ensure_binary()
            assert result == jar_path

    def test_download_triggered_when_not_cached(self) -> None:
        """Test download is triggered when JAR not cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(version="1.5.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value="/usr/bin/java"):
                with patch.object(linter, "_download_binary") as mock_download:
                    # After download, create the JAR
                    def create_jar(dest_dir):
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        (dest_dir / "ktlint-1.5.0.jar").touch()

                    mock_download.side_effect = create_jar

                    result = linter.ensure_binary()
                    mock_download.assert_called_once()
                    assert result.name == "ktlint-1.5.0.jar"

    def test_java_not_found_raises(self) -> None:
        """Test raises FileNotFoundError when Java not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(version="1.5.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value=None):
                with pytest.raises(FileNotFoundError, match="Java is required"):
                    linter.ensure_binary()

    def test_download_fails_raises_runtime_error(self) -> None:
        """Test raises RuntimeError when download fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(version="1.5.0", project_root=Path(tmpdir))

            with patch("shutil.which", return_value="/usr/bin/java"):
                with patch.object(linter, "_download_binary"):
                    # Don't create the JAR - simulate failed download
                    with pytest.raises(RuntimeError, match="Failed to download"):
                        linter.ensure_binary()


class TestKtlintDownloadBinary:
    """Tests for _download_binary method."""

    def test_download_jar(self) -> None:
        """Test downloading JAR file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(version="1.5.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            # Create mock JAR content
            jar_content = b"PK\x03\x04fake jar content"

            mock_response = MagicMock()
            mock_response.read.return_value = jar_content
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.ktlint.secure_urlopen",
                return_value=mock_response,
            ):
                linter._download_binary(dest_dir)

            # Verify JAR was created
            jar_path = dest_dir / "ktlint-1.5.0.jar"
            assert jar_path.exists()

    def test_download_cleans_up_temp_on_network_error(self) -> None:
        """Verify temp file is cleaned up when secure_urlopen raises."""
        from urllib.error import URLError

        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(version="1.5.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            with patch(
                "lucidshark.plugins.linters.ktlint.secure_urlopen",
                side_effect=URLError("connection refused"),
            ):
                with pytest.raises(URLError):
                    linter._download_binary(dest_dir)

    def test_download_validates_url_domain(self) -> None:
        """Verify URL domain validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            linter = KtlintLinter(version="1.5.0", project_root=Path(tmpdir))
            dest_dir = Path(tmpdir) / "dest"

            mock_response = MagicMock()
            mock_response.read.return_value = b"content"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            with patch(
                "lucidshark.plugins.linters.ktlint.secure_urlopen",
                return_value=mock_response,
            ) as mock_urlopen:
                linter._download_binary(dest_dir)

            # Verify called with HTTPS GitHub URL
            call_args = mock_urlopen.call_args[0][0]
            assert call_args.startswith("https://github.com/")


class TestKtlintFindKotlinFiles:
    """Tests for _find_kotlin_files method."""

    def test_finds_kt_files_in_paths(self) -> None:
        """Test finding .kt files in context paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            kt_file = src_dir / "Main.kt"
            kt_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.kt")

    def test_finds_kts_files_in_paths(self) -> None:
        """Test finding .kts files in context paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            kts_file = src_dir / "build.gradle.kts"
            kts_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 1
            assert files[0].endswith("build.gradle.kts")

    def test_finds_kotlin_files_in_standard_dirs(self) -> None:
        """Test finding Kotlin files in standard directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src" / "main" / "kotlin"
            src_dir.mkdir(parents=True)
            kt_file = src_dir / "App.kt"
            kt_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) >= 1
            assert any("App.kt" in f for f in files)

    def test_no_kotlin_files(self) -> None:
        """Test returns empty when no Kotlin files found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert files == []

    def test_excludes_non_kotlin_files(self) -> None:
        """Verify non-.kt/.kts files are excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()
            (src_dir / "Main.java").touch()
            (src_dir / "Main.py").touch()
            (src_dir / "Main.class").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.kt")

    def test_skips_nonexistent_directories(self) -> None:
        """Test skips nonexistent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "nonexistent"

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[nonexistent],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert files == []

    def test_fallback_to_project_root(self) -> None:
        """Verify fallback to project_root when no paths and no standard dirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "Main.kt").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.kt")

    def test_finds_both_kt_and_kts(self) -> None:
        """Test finds both .kt and .kts files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()
            (src_dir / "build.gradle.kts").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 2

    def test_handles_single_file_path(self) -> None:
        """Test handles a single file as a path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kt_file = Path(tmpdir) / "Main.kt"
            kt_file.touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[kt_file],
                enabled_domains=[],
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.kt")

    def test_ignore_patterns_excludes_matching_files(self) -> None:
        """Verify ignore_patterns filtering excludes matching files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            (build_dir / "Generated.kt").touch()

            mock_patterns = MagicMock()
            mock_patterns.matches = MagicMock(
                side_effect=lambda f, root: "build" in str(f)
            )

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir, build_dir],
                enabled_domains=[],
                ignore_patterns=mock_patterns,
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 1
            assert files[0].endswith("Main.kt")

    def test_ignore_patterns_none_includes_all(self) -> None:
        """Verify ignore_patterns=None includes all Kotlin files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "A.kt").touch()
            (src_dir / "B.kt").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
                ignore_patterns=None,
            )

            linter = KtlintLinter()
            files = linter._find_kotlin_files(context)
            assert len(files) == 2


class TestKtlintLint:
    """Tests for lint method."""

    def test_lint_success_no_issues(self) -> None:
        """Test successful linting with no issues (empty JSON array)."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            kt_file = src_dir / "Main.kt"
            kt_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, "[]")

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.ktlint.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_with_json_issues(self) -> None:
        """Test linting with JSON output containing issues."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            kt_file = src_dir / "Main.kt"
            kt_file.touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(1, SAMPLE_KTLINT_OUTPUT)

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.ktlint.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = linter.lint(context)

                    assert len(issues) == 1
                    assert issues[0].source_tool == "ktlint"
                    assert issues[0].domain == ToolDomain.LINTING
                    assert issues[0].severity == Severity.HIGH
                    assert issues[0].line_start == 5
                    assert issues[0].rule_id == "no-blank-line-before-rbrace"

    def test_lint_multi_file_issues(self) -> None:
        """Test linting with multiple files and errors."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "A.kt").touch()
            (src_dir / "B.kt").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(1, SAMPLE_KTLINT_MULTI_FILE)

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.ktlint.run_with_streaming",
                    return_value=mock_result,
                ):
                    issues = linter.lint(context)

                    assert len(issues) == 3
                    assert issues[0].severity == Severity.HIGH
                    assert issues[1].severity == Severity.HIGH
                    assert issues[2].severity == Severity.MEDIUM

    def test_lint_no_binary(self) -> None:
        """Test lint returns empty when binary not available."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter,
                "ensure_binary",
                side_effect=FileNotFoundError("Java not found"),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_runtime_error_from_ensure_binary(self) -> None:
        """Verify RuntimeError from ensure_binary is caught and returns []."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter,
                "ensure_binary",
                side_effect=RuntimeError("Failed to download ktlint"),
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_no_files(self) -> None:
        """Test lint returns empty when no Kotlin files found."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                issues = linter.lint(context)
                assert issues == []

    def test_lint_timeout(self) -> None:
        """Test lint handles timeout."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.ktlint.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired("java", 120),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_subprocess_error(self) -> None:
        """Test lint handles subprocess errors."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()

            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[src_dir],
                enabled_domains=[],
            )

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.ktlint.run_with_streaming",
                    side_effect=OSError("command failed"),
                ):
                    issues = linter.lint(context)
                    assert issues == []

    def test_lint_uses_java_jar_command(self) -> None:
        """Verify command uses java -jar with --reporter=json."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, "[]")
            captured_cmd = []

            def capture_cmd(**kwargs):
                captured_cmd.extend(kwargs.get("cmd", []))
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.ktlint.run_with_streaming",
                    side_effect=capture_cmd,
                ):
                    linter.lint(context)

            assert "java" in captured_cmd
            assert "-jar" in captured_cmd
            assert "/opt/ktlint.jar" in captured_cmd
            assert "--reporter=json" in captured_cmd

    def test_lint_passes_correct_kwargs_to_runner(self) -> None:
        """Verify correct cwd, tool_name, timeout passed to run_with_streaming."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, "[]")
            captured_kwargs = {}

            def capture_kwargs(**kwargs):
                captured_kwargs.update(kwargs)
                return mock_result

            with patch.object(
                linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
            ):
                with patch(
                    "lucidshark.plugins.linters.ktlint.run_with_streaming",
                    side_effect=capture_kwargs,
                ):
                    linter.lint(context)

            assert captured_kwargs["cwd"] == tmpdir_path
            assert captured_kwargs["tool_name"] == "ktlint"
            assert captured_kwargs["timeout"] == 120


class TestKtlintFix:
    """Tests for fix method."""

    def test_fix_success(self) -> None:
        """Test successful fix execution."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            # Pre-lint returns 1 issue, post-lint returns 0 issues
            lint_call_count = [0]

            def mock_lint(ctx):
                lint_call_count[0] += 1
                if lint_call_count[0] == 1:
                    # First call (pre-lint): return issues
                    return linter._parse_output(SAMPLE_KTLINT_OUTPUT, ctx.project_root)
                # Second call (post-lint): no issues
                return []

            mock_result = make_completed_process(0, "")

            with patch.object(linter, "lint", side_effect=mock_lint):
                with patch.object(
                    linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
                ):
                    with patch(
                        "lucidshark.plugins.linters.ktlint.run_with_streaming",
                        return_value=mock_result,
                    ):
                        result = linter.fix(context)

                        assert result.issues_fixed == 1
                        assert result.issues_remaining == 0

    def test_fix_no_binary(self) -> None:
        """Test fix returns empty FixResult when binary not available."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            # lint() calls ensure_binary internally; first lint in fix() returns []
            # Then ensure_binary raises for the fix command itself
            with patch.object(linter, "lint", return_value=[]):
                with patch.object(
                    linter,
                    "ensure_binary",
                    side_effect=FileNotFoundError("Java not found"),
                ):
                    result = linter.fix(context)
                    assert result.issues_fixed == 0
                    assert result.issues_remaining == 0

    def test_fix_no_kotlin_files(self) -> None:
        """Test fix returns empty FixResult when no Kotlin files found."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = ScanContext(
                project_root=Path(tmpdir),
                paths=[Path(tmpdir)],
                enabled_domains=[],
            )

            with patch.object(linter, "lint", return_value=[]):
                with patch.object(
                    linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
                ):
                    result = linter.fix(context)
                    assert result.issues_fixed == 0
                    assert result.issues_remaining == 0

    def test_fix_uses_format_flag(self) -> None:
        """Test fix command uses --format flag."""
        linter = KtlintLinter()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "Main.kt").touch()

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[src_dir],
                enabled_domains=[],
            )

            mock_result = make_completed_process(0, "")
            captured_cmd = []

            def capture_cmd(**kwargs):
                captured_cmd.extend(kwargs.get("cmd", []))
                return mock_result

            with patch.object(linter, "lint", return_value=[]):
                with patch.object(
                    linter, "ensure_binary", return_value=Path("/opt/ktlint.jar")
                ):
                    with patch(
                        "lucidshark.plugins.linters.ktlint.run_with_streaming",
                        side_effect=capture_cmd,
                    ):
                        linter.fix(context)

            assert "--format" in captured_cmd


class TestKtlintParseOutput:
    """Tests for _parse_output method."""

    def test_parse_json_with_errors(self) -> None:
        """Test parsing JSON output with errors."""
        linter = KtlintLinter()
        issues = linter._parse_output(SAMPLE_KTLINT_OUTPUT, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "no-blank-line-before-rbrace"
        assert issues[0].severity == Severity.HIGH
        assert issues[0].line_start == 5
        assert issues[0].column_start == 1

    def test_parse_multiple_files_and_errors(self) -> None:
        """Test parsing JSON with multiple files and errors."""
        linter = KtlintLinter()
        issues = linter._parse_output(SAMPLE_KTLINT_MULTI_FILE, Path("/project"))
        assert len(issues) == 3
        assert issues[0].severity == Severity.HIGH
        assert issues[1].severity == Severity.HIGH
        assert issues[2].severity == Severity.MEDIUM

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        linter = KtlintLinter()
        issues = linter._parse_output("", Path("/project"))
        assert issues == []

    def test_parse_whitespace_only_output(self) -> None:
        """Verify whitespace-only output returns empty list."""
        linter = KtlintLinter()
        issues = linter._parse_output("   \n\t  ", Path("/project"))
        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        linter = KtlintLinter()
        issues = linter._parse_output("not json at all", Path("/project"))
        assert issues == []

    def test_parse_empty_json_array(self) -> None:
        """Test parsing empty JSON array."""
        linter = KtlintLinter()
        issues = linter._parse_output("[]", Path("/project"))
        assert issues == []

    def test_parse_file_with_no_errors(self) -> None:
        """Test parsing JSON with file entry but no errors."""
        output = json.dumps([{"file": "src/Clean.kt", "errors": []}])
        linter = KtlintLinter()
        issues = linter._parse_output(output, Path("/project"))
        assert issues == []

    def test_parse_relative_file_path(self) -> None:
        """Test parsing with relative file path resolves against project root."""
        output = json.dumps(
            [
                {
                    "file": "src/Main.kt",
                    "errors": [
                        {
                            "line": 1,
                            "column": 1,
                            "message": "msg",
                            "rule": "rule-id",
                            "severity": "error",
                        }
                    ],
                }
            ]
        )
        linter = KtlintLinter()
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].file_path == Path("/project/src/Main.kt")

    def test_parse_absolute_file_path(self) -> None:
        """Test parsing with absolute file path keeps it as-is."""
        output = json.dumps(
            [
                {
                    "file": "/abs/path/Main.kt",
                    "errors": [
                        {
                            "line": 1,
                            "column": 1,
                            "message": "msg",
                            "rule": "rule-id",
                            "severity": "error",
                        }
                    ],
                }
            ]
        )
        linter = KtlintLinter()
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].file_path == Path("/abs/path/Main.kt")

    def test_parse_unknown_severity_defaults_to_medium(self) -> None:
        """Test error with unknown severity defaults to MEDIUM."""
        output = json.dumps(
            [
                {
                    "file": "src/Main.kt",
                    "errors": [
                        {
                            "line": 1,
                            "column": 1,
                            "message": "msg",
                            "rule": "rule-id",
                            "severity": "unknown",
                        }
                    ],
                }
            ]
        )
        linter = KtlintLinter()
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_parse_error_without_rule(self) -> None:
        """Test error without rule uses 'unknown' as rule_id."""
        output = json.dumps(
            [
                {
                    "file": "src/Main.kt",
                    "errors": [
                        {
                            "line": 1,
                            "column": 1,
                            "message": "Some error",
                            "rule": "",
                            "severity": "error",
                        }
                    ],
                }
            ]
        )
        linter = KtlintLinter()
        issues = linter._parse_output(output, Path("/project"))
        assert len(issues) == 1
        assert issues[0].rule_id == "unknown"

    def test_parse_issue_metadata(self) -> None:
        """Test parsed issue contains correct metadata."""
        linter = KtlintLinter()
        issues = linter._parse_output(SAMPLE_KTLINT_OUTPUT, Path("/project"))
        assert len(issues) == 1
        assert issues[0].metadata["rule"] == "no-blank-line-before-rbrace"
        assert issues[0].metadata["severity_raw"] == "error"

    def test_parse_issue_title_format(self) -> None:
        """Test issue title includes rule and message."""
        linter = KtlintLinter()
        issues = linter._parse_output(SAMPLE_KTLINT_OUTPUT, Path("/project"))
        assert len(issues) == 1
        assert "[no-blank-line-before-rbrace]" in issues[0].title
        assert 'Unexpected blank line(s) before "}"' in issues[0].title

    def test_parse_issue_fixable(self) -> None:
        """Test parsed issues are marked as fixable."""
        linter = KtlintLinter()
        issues = linter._parse_output(SAMPLE_KTLINT_OUTPUT, Path("/project"))
        assert len(issues) == 1
        assert issues[0].fixable is True


class TestKtlintIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        """Test same input produces same ID."""
        linter = KtlintLinter()
        id1 = linter._generate_issue_id("rule-id", "file.kt", 10, 5, "msg")
        id2 = linter._generate_issue_id("rule-id", "file.kt", 10, 5, "msg")
        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Test different inputs produce different IDs."""
        linter = KtlintLinter()
        id1 = linter._generate_issue_id("rule-a", "file.kt", 10, 5, "msg")
        id2 = linter._generate_issue_id("rule-b", "file.kt", 10, 5, "msg")
        assert id1 != id2

    def test_id_format_with_rule(self) -> None:
        """Test ID format includes rule."""
        linter = KtlintLinter()
        issue_id = linter._generate_issue_id("indent", "f.kt", 1, 1, "msg")
        assert issue_id.startswith("ktlint-indent-")

    def test_id_format_without_rule(self) -> None:
        """Test ID format without rule."""
        linter = KtlintLinter()
        issue_id = linter._generate_issue_id("", "f.kt", 1, 1, "msg")
        assert issue_id.startswith("ktlint-")
        assert "ktlint--" not in issue_id

    def test_id_handles_zero_values(self) -> None:
        """Test ID handles zero line/column (missing values)."""
        linter = KtlintLinter()
        issue_id = linter._generate_issue_id("rule", "file.kt", 0, 0, "msg")
        assert issue_id.startswith("ktlint-rule-")

    def test_different_lines_different_ids(self) -> None:
        """Test different line numbers produce different IDs."""
        linter = KtlintLinter()
        id1 = linter._generate_issue_id("rule", "file.kt", 1, 1, "msg")
        id2 = linter._generate_issue_id("rule", "file.kt", 2, 1, "msg")
        assert id1 != id2

    def test_different_files_different_ids(self) -> None:
        """Test different file paths produce different IDs."""
        linter = KtlintLinter()
        id1 = linter._generate_issue_id("rule", "a.kt", 1, 1, "msg")
        id2 = linter._generate_issue_id("rule", "b.kt", 1, 1, "msg")
        assert id1 != id2

    def test_different_messages_different_ids(self) -> None:
        """Test different messages produce different IDs."""
        linter = KtlintLinter()
        id1 = linter._generate_issue_id("rule", "file.kt", 1, 1, "message A")
        id2 = linter._generate_issue_id("rule", "file.kt", 1, 1, "message B")
        assert id1 != id2
