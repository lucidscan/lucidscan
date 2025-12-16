"""Scanner plugins for integrating external security tools.

Plugins are discovered via Python entry points (lucidscan.scanners group).
"""

from typing import Dict, Type

from lucidscan.scanners.base import ScannerPlugin
from lucidscan.scanners.trivy import TrivyScanner
from lucidscan.scanners.opengrep import OpenGrepScanner
from lucidscan.scanners.checkov import CheckovScanner
from lucidscan.plugins import SCANNER_ENTRY_POINT_GROUP
from lucidscan.plugins.discovery import discover_plugins, get_plugin, list_available_plugins as _list_plugins


def discover_scanner_plugins() -> Dict[str, Type[ScannerPlugin]]:
    """Discover all installed scanner plugins via entry points."""
    return discover_plugins(SCANNER_ENTRY_POINT_GROUP, ScannerPlugin)


def get_scanner_plugin(name: str) -> ScannerPlugin | None:
    """Get an instantiated scanner plugin by name."""
    return get_plugin(SCANNER_ENTRY_POINT_GROUP, name, ScannerPlugin)


def list_available_scanners() -> list[str]:
    """List names of all available scanner plugins."""
    return _list_plugins(SCANNER_ENTRY_POINT_GROUP)


__all__ = [
    "ScannerPlugin",
    "TrivyScanner",
    "OpenGrepScanner",
    "CheckovScanner",
    "discover_scanner_plugins",
    "get_scanner_plugin",
    "list_available_scanners",
]


