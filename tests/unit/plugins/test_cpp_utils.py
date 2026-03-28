"""Unit tests for C++ plugin utilities."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.plugins.cpp_utils import (
    CPP_EXTENSIONS,
    CPP_SOURCE_EXTENSIONS,
    find_build_dir,
    find_clang_format,
    find_clang_tidy,
    find_cmake,
    find_cppcheck,
    find_ctest,
    find_lcov,
    generate_issue_id,
    has_cmake_project,
)


class TestCppExtensions:
    """Tests for C++ extension constants."""

    def test_cpp_extensions_includes_cpp(self) -> None:
        assert ".cpp" in CPP_EXTENSIONS

    def test_cpp_extensions_includes_cc(self) -> None:
        assert ".cc" in CPP_EXTENSIONS

    def test_cpp_extensions_includes_cxx(self) -> None:
        assert ".cxx" in CPP_EXTENSIONS

    def test_cpp_extensions_includes_hpp(self) -> None:
        assert ".hpp" in CPP_EXTENSIONS

    def test_cpp_extensions_includes_h(self) -> None:
        assert ".h" in CPP_EXTENSIONS

    def test_cpp_source_extensions_no_headers(self) -> None:
        assert ".h" not in CPP_SOURCE_EXTENSIONS
        assert ".hpp" not in CPP_SOURCE_EXTENSIONS


class TestFindBinaries:
    """Tests for binary finder functions."""

    @patch("shutil.which", return_value="/usr/bin/clang-tidy")
    def test_find_clang_tidy(self, mock_which) -> None:
        result = find_clang_tidy()
        assert result == Path("/usr/bin/clang-tidy")

    @patch("shutil.which", return_value=None)
    def test_find_clang_tidy_not_found(self, mock_which) -> None:
        with pytest.raises(FileNotFoundError, match="clang-tidy"):
            find_clang_tidy()

    @patch("shutil.which", return_value="/usr/bin/cppcheck")
    def test_find_cppcheck(self, mock_which) -> None:
        result = find_cppcheck()
        assert result == Path("/usr/bin/cppcheck")

    @patch("shutil.which", return_value=None)
    def test_find_cppcheck_not_found(self, mock_which) -> None:
        with pytest.raises(FileNotFoundError, match="cppcheck"):
            find_cppcheck()

    @patch("shutil.which", return_value="/usr/bin/ctest")
    def test_find_ctest(self, mock_which) -> None:
        result = find_ctest()
        assert result == Path("/usr/bin/ctest")

    @patch("shutil.which", return_value=None)
    def test_find_ctest_not_found(self, mock_which) -> None:
        with pytest.raises(FileNotFoundError, match="ctest"):
            find_ctest()

    @patch("shutil.which", return_value="/usr/bin/lcov")
    def test_find_lcov(self, mock_which) -> None:
        result = find_lcov()
        assert result == Path("/usr/bin/lcov")

    @patch("shutil.which", return_value=None)
    def test_find_lcov_not_found(self, mock_which) -> None:
        with pytest.raises(FileNotFoundError, match="lcov"):
            find_lcov()

    @patch("shutil.which", return_value="/usr/bin/clang-format")
    def test_find_clang_format(self, mock_which) -> None:
        result = find_clang_format()
        assert result == Path("/usr/bin/clang-format")

    @patch("shutil.which", return_value=None)
    def test_find_clang_format_not_found(self, mock_which) -> None:
        with pytest.raises(FileNotFoundError, match="clang-format"):
            find_clang_format()

    @patch("shutil.which", return_value="/usr/bin/cmake")
    def test_find_cmake(self, mock_which) -> None:
        result = find_cmake()
        assert result == Path("/usr/bin/cmake")

    @patch("shutil.which", return_value=None)
    def test_find_cmake_not_found(self, mock_which) -> None:
        with pytest.raises(FileNotFoundError, match="cmake"):
            find_cmake()


class TestHasCMakeProject:
    """Tests for has_cmake_project."""

    def test_has_cmake_project_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CMakeLists.txt").write_text("project(test)")
            assert has_cmake_project(Path(tmpdir)) is True

    def test_has_cmake_project_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            assert has_cmake_project(Path(tmpdir)) is False


class TestFindBuildDir:
    """Tests for find_build_dir."""

    def test_finds_build_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            (build_dir / "CMakeCache.txt").write_text("# CMake cache")
            result = find_build_dir(Path(tmpdir))
            assert result == build_dir

    def test_finds_cmake_build_debug(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "cmake-build-debug"
            build_dir.mkdir()
            (build_dir / "CMakeCache.txt").write_text("# CMake cache")
            result = find_build_dir(Path(tmpdir))
            assert result == build_dir

    def test_returns_none_when_no_build_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_build_dir(Path(tmpdir))
            assert result is None

    def test_returns_none_without_cmake_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            # No CMakeCache.txt
            result = find_build_dir(Path(tmpdir))
            assert result is None


class TestGenerateIssueId:
    """Tests for generate_issue_id."""

    def test_deterministic(self) -> None:
        id1 = generate_issue_id("clang-tidy", "bugprone", "main.cpp", 42, 5, "msg")
        id2 = generate_issue_id("clang-tidy", "bugprone", "main.cpp", 42, 5, "msg")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        id1 = generate_issue_id("clang-tidy", "bugprone", "main.cpp", 42, 5, "msg1")
        id2 = generate_issue_id("clang-tidy", "bugprone", "main.cpp", 42, 5, "msg2")
        assert id1 != id2

    def test_includes_tool_prefix(self) -> None:
        issue_id = generate_issue_id("clang-tidy", "bugprone", "main.cpp", 1, 1, "msg")
        assert issue_id.startswith("clang-tidy-")

    def test_handles_none_line_column(self) -> None:
        issue_id = generate_issue_id("cppcheck", "error", "test.cpp", None, None, "msg")
        assert issue_id.startswith("cppcheck-")
