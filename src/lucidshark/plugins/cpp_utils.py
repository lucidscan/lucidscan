"""Shared utilities for C++ plugins.

Common functionality used across C++ plugins (clang-tidy, cppcheck,
ctest, lcov, clang-format) to avoid code duplication.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Dict, Optional

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)

# C++ file extensions
CPP_EXTENSIONS = {".cpp", ".cc", ".cxx", ".hpp", ".h", ".hh", ".hxx"}

# C++ source file extensions (excluding headers)
CPP_SOURCE_EXTENSIONS = {".cpp", ".cc", ".cxx"}


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
        "clang-tidy not found in PATH. Install via:\n"
        "  macOS: brew install llvm\n"
        "  Ubuntu/Debian: apt install clang-tidy\n"
        "  or: https://clang.llvm.org/extra/clang-tidy/"
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
        "cppcheck not found in PATH. Install via:\n"
        "  macOS: brew install cppcheck\n"
        "  Ubuntu/Debian: apt install cppcheck\n"
        "  or: https://cppcheck.sourceforge.io/"
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
        "ctest not found in PATH. Install CMake via:\n"
        "  macOS: brew install cmake\n"
        "  Ubuntu/Debian: apt install cmake\n"
        "  or: https://cmake.org/download/"
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
        "lcov not found in PATH. Install via:\n"
        "  macOS: brew install lcov\n"
        "  Ubuntu/Debian: apt install lcov\n"
        "  or: https://github.com/linux-test-project/lcov"
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
        "clang-format not found in PATH. Install via:\n"
        "  macOS: brew install clang-format\n"
        "  Ubuntu/Debian: apt install clang-format\n"
        "  or: https://clang.llvm.org/docs/ClangFormat.html"
    )


def find_cmake() -> Path:
    """Find cmake binary in PATH.

    Returns:
        Path to cmake binary.

    Raises:
        FileNotFoundError: If cmake is not found.
    """
    binary = shutil.which("cmake")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "cmake not found in PATH. Install via:\n"
        "  macOS: brew install cmake\n"
        "  Ubuntu/Debian: apt install cmake\n"
        "  or: https://cmake.org/download/"
    )


def has_cmake_project(project_root: Path) -> bool:
    """Check if project has a CMakeLists.txt file.

    Args:
        project_root: Project root directory.

    Returns:
        True if CMakeLists.txt exists.
    """
    return (project_root / "CMakeLists.txt").exists()


def find_build_dir(project_root: Path) -> Optional[Path]:
    """Find the CMake build directory.

    Checks common build directory names in order of preference.

    Args:
        project_root: Project root directory.

    Returns:
        Path to build directory, or None if not found.
    """
    candidates = ["build", "cmake-build-debug", "cmake-build-release", "out/build"]
    for candidate in candidates:
        build_dir = project_root / candidate
        if build_dir.exists() and (build_dir / "CMakeCache.txt").exists():
            return build_dir
    return None


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
        tool_prefix: Tool name prefix for the ID.
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


def get_tool_version(binary_finder, version_flag: str = "--version") -> str:
    """Get version string from a C++ tool.

    Args:
        binary_finder: Callable that returns a Path to the binary.
        version_flag: CLI flag to get version.

    Returns:
        Version string or "unknown".
    """
    import subprocess

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
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return "unknown"


def ensure_cpp_tools_in_path() -> Dict[str, str]:
    """Ensure C++ tools are findable in PATH.

    Checks common LLVM/Homebrew installation locations and adds them
    to PATH if needed.

    Returns:
        Dict of environment variables to set (may be empty).
    """
    current_path = os.environ.get("PATH", "")
    extra_dirs = []

    # Common LLVM/clang installation directories
    common_dirs = [
        "/usr/local/opt/llvm/bin",
        "/opt/homebrew/opt/llvm/bin",
        "/usr/lib/llvm-18/bin",
        "/usr/lib/llvm-17/bin",
        "/usr/lib/llvm-16/bin",
        "/usr/lib/llvm-15/bin",
        "/usr/lib/llvm-14/bin",
    ]

    for d in common_dirs:
        if Path(d).exists() and d not in current_path:
            extra_dirs.append(d)

    if extra_dirs:
        new_path = os.pathsep.join(extra_dirs) + os.pathsep + current_path
        return {"PATH": new_path}

    return {}
