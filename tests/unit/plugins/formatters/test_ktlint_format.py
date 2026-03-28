"""Unit tests for Ktlint formatter plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.formatters.ktlint_format import KtlintFormatter, KOTLIN_EXTENSIONS
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


FAKE_JAR = Path("/opt/ktlint/ktlint.jar")


class TestKtlintFormatterProperties:
    def test_name(self) -> None:
        formatter = KtlintFormatter()
        assert formatter.name == "ktlint_format"

    def test_languages(self) -> None:
        formatter = KtlintFormatter()
        assert formatter.languages == ["kotlin"]

    def test_domain(self) -> None:
        formatter = KtlintFormatter()
        assert formatter.domain == ToolDomain.FORMATTING

    def test_extensions(self) -> None:
        assert ".kt" in KOTLIN_EXTENSIONS
        assert ".kts" in KOTLIN_EXTENSIONS

    def test_supports_fix(self) -> None:
        formatter = KtlintFormatter()
        assert formatter.supports_fix is True


class TestKtlintFormatterEnsureBinary:
    def test_delegates_to_ktlint_linter(self) -> None:
        """ensure_binary delegates to the internal KtlintLinter instance."""
        formatter = KtlintFormatter()
        with patch.object(
            formatter._ktlint, "ensure_binary", return_value=FAKE_JAR
        ) as mock_ensure:
            result = formatter.ensure_binary()
            assert result == FAKE_JAR
            mock_ensure.assert_called_once()

    def test_binary_found(self) -> None:
        formatter = KtlintFormatter()
        with patch.object(formatter._ktlint, "ensure_binary", return_value=FAKE_JAR):
            binary = formatter.ensure_binary()
            assert binary == FAKE_JAR

    def test_binary_not_found(self) -> None:
        formatter = KtlintFormatter()
        with patch.object(
            formatter._ktlint,
            "ensure_binary",
            side_effect=FileNotFoundError("ktlint not found"),
        ):
            with pytest.raises(FileNotFoundError):
                formatter.ensure_binary()


class TestKtlintFormatterCheck:
    def test_check_no_issues(self) -> None:
        """Empty stdout means no formatting violations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("fun main() {}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_with_issues(self) -> None:
        """Plain output with file:line:col format is parsed into issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "src" / "Main.kt"
            kt_file.parent.mkdir(parents=True, exist_ok=True)
            kt_file.write_text("fun main() {\n}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            stdout = (
                "src/Main.kt:1:1: Unexpected indentation (standard:indent)\n"
                "src/Main.kt:5:10: Missing newline before \")\" (standard:parameter-list-wrapping)\n"
            )
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1  # same file deduplicated
                assert issues[0].domain == ToolDomain.FORMATTING
                assert issues[0].source_tool == "ktlint_format"
                assert issues[0].severity == Severity.LOW
                assert issues[0].fixable is True
                assert "src/Main.kt" in issues[0].title
                assert issues[0].rule_id == "format"

    def test_check_multiple_files(self) -> None:
        """Multiple different files produce separate issues, sorted by path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_a = project_root / "A.kt"
            kt_a.write_text("")
            kt_b = project_root / "B.kt"
            kt_b.write_text("")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_a, kt_b])

            stdout = (
                "B.kt:1:1: Some issue (standard:rule)\n"
                "A.kt:3:5: Another issue (standard:rule2)\n"
            )
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert len(issues) == 2
                # Sorted by file path
                assert "A.kt" in issues[0].title
                assert "B.kt" in issues[1].title

    def test_check_deduplicates_same_file(self) -> None:
        """Multiple violations in the same file produce only one issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            stdout = (
                "Main.kt:1:1: First issue (standard:rule1)\n"
                "Main.kt:5:10: Second issue (standard:rule2)\n"
                "Main.kt:10:1: Third issue (standard:rule3)\n"
            )
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert "Main.kt" in issues[0].title

    def test_check_binary_not_found(self) -> None:
        """When binary is not found, check returns empty list."""
        formatter = KtlintFormatter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            issues = formatter.check(context)
            assert issues == []

    def test_check_timeout(self) -> None:
        """Timeout returns empty list and records skip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("fun main() {}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    side_effect=subprocess.TimeoutExpired(cmd="ktlint", timeout=120),
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_generic_exception(self) -> None:
        """Generic exception returns empty list and records skip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("fun main() {}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    side_effect=RuntimeError("unexpected error"),
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_empty_paths(self) -> None:
        """Empty paths returns empty list without running subprocess."""
        formatter = KtlintFormatter()
        context = _make_context(Path("/tmp"), paths=[])

        with patch.object(formatter, "ensure_binary", return_value=FAKE_JAR):
            issues = formatter.check(context)
            assert issues == []

    def test_check_skips_non_kotlin_files(self) -> None:
        """Non-Kotlin files are filtered out by _resolve_paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("x = 1\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [py_file])

            with patch.object(formatter, "ensure_binary", return_value=FAKE_JAR):
                issues = formatter.check(context)
                assert issues == []

    def test_check_includes_kts_files(self) -> None:
        """Kotlin script (.kts) files are also included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kts_file = project_root / "build.gradle.kts"
            kts_file.write_text("plugins {}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kts_file])

            stdout = "build.gradle.kts:1:1: Issue (standard:rule)\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert "build.gradle.kts" in issues[0].title

    def test_check_empty_stdout_on_nonzero_returncode(self) -> None:
        """Non-zero return code but empty stdout produces no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("fun main() {}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            result = make_completed_process(1, "", "")
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert issues == []

    def test_check_relative_path_resolved_to_absolute(self) -> None:
        """Relative file paths in output are resolved relative to project_root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "src" / "Main.kt"
            kt_file.parent.mkdir(parents=True, exist_ok=True)
            kt_file.write_text("")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            stdout = "src/Main.kt:1:1: Issue (standard:rule)\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert issues[0].file_path == project_root / "src" / "Main.kt"
                assert issues[0].file_path.is_absolute()

    def test_check_issue_id_contains_hash(self) -> None:
        """Each issue gets a deterministic hash-based ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            stdout = "Main.kt:1:1: Issue (standard:rule)\n"
            result = make_completed_process(1, stdout)
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                issues = formatter.check(context)
                assert len(issues) == 1
                assert issues[0].id.startswith("ktlint_format-format-")
                # Hash portion is 12 hex chars
                hash_part = issues[0].id.split("ktlint_format-format-")[1]
                assert len(hash_part) == 12


class TestKtlintFormatterFix:
    def test_fix_success(self) -> None:
        """Fix runs ktlint --format and reports files modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("fun main(){}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            fix_run_result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=fix_run_result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 1
                assert result.issues_remaining == 0

    def test_fix_multiple_files(self) -> None:
        """Fix with multiple Kotlin files reports correct file count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_a = project_root / "A.kt"
            kt_a.write_text("")
            kt_b = project_root / "B.kt"
            kt_b.write_text("")
            kts_file = project_root / "build.gradle.kts"
            kts_file.write_text("")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_a, kt_b, kts_file])

            fix_run_result = make_completed_process(0, "")
            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    return_value=fix_run_result,
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 3

    def test_fix_binary_not_found(self) -> None:
        """When binary is not found, fix returns empty FixResult."""
        formatter = KtlintFormatter()
        context = _make_context(Path("/tmp"))
        with patch.object(
            formatter, "ensure_binary", side_effect=FileNotFoundError("not found")
        ):
            result = formatter.fix(context)
            assert isinstance(result, FixResult)
            assert result.files_modified == 0
            assert result.issues_fixed == 0

    def test_fix_no_matching_paths(self) -> None:
        """Fix with no .kt/.kts files returns empty FixResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            py_file = project_root / "main.py"
            py_file.write_text("x = 1\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [py_file])

            with patch.object(formatter, "ensure_binary", return_value=FAKE_JAR):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 0
                assert result.issues_fixed == 0

    def test_fix_subprocess_exception(self) -> None:
        """Fix returns empty FixResult when subprocess raises an exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            kt_file = project_root / "Main.kt"
            kt_file.write_text("fun main(){}\n")

            formatter = KtlintFormatter(project_root=project_root)
            context = _make_context(project_root, [kt_file])

            with (
                patch(
                    "lucidshark.plugins.formatters.ktlint_format.run_with_streaming",
                    side_effect=RuntimeError("ktlint crashed"),
                ),
                patch.object(formatter, "ensure_binary", return_value=FAKE_JAR),
            ):
                result = formatter.fix(context)
                assert isinstance(result, FixResult)
                assert result.files_modified == 0
                assert result.issues_fixed == 0
                assert result.issues_remaining == 0

    def test_fix_empty_paths(self) -> None:
        """Fix with empty paths returns empty FixResult."""
        formatter = KtlintFormatter()
        context = _make_context(Path("/tmp"), paths=[])

        with patch.object(formatter, "ensure_binary", return_value=FAKE_JAR):
            result = formatter.fix(context)
            assert isinstance(result, FixResult)
            assert result.files_modified == 0
