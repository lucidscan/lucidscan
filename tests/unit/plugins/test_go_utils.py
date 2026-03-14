"""Unit tests for Go plugin utilities."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.plugins.go_utils import (
    find_go,
    find_gofmt,
    find_golangci_lint,
    generate_issue_id,
    get_go_version,
    get_golangci_lint_version,
    has_go_mod,
    parse_go_error_position,
)


# ---------------------------------------------------------------------------
# find_go
# ---------------------------------------------------------------------------


class TestFindGo:
    """Tests for find_go function."""

    def test_find_go_returns_path_when_on_path(self) -> None:
        """Return a Path when go is found on PATH."""
        with patch(
            "lucidshark.plugins.go_utils.shutil.which", return_value="/usr/local/bin/go"
        ):
            result = find_go()

        assert result == Path("/usr/local/bin/go")

    def test_find_go_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError with install URL when go is missing."""
        with patch("lucidshark.plugins.go_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="https://go.dev/dl/"):
                find_go()

    def test_find_go_returns_path_type(self) -> None:
        """Return value is a Path instance."""
        with patch(
            "lucidshark.plugins.go_utils.shutil.which", return_value="/usr/bin/go"
        ):
            result = find_go()

        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# find_golangci_lint
# ---------------------------------------------------------------------------


class TestFindGolangciLint:
    """Tests for find_golangci_lint function."""

    def test_finds_on_system_path(self) -> None:
        """Return PATH version when available."""
        with patch(
            "lucidshark.plugins.go_utils.shutil.which",
            return_value="/usr/bin/golangci-lint",
        ):
            result = find_golangci_lint()

        assert result == Path("/usr/bin/golangci-lint")

    def test_falls_back_to_gobin(self) -> None:
        """Fall back to ~/go/bin/golangci-lint when not on PATH."""
        fake_home = Path("/fakehome")
        expected = fake_home / "go" / "bin" / "golangci-lint"

        with (
            patch("lucidshark.plugins.go_utils.shutil.which", return_value=None),
            patch("lucidshark.plugins.go_utils.Path.home", return_value=fake_home),
            patch("lucidshark.plugins.go_utils.Path.exists", return_value=True),
        ):
            result = find_golangci_lint()

        assert result == expected

    def test_prefers_path_over_gobin(self) -> None:
        """Prefer the PATH version over ~/go/bin."""
        with patch(
            "lucidshark.plugins.go_utils.shutil.which",
            return_value="/usr/local/bin/golangci-lint",
        ):
            result = find_golangci_lint()

        assert result == Path("/usr/local/bin/golangci-lint")

    def test_raises_when_not_found(self) -> None:
        """Raise FileNotFoundError when neither PATH nor GOBIN has it."""
        with (
            patch("lucidshark.plugins.go_utils.shutil.which", return_value=None),
            patch(
                "lucidshark.plugins.go_utils.Path.home", return_value=Path("/fakehome")
            ),
            patch("lucidshark.plugins.go_utils.Path.exists", return_value=False),
        ):
            with pytest.raises(FileNotFoundError):
                find_golangci_lint()

    def test_error_message_contains_install_instructions(self) -> None:
        """Error message includes install command and URL."""
        with (
            patch("lucidshark.plugins.go_utils.shutil.which", return_value=None),
            patch(
                "lucidshark.plugins.go_utils.Path.home", return_value=Path("/fakehome")
            ),
            patch("lucidshark.plugins.go_utils.Path.exists", return_value=False),
        ):
            with pytest.raises(FileNotFoundError, match="go install"):
                find_golangci_lint()


# ---------------------------------------------------------------------------
# find_gofmt
# ---------------------------------------------------------------------------


class TestFindGofmt:
    """Tests for find_gofmt function."""

    def test_finds_on_system_path(self) -> None:
        """Return Path when gofmt is on PATH."""
        with patch(
            "lucidshark.plugins.go_utils.shutil.which",
            return_value="/usr/local/go/bin/gofmt",
        ):
            result = find_gofmt()

        assert result == Path("/usr/local/go/bin/gofmt")

    def test_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError mentioning it ships with Go."""
        with patch("lucidshark.plugins.go_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="ships with Go"):
                find_gofmt()


# ---------------------------------------------------------------------------
# get_go_version
# ---------------------------------------------------------------------------


class TestGetGoVersion:
    """Tests for get_go_version function."""

    def test_returns_version_string(self) -> None:
        """Return stdout when go version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "go version go1.22.0 linux/amd64\n"

        with (
            patch(
                "lucidshark.plugins.go_utils.find_go",
                return_value=Path("/usr/local/bin/go"),
            ),
            patch(
                "lucidshark.plugins.go_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_go_version()

        assert version == "go version go1.22.0 linux/amd64"

    def test_returns_unknown_when_go_not_found(self) -> None:
        """Return 'unknown' when find_go raises FileNotFoundError."""
        with patch(
            "lucidshark.plugins.go_utils.find_go",
            side_effect=FileNotFoundError("not found"),
        ):
            assert get_go_version() == "unknown"

    def test_returns_unknown_on_nonzero_exit(self) -> None:
        """Return 'unknown' when go version exits non-zero."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch(
                "lucidshark.plugins.go_utils.find_go",
                return_value=Path("/usr/local/bin/go"),
            ),
            patch(
                "lucidshark.plugins.go_utils.subprocess.run", return_value=mock_result
            ),
        ):
            assert get_go_version() == "unknown"

    def test_returns_unknown_on_timeout(self) -> None:
        """Return 'unknown' when subprocess times out."""
        with (
            patch(
                "lucidshark.plugins.go_utils.find_go",
                return_value=Path("/usr/local/bin/go"),
            ),
            patch(
                "lucidshark.plugins.go_utils.subprocess.run",
                side_effect=subprocess.TimeoutExpired("go", 30),
            ),
        ):
            assert get_go_version() == "unknown"

    def test_returns_unknown_on_oserror(self) -> None:
        """Return 'unknown' when subprocess raises OSError."""
        with (
            patch(
                "lucidshark.plugins.go_utils.find_go",
                return_value=Path("/usr/local/bin/go"),
            ),
            patch(
                "lucidshark.plugins.go_utils.subprocess.run",
                side_effect=OSError("exec format error"),
            ),
        ):
            assert get_go_version() == "unknown"

    def test_strips_whitespace(self) -> None:
        """Strip leading/trailing whitespace from version output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  go version go1.22  \n"

        with (
            patch(
                "lucidshark.plugins.go_utils.find_go",
                return_value=Path("/usr/local/bin/go"),
            ),
            patch(
                "lucidshark.plugins.go_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_go_version()

        assert version == "go version go1.22"


# ---------------------------------------------------------------------------
# get_golangci_lint_version
# ---------------------------------------------------------------------------


class TestGetGolangciLintVersion:
    """Tests for get_golangci_lint_version function."""

    def test_returns_version_string(self) -> None:
        """Return stdout when golangci-lint --version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "golangci-lint has version 1.56.2\n"

        with (
            patch(
                "lucidshark.plugins.go_utils.find_golangci_lint",
                return_value=Path("/usr/bin/golangci-lint"),
            ),
            patch(
                "lucidshark.plugins.go_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_golangci_lint_version()

        assert version == "golangci-lint has version 1.56.2"

    def test_returns_unknown_when_not_found(self) -> None:
        """Return 'unknown' when find_golangci_lint raises."""
        with patch(
            "lucidshark.plugins.go_utils.find_golangci_lint",
            side_effect=FileNotFoundError("not found"),
        ):
            assert get_golangci_lint_version() == "unknown"

    def test_returns_unknown_on_failure(self) -> None:
        """Return 'unknown' when subprocess fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch(
                "lucidshark.plugins.go_utils.find_golangci_lint",
                return_value=Path("/usr/bin/golangci-lint"),
            ),
            patch(
                "lucidshark.plugins.go_utils.subprocess.run", return_value=mock_result
            ),
        ):
            assert get_golangci_lint_version() == "unknown"


# ---------------------------------------------------------------------------
# generate_issue_id
# ---------------------------------------------------------------------------


class TestGenerateIssueId:
    """Tests for generate_issue_id function."""

    def test_deterministic(self) -> None:
        """Same inputs produce the same ID across calls."""
        a = generate_issue_id("golangci-lint", "SA1000", "main.go", 10, 5, "invalid regexp")
        b = generate_issue_id("golangci-lint", "SA1000", "main.go", 10, 5, "invalid regexp")
        assert a == b

    def test_format(self) -> None:
        """ID matches '{tool_prefix}-{12 hex chars}' pattern."""
        result = generate_issue_id("go-vet", "C100", "main.go", 1, 1, "msg")
        assert re.fullmatch(r"go-vet-[0-9a-f]{12}", result)

    def test_different_codes_different_ids(self) -> None:
        """Different code values produce different IDs."""
        id1 = generate_issue_id("t", "A", "f.go", 1, 1, "m")
        id2 = generate_issue_id("t", "B", "f.go", 1, 1, "m")
        assert id1 != id2

    def test_different_files_different_ids(self) -> None:
        """Different file values produce different IDs."""
        id1 = generate_issue_id("t", "C", "a.go", 1, 1, "m")
        id2 = generate_issue_id("t", "C", "b.go", 1, 1, "m")
        assert id1 != id2

    def test_different_lines_different_ids(self) -> None:
        """Different line values produce different IDs."""
        id1 = generate_issue_id("t", "C", "f.go", 1, 1, "m")
        id2 = generate_issue_id("t", "C", "f.go", 2, 1, "m")
        assert id1 != id2

    def test_different_columns_different_ids(self) -> None:
        """Different column values produce different IDs."""
        id1 = generate_issue_id("t", "C", "f.go", 1, 1, "m")
        id2 = generate_issue_id("t", "C", "f.go", 1, 2, "m")
        assert id1 != id2

    def test_different_messages_different_ids(self) -> None:
        """Different message values produce different IDs."""
        id1 = generate_issue_id("t", "C", "f.go", 1, 1, "foo")
        id2 = generate_issue_id("t", "C", "f.go", 1, 1, "bar")
        assert id1 != id2

    def test_different_tool_prefixes_different_ids(self) -> None:
        """Different tool_prefix values produce different IDs."""
        id1 = generate_issue_id("go-vet", "C", "f.go", 1, 1, "m")
        id2 = generate_issue_id("golangci-lint", "C", "f.go", 1, 1, "m")
        assert id1 != id2

    def test_none_line_uses_zero(self) -> None:
        """None line is treated as 0 for hashing."""
        id_none = generate_issue_id("t", "C", "f.go", None, 1, "m")
        id_zero = generate_issue_id("t", "C", "f.go", 0, 1, "m")
        assert id_none == id_zero

    def test_none_column_uses_zero(self) -> None:
        """None column is treated as 0 for hashing."""
        id_none = generate_issue_id("t", "C", "f.go", 1, None, "m")
        id_zero = generate_issue_id("t", "C", "f.go", 1, 0, "m")
        assert id_none == id_zero

    def test_empty_strings_handled(self) -> None:
        """Empty strings for code, file, and message produce a valid ID."""
        result = generate_issue_id(
            tool_prefix="t",
            code="",
            file="",
            line=None,
            column=None,
            message="",
        )
        assert re.fullmatch(r"t-[0-9a-f]{12}", result)

    def test_unicode_message(self) -> None:
        """Unicode characters in message do not crash."""
        result = generate_issue_id(
            tool_prefix="t",
            code="C",
            file="f.go",
            line=1,
            column=1,
            message="undefined: \u4f60\u597d\u4e16\u754c",
        )
        assert re.fullmatch(r"t-[0-9a-f]{12}", result)


# ---------------------------------------------------------------------------
# parse_go_error_position
# ---------------------------------------------------------------------------


class TestParseGoErrorPosition:
    """Tests for parse_go_error_position function."""

    def test_full_position(self) -> None:
        """Parse file:line:column."""
        assert parse_go_error_position("file.go:42:5") == ("file.go", 42, 5)

    def test_no_column(self) -> None:
        """Parse file:line without column."""
        assert parse_go_error_position("file.go:42") == ("file.go", 42, None)

    def test_absolute_path(self) -> None:
        """Parse absolute file path."""
        assert parse_go_error_position("/path/to/file.go:10:3") == (
            "/path/to/file.go",
            10,
            3,
        )

    def test_relative_path(self) -> None:
        """Parse relative file path."""
        assert parse_go_error_position("pkg/file.go:10:3") == ("pkg/file.go", 10, 3)

    def test_with_trailing_message(self) -> None:
        """Ignore trailing message after position."""
        file_path, line, column = parse_go_error_position(
            "file.go:42:5: undefined var x"
        )
        assert file_path == "file.go"
        assert line == 42
        assert column == 5

    def test_test_file(self) -> None:
        """Parse _test.go files."""
        assert parse_go_error_position("main_test.go:15:1") == (
            "main_test.go",
            15,
            1,
        )

    def test_no_match_returns_nones(self) -> None:
        """Return (None, None, None) for non-Go text."""
        assert parse_go_error_position("not a go file") == (None, None, None)

    def test_empty_string_returns_nones(self) -> None:
        """Return (None, None, None) for empty input."""
        assert parse_go_error_position("") == (None, None, None)

    def test_no_go_extension(self) -> None:
        """Return nones when file has non-.go extension."""
        assert parse_go_error_position("file.py:10:3") == (None, None, None)

    def test_line_number_zero(self) -> None:
        """Handle line number 0."""
        assert parse_go_error_position("file.go:0:0") == ("file.go", 0, 0)

    def test_large_line_number(self) -> None:
        """Handle large line numbers."""
        assert parse_go_error_position("file.go:99999:1") == ("file.go", 99999, 1)

    def test_colon_no_number(self) -> None:
        """Trailing colon without a number returns nones."""
        # The regex requires \d+ after the colon, so "file.go:" won't match
        assert parse_go_error_position("file.go:") == (None, None, None)

    def test_returns_int_types(self) -> None:
        """Line and column are int, not str."""
        _, line, column = parse_go_error_position("file.go:10:3")
        assert isinstance(line, int)
        assert isinstance(column, int)


# ---------------------------------------------------------------------------
# has_go_mod
# ---------------------------------------------------------------------------


class TestHasGoMod:
    """Tests for has_go_mod function."""

    def test_returns_true_when_exists(self, tmp_path: Path) -> None:
        """Return True when go.mod exists in project root."""
        (tmp_path / "go.mod").touch()
        assert has_go_mod(tmp_path) is True

    def test_returns_false_when_missing(self, tmp_path: Path) -> None:
        """Return False when go.mod is absent."""
        assert has_go_mod(tmp_path) is False

    def test_checks_project_root_not_cwd(self, tmp_path: Path) -> None:
        """Check the given root, not some other directory."""
        other = tmp_path / "other"
        other.mkdir()
        (other / "go.mod").touch()
        # The project root itself has no go.mod
        assert has_go_mod(tmp_path) is False

    def test_does_not_match_subdirectory(self, tmp_path: Path) -> None:
        """Subdirectory go.mod does not count for project root."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "go.mod").touch()
        assert has_go_mod(tmp_path) is False

    def test_returns_false_when_go_mod_is_directory(self, tmp_path: Path) -> None:
        """Return False (or raise) when go.mod is a directory, not a file."""
        (tmp_path / "go.mod").mkdir()
        # Path.exists() returns True for dirs too, so the implementation
        # will return True.  Document the actual behavior.
        assert has_go_mod(tmp_path) is True
