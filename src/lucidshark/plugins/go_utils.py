"""Shared utilities for Go plugins.

Common functionality used across Go-based plugins (golangci-lint, go vet,
go test, go cover, gofmt) to avoid code duplication.
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


def get_go_version() -> str:
    """Get Go version string.

    Returns:
        Version string (e.g., "go version go1.22.0 linux/amd64") or "unknown".
    """
    try:
        go_bin = find_go()
        result = subprocess.run(
            [str(go_bin), "version"],
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


def get_golangci_lint_version() -> str:
    """Get golangci-lint version string.

    Returns:
        Version string or "unknown".
    """
    try:
        binary = find_golangci_lint()
        result = subprocess.run(
            [str(binary), "--version"],
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
