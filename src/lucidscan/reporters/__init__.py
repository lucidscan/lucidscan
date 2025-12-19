"""Reporter plugins for lucidscan output formatting.

Plugins are discovered via Python entry points (lucidscan.reporters group).
"""

from typing import Dict, Type

from lucidscan.reporters.base import ReporterPlugin
from lucidscan.reporters.json_reporter import JSONReporter
from lucidscan.reporters.table_reporter import TableReporter
from lucidscan.reporters.summary_reporter import SummaryReporter
from lucidscan.reporters.sarif_reporter import SARIFReporter
from lucidscan.plugins import REPORTER_ENTRY_POINT_GROUP
from lucidscan.plugins.discovery import (
    discover_plugins,
    get_plugin,
    list_available_plugins as _list_plugins,
)


def discover_reporter_plugins() -> Dict[str, Type[ReporterPlugin]]:
    """Discover all installed reporter plugins via entry points."""
    return discover_plugins(REPORTER_ENTRY_POINT_GROUP, ReporterPlugin)


def get_reporter_plugin(name: str) -> ReporterPlugin | None:
    """Get an instantiated reporter plugin by name."""
    return get_plugin(REPORTER_ENTRY_POINT_GROUP, name, ReporterPlugin)


def list_available_reporters() -> list[str]:
    """List names of all available reporter plugins."""
    return _list_plugins(REPORTER_ENTRY_POINT_GROUP)


__all__ = [
    "ReporterPlugin",
    "JSONReporter",
    "TableReporter",
    "SummaryReporter",
    "SARIFReporter",
    "discover_reporter_plugins",
    "get_reporter_plugin",
    "list_available_reporters",
]
