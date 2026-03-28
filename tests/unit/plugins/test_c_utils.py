"""Unit tests for C plugin utilities."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lucidshark.plugins.c_utils import (
    C_EXTENSIONS,
    C_MARKER_FILES,
    find_clang_format,
    find_clang_tidy,
    find_cppcheck,
    find_ctest,
    find_gcov,
    find_lcov,
    generate_issue_id,
    get_clang_format_version,
    get_clang_tidy_version,
    get_cppcheck_version,
    get_ctest_version,
    get_gcov_version,
    has_build_dir,
    has_c_marker,
    has_cmake,
    parse_c_error_position,
)


# ---------------------------------------------------------------------------
# C_EXTENSIONS
# ---------------------------------------------------------------------------


class TestCExtensions:
    """Tests for C_EXTENSIONS constant."""

    def test_includes_c(self) -> None:
        """Test .c is included."""
        assert ".c" in C_EXTENSIONS

    def test_includes_h(self) -> None:
        """Test .h is included."""
        assert ".h" in C_EXTENSIONS

    def test_does_not_include_cpp(self) -> None:
        """Test .cpp is not included."""
        assert ".cpp" not in C_EXTENSIONS


# ---------------------------------------------------------------------------
# C_MARKER_FILES
# ---------------------------------------------------------------------------


class TestCMarkerFiles:
    """Tests for C_MARKER_FILES constant."""

    def test_includes_cmakelists(self) -> None:
        """Test CMakeLists.txt is included."""
        assert "CMakeLists.txt" in C_MARKER_FILES

    def test_includes_makefile(self) -> None:
        """Test Makefile is included."""
        assert "Makefile" in C_MARKER_FILES

    def test_includes_lowercase_makefile(self) -> None:
        """Test makefile (lowercase) is included."""
        assert "makefile" in C_MARKER_FILES

    def test_includes_gnumakefile(self) -> None:
        """Test GNUmakefile is included."""
        assert "GNUmakefile" in C_MARKER_FILES

    def test_includes_meson_build(self) -> None:
        """Test meson.build is included."""
        assert "meson.build" in C_MARKER_FILES


# ---------------------------------------------------------------------------
# find_clang_tidy
# ---------------------------------------------------------------------------


class TestFindClangTidy:
    """Tests for find_clang_tidy function."""

    def test_returns_path_when_on_path(self) -> None:
        """Return a Path when clang-tidy is found on PATH."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/bin/clang-tidy",
        ):
            result = find_clang_tidy()

        assert result == Path("/usr/bin/clang-tidy")

    def test_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError with install instructions when clang-tidy is missing."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="clang-tidy not found"):
                find_clang_tidy()

    def test_returns_path_type(self) -> None:
        """Return value is a Path instance."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/local/bin/clang-tidy",
        ):
            result = find_clang_tidy()

        assert isinstance(result, Path)

    def test_error_message_contains_install_instructions(self) -> None:
        """Error message includes install hints for macOS and Ubuntu."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="brew install"):
                find_clang_tidy()


# ---------------------------------------------------------------------------
# find_clang_format
# ---------------------------------------------------------------------------


class TestFindClangFormat:
    """Tests for find_clang_format function."""

    def test_returns_path_when_on_path(self) -> None:
        """Return a Path when clang-format is found on PATH."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/bin/clang-format",
        ):
            result = find_clang_format()

        assert result == Path("/usr/bin/clang-format")

    def test_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError when clang-format is missing."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="clang-format not found"):
                find_clang_format()

    def test_returns_path_type(self) -> None:
        """Return value is a Path instance."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/local/bin/clang-format",
        ):
            result = find_clang_format()

        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# find_cppcheck
# ---------------------------------------------------------------------------


class TestFindCppcheck:
    """Tests for find_cppcheck function."""

    def test_returns_path_when_on_path(self) -> None:
        """Return a Path when cppcheck is found on PATH."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/bin/cppcheck",
        ):
            result = find_cppcheck()

        assert result == Path("/usr/bin/cppcheck")

    def test_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError when cppcheck is missing."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="cppcheck not found"):
                find_cppcheck()

    def test_error_message_contains_install_instructions(self) -> None:
        """Error message includes install hints."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="brew install cppcheck"):
                find_cppcheck()


# ---------------------------------------------------------------------------
# find_ctest
# ---------------------------------------------------------------------------


class TestFindCtest:
    """Tests for find_ctest function."""

    def test_returns_path_when_on_path(self) -> None:
        """Return a Path when ctest is found on PATH."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/bin/ctest",
        ):
            result = find_ctest()

        assert result == Path("/usr/bin/ctest")

    def test_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError when ctest is missing."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="ctest not found"):
                find_ctest()

    def test_error_message_mentions_cmake(self) -> None:
        """Error message mentions installing CMake to get ctest."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="cmake"):
                find_ctest()


# ---------------------------------------------------------------------------
# find_gcov
# ---------------------------------------------------------------------------


class TestFindGcov:
    """Tests for find_gcov function."""

    def test_returns_path_when_on_path(self) -> None:
        """Return a Path when gcov is found on PATH."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/bin/gcov",
        ):
            result = find_gcov()

        assert result == Path("/usr/bin/gcov")

    def test_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError when gcov is missing."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="gcov not found"):
                find_gcov()

    def test_error_message_mentions_gcc(self) -> None:
        """Error message mentions gcov ships with GCC."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="GCC"):
                find_gcov()


# ---------------------------------------------------------------------------
# find_lcov
# ---------------------------------------------------------------------------


class TestFindLcov:
    """Tests for find_lcov function."""

    def test_returns_path_when_on_path(self) -> None:
        """Return a Path when lcov is found on PATH."""
        with patch(
            "lucidshark.plugins.c_utils.shutil.which",
            return_value="/usr/bin/lcov",
        ):
            result = find_lcov()

        assert result == Path("/usr/bin/lcov")

    def test_raises_when_not_on_path(self) -> None:
        """Raise FileNotFoundError when lcov is missing."""
        with patch("lucidshark.plugins.c_utils.shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="lcov not found"):
                find_lcov()


# ---------------------------------------------------------------------------
# get_clang_tidy_version
# ---------------------------------------------------------------------------


class TestGetClangTidyVersion:
    """Tests for get_clang_tidy_version function."""

    def test_returns_version_string(self) -> None:
        """Return stdout when clang-tidy --version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "LLVM version 17.0.6\n"

        with (
            patch(
                "lucidshark.plugins.c_utils.find_clang_tidy",
                return_value=Path("/usr/bin/clang-tidy"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_clang_tidy_version()

        assert version == "LLVM version 17.0.6"

    def test_returns_unknown_when_not_found(self) -> None:
        """Return 'unknown' when find_clang_tidy raises FileNotFoundError."""
        with patch(
            "lucidshark.plugins.c_utils.find_clang_tidy",
            side_effect=FileNotFoundError("not found"),
        ):
            assert get_clang_tidy_version() == "unknown"

    def test_returns_unknown_on_timeout(self) -> None:
        """Return 'unknown' when subprocess times out."""
        with (
            patch(
                "lucidshark.plugins.c_utils.find_clang_tidy",
                return_value=Path("/usr/bin/clang-tidy"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run",
                side_effect=subprocess.TimeoutExpired("clang-tidy", 30),
            ),
        ):
            assert get_clang_tidy_version() == "unknown"

    def test_returns_stderr_on_nonzero_exit(self) -> None:
        """Return stderr when returncode is non-zero but stderr has content."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "clang-tidy version 17.0.6"

        with (
            patch(
                "lucidshark.plugins.c_utils.find_clang_tidy",
                return_value=Path("/usr/bin/clang-tidy"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_clang_tidy_version()

        assert version == "clang-tidy version 17.0.6"

    def test_returns_unknown_on_failure(self) -> None:
        """Return 'unknown' when subprocess fails with empty stderr."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = ""

        with (
            patch(
                "lucidshark.plugins.c_utils.find_clang_tidy",
                return_value=Path("/usr/bin/clang-tidy"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            assert get_clang_tidy_version() == "unknown"

    def test_strips_whitespace(self) -> None:
        """Strip leading/trailing whitespace from version output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  LLVM version 17.0.6  \n"

        with (
            patch(
                "lucidshark.plugins.c_utils.find_clang_tidy",
                return_value=Path("/usr/bin/clang-tidy"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_clang_tidy_version()

        assert version == "LLVM version 17.0.6"


# ---------------------------------------------------------------------------
# get_clang_format_version
# ---------------------------------------------------------------------------


class TestGetClangFormatVersion:
    """Tests for get_clang_format_version function."""

    def test_returns_version_string(self) -> None:
        """Return stdout when clang-format --version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "clang-format version 17.0.6\n"

        with (
            patch(
                "lucidshark.plugins.c_utils.find_clang_format",
                return_value=Path("/usr/bin/clang-format"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_clang_format_version()

        assert version == "clang-format version 17.0.6"

    def test_returns_unknown_when_not_found(self) -> None:
        """Return 'unknown' when find_clang_format raises FileNotFoundError."""
        with patch(
            "lucidshark.plugins.c_utils.find_clang_format",
            side_effect=FileNotFoundError("not found"),
        ):
            assert get_clang_format_version() == "unknown"


# ---------------------------------------------------------------------------
# get_cppcheck_version
# ---------------------------------------------------------------------------


class TestGetCppcheckVersion:
    """Tests for get_cppcheck_version function."""

    def test_returns_version_string(self) -> None:
        """Return stdout when cppcheck --version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Cppcheck 2.13\n"

        with (
            patch(
                "lucidshark.plugins.c_utils.find_cppcheck",
                return_value=Path("/usr/bin/cppcheck"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_cppcheck_version()

        assert version == "Cppcheck 2.13"

    def test_returns_unknown_when_not_found(self) -> None:
        """Return 'unknown' when find_cppcheck raises FileNotFoundError."""
        with patch(
            "lucidshark.plugins.c_utils.find_cppcheck",
            side_effect=FileNotFoundError("not found"),
        ):
            assert get_cppcheck_version() == "unknown"


# ---------------------------------------------------------------------------
# get_ctest_version
# ---------------------------------------------------------------------------


class TestGetCtestVersion:
    """Tests for get_ctest_version function."""

    def test_returns_version_string(self) -> None:
        """Return stdout when ctest --version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ctest version 3.28.1\n"

        with (
            patch(
                "lucidshark.plugins.c_utils.find_ctest",
                return_value=Path("/usr/bin/ctest"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_ctest_version()

        assert version == "ctest version 3.28.1"

    def test_returns_unknown_when_not_found(self) -> None:
        """Return 'unknown' when find_ctest raises FileNotFoundError."""
        with patch(
            "lucidshark.plugins.c_utils.find_ctest",
            side_effect=FileNotFoundError("not found"),
        ):
            assert get_ctest_version() == "unknown"


# ---------------------------------------------------------------------------
# get_gcov_version
# ---------------------------------------------------------------------------


class TestGetGcovVersion:
    """Tests for get_gcov_version function."""

    def test_returns_version_string(self) -> None:
        """Return stdout when gcov --version succeeds."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "gcov (GCC) 13.2.0\n"

        with (
            patch(
                "lucidshark.plugins.c_utils.find_gcov",
                return_value=Path("/usr/bin/gcov"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run", return_value=mock_result
            ),
        ):
            version = get_gcov_version()

        assert version == "gcov (GCC) 13.2.0"

    def test_returns_unknown_when_not_found(self) -> None:
        """Return 'unknown' when find_gcov raises FileNotFoundError."""
        with patch(
            "lucidshark.plugins.c_utils.find_gcov",
            side_effect=FileNotFoundError("not found"),
        ):
            assert get_gcov_version() == "unknown"

    def test_returns_unknown_on_oserror(self) -> None:
        """Return 'unknown' when subprocess raises OSError."""
        with (
            patch(
                "lucidshark.plugins.c_utils.find_gcov",
                return_value=Path("/usr/bin/gcov"),
            ),
            patch(
                "lucidshark.plugins.c_utils.subprocess.run",
                side_effect=OSError("exec format error"),
            ),
        ):
            assert get_gcov_version() == "unknown"


# ---------------------------------------------------------------------------
# generate_issue_id
# ---------------------------------------------------------------------------


class TestGenerateIssueId:
    """Tests for generate_issue_id function."""

    def test_deterministic(self) -> None:
        """Same inputs produce the same ID across calls."""
        a = generate_issue_id(
            "clang-tidy", "bugprone-use-after-move", "main.c", 10, 5, "use after move"
        )
        b = generate_issue_id(
            "clang-tidy", "bugprone-use-after-move", "main.c", 10, 5, "use after move"
        )
        assert a == b

    def test_format(self) -> None:
        """ID matches '{tool_prefix}-{12 hex chars}' pattern."""
        result = generate_issue_id("clang-tidy", "C100", "main.c", 1, 1, "msg")
        assert re.fullmatch(r"clang-tidy-[0-9a-f]{12}", result)

    def test_different_codes_different_ids(self) -> None:
        """Different code values produce different IDs."""
        id1 = generate_issue_id("t", "A", "f.c", 1, 1, "m")
        id2 = generate_issue_id("t", "B", "f.c", 1, 1, "m")
        assert id1 != id2

    def test_different_files_different_ids(self) -> None:
        """Different file values produce different IDs."""
        id1 = generate_issue_id("t", "C", "a.c", 1, 1, "m")
        id2 = generate_issue_id("t", "C", "b.c", 1, 1, "m")
        assert id1 != id2

    def test_different_lines_different_ids(self) -> None:
        """Different line values produce different IDs."""
        id1 = generate_issue_id("t", "C", "f.c", 1, 1, "m")
        id2 = generate_issue_id("t", "C", "f.c", 2, 1, "m")
        assert id1 != id2

    def test_different_columns_different_ids(self) -> None:
        """Different column values produce different IDs."""
        id1 = generate_issue_id("t", "C", "f.c", 1, 1, "m")
        id2 = generate_issue_id("t", "C", "f.c", 1, 2, "m")
        assert id1 != id2

    def test_different_messages_different_ids(self) -> None:
        """Different message values produce different IDs."""
        id1 = generate_issue_id("t", "C", "f.c", 1, 1, "foo")
        id2 = generate_issue_id("t", "C", "f.c", 1, 1, "bar")
        assert id1 != id2

    def test_different_tool_prefixes_different_ids(self) -> None:
        """Different tool_prefix values produce different IDs."""
        id1 = generate_issue_id("clang-tidy", "C", "f.c", 1, 1, "m")
        id2 = generate_issue_id("cppcheck", "C", "f.c", 1, 1, "m")
        assert id1 != id2

    def test_none_line_uses_zero(self) -> None:
        """None line is treated as 0 for hashing."""
        id_none = generate_issue_id("t", "C", "f.c", None, 1, "m")
        id_zero = generate_issue_id("t", "C", "f.c", 0, 1, "m")
        assert id_none == id_zero

    def test_none_column_uses_zero(self) -> None:
        """None column is treated as 0 for hashing."""
        id_none = generate_issue_id("t", "C", "f.c", 1, None, "m")
        id_zero = generate_issue_id("t", "C", "f.c", 1, 0, "m")
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
            file="f.c",
            line=1,
            column=1,
            message="undefined: \u4f60\u597d\u4e16\u754c",
        )
        assert re.fullmatch(r"t-[0-9a-f]{12}", result)


# ---------------------------------------------------------------------------
# parse_c_error_position
# ---------------------------------------------------------------------------


class TestParseCErrorPosition:
    """Tests for parse_c_error_position function."""

    def test_full_position(self) -> None:
        """Parse file:line:column."""
        assert parse_c_error_position("file.c:42:5") == ("file.c", 42, 5)

    def test_no_column(self) -> None:
        """Parse file:line without column."""
        assert parse_c_error_position("file.c:42") == ("file.c", 42, None)

    def test_absolute_path(self) -> None:
        """Parse absolute file path."""
        assert parse_c_error_position("/path/to/file.c:10:3") == (
            "/path/to/file.c",
            10,
            3,
        )

    def test_relative_path(self) -> None:
        """Parse relative file path."""
        assert parse_c_error_position("src/file.c:10:3") == ("src/file.c", 10, 3)

    def test_header_file(self) -> None:
        """Parse .h header file."""
        assert parse_c_error_position("include/header.h:5:1") == (
            "include/header.h",
            5,
            1,
        )

    def test_with_trailing_message(self) -> None:
        """Ignore trailing message after position."""
        file_path, line, column = parse_c_error_position(
            "file.c:42:5: error: undeclared identifier"
        )
        assert file_path == "file.c"
        assert line == 42
        assert column == 5

    def test_no_match_returns_nones(self) -> None:
        """Return (None, None, None) for non-C text."""
        assert parse_c_error_position("not a c file") == (None, None, None)

    def test_empty_string_returns_nones(self) -> None:
        """Return (None, None, None) for empty input."""
        assert parse_c_error_position("") == (None, None, None)

    def test_no_c_extension(self) -> None:
        """Return nones when file has non-.c/.h extension."""
        assert parse_c_error_position("file.py:10:3") == (None, None, None)

    def test_line_number_zero(self) -> None:
        """Handle line number 0."""
        assert parse_c_error_position("file.c:0:0") == ("file.c", 0, 0)

    def test_large_line_number(self) -> None:
        """Handle large line numbers."""
        assert parse_c_error_position("file.c:99999:1") == ("file.c", 99999, 1)

    def test_returns_int_types(self) -> None:
        """Line and column are int, not str."""
        _, line, column = parse_c_error_position("file.c:10:3")
        assert isinstance(line, int)
        assert isinstance(column, int)


# ---------------------------------------------------------------------------
# has_c_marker
# ---------------------------------------------------------------------------


class TestHasCMarker:
    """Tests for has_c_marker function."""

    def test_returns_true_when_cmakelists_exists(self, tmp_path: Path) -> None:
        """Return True when CMakeLists.txt exists in project root."""
        (tmp_path / "CMakeLists.txt").touch()
        assert has_c_marker(tmp_path) is True

    def test_returns_true_when_makefile_exists(self, tmp_path: Path) -> None:
        """Return True when Makefile exists in project root."""
        (tmp_path / "Makefile").touch()
        assert has_c_marker(tmp_path) is True

    def test_returns_true_when_meson_exists(self, tmp_path: Path) -> None:
        """Return True when meson.build exists in project root."""
        (tmp_path / "meson.build").touch()
        assert has_c_marker(tmp_path) is True

    def test_returns_false_when_no_markers(self, tmp_path: Path) -> None:
        """Return False when no C marker files exist."""
        assert has_c_marker(tmp_path) is False

    def test_does_not_check_subdirectories(self, tmp_path: Path) -> None:
        """Subdirectory marker files do not count for project root."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "CMakeLists.txt").touch()
        assert has_c_marker(tmp_path) is False


# ---------------------------------------------------------------------------
# has_cmake
# ---------------------------------------------------------------------------


class TestHasCmake:
    """Tests for has_cmake function."""

    def test_returns_true_when_exists(self, tmp_path: Path) -> None:
        """Return True when CMakeLists.txt exists in project root."""
        (tmp_path / "CMakeLists.txt").touch()
        assert has_cmake(tmp_path) is True

    def test_returns_false_when_missing(self, tmp_path: Path) -> None:
        """Return False when CMakeLists.txt is absent."""
        assert has_cmake(tmp_path) is False

    def test_checks_project_root_not_cwd(self, tmp_path: Path) -> None:
        """Check the given root, not some other directory."""
        other = tmp_path / "other"
        other.mkdir()
        (other / "CMakeLists.txt").touch()
        assert has_cmake(tmp_path) is False


# ---------------------------------------------------------------------------
# has_build_dir
# ---------------------------------------------------------------------------


class TestHasBuildDir:
    """Tests for has_build_dir function."""

    def test_finds_build_dir_with_cmake_cache(self, tmp_path: Path) -> None:
        """Return build directory when it contains CMakeCache.txt."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "CMakeCache.txt").touch()
        assert has_build_dir(tmp_path) == build_dir

    def test_finds_cmake_build_debug(self, tmp_path: Path) -> None:
        """Return cmake-build-debug directory when it contains CMakeCache.txt."""
        build_dir = tmp_path / "cmake-build-debug"
        build_dir.mkdir()
        (build_dir / "CMakeCache.txt").touch()
        assert has_build_dir(tmp_path) == build_dir

    def test_returns_none_when_no_build_dir(self, tmp_path: Path) -> None:
        """Return None when no build directory exists."""
        assert has_build_dir(tmp_path) is None

    def test_returns_none_when_build_dir_has_no_cache(self, tmp_path: Path) -> None:
        """Return None when build dir exists but has no CMakeCache.txt."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        assert has_build_dir(tmp_path) is None

    def test_prefers_first_match(self, tmp_path: Path) -> None:
        """Return the first matching build directory (build before cmake-build-debug)."""
        build1 = tmp_path / "build"
        build1.mkdir()
        (build1 / "CMakeCache.txt").touch()
        build2 = tmp_path / "cmake-build-debug"
        build2.mkdir()
        (build2 / "CMakeCache.txt").touch()
        assert has_build_dir(tmp_path) == build1

    def test_finds_out_dir(self, tmp_path: Path) -> None:
        """Return out directory when it contains CMakeCache.txt."""
        build_dir = tmp_path / "out"
        build_dir.mkdir()
        (build_dir / "CMakeCache.txt").touch()
        assert has_build_dir(tmp_path) == build_dir

    def test_finds_underscore_build_dir(self, tmp_path: Path) -> None:
        """Return _build directory when it contains CMakeCache.txt."""
        build_dir = tmp_path / "_build"
        build_dir.mkdir()
        (build_dir / "CMakeCache.txt").touch()
        assert has_build_dir(tmp_path) == build_dir
