"""Quality overview generation for LucidShark.

This module provides functionality to generate and maintain a QUALITY.md
file that summarizes the quality state of a repository, including trends
over time.
"""

from lucidshark.overview.models import DomainStatus, Snapshot
from lucidshark.overview.history import HistoryManager
from lucidshark.overview.generator import OverviewGenerator

__all__ = [
    "DomainStatus",
    "Snapshot",
    "HistoryManager",
    "OverviewGenerator",
]
