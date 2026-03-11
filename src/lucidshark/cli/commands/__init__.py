"""CLI commands package.

This module provides the base Command class and exports all command implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from argparse import Namespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lucidshark.config.models import LucidSharkConfig


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
    def execute(self, args: Namespace, config: "LucidSharkConfig | None" = None) -> int:
        """Execute the command.

        Args:
            args: Parsed command-line arguments.
            config: Optional LucidShark configuration.

        Returns:
            Exit code (0 for success, non-zero for error).
        """


# Import command implementations for convenience
# ruff: noqa: E402
from lucidshark.cli.commands.status import StatusCommand
from lucidshark.cli.commands.list_scanners import ListScannersCommand
from lucidshark.cli.commands.scan import ScanCommand
from lucidshark.cli.commands.init import InitCommand
from lucidshark.cli.commands.serve import ServeCommand
from lucidshark.cli.commands.validate import ValidateCommand
from lucidshark.cli.commands.overview import OverviewCommand

__all__ = [
    "Command",
    "StatusCommand",
    "ListScannersCommand",
    "ScanCommand",
    "InitCommand",
    "ServeCommand",
    "ValidateCommand",
    "OverviewCommand",
]
