"""Status command implementation."""

from __future__ import annotations

from argparse import Namespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lucidscan.config.models import LucidScanConfig

from lucidscan.bootstrap.paths import get_lucidscan_home, LucidscanPaths
from lucidscan.bootstrap.platform import get_platform_info
from lucidscan.bootstrap.validation import validate_binary, ToolStatus
from lucidscan.cli.commands import Command
from lucidscan.cli.exit_codes import EXIT_SUCCESS
from lucidscan.plugins.scanners import discover_scanner_plugins


class StatusCommand(Command):
    """Shows scanner plugin status and environment information."""

    def __init__(self, version: str):
        """Initialize StatusCommand.

        Args:
            version: Current lucidscan version string.
        """
        self._version = version

    @property
    def name(self) -> str:
        """Command identifier."""
        return "status"

    def execute(self, args: Namespace, config: "LucidScanConfig | None" = None) -> int:
        """Execute the status command.

        Displays lucidscan version, platform info, and scanner plugin status.

        Args:
            args: Parsed command-line arguments.
            config: Optional LucidScan configuration (unused).

        Returns:
            Exit code (always 0 for status).
        """
        # Use current directory as project root
        home = get_lucidscan_home()
        paths = LucidscanPaths(home)
        platform_info = get_platform_info()

        print(f"lucidscan version: {self._version}")
        print(f"Platform: {platform_info.os}-{platform_info.arch}")
        print(f"Tool cache: {home}/bin/")
        print()

        # Discover plugins via entry points
        print("Scanner plugins:")
        plugins = discover_scanner_plugins()

        if plugins:
            for name, plugin_class in sorted(plugins.items()):
                try:
                    plugin = plugin_class()
                    domains = ", ".join(d.value.upper() for d in plugin.domains)
                    binary_dir = paths.plugin_bin_dir(name, plugin.get_version())
                    binary_path = binary_dir / name

                    status = validate_binary(binary_path)
                    if status == ToolStatus.PRESENT:
                        status_str = f"v{plugin.get_version()} installed"
                    else:
                        status_str = f"v{plugin.get_version()} (not downloaded)"

                    print(f"  {name}: {status_str} [{domains}]")
                except Exception as e:
                    print(f"  {name}: error loading plugin ({e})")
        else:
            print("  No plugins discovered.")

        print()
        print("Tools are downloaded to .lucidscan/ on first scan.")

        return EXIT_SUCCESS
