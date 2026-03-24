"""Pytest configuration for binary integration tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def get_binary_path() -> Path:
    """Get the path to the lucidshark binary."""
    project_root = Path(__file__).parent.parent.parent.parent
    binary_path = project_root / "dist" / "lucidshark"

    # Platform-specific binary name
    if sys.platform == "win32":
        binary_path = binary_path.with_suffix(".exe")

    return binary_path


def binary_exists() -> bool:
    """Check if the binary exists."""
    return get_binary_path().exists()


@pytest.fixture
def binary_path() -> Path:
    """Provide the path to the lucidshark binary."""
    path = get_binary_path()
    if not path.exists():
        pytest.skip(f"Binary not found at {path}. Run 'pyinstaller lucidshark.spec' first.")
    return path


@pytest.fixture
def run_binary():
    """Fixture to run the binary with arguments."""

    def _run(*args: str, timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess:
        """Run the binary with given arguments.

        Args:
            *args: Command line arguments to pass to the binary
            timeout: Timeout in seconds (default: 30)
            check: Whether to check return code (default: False)

        Returns:
            CompletedProcess with stdout, stderr, and returncode
        """
        binary = get_binary_path()
        if not binary.exists():
            pytest.skip(f"Binary not found at {binary}")

        result = subprocess.run(
            [str(binary), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
        return result

    return _run
