"""CLI commands package.

This module provides the base Command class and exports all command implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from argparse import Namespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lucidscan.config.models import LucidScanConfig


class Command(ABC):
    """Base class for CLI commands.

    All CLI commands should inherit from this class and implement
    the execute method.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Command identifier.

        Returns:
            String name of the command.
        """

    @abstractmethod
    def execute(self, args: Namespace, config: "LucidScanConfig | None" = None) -> int:
        """Execute the command.

        Args:
            args: Parsed command-line arguments.
            config: Optional LucidScan configuration.

        Returns:
            Exit code (0 for success, non-zero for error).
        """


# Import command implementations for convenience
# ruff: noqa: E402
from lucidscan.cli.commands.status import StatusCommand
from lucidscan.cli.commands.list_scanners import ListScannersCommand
from lucidscan.cli.commands.scan import ScanCommand
from lucidscan.cli.commands.init import InitCommand
from lucidscan.cli.commands.serve import ServeCommand
from lucidscan.cli.commands.setup import SetupCommand

__all__ = [
    "Command",
    "StatusCommand",
    "ListScannersCommand",
    "ScanCommand",
    "InitCommand",
    "ServeCommand",
    "SetupCommand",
]
