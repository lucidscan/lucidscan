"""Centralized tool version management.

Reads tool versions from pyproject.toml [tool.lucidshark.tools] section.
This is the single source of truth for all lucidshark-managed tool versions.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

# Import tomllib (Python 3.11+) or tomli (Python 3.10)
try:
    if sys.version_info >= (3, 11):
        import tomllib

        _tomllib: Any = tomllib
    else:
        import tomli

        _tomllib = tomli
except ImportError:
    _tomllib = None  # Will use fallback versions


# Hardcoded fallback versions (kept in sync with pyproject.toml)
# These are used if pyproject.toml cannot be read at runtime
_FALLBACK_VERSIONS: Dict[str, str] = {
    # Security scanners
    "trivy": "0.68.2",
    "opengrep": "1.15.0",
    "checkov": "3.2.499",
    # Linters
    "ruff": "0.14.11",
    "biome": "2.3.11",
    "checkstyle": "13.0.0",
    # Type checkers
    "pyright": "1.1.408",
    # Duplication detection
    "duplo": "0.1.4",
}


@lru_cache(maxsize=1)
def _load_pyproject_versions() -> Dict[str, str]:
    """Load tool versions from lucidshark's pyproject.toml.

    Returns:
        Dictionary mapping tool names to versions.
    """
    if _tomllib is None:
        return _FALLBACK_VERSIONS.copy()

    # Find pyproject.toml relative to this module
    # Structure: src/lucidshark/bootstrap/versions.py -> ../../../pyproject.toml
    pyproject_path = Path(__file__).parent.parent.parent.parent / "pyproject.toml"

    if not pyproject_path.exists():
        # Installed package - pyproject.toml not available
        return _FALLBACK_VERSIONS.copy()

    try:
        with open(pyproject_path, "rb") as f:
            data = _tomllib.load(f)

        versions = {}

        # Read from [tool.lucidshark.tools] section (new unified section)
        tools_section = data.get("tool", {}).get("lucidshark", {}).get("tools", {})
        versions.update(tools_section)

        # Also read from legacy [tool.lucidshark.scanners] section for backwards compat
        scanners_section = data.get("tool", {}).get("lucidshark", {}).get("scanners", {})
        for tool, version in scanners_section.items():
            if tool not in versions:
                versions[tool] = version

        # Fill in any missing tools from fallbacks
        for tool, version in _FALLBACK_VERSIONS.items():
            if tool not in versions:
                versions[tool] = version

        return versions

    except Exception:
        return _FALLBACK_VERSIONS.copy()


def get_tool_version(tool_name: str, default: Optional[str] = None) -> str:
    """Get the version for a specific tool.

    Args:
        tool_name: Name of the tool (e.g., 'trivy', 'ruff').
        default: Optional default version if tool not found.

    Returns:
        Version string for the tool.

    Raises:
        KeyError: If tool not found and no default provided.
    """
    versions = _load_pyproject_versions()

    if tool_name in versions:
        return versions[tool_name]

    if default is not None:
        return default

    raise KeyError(f"Unknown tool: {tool_name}. Available: {list(versions.keys())}")


def get_all_versions() -> Dict[str, str]:
    """Get all tool versions.

    Returns:
        Dictionary mapping tool names to versions.
    """
    return _load_pyproject_versions().copy()
