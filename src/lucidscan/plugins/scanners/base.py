from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from lucidscan.core.models import ScanContext, ScanDomain, UnifiedIssue


class ScannerPlugin(ABC):
    """Base class for all scanner plugins.

    Each scanner plugin wraps an underlying security tool and exposes it
    through a common interface. Plugins are self-contained and manage
    their own binary lifecycle.
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize the scanner plugin.

        Args:
            project_root: Optional project root for tool installation.
            **kwargs: Additional arguments for subclasses.
        """
        self.project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier (e.g., 'trivy', 'opengrep')."""

    @property
    @abstractmethod
    def domains(self) -> List[ScanDomain]:
        """Scan domains this plugin supports (SCA, SAST, IAC, CONTAINER)."""

    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the scanner binary is available, downloading if needed.

        Returns:
            Path to the scanner binary.
        """

    @abstractmethod
    def get_version(self) -> str:
        """Return the version of the underlying scanner."""

    @abstractmethod
    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        """Execute scan and return normalized issues.

        Args:
            context: Scan context containing target paths and configuration.

        Returns:
            List of unified issues found during the scan.
        """


