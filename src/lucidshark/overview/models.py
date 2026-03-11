"""Data models for quality overview snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class DomainStatus:
    """Status of a single domain in a snapshot.

    Attributes:
        domain: Domain name (e.g., "linting", "sast", "coverage").
        status: Pass/warn/fail status.
        issue_count: Number of issues in this domain.
        details: Domain-specific details (e.g., coverage percentage).
    """

    domain: str
    status: str  # "pass" | "warn" | "fail" | "skipped"
    issue_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "domain": self.domain,
            "status": self.status,
            "issue_count": self.issue_count,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainStatus":
        """Create from dictionary."""
        return cls(
            domain=data["domain"],
            status=data["status"],
            issue_count=data.get("issue_count", 0),
            details=data.get("details", {}),
        )


@dataclass
class IssuesBySeverity:
    """Issue counts by severity level.

    Attributes:
        critical: Number of critical severity issues.
        high: Number of high severity issues.
        medium: Number of medium severity issues.
        low: Number of low severity issues.
        info: Number of info severity issues.
    """

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0

    @property
    def total(self) -> int:
        """Total number of issues across all severities."""
        return self.critical + self.high + self.medium + self.low + self.info

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for JSON serialization."""
        return {
            "critical": self.critical,
            "high": self.high,
            "medium": self.medium,
            "low": self.low,
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "IssuesBySeverity":
        """Create from dictionary."""
        return cls(
            critical=data.get("critical", 0),
            high=data.get("high", 0),
            medium=data.get("medium", 0),
            low=data.get("low", 0),
            info=data.get("info", 0),
        )


@dataclass
class Snapshot:
    """A point-in-time snapshot of repository quality.

    Captures the quality state at a specific commit, including issue counts,
    coverage, duplication, and per-domain status.

    Attributes:
        date: ISO 8601 timestamp of when the snapshot was taken.
        commit: Short git commit SHA.
        branch: Branch name (e.g., "main").
        score: Overall quality score (0-10).
        issues: Issue counts by severity.
        coverage: Test coverage percentage (None if not measured).
        duplication: Code duplication percentage (None if not measured).
        domains: Per-domain status information.
    """

    date: str
    commit: str
    branch: str
    score: float
    issues: IssuesBySeverity
    coverage: Optional[float] = None
    duplication: Optional[float] = None
    domains: List[DomainStatus] = field(default_factory=list)

    @classmethod
    def create_now(
        cls,
        commit: str,
        branch: str,
        score: float,
        issues: IssuesBySeverity,
        coverage: Optional[float] = None,
        duplication: Optional[float] = None,
        domains: Optional[List[DomainStatus]] = None,
    ) -> "Snapshot":
        """Create a snapshot with the current timestamp.

        Args:
            commit: Short git commit SHA.
            branch: Branch name.
            score: Overall quality score (0-10).
            issues: Issue counts by severity.
            coverage: Test coverage percentage.
            duplication: Code duplication percentage.
            domains: Per-domain status information.

        Returns:
            New Snapshot instance with current timestamp.
        """
        return cls(
            date=datetime.now(timezone.utc).isoformat(),
            commit=commit,
            branch=branch,
            score=score,
            issues=issues,
            coverage=coverage,
            duplication=duplication,
            domains=domains or [],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date,
            "commit": self.commit,
            "branch": self.branch,
            "score": self.score,
            "issues": self.issues.to_dict(),
            "coverage": self.coverage,
            "duplication": self.duplication,
            "domains": [d.to_dict() for d in self.domains],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Snapshot":
        """Create from dictionary."""
        return cls(
            date=data["date"],
            commit=data["commit"],
            branch=data["branch"],
            score=data["score"],
            issues=IssuesBySeverity.from_dict(data.get("issues", {})),
            coverage=data.get("coverage"),
            duplication=data.get("duplication"),
            domains=[DomainStatus.from_dict(d) for d in data.get("domains", [])],
        )


@dataclass
class TrendIndicator:
    """Trend indicator comparing current to previous value.

    Attributes:
        current: Current value.
        previous: Previous value (None if no history).
        direction: Trend direction ("up", "down", "stable").
        delta: Absolute change from previous.
    """

    current: float
    previous: Optional[float]
    direction: str  # "up" | "down" | "stable"
    delta: float

    @classmethod
    def calculate(
        cls,
        current: float,
        previous: Optional[float],
        higher_is_better: bool = True,
        threshold: float = 0.01,
    ) -> "TrendIndicator":
        """Calculate trend indicator from current and previous values.

        Args:
            current: Current value.
            previous: Previous value (None if no history).
            higher_is_better: If True, increases are good (↑). If False, decreases are good.
            threshold: Minimum change to be considered non-stable.

        Returns:
            TrendIndicator with calculated direction and delta.
        """
        if previous is None:
            return cls(current=current, previous=None, direction="stable", delta=0.0)

        delta = current - previous
        abs_delta = abs(delta)

        if abs_delta < threshold:
            direction = "stable"
        elif delta > 0:
            direction = "up" if higher_is_better else "down"
        else:
            direction = "down" if higher_is_better else "up"

        return cls(current=current, previous=previous, direction=direction, delta=delta)

    @property
    def arrow(self) -> str:
        """Get arrow character for trend direction."""
        arrows = {"up": "↑", "down": "↓", "stable": "→"}
        return arrows.get(self.direction, "→")

    @property
    def delta_str(self) -> str:
        """Get formatted delta string (e.g., '+0.3', '-1.2')."""
        if self.previous is None or abs(self.delta) < 0.01:
            return ""
        sign = "+" if self.delta > 0 else ""
        return f"{sign}{self.delta:.1f}"
