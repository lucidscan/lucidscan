"""Plugin discovery via Python entry points.

Supports discovering different plugin types:
- Scanner plugins: lucidscan.scanners
- Enricher plugins: lucidscan.enrichers (future)
- Reporter plugins: lucidscan.reporters (future)
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Dict, List, Type, TypeVar

from lucidscan.core.logging import get_logger

LOGGER = get_logger(__name__)

# Entry point group names for different plugin types
SCANNER_ENTRY_POINT_GROUP = "lucidscan.scanners"
ENRICHER_ENTRY_POINT_GROUP = "lucidscan.enrichers"
REPORTER_ENTRY_POINT_GROUP = "lucidscan.reporters"

# New plugin groups for v0.2+ quality pipeline
LINTER_ENTRY_POINT_GROUP = "lucidscan.linters"
TYPE_CHECKER_ENTRY_POINT_GROUP = "lucidscan.type_checkers"
TEST_RUNNER_ENTRY_POINT_GROUP = "lucidscan.test_runners"
COVERAGE_ENTRY_POINT_GROUP = "lucidscan.coverage"

T = TypeVar("T")


def discover_plugins(group: str, base_class: Type[T] | None = None) -> Dict[str, Type[T]]:
    """Discover all installed plugins for a given entry point group.

    Plugins register themselves in their pyproject.toml:

        [project.entry-points."lucidscan.scanners"]
        trivy = "lucidscan.scanners.trivy:TrivyScanner"

    Args:
        group: Entry point group name (e.g., 'lucidscan.scanners').
        base_class: Optional base class to validate plugins against.

    Returns:
        Dictionary mapping plugin names to plugin classes.
    """
    plugins: Dict[str, Type[T]] = {}

    try:
        eps = entry_points(group=group)
    except TypeError:
        # Python 3.9 compatibility
        all_eps = entry_points()
        eps = getattr(all_eps, group, [])  # type: ignore[assignment]

    for ep in eps:
        try:
            plugin_class = ep.load()
            if base_class is not None and not issubclass(plugin_class, base_class):
                LOGGER.warning(
                    f"Plugin '{ep.name}' does not inherit from {base_class.__name__}, skipping"
                )
                continue
            plugins[ep.name] = plugin_class
            LOGGER.debug(f"Discovered plugin: {ep.name} (group: {group})")
        except Exception as e:
            LOGGER.warning(f"Failed to load plugin '{ep.name}': {e}")

    return plugins


def get_plugin(
    group: str,
    name: str,
    base_class: Type[T] | None = None,
    **kwargs,
) -> T | None:
    """Get an instantiated plugin by name.

    Args:
        group: Entry point group name.
        name: Plugin name (e.g., 'trivy').
        base_class: Optional base class to validate against.
        **kwargs: Additional arguments to pass to the plugin constructor.
                  Common kwargs include:
                  - project_root: Path to project root for tool installation.

    Returns:
        Instantiated plugin or None if not found.
    """
    plugins = discover_plugins(group, base_class)
    plugin_class = plugins.get(name)
    if plugin_class:
        return plugin_class(**kwargs)
    return None


def list_available_plugins(group: str) -> List[str]:
    """List names of all available plugins in a group.

    Args:
        group: Entry point group name.

    Returns:
        List of plugin names.
    """
    return list(discover_plugins(group).keys())
