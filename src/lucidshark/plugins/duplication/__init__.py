"""Duplication detection plugins for lucidshark.

This module provides code duplication detection integrations.
Duplication plugins are discovered via the lucidshark.duplication entry point group.
"""

from lucidshark.plugins.duplication.base import (
    DuplicateBlock,
    DuplicationPlugin,
    DuplicationResult,
)
from lucidshark.plugins.discovery import (
    DUPLICATION_ENTRY_POINT_GROUP,
    discover_plugins,
)


def discover_duplication_plugins():
    """Discover all installed duplication plugins.

    Returns:
        Dictionary mapping plugin names to plugin classes.
    """
    return discover_plugins(DUPLICATION_ENTRY_POINT_GROUP, DuplicationPlugin)


__all__ = [
    "DuplicateBlock",
    "DuplicationPlugin",
    "DuplicationResult",
    "discover_duplication_plugins",
]
