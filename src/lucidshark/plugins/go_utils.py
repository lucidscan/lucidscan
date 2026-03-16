"""Shared utilities for Go plugins.

Common functionality used across Go-based plugins (golangci-lint, go vet,
go test, go cover, gofmt) to avoid code duplication.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)


def find_go() -> Path:
    """Find go binary in PATH.

    Returns:
        Path to go binary.

    Raises:
        FileNotFoundError: If go is not found.
    """
    go_bin = shutil.which("go")
    if go_bin:
        return Path(go_bin)
    raise FileNotFoundError("go not found in PATH. Install Go via https://go.dev/dl/")


def find_golangci_lint() -> Path:
    """Find golangci-lint binary.

    Checks:
    1. System PATH
    2. ~/go/bin/ (default GOBIN)

    Returns:
        Path to golangci-lint binary.

    Raises:
        FileNotFoundError: If golangci-lint is not found.
    """
    # Check system PATH
    binary = shutil.which("golangci-lint")
    if binary:
        return Path(binary)

    # Check ~/go/bin/
    gobin = Path.home() / "go" / "bin" / "golangci-lint"
    if gobin.exists():
        return gobin

    raise FileNotFoundError(
        "golangci-lint not found. Install with:\n"
        "  go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest\n"
        "  or: https://golangci-lint.run/welcome/install/"
    )


def find_gofmt() -> Path:
    """Find gofmt binary in PATH.

    Returns:
        Path to gofmt binary.

    Raises:
        FileNotFoundError: If gofmt is not found.
    """
    binary = shutil.which("gofmt")
    if binary:
        return Path(binary)
    raise FileNotFoundError(
        "gofmt not found in PATH. It ships with Go — install Go via https://go.dev/dl/"
    )


def _get_tool_version(binary_finder, version_flag: str) -> str:
    """Get version string from a Go-based tool.

    Args:
        binary_finder: Callable that returns a Path to the binary.
        version_flag: CLI flag to get version (e.g., "version", "-version", "--version").

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
    except Exception:
        pass
    return "unknown"


def get_go_version() -> str:
    """Get Go version string.

    Returns:
        Version string (e.g., "go version go1.22.0 linux/amd64") or "unknown".
    """
    return _get_tool_version(find_go, "version")


def find_gosec() -> Path:
    """Find gosec binary.

    Checks:
    1. System PATH
    2. ~/go/bin/ (default GOBIN)

    Returns:
        Path to gosec binary.

    Raises:
        FileNotFoundError: If gosec is not found.
    """
    # Check system PATH
    binary = shutil.which("gosec")
    if binary:
        return Path(binary)

    # Check ~/go/bin/
    gobin = Path.home() / "go" / "bin" / "gosec"
    if gobin.exists():
        return gobin

    raise FileNotFoundError(
        "gosec not found. Install with:\n"
        "  go install github.com/securego/gosec/v2/cmd/gosec@latest\n"
        "  or download from: https://github.com/securego/gosec/releases"
    )


def get_gosec_version() -> str:
    """Get gosec version string.

    Returns:
        Version string or "unknown".
    """
    return _get_tool_version(find_gosec, "-version")


def get_golangci_lint_version() -> str:
    """Get golangci-lint version string.

    Returns:
        Version string or "unknown".
    """
    return _get_tool_version(find_golangci_lint, "--version")


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
        tool_prefix: Tool name prefix for the ID (e.g., "golangci-lint", "go-vet").
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


def parse_go_error_position(
    text: str,
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Parse Go error position from a string like 'file.go:42:5'.

    Args:
        text: Text containing a Go error position.

    Returns:
        Tuple of (file_path, line, column). Any may be None.
    """
    # Match patterns like: /path/to/file.go:42:5: or file.go:42:
    match = re.match(r"^(.+\.go):(\d+)(?::(\d+))?", text)
    if match:
        file_path = match.group(1)
        line = int(match.group(2))
        column = int(match.group(3)) if match.group(3) else None
        return file_path, line, column
    return None, None, None


def has_go_mod(project_root: Path) -> bool:
    """Check if project has a go.mod file.

    Args:
        project_root: Project root directory.

    Returns:
        True if go.mod exists.
    """
    return (project_root / "go.mod").exists()


def ensure_go_in_path() -> Dict[str, str]:
    """Ensure 'go' command is in PATH for Go tools to work.

    Many Go tools (golangci-lint, go vet, go test, etc.) require the 'go'
    command to be available in PATH. This function finds the Go binary and
    returns environment variables to add it to PATH if needed.

    Returns:
        Dict of environment variables to set (may be empty if go already in PATH).
        Use with lucidshark.core.subprocess_runner.temporary_env().
    """
    current_path = os.environ.get("PATH", "")

    # Try to find 'go' binary
    go_binary = shutil.which("go")

    # If not found in PATH, check common locations
    if not go_binary:
        common_locations = [
            "/usr/local/go/bin/go",
            "/usr/bin/go",
            "/opt/homebrew/bin/go",
            str(Path.home() / "go/bin/go"),
            "/usr/local/bin/go",
        ]
        for location in common_locations:
            if Path(location).exists():
                go_binary = location
                LOGGER.debug(f"Found go binary at common location: {go_binary}")
                break

    env_vars: Dict[str, str] = {}
    if go_binary:
        go_bin_dir = str(Path(go_binary).parent)
        if go_bin_dir not in current_path:
            new_path = (
                f"{go_bin_dir}{os.pathsep}{current_path}"
                if current_path
                else go_bin_dir
            )
            env_vars["PATH"] = new_path
            LOGGER.debug(f"Adding Go binary directory to PATH: {go_bin_dir}")
    else:
        LOGGER.warning("Could not find 'go' binary - Go tools may fail")

    return env_vars
