"""Integration tests for gofmt formatter plugin.

These tests require gofmt (ships with Go) to be installed.

Run with: pytest tests/integration/formatters/test_gofmt_integration.py -v
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.formatters.gofmt import GofmtFormatter
from lucidshark.plugins.linters.base import FixResult
from tests.integration.conftest import gofmt_available


class TestGofmtAvailability:
    """Tests for gofmt availability."""

    @gofmt_available
    def test_ensure_binary_finds_gofmt(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that ensure_binary finds the gofmt binary."""
        binary_path = gofmt_formatter.ensure_binary()
        assert binary_path.exists()
        assert "gofmt" in binary_path.name

    @gofmt_available
    def test_get_version(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that get_version returns a version string."""
        version = gofmt_formatter.get_version()
        # gofmt reports "installed" since it has no --version flag
        assert version != "unknown"

    def test_ensure_binary_raises_when_not_installed(self) -> None:
        """Test that ensure_binary raises FileNotFoundError when gofmt is missing."""
        formatter = GofmtFormatter(project_root=Path("/nonexistent"))
        try:
            binary_path = formatter.ensure_binary()
            # If gofmt is installed, verify it exists
            assert binary_path.exists()
        except FileNotFoundError as e:
            assert "gofmt" in str(e).lower()


@gofmt_available
class TestGofmtChecking:
    """Integration tests for gofmt formatting checks."""

    def test_check_clean_files(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that properly formatted Go files produce 0 issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            clean_go = tmpdir_path / "clean.go"
            clean_go.write_text(
                'package main\n\nimport "fmt"\n\nfunc main() {\n'
                '\tfmt.Println("hello")\n}\n'
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = gofmt_formatter.check(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_check_detects_unformatted_files(
        self, gofmt_formatter: GofmtFormatter
    ) -> None:
        """Test that unformatted Go files are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            unformatted_go = tmpdir_path / "bad.go"
            unformatted_go.write_text(
                'package main\n\nimport "fmt"\n\nfunc main()  {\n'
                'fmt.Println(  "hello"  )\n'
                "  x:=42\n"
                "fmt.Println(x)\n}\n"
            )

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = gofmt_formatter.check(context)

            assert isinstance(issues, list)
            assert len(issues) >= 1

            for issue in issues:
                assert issue.source_tool == "gofmt"
                assert issue.domain == ToolDomain.FORMATTING
                assert issue.severity == Severity.LOW
                assert issue.fixable is True

    def test_check_multiple_files(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that multiple unformatted files each produce an issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create two unformatted files
            for name in ["a.go", "b.go"]:
                f = tmpdir_path / name
                f.write_text("package main\n\nfunc main()  {\n}\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = gofmt_formatter.check(context)

            assert len(issues) >= 2

    def test_check_skips_non_go_files(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that non-Go files are ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a Python file (should be ignored)
            py_file = tmpdir_path / "main.py"
            py_file.write_text("print('hello')\n")

            # Create a text file (should be ignored)
            txt_file = tmpdir_path / "notes.txt"
            txt_file.write_text("some notes\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = gofmt_formatter.check(context)

            assert isinstance(issues, list)
            assert len(issues) == 0

    def test_check_empty_directory(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that empty directory returns no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = gofmt_formatter.check(context)

            assert isinstance(issues, list)
            assert len(issues) == 0


@gofmt_available
class TestGofmtFixMode:
    """Integration tests for gofmt auto-fix functionality."""

    def test_fix_reformats_files(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that fix mode reformats unformatted files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            unformatted_go = tmpdir_path / "fixme.go"
            original_content = (
                'package main\n\nimport "fmt"\n\nfunc main()  {\n'
                'fmt.Println(  "hello"  )\n'
                "  x:=42\n"
                "fmt.Println(x)\n}\n"
            )
            unformatted_go.write_text(original_content)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            # Verify file needs formatting first
            issues_before = gofmt_formatter.check(context)
            assert len(issues_before) >= 1

            # Apply fix
            fix_result = gofmt_formatter.fix(context)

            assert fix_result.files_modified >= 1

            # Verify file is now formatted
            issues_after = gofmt_formatter.check(context)
            assert len(issues_after) == 0

            # Verify file content changed
            new_content = unformatted_go.read_text()
            assert new_content != original_content

    def test_fix_no_op_on_clean_files(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that fix on already-formatted files does not break them."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            clean_go = tmpdir_path / "clean.go"
            original_content = (
                'package main\n\nimport "fmt"\n\nfunc main() {\n'
                '\tfmt.Println("hello")\n}\n'
            )
            clean_go.write_text(original_content)

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            gofmt_formatter.fix(context)

            # Content should be unchanged
            assert clean_go.read_text() == original_content


@gofmt_available
class TestGofmtIssueGeneration:
    """Tests for gofmt issue field correctness."""

    def test_issue_has_correct_fields(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that generated issues have all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            unformatted_go = tmpdir_path / "check.go"
            unformatted_go.write_text("package main\n\nfunc main()  {\n}\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues = gofmt_formatter.check(context)

            assert len(issues) >= 1

            issue = issues[0]
            assert issue.id is not None
            assert issue.id.startswith("gofmt-format-")
            assert issue.domain == ToolDomain.FORMATTING
            assert issue.source_tool == "gofmt"
            assert issue.severity == Severity.LOW
            assert issue.rule_id == "format"
            assert issue.fixable is True
            assert issue.file_path is not None
            assert "needs formatting" in issue.title.lower()

    def test_issue_id_is_deterministic(self, gofmt_formatter: GofmtFormatter) -> None:
        """Test that issue IDs are consistent across runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            unformatted_go = tmpdir_path / "determ.go"
            unformatted_go.write_text("package main\n\nfunc main()  {\n}\n")

            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )

            issues1 = gofmt_formatter.check(context)
            issues2 = gofmt_formatter.check(context)

            assert len(issues1) >= 1
            assert len(issues2) >= 1
            assert issues1[0].id == issues2[0].id


# ---------------------------------------------------------------------------
# Unit tests below  -  no gofmt/Go binary required
# ---------------------------------------------------------------------------


class TestGofmtProperties:
    """Test basic formatter properties without needing the binary."""

    def test_name(self) -> None:
        formatter = GofmtFormatter()
        assert formatter.name == "gofmt"

    def test_languages(self) -> None:
        formatter = GofmtFormatter()
        assert formatter.languages == ["go"]

    def test_domain(self) -> None:
        formatter = GofmtFormatter()
        assert formatter.domain == ToolDomain.FORMATTING

    def test_supports_fix(self) -> None:
        formatter = GofmtFormatter()
        assert formatter.supports_fix is True


class TestGofmtCheckOutputParsing:
    """Test check() output parsing with mocked subprocess calls."""

    def _make_context(self, tmp_path: Path, go_files: list[str] | None = None):
        """Create a ScanContext with optional .go files on disk."""
        if go_files:
            for name in go_files:
                f = tmp_path / name
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("package main\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        return ctx

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_empty_stdout_means_all_formatted(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert issues == []

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_single_file_in_stdout(self, mock_binary, mock_run, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "main.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 1

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_multiple_files_in_stdout(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "main.go\nutils.go\npkg/handler.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        for name in ["main.go", "utils.go", "pkg/handler.go"]:
            f = tmp_path / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 3

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_blank_lines_in_stdout_skipped(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "\n  \nmain.go\n\n  \nutils.go\n\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        (tmp_path / "utils.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 2

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_relative_path_resolved(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "pkg/handler.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "pkg").mkdir(parents=True, exist_ok=True)
        (tmp_path / "pkg" / "handler.go").write_text("package pkg\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 1
        assert issues[0].file_path == tmp_path / "pkg" / "handler.go"

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_absolute_path_preserved(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        abs_path = str(tmp_path / "main.go")
        mock_result = MagicMock()
        mock_result.stdout = f"{abs_path}\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 1
        assert issues[0].file_path is not None and issues[0].file_path.is_absolute()
        assert issues[0].file_path == Path(abs_path)

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_issue_fields_correct(self, mock_binary, mock_run, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "main.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 1

        issue = issues[0]
        assert issue.domain == ToolDomain.FORMATTING
        assert issue.source_tool == "gofmt"
        assert issue.severity == Severity.LOW
        assert issue.rule_id == "format"
        assert issue.fixable is True
        assert issue.suggested_fix == "Run gofmt to fix formatting."

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_issue_title_contains_filename(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "main.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 1
        assert "main.go" in issues[0].title

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_issue_description_contains_gofmt_style(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "main.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 1
        assert "gofmt style" in issues[0].description

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_issue_id_deterministic(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "main.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues1 = formatter.check(ctx)
        issues2 = formatter.check(ctx)
        assert len(issues1) == 1
        assert len(issues2) == 1
        assert issues1[0].id == issues2[0].id

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_different_files_different_ids(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "a.go\nb.go\n"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "a.go").write_text("package main\n")
        (tmp_path / "b.go").write_text("package main\n")
        ctx = self._make_context(tmp_path)

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert len(issues) == 2
        assert issues[0].id != issues[1].id


class TestGofmtErrorHandling:
    """Test error handling paths with mocked dependencies."""

    @patch.object(
        GofmtFormatter,
        "ensure_binary",
        side_effect=FileNotFoundError("gofmt not found"),
    )
    def test_check_returns_empty_on_binary_not_found(
        self, mock_binary, tmp_path: Path
    ) -> None:
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert issues == []

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_check_returns_empty_on_timeout(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gofmt", timeout=120)

        (tmp_path / "main.go").write_text("package main\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        ctx.record_skip = MagicMock()  # type: ignore[method-assign]

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert issues == []
        ctx.record_skip.assert_called_once()

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_check_returns_empty_on_exception(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_run.side_effect = RuntimeError("unexpected error")

        (tmp_path / "main.go").write_text("package main\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        ctx.record_skip = MagicMock()  # type: ignore[method-assign]

        formatter = GofmtFormatter()
        issues = formatter.check(ctx)
        assert issues == []
        ctx.record_skip.assert_called_once()

    @patch.object(
        GofmtFormatter,
        "ensure_binary",
        side_effect=FileNotFoundError("gofmt not found"),
    )
    def test_fix_returns_empty_on_binary_not_found(
        self, mock_binary, tmp_path: Path
    ) -> None:
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        formatter = GofmtFormatter()
        result = formatter.fix(ctx)
        assert isinstance(result, FixResult)
        assert result.files_modified == 0

    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_fix_returns_empty_on_no_go_files(
        self, mock_binary, tmp_path: Path
    ) -> None:
        # Directory with no .go files
        (tmp_path / "readme.txt").write_text("hello\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        formatter = GofmtFormatter()
        result = formatter.fix(ctx)
        assert isinstance(result, FixResult)
        assert result.files_modified == 0

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_fix_returns_empty_on_exception(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_run.side_effect = RuntimeError("unexpected error")

        (tmp_path / "main.go").write_text("package main\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )
        formatter = GofmtFormatter()
        result = formatter.fix(ctx)
        assert isinstance(result, FixResult)
        assert result.files_modified == 0


class TestGofmtFixResult:
    """Test fix() return values with mocked dependencies."""

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_fix_result_files_modified_equals_path_count(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        for name in ["a.go", "b.go", "c.go"]:
            (tmp_path / name).write_text("package main\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )

        formatter = GofmtFormatter()
        result = formatter.fix(ctx)
        assert result.files_modified == 3

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_fix_result_issues_fixed_zero(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )

        formatter = GofmtFormatter()
        result = formatter.fix(ctx)
        assert result.issues_fixed == 0

    @patch("lucidshark.plugins.formatters.gofmt.run_with_streaming")
    @patch.object(GofmtFormatter, "ensure_binary", return_value=Path("/usr/bin/gofmt"))
    def test_fix_result_issues_remaining_zero(
        self, mock_binary, mock_run, tmp_path: Path
    ) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "main.go").write_text("package main\n")
        ctx = ScanContext(
            project_root=tmp_path,
            paths=[tmp_path],
            enabled_domains=[],
        )

        formatter = GofmtFormatter()
        result = formatter.fix(ctx)
        assert result.issues_remaining == 0


class TestGofmtGetVersion:
    """Test get_version() with mocked binary lookup."""

    @patch.object(
        GofmtFormatter,
        "ensure_binary",
        side_effect=FileNotFoundError("gofmt not found"),
    )
    def test_get_version_returns_unknown_on_missing_binary(self, mock_binary) -> None:
        formatter = GofmtFormatter()
        assert formatter.get_version() == "unknown"
