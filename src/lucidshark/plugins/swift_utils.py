"""Shared utilities for Swift plugins.

Common helpers for Swift tool plugins to avoid code duplication
across swiftlint, swift_compiler, swift_test, swift_coverage, and swiftformat.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)


def find_swift() -> Path:
    """Find the swift binary.

    Returns:
        Path to swift binary.

    Raises:
        FileNotFoundError: If swift is not available.
    """
    binary = shutil.which("swift")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "swift is not installed. Install Xcode or Swift toolchain:\n"
        "  xcode-select --install  (macOS)\n"
        "  or see https://swift.org/install"
    )


def get_swift_version() -> str:
    """Get Swift version string.

    Returns:
        Version string or 'unknown'.
    """
    try:
        result = subprocess.run(
            ["swift", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            # Parse "Swift version X.Y.Z ..." from output
            for word in result.stdout.split():
                if word and word[0].isdigit():
                    return word
        return "unknown"
    except Exception:
        return "unknown"


def has_package_swift(project_root: Path) -> bool:
    """Check if project has Package.swift."""
    return (project_root / "Package.swift").exists()


def generate_issue_id(
    tool: str,
    code: str,
    file_path: str,
    line: Optional[int],
    column: Optional[int],
    message: str,
) -> str:
    """Generate deterministic issue ID for Swift tools."""
    content = f"{tool}:{code}:{file_path}:{line}:{column}:{message}"[:100]
    hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"{tool}-{hash_val}"
