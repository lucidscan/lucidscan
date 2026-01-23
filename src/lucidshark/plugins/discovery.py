"""Plugin discovery via Python entry points.

Supports discovering different plugin types:
- Scanner plugins: lucidshark.scanners
- Enricher plugins: lucidshark.enrichers (future)
- Reporter plugins: lucidshark.reporters (future)
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Dict, List, Type, TypeVar

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)

# Entry point group names for different plugin types
SCANNER_ENTRY_POINT_GROUP = "lucidshark.scanners"
ENRICHER_ENTRY_POINT_GROUP = "lucidshark.enrichers"
REPORTER_ENTRY_POINT_GROUP = "lucidshark.reporters"

# New plugin groups for v0.2+ quality pipeline
LINTER_ENTRY_POINT_GROUP = "lucidshark.linters"
TYPE_CHECKER_ENTRY_POINT_GROUP = "lucidshark.type_checkers"
TEST_RUNNER_ENTRY_POINT_GROUP = "lucidshark.test_runners"
COVERAGE_ENTRY_POINT_GROUP = "lucidshark.coverage"
DUPLICATION_ENTRY_POINT_GROUP = "lucidshark.duplication"

T = TypeVar("T")


def discover_plugins(group: str, base_class: Type[T] | None = None) -> Dict[str, Type[T]]:
    """Discover all installed plugins for a given entry point group.

    Plugins register themselves in their pyproject.toml:

        [project.entry-points."lucidshark.scanners"]
        trivy = "lucidshark.scanners.trivy:TrivyScanner"

    Args:
        group: Entry point group name (e.g., 'lucidshark.scanners').
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


def get_all_available_tools() -> Dict[str, List[str]]:
    """Get all available tools organized by category.

    This is a convenience function that discovers all plugin types
    and returns them in a structured format.

    Returns:
        Dictionary with keys 'scanners', 'linters', 'type_checkers',
        'test_runners', 'coverage', 'duplication' mapping to lists of plugin names.
    """
    return {
        "scanners": list_available_plugins(SCANNER_ENTRY_POINT_GROUP),
        "linters": list_available_plugins(LINTER_ENTRY_POINT_GROUP),
        "type_checkers": list_available_plugins(TYPE_CHECKER_ENTRY_POINT_GROUP),
        "test_runners": list_available_plugins(TEST_RUNNER_ENTRY_POINT_GROUP),
        "coverage": list_available_plugins(COVERAGE_ENTRY_POINT_GROUP),
        "duplication": list_available_plugins(DUPLICATION_ENTRY_POINT_GROUP),
    }
