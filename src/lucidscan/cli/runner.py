"""CLI runner orchestration.

This module handles command dispatch and execution for the lucidscan CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from importlib.metadata import version, PackageNotFoundError

from lucidscan.cli.arguments import build_parser
from lucidscan.cli.config_bridge import ConfigBridge
from lucidscan.cli.exit_codes import (
    EXIT_INVALID_USAGE,
    EXIT_SCANNER_ERROR,
    EXIT_SUCCESS,
)
from lucidscan.cli.commands.status import StatusCommand
from lucidscan.cli.commands.scan import ScanCommand
from lucidscan.config import load_config
from lucidscan.config.loader import ConfigError
from lucidscan.core.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def get_version() -> str:
    """Get lucidscan version.

    Returns:
        Version string from package metadata or fallback.
    """
    try:
        return version("lucidscan")
    except PackageNotFoundError:
        # Fallback for editable installs that have not yet built metadata.
        from lucidscan import __version__
        return __version__


class CLIRunner:
    """Orchestrates CLI execution with subcommand dispatch."""

    def __init__(self) -> None:
        """Initialize CLIRunner with parser and commands."""
        self.parser = build_parser()
        self._version = get_version()
        self.status_cmd = StatusCommand(version=self._version)
        self.scan_cmd = ScanCommand(version=self._version)
        # InitCommand will be imported lazily when needed to avoid
        # import errors until the module is created
        self._init_cmd = None

    @property
    def init_cmd(self):
        """Lazy-load InitCommand to avoid import errors during development."""
        if self._init_cmd is None:
            try:
                from lucidscan.cli.commands.init import InitCommand
                self._init_cmd = InitCommand()
            except ImportError:
                self._init_cmd = None
        return self._init_cmd

    def run(self, argv: Optional[Iterable[str]] = None) -> int:
        """Run the CLI.

        Args:
            argv: Command-line arguments (defaults to sys.argv).

        Returns:
            Exit code.
        """
        # Handle --help specially to return 0
        if argv is not None:
            argv_list = list(argv)
            if "--help" in argv_list or "-h" in argv_list:
                self.parser.print_help()
                return EXIT_SUCCESS
        else:
            argv_list = None

        args = self.parser.parse_args(argv_list)

        # Configure logging as early as possible
        configure_logging(
            debug=args.debug,
            verbose=args.verbose,
            quiet=args.quiet,
        )

        # Handle --version
        if args.version:
            print(self._version)
            return EXIT_SUCCESS

        # Dispatch to appropriate command handler
        command = getattr(args, "command", None)

        if command == "init":
            return self._handle_init(args)
        elif command == "scan":
            return self._handle_scan(args)
        elif command == "status":
            return self._handle_status(args)
        elif command == "serve":
            return self._handle_serve(args)
        else:
            # No command specified - show help
            self.parser.print_help()
            return EXIT_SUCCESS

    def _handle_init(self, args) -> int:
        """Handle the init command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        if self.init_cmd is None:
            LOGGER.error("Init command not available. This feature is in development.")
            return EXIT_INVALID_USAGE

        return self.init_cmd.execute(args)

    def _handle_scan(self, args) -> int:
        """Handle the scan command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        # Load configuration
        project_root = Path(args.path).resolve()
        cli_overrides = ConfigBridge.args_to_overrides(args)

        try:
            config = load_config(
                project_root=project_root,
                cli_config_path=getattr(args, "config", None),
                cli_overrides=cli_overrides,
            )
        except ConfigError as e:
            LOGGER.error(str(e))
            return EXIT_INVALID_USAGE

        # Check if any domains are enabled
        cli_scan_requested = any([
            getattr(args, "sca", False),
            getattr(args, "container", False),
            getattr(args, "iac", False),
            getattr(args, "sast", False),
            getattr(args, "lint", False),
            getattr(args, "type_check", False),
            getattr(args, "all", False),
        ])

        config_has_enabled_domains = bool(config.get_enabled_domains())

        if cli_scan_requested or config_has_enabled_domains:
            try:
                return self.scan_cmd.execute(args, config)
            except FileNotFoundError:
                return EXIT_INVALID_USAGE
            except Exception as e:
                if args.debug:
                    import traceback
                    traceback.print_exc()
                LOGGER.error(f"Scan failed: {e}")
                return EXIT_SCANNER_ERROR

        # No scanners selected - show scan help
        print("No scan domains selected. Use --sca, --sast, --iac, --lint, --type-check, or --all.")
        print("\nRun 'lucidscan scan --help' for more options.")
        return EXIT_SUCCESS

    def _handle_status(self, args) -> int:
        """Handle the status command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        return self.status_cmd.execute(args)

    def _handle_serve(self, args) -> int:
        """Handle the serve command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        # Load configuration
        project_root = Path(args.path).resolve()
        cli_overrides = ConfigBridge.args_to_overrides(args)

        try:
            config = load_config(
                project_root=project_root,
                cli_config_path=getattr(args, "config", None),
                cli_overrides=cli_overrides,
            )
        except ConfigError as e:
            LOGGER.error(str(e))
            return EXIT_INVALID_USAGE

        try:
            from lucidscan.cli.commands.serve import ServeCommand
            serve_cmd = ServeCommand(version=self._version)
            return serve_cmd.execute(args, config)
        except ImportError as e:
            LOGGER.error(f"Serve command not available: {e}")
            return EXIT_INVALID_USAGE
