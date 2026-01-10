"""Serve command implementation.

Run LucidScan as an MCP server for AI agents or as a file watcher.
"""

from __future__ import annotations

import asyncio
from argparse import Namespace
from pathlib import Path

from lucidscan.cli.commands import Command
from lucidscan.cli.exit_codes import EXIT_SUCCESS, EXIT_SCANNER_ERROR
from lucidscan.config import LucidScanConfig
from lucidscan.core.logging import get_logger

LOGGER = get_logger(__name__)


class ServeCommand(Command):
    """Run LucidScan as a server for AI integration."""

    def __init__(self, version: str):
        """Initialize ServeCommand.

        Args:
            version: Current lucidscan version string.
        """
        self._version = version

    @property
    def name(self) -> str:
        """Command identifier."""
        return "serve"

    def execute(self, args: Namespace, config: "LucidScanConfig | None" = None) -> int:
        """Execute the serve command.

        Args:
            args: Parsed command-line arguments.
            config: LucidScan configuration.

        Returns:
            Exit code.
        """
        if config is None:
            LOGGER.error("Configuration is required for serve command")
            return EXIT_SCANNER_ERROR

        project_root = Path(args.path).resolve()

        if not project_root.is_dir():
            LOGGER.error(f"Not a directory: {project_root}")
            return EXIT_SCANNER_ERROR

        # Determine mode
        if args.mcp:
            return self._run_mcp_server(args, config, project_root)
        elif args.watch:
            return self._run_file_watcher(args, config, project_root)
        else:
            # Default to MCP mode
            return self._run_mcp_server(args, config, project_root)

    def _run_mcp_server(
        self,
        args: Namespace,
        config: LucidScanConfig,
        project_root: Path,
    ) -> int:
        """Run LucidScan as an MCP server.

        Args:
            args: Parsed command-line arguments.
            config: LucidScan configuration.
            project_root: Project root directory.

        Returns:
            Exit code.
        """
        try:
            from lucidscan.mcp.server import LucidScanMCPServer

            LOGGER.info(f"Starting MCP server for {project_root}")
            server = LucidScanMCPServer(project_root, config)
            asyncio.run(server.run())
            return EXIT_SUCCESS
        except ImportError as e:
            LOGGER.error(f"MCP dependencies not installed: {e}")
            LOGGER.error("Install with: pip install lucidscan[mcp]")
            return EXIT_SCANNER_ERROR
        except Exception as e:
            LOGGER.error(f"MCP server error: {e}")
            return EXIT_SCANNER_ERROR

    def _run_file_watcher(
        self,
        args: Namespace,
        config: LucidScanConfig,
        project_root: Path,
    ) -> int:
        """Run LucidScan in file watcher mode.

        Args:
            args: Parsed command-line arguments.
            config: LucidScan configuration.
            project_root: Project root directory.

        Returns:
            Exit code.
        """
        try:
            from lucidscan.mcp.watcher import LucidScanFileWatcher

            debounce_ms = getattr(args, "debounce", 1000)
            LOGGER.info(f"Starting file watcher for {project_root}")
            LOGGER.info(f"Debounce: {debounce_ms}ms")

            watcher = LucidScanFileWatcher(
                project_root=project_root,
                config=config,
                debounce_ms=debounce_ms,
            )

            # Set up result callback
            def on_result(result):
                """Print scan results to stdout."""
                import json
                print(json.dumps(result, indent=2))

            watcher.on_result(on_result)
            asyncio.run(watcher.start())
            return EXIT_SUCCESS
        except ImportError as e:
            LOGGER.error(f"Watcher dependencies not installed: {e}")
            return EXIT_SCANNER_ERROR
        except KeyboardInterrupt:
            LOGGER.info("File watcher stopped")
            return EXIT_SUCCESS
        except Exception as e:
            LOGGER.error(f"File watcher error: {e}")
            return EXIT_SCANNER_ERROR
