"""CLI runner orchestration.

This module handles command dispatch and execution for the lucidshark CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple

from importlib.metadata import version, PackageNotFoundError

from lucidshark.cli.arguments import build_parser
from lucidshark.cli.config_bridge import ConfigBridge
from lucidshark.cli.exit_codes import (
    EXIT_INVALID_USAGE,
    EXIT_SCANNER_ERROR,
    EXIT_SUCCESS,
)
from lucidshark.cli.commands.status import StatusCommand
from lucidshark.cli.commands.scan import ScanCommand
from lucidshark.cli.commands.help import HelpCommand
from lucidshark.cli.commands.doctor import DoctorCommand
from lucidshark.cli.commands.overview import OverviewCommand
from lucidshark.config import load_config
from lucidshark.config.loader import ConfigError, find_project_config
from lucidshark.config.models import LucidSharkConfig
from lucidshark.core.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def get_version() -> str:
    """Get lucidshark version.

    Returns:
        Version string from module __version__ (source of truth for binary distribution).
    """
    # Always use __version__ from module as source of truth
    # pyproject.toml version is 0.0.0-dev for development only
    from lucidshark import __version__

    return __version__


class CLIRunner:
    """Orchestrates CLI execution with subcommand dispatch."""

    def __init__(self) -> None:
        """Initialize CLIRunner with parser and commands."""
        self.parser = build_parser()
        self._version = get_version()
        self.status_cmd = StatusCommand(version=self._version)
        self.scan_cmd = ScanCommand(version=self._version)
        self.help_cmd = HelpCommand(version=self._version)
        self.doctor_cmd = DoctorCommand(version=self._version)
        self.overview_cmd = OverviewCommand(version=self._version)
        # InitCommand will be imported lazily when needed
        self._init_cmd = None

    @property
    def init_cmd(self):
        """Lazy-load InitCommand to avoid import errors during development."""
        if self._init_cmd is None:
            try:
                from lucidshark.cli.commands.init import InitCommand

                self._init_cmd = InitCommand(version=self._version)
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
        elif command == "help":
            return self._handle_help(args)
        elif command == "validate":
            return self._handle_validate(args)
        elif command == "doctor":
            return self._handle_doctor(args)
        elif command == "overview":
            return self._handle_overview(args)
        else:
            # No command specified - show help
            self.parser.print_help()
            return EXIT_SUCCESS

    def _handle_init(self, args) -> int:
        """Handle the init command (configure AI tools).

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        if self.init_cmd is None:
            LOGGER.error("Init command not available. This feature is in development.")
            return EXIT_INVALID_USAGE

        return self.init_cmd.execute(args)

    def _load_config(self, args) -> Tuple[Optional[LucidSharkConfig], int]:
        """Load configuration from args, returning (config, exit_code).

        On success ``exit_code`` is ``EXIT_SUCCESS`` and ``config`` is the
        loaded :class:`LucidSharkConfig`.  On failure ``config`` is ``None``
        and ``exit_code`` should be returned to the caller immediately.
        """
        project_root = Path(args.path).resolve()
        cli_overrides = ConfigBridge.args_to_overrides(args)
        try:
            config = load_config(
                project_root=project_root,
                cli_config_path=getattr(args, "config", None),
                cli_overrides=cli_overrides,
            )
            return config, EXIT_SUCCESS
        except ConfigError as e:
            LOGGER.error(str(e))
            return None, EXIT_INVALID_USAGE

    def _handle_scan(self, args) -> int:
        """Handle the scan command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        config, err = self._load_config(args)
        if config is None:
            return err

        # Check if any domains are enabled
        cli_scan_requested = any(
            [
                getattr(args, "sca", False),
                getattr(args, "container", False),
                getattr(args, "iac", False),
                getattr(args, "sast", False),
                getattr(args, "linting", False),
                getattr(args, "type_checking", False),
                getattr(args, "testing", False),
                getattr(args, "coverage", False),
                getattr(args, "duplication", False),
                getattr(args, "formatting", False),
                getattr(args, "all", False),
            ]
        )

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

        # No scanners selected - provide context-specific guidance
        project_root = Path(args.path).resolve()
        has_config = find_project_config(project_root) is not None
        if has_config:
            print(
                "All domains in config are disabled. Enable domains in lucidshark.yml or use CLI flags:"
            )
            print(
                "  lucidshark scan --sca, --sast, --iac, --linting, --type-checking, --formatting, --testing, --coverage, --duplication, or --all"
            )
        else:
            print("No lucidshark.yml found and no scan domains specified.")
            print("\nQuick start:")
            print('  Ask Claude Code: "Autoconfigure LucidShark for this project"')
            print("  lucidshark scan --all   Run all available checks without a config")
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
        config, err = self._load_config(args)
        if config is None:
            return err

        try:
            from lucidshark.cli.commands.serve import ServeCommand

            serve_cmd = ServeCommand(version=self._version)
            return serve_cmd.execute(args, config)
        except ImportError as e:
            LOGGER.error(f"Serve command not available: {e}")
            return EXIT_INVALID_USAGE

    def _handle_help(self, args) -> int:
        """Handle the help command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        return self.help_cmd.execute(args)

    def _handle_validate(self, args) -> int:
        """Handle the validate command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        from lucidshark.cli.commands.validate import ValidateCommand

        validate_cmd = ValidateCommand()
        return validate_cmd.execute(args)

    def _handle_doctor(self, args) -> int:
        """Handle the doctor command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        return self.doctor_cmd.execute(args)

    def _handle_overview(self, args) -> int:
        """Handle the overview command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        config, err = self._load_config(args)
        if config is None:
            # Overview can work without config
            config = None

        try:
            return self.overview_cmd.execute(args, config)
        except Exception as e:
            if args.debug:
                import traceback

                traceback.print_exc()
            LOGGER.error(f"Overview generation failed: {e}")
            return EXIT_SCANNER_ERROR
