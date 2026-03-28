"""Shared utilities for C plugins.

Common functionality used across C-based plugins (clang-tidy, clang-format,
cppcheck, ctest, gcov) to avoid code duplication.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)

# File extensions recognised as C source/header files.
C_EXTENSIONS = {".c", ".h"}

# Marker files that indicate a C project.
C_MARKER_FILES = ("CMakeLists.txt", "Makefile", "makefile", "GNUmakefile", "meson.build")


def find_clang_tidy() -> Path:
    """Find clang-tidy binary in PATH.

    Returns:
        Path to clang-tidy binary.

    Raises:
        FileNotFoundError: If clang-tidy is not found.
    """
    binary = shutil.which("clang-tidy")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "clang-tidy not found in PATH. Install via your package manager:\n"
        "  macOS: brew install llvm\n"
        "  Ubuntu/Debian: apt install clang-tidy\n"
        "  Fedora: dnf install clang-tools-extra"
    )


def find_clang_format() -> Path:
    """Find clang-format binary in PATH.

    Returns:
        Path to clang-format binary.

    Raises:
        FileNotFoundError: If clang-format is not found.
    """
    binary = shutil.which("clang-format")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "clang-format not found in PATH. Install via your package manager:\n"
        "  macOS: brew install clang-format\n"
        "  Ubuntu/Debian: apt install clang-format\n"
        "  Fedora: dnf install clang-tools-extra"
    )


def find_cppcheck() -> Path:
    """Find cppcheck binary in PATH.

    Returns:
        Path to cppcheck binary.

    Raises:
        FileNotFoundError: If cppcheck is not found.
    """
    binary = shutil.which("cppcheck")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "cppcheck not found in PATH. Install via your package manager:\n"
        "  macOS: brew install cppcheck\n"
        "  Ubuntu/Debian: apt install cppcheck\n"
        "  Fedora: dnf install cppcheck"
    )


def find_ctest() -> Path:
    """Find ctest binary in PATH.

    Returns:
        Path to ctest binary.

    Raises:
        FileNotFoundError: If ctest is not found.
    """
    binary = shutil.which("ctest")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "ctest not found in PATH. Install CMake to get ctest:\n"
        "  macOS: brew install cmake\n"
        "  Ubuntu/Debian: apt install cmake\n"
        "  Fedora: dnf install cmake"
    )


def find_gcov() -> Path:
    """Find gcov binary in PATH.

    Returns:
        Path to gcov binary.

    Raises:
        FileNotFoundError: If gcov is not found.
    """
    binary = shutil.which("gcov")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "gcov not found in PATH. It ships with GCC:\n"
        "  macOS: brew install gcc\n"
        "  Ubuntu/Debian: apt install gcc\n"
        "  Fedora: dnf install gcc"
    )


def find_lcov() -> Path:
    """Find lcov binary in PATH.

    Returns:
        Path to lcov binary.

    Raises:
        FileNotFoundError: If lcov is not found.
    """
    binary = shutil.which("lcov")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "lcov not found in PATH. Install via your package manager:\n"
        "  macOS: brew install lcov\n"
        "  Ubuntu/Debian: apt install lcov\n"
        "  Fedora: dnf install lcov"
    )


def _get_tool_version(binary_finder, version_flag: str) -> str:
    """Get version string from a C-related tool.

    Args:
        binary_finder: Callable that returns a Path to the binary.
        version_flag: CLI flag to get version (e.g., "--version").

    Returns:
        Version string or "unknown".
    """
    try:
        binary = binary_finder()
        result = subprocess.run(
            [str(binary), version_flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        # Some tools output version to stderr
        if result.stderr.strip():
            return result.stderr.strip()
    except Exception:
        pass
    return "unknown"


def get_clang_tidy_version() -> str:
    """Get clang-tidy version string."""
    return _get_tool_version(find_clang_tidy, "--version")


def get_clang_format_version() -> str:
    """Get clang-format version string."""
    return _get_tool_version(find_clang_format, "--version")


def get_cppcheck_version() -> str:
    """Get cppcheck version string."""
    return _get_tool_version(find_cppcheck, "--version")


def get_ctest_version() -> str:
    """Get ctest version string."""
    return _get_tool_version(find_ctest, "--version")


def get_gcov_version() -> str:
    """Get gcov version string."""
    return _get_tool_version(find_gcov, "--version")


def generate_issue_id(
    tool_prefix: str,
    code: str,
    file: str,
    line: Optional[int],
    column: Optional[int],
    message: str,
) -> str:
    """Generate deterministic issue ID.

    Args:
        tool_prefix: Tool name prefix for the ID (e.g., "clang-tidy").
        code: Error/lint code.
        file: File path.
        line: Line number.
        column: Column number.
        message: Error message.

    Returns:
        Unique issue ID.
    """
    content = f"{code}:{file}:{line or 0}:{column or 0}:{message}"
    hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"{tool_prefix}-{hash_val}"


def has_c_marker(project_root: Path) -> bool:
    """Check if project has any C project marker files.

    Args:
        project_root: Project root directory.

    Returns:
        True if any C marker file exists.
    """
    for marker in C_MARKER_FILES:
        if (project_root / marker).exists():
            return True
    return False


def has_cmake(project_root: Path) -> bool:
    """Check if project uses CMake.

    Args:
        project_root: Project root directory.

    Returns:
        True if CMakeLists.txt exists.
    """
    return (project_root / "CMakeLists.txt").exists()


def has_build_dir(project_root: Path) -> Optional[Path]:
    """Find the CMake build directory.

    Checks common build directory names.

    Args:
        project_root: Project root directory.

    Returns:
        Path to build directory or None.
    """
    for name in ("build", "cmake-build-debug", "cmake-build-release", "out", "_build"):
        build_dir = project_root / name
        if build_dir.is_dir() and (build_dir / "CMakeCache.txt").exists():
            return build_dir
    return None


def parse_c_error_position(
    text: str,
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Parse C compiler/tool error position from a string like 'file.c:42:5'.

    Args:
        text: Text containing an error position.

    Returns:
        Tuple of (file_path, line, column). Any may be None.
    """
    match = re.match(r"^(.+\.[ch]):(\d+)(?::(\d+))?", text)
    if match:
        file_path = match.group(1)
        line = int(match.group(2))
        column = int(match.group(3)) if match.group(3) else None
        return file_path, line, column
    return None, None, None
