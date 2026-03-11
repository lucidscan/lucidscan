"""History management for quality snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from lucidshark.overview.models import Snapshot


@dataclass
class History:
    """Container for quality snapshot history.

    Attributes:
        version: Schema version for the history file.
        snapshots: List of snapshots, newest first.
    """

    version: str = "1"
    snapshots: List[Snapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "snapshots": [s.to_dict() for s in self.snapshots],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "History":
        """Create from dictionary."""
        return cls(
            version=data.get("version", "1"),
            snapshots=[Snapshot.from_dict(s) for s in data.get("snapshots", [])],
        )


class HistoryManager:
    """Manages loading, saving, and pruning of quality history.

    The history is stored as a JSON file containing snapshots of quality
    metrics over time. This enables trend calculation and historical analysis.

    Attributes:
        path: Path to the history JSON file.
        limit: Maximum number of snapshots to retain.
    """

    DEFAULT_PATH = ".lucidshark/quality-history.json"
    DEFAULT_LIMIT = 90

    def __init__(
        self,
        project_root: Path,
        path: Optional[str] = None,
        limit: Optional[int] = None,
    ):
        """Initialize history manager.

        Args:
            project_root: Root directory of the project.
            path: Path to history file relative to project root.
            limit: Maximum number of snapshots to retain.
        """
        self.project_root = project_root
        self.path = project_root / (path or self.DEFAULT_PATH)
        self.limit = limit or self.DEFAULT_LIMIT
        self._history: Optional[History] = None

    def load(self) -> History:
        """Load history from file.

        Creates empty history if file doesn't exist.

        Returns:
            History object with loaded snapshots.
        """
        if self._history is not None:
            return self._history

        if not self.path.exists():
            self._history = History()
            return self._history

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._history = History.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Corrupted file - start fresh but log warning
            from lucidshark.core.logging import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Could not parse history file {self.path}: {e}")
            self._history = History()

        return self._history

    def save(self, history: Optional[History] = None) -> None:
        """Save history to file.

        Args:
            history: History to save. Uses cached history if not provided.
        """
        if history is not None:
            self._history = history

        if self._history is None:
            return

        # Ensure directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._history.to_dict(), f, indent=2)

    def append(self, snapshot: Snapshot) -> History:
        """Append a new snapshot and prune old ones.

        The new snapshot is added to the front of the list (newest first).
        Old snapshots beyond the limit are removed.

        Args:
            snapshot: New snapshot to add.

        Returns:
            Updated history.
        """
        history = self.load()

        # Add new snapshot at the front
        history.snapshots.insert(0, snapshot)

        # Prune old snapshots
        if len(history.snapshots) > self.limit:
            history.snapshots = history.snapshots[: self.limit]

        self._history = history
        return history

    def get_latest(self) -> Optional[Snapshot]:
        """Get the most recent snapshot.

        Returns:
            Most recent snapshot, or None if no history.
        """
        history = self.load()
        if history.snapshots:
            return history.snapshots[0]
        return None

    def get_previous(self) -> Optional[Snapshot]:
        """Get the second most recent snapshot.

        Useful for trend calculation comparing current to previous.

        Returns:
            Second most recent snapshot, or None if fewer than 2 snapshots.
        """
        history = self.load()
        if len(history.snapshots) >= 2:
            return history.snapshots[1]
        return None

    def get_snapshots(self, count: Optional[int] = None) -> List[Snapshot]:
        """Get recent snapshots.

        Args:
            count: Number of snapshots to return. None for all.

        Returns:
            List of snapshots, newest first.
        """
        history = self.load()
        if count is None:
            return history.snapshots
        return history.snapshots[:count]

    def clear(self) -> None:
        """Clear all history."""
        self._history = History()
        if self.path.exists():
            self.path.unlink()
