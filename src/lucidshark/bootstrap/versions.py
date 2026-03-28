"""Centralized tool version management.

Reads tool versions from pyproject.toml [tool.lucidshark.tools] section.
This is the single source of truth for all lucidshark-managed tool versions.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from lucidshark.plugins.utils import get_tomllib

_tomllib = get_tomllib()


# Hardcoded fallback versions (kept in sync with pyproject.toml)
# These are used if pyproject.toml cannot be read at runtime
# Only includes tools that LucidShark downloads itself (security tools + duplo)
# Language-specific tools (ruff, biome, etc.) should be installed via package managers
_FALLBACK_VERSIONS: Dict[str, str] = {
    # Security scanners
    "trivy": "0.69.3",
    "opengrep": "1.16.4",
    "checkov": "3.2.508",
    "gosec": "2.24.7",
    # Java tools
    "pmd": "7.22.0",
    "checkstyle": "13.3.0",
    "spotbugs": "4.9.8",
    # Kotlin tools
    "ktlint": "1.5.0",
    "detekt": "1.23.7",
    # Duplication detection
    "duplo": "0.1.7",
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
        scanners_section = (
            data.get("tool", {}).get("lucidshark", {}).get("scanners", {})
        )
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
