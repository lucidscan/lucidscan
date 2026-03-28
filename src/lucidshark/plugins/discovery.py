"""Plugin discovery via Python entry points.

Supports discovering different plugin types:
- Scanner plugins: lucidshark.scanners
- Enricher plugins: lucidshark.enrichers (future)
- Reporter plugins: lucidshark.reporters (future)
"""

from __future__ import annotations

import sys
from importlib.metadata import entry_points
from typing import Dict, List, Type, TypeVar

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)


def _is_frozen() -> bool:
    """Check if running in a PyInstaller frozen binary."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

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
FORMATTER_ENTRY_POINT_GROUP = "lucidshark.formatters"

T = TypeVar("T")


def _get_frozen_plugins(group: str) -> Dict[str, Type]:
    """Get plugins for frozen binary (PyInstaller) where entry_points don't work.

    This manually imports and registers all built-in plugins since entry_points()
    doesn't work in frozen binaries.
    """
    plugins: Dict[str, Type] = {}

    # Map of group names to (plugin_name, module_path, class_name) tuples
    FROZEN_PLUGIN_REGISTRY = {
        LINTER_ENTRY_POINT_GROUP: [
            ('ruff', 'lucidshark.plugins.linters.ruff', 'RuffLinter'),
            ('eslint', 'lucidshark.plugins.linters.eslint', 'ESLintLinter'),
            ('biome', 'lucidshark.plugins.linters.biome', 'BiomeLinter'),
            ('clippy', 'lucidshark.plugins.linters.clippy', 'ClippyLinter'),
            ('golangci_lint', 'lucidshark.plugins.linters.golangci_lint', 'GoLangCILintLinter'),
            ('checkstyle', 'lucidshark.plugins.linters.checkstyle', 'CheckstyleLinter'),
            ('pmd', 'lucidshark.plugins.linters.pmd', 'PmdLinter'),
            ('scalafix', 'lucidshark.plugins.linters.scalafix', 'ScalafixLinter'),
        ],
        SCANNER_ENTRY_POINT_GROUP: [
            ('trivy', 'lucidshark.plugins.scanners.trivy', 'TrivyScanner'),
            ('opengrep', 'lucidshark.plugins.scanners.opengrep', 'OpenGrepScanner'),
            ('checkov', 'lucidshark.plugins.scanners.checkov', 'CheckovScanner'),
            ('gosec', 'lucidshark.plugins.scanners.gosec', 'GosecScanner'),
        ],
        REPORTER_ENTRY_POINT_GROUP: [
            ('ai', 'lucidshark.plugins.reporters.ai_reporter', 'AIReporter'),
            ('json', 'lucidshark.plugins.reporters.json_reporter', 'JSONReporter'),
            ('sarif', 'lucidshark.plugins.reporters.sarif_reporter', 'SARIFReporter'),
            ('summary', 'lucidshark.plugins.reporters.summary_reporter', 'SummaryReporter'),
            ('table', 'lucidshark.plugins.reporters.table_reporter', 'TableReporter'),
        ],
        TYPE_CHECKER_ENTRY_POINT_GROUP: [
            ('mypy', 'lucidshark.plugins.type_checkers.mypy', 'MypyChecker'),
            ('pyright', 'lucidshark.plugins.type_checkers.pyright', 'PyrightChecker'),
            ('typescript', 'lucidshark.plugins.type_checkers.typescript', 'TypeScriptChecker'),
            ('spotbugs', 'lucidshark.plugins.type_checkers.spotbugs', 'SpotBugsChecker'),
            ('cargo_check', 'lucidshark.plugins.type_checkers.cargo_check', 'CargoCheckChecker'),
            ('go_vet', 'lucidshark.plugins.type_checkers.go_vet', 'GoVetChecker'),
            ('scala_compile', 'lucidshark.plugins.type_checkers.scala_compile', 'ScalaCompileChecker'),
        ],
        TEST_RUNNER_ENTRY_POINT_GROUP: [
            ('pytest', 'lucidshark.plugins.test_runners.pytest', 'PytestRunner'),
            ('jest', 'lucidshark.plugins.test_runners.jest', 'JestRunner'),
            ('karma', 'lucidshark.plugins.test_runners.karma', 'KarmaRunner'),
            ('playwright', 'lucidshark.plugins.test_runners.playwright', 'PlaywrightRunner'),
            ('maven', 'lucidshark.plugins.test_runners.maven', 'MavenTestRunner'),
            ('cargo', 'lucidshark.plugins.test_runners.cargo', 'CargoTestRunner'),
            ('go_test', 'lucidshark.plugins.test_runners.go_test', 'GoTestRunner'),
            ('vitest', 'lucidshark.plugins.test_runners.vitest', 'VitestRunner'),
            ('mocha', 'lucidshark.plugins.test_runners.mocha', 'MochaRunner'),
            ('sbt', 'lucidshark.plugins.test_runners.sbt', 'SbtTestRunner'),
        ],
        COVERAGE_ENTRY_POINT_GROUP: [
            ('coverage_py', 'lucidshark.plugins.coverage.coverage_py', 'CoveragePyPlugin'),
            ('istanbul', 'lucidshark.plugins.coverage.istanbul', 'IstanbulPlugin'),
            ('jacoco', 'lucidshark.plugins.coverage.jacoco', 'JaCoCoPlugin'),
            ('tarpaulin', 'lucidshark.plugins.coverage.tarpaulin', 'TarpaulinPlugin'),
            ('go_cover', 'lucidshark.plugins.coverage.go_cover', 'GoCoverPlugin'),
            ('vitest_coverage', 'lucidshark.plugins.coverage.vitest', 'VitestCoveragePlugin'),
            ('scoverage', 'lucidshark.plugins.coverage.scoverage', 'ScoveragePlugin'),
        ],
        DUPLICATION_ENTRY_POINT_GROUP: [
            ('duplo', 'lucidshark.plugins.duplication.duplo', 'DuploPlugin'),
        ],
        FORMATTER_ENTRY_POINT_GROUP: [
            ('ruff_format', 'lucidshark.plugins.formatters.ruff_format', 'RuffFormatter'),
            ('prettier', 'lucidshark.plugins.formatters.prettier', 'PrettierFormatter'),
            ('rustfmt', 'lucidshark.plugins.formatters.rustfmt', 'RustfmtFormatter'),
            ('gofmt', 'lucidshark.plugins.formatters.gofmt', 'GofmtFormatter'),
            ('scalafmt', 'lucidshark.plugins.formatters.scalafmt', 'ScalafmtFormatter'),
        ],
    }

    plugin_specs = FROZEN_PLUGIN_REGISTRY.get(group, [])

    for plugin_name, module_path, class_name in plugin_specs:
        try:
            module = __import__(module_path, fromlist=[class_name])
            plugin_class = getattr(module, class_name)
            plugins[plugin_name] = plugin_class
            LOGGER.debug(f"Loaded frozen plugin: {plugin_name} (group: {group})")
        except Exception as e:
            LOGGER.warning(f"Failed to load frozen plugin '{plugin_name}': {e}")

    return plugins


def discover_plugins(
    group: str, base_class: Type[T] | None = None
) -> Dict[str, Type[T]]:
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
    # Use manual plugin registry for frozen binaries (PyInstaller)
    if _is_frozen():
        LOGGER.debug(f"Running in frozen binary, using manual plugin registry for group: {group}")
        return _get_frozen_plugins(group)  # type: ignore[return-value]

    # Normal entry_points discovery for non-frozen execution
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
        "formatters": list_available_plugins(FORMATTER_ENTRY_POINT_GROUP),
    }
