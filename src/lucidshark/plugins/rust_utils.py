"""Shared utilities for Rust plugins.

Common functionality used across cargo-based plugins (clippy, cargo check,
cargo test, tarpaulin) to avoid code duplication.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)


def find_cargo() -> Path:
    """Find cargo binary in PATH.

    Returns:
        Path to cargo binary.

    Raises:
        FileNotFoundError: If cargo is not found.
    """
    cargo = shutil.which("cargo")
    if cargo:
        return Path(cargo)
    raise FileNotFoundError(
        "cargo not found in PATH. Install Rust via https://rustup.rs/"
    )


def get_cargo_version(subcommand: Optional[str] = None) -> str:
    """Get version string for a cargo subcommand.

    Args:
        subcommand: Cargo subcommand (e.g., "clippy", "tarpaulin").
            If None, returns cargo's own version.

    Returns:
        Version string or "unknown".
    """
    try:
        cargo = find_cargo()
        cmd = [str(cargo)]
        if subcommand:
            cmd.append(subcommand)
        cmd.append("--version")
        result = subprocess.run(
            cmd,
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


def ensure_cargo_subcommand(
    subcommand: str,
    install_hint: str,
) -> Path:
    """Ensure a cargo subcommand is available.

    Args:
        subcommand: Cargo subcommand to verify (e.g., "clippy", "tarpaulin").
        install_hint: Installation instructions if not found.

    Returns:
        Path to cargo binary.

    Raises:
        FileNotFoundError: If cargo or the subcommand is not available.
    """
    cargo = find_cargo()
    result = subprocess.run(
        [str(cargo), subcommand, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        raise FileNotFoundError(install_hint)
    return cargo


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
        tool_prefix: Tool name prefix for the ID (e.g., "clippy", "cargo-check").
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


def parse_diagnostic_spans(
    message: dict, project_root: Path
) -> tuple[
    Optional[Path],
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[str],
]:
    """Extract location info from a cargo diagnostic message's spans.

    Args:
        message: Parsed JSON message object with "spans" field.
        project_root: Project root directory.

    Returns:
        Tuple of (file_path, line_start, line_end, column_start, column_end, code_snippet).
    """
    spans = message.get("spans", [])
    primary_span = None
    for span in spans:
        if span.get("is_primary", False):
            primary_span = span
            break
    if not primary_span and spans:
        primary_span = spans[0]

    file_path = None
    line_start = None
    line_end = None
    column_start = None
    column_end = None
    code_snippet = None

    if primary_span:
        file_name = primary_span.get("file_name", "")
        if file_name and not file_name.startswith("/rustc/"):
            file_path = Path(file_name)
            if not file_path.is_absolute():
                file_path = project_root / file_path

        line_start = primary_span.get("line_start")
        line_end = primary_span.get("line_end")
        column_start = primary_span.get("column_start")
        column_end = primary_span.get("column_end")

        span_text = primary_span.get("text", [])
        if span_text:
            code_snippet = "\n".join(
                t.get("text", "") for t in span_text
            )

    return file_path, line_start, line_end, column_start, column_end, code_snippet


def extract_suggestion(message: dict) -> Optional[str]:
    """Extract suggestion from diagnostic message children.

    Args:
        message: Parsed JSON message object with "children" field.

    Returns:
        Suggestion string or None.
    """
    children = message.get("children", [])
    for child in children:
        if child.get("level") == "help":
            return child.get("message", "")
    return None
