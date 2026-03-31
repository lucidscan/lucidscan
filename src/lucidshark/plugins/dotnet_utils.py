"""Shared utilities for .NET / C# plugins.

Common functionality used across dotnet-based plugins (dotnet format,
dotnet build, dotnet test, dotnet coverage) to avoid code duplication.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)


def find_dotnet() -> Path:
    """Find the dotnet CLI binary.

    Returns:
        Path to dotnet binary.

    Raises:
        FileNotFoundError: If dotnet is not installed.
    """
    dotnet = shutil.which("dotnet")
    if dotnet:
        return Path(dotnet)

    raise FileNotFoundError(
        "dotnet is not installed. Install the .NET SDK from:\n"
        "  https://dotnet.microsoft.com/download"
    )


def find_project_file(project_root: Path) -> Optional[Path]:
    """Find a .sln or .csproj file in the project root.

    Prefers .sln files over .csproj. For nested projects, returns
    the .csproj file itself (not its parent directory).

    Args:
        project_root: Project root directory.

    Returns:
        Path to the project/solution file, or None.
    """
    # Prefer .sln files
    sln_files = list(project_root.glob("*.sln"))
    if sln_files:
        return sln_files[0]

    # Fall back to .csproj
    csproj_files = list(project_root.glob("*.csproj"))
    if csproj_files:
        return csproj_files[0]

    # Check one level deep for .csproj
    csproj_files = list(project_root.glob("*/*.csproj"))
    if csproj_files:
        return csproj_files[0]

    return None
