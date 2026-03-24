"""LucidShark CLI package.

This package provides the command-line interface for lucidshark.
"""

from __future__ import annotations

import signal
from typing import Iterable, Optional

# Ignore SIGPIPE to prevent BrokenPipeError when piping to head/less/etc
# Only available on Unix-like systems (not Windows)
if hasattr(signal, 'SIGPIPE'):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

from lucidshark.cli.runner import CLIRunner, get_version
from lucidshark.cli.arguments import build_parser
from lucidshark.cli.exit_codes import (
    EXIT_SUCCESS,
    EXIT_ISSUES_FOUND,
    EXIT_SCANNER_ERROR,
    EXIT_INVALID_USAGE,
    EXIT_BOOTSTRAP_FAILURE,
)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI entrypoint.

    Returns an exit code suitable for use as a console script.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        Exit code.
    """
    runner = CLIRunner()
    return runner.run(argv)


__all__ = [
    "main",
    "build_parser",
    "get_version",
    "CLIRunner",
    "EXIT_SUCCESS",
    "EXIT_ISSUES_FOUND",
    "EXIT_SCANNER_ERROR",
    "EXIT_INVALID_USAGE",
    "EXIT_BOOTSTRAP_FAILURE",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
