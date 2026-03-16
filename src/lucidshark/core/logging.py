from __future__ import annotations

import logging
import sys
from typing import Optional


def configure_logging(
    *, debug: bool = False, verbose: bool = False, quiet: bool = False
) -> None:
    """Configure root logging level based on CLI flags.

    Precedence:
    - quiet → ERROR
    - debug → DEBUG
    - verbose → INFO
    - default → WARNING

    Logs are always written to stderr to avoid polluting structured output
    (JSON, SARIF, etc.) on stdout.
    """

    if quiet:
        level = logging.ERROR
    elif debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    # Configure logging to write to stderr instead of stdout
    # This prevents logs from polluting structured output (JSON, SARIF)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    # Clear any existing handlers and add our stderr handler
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a module-level logger."""

    return logging.getLogger(name if name is not None else __name__)
