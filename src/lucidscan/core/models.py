from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from lucidscan.config.ignore import IgnorePatterns
    from lucidscan.config.models import LucidScanConfig


class ScanDomain(str, Enum):
    """Scanning domains supported by lucidscan."""

    SCA = "sca"
    CONTAINER = "container"
    IAC = "iac"
    SAST = "sast"


class Severity(str, Enum):
    """Unified severity levels used across all scanners."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class UnifiedIssue:
    """Normalized issue representation shared by all scanners.

    This is a preliminary skeleton aligned with the main specification's
    unified issue schema. Additional fields may be added in later phases.
    """

    id: str
    scanner: ScanDomain
    source_tool: str
    severity: Severity
    title: str
    description: str

    file_path: Optional[Path] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None

    dependency: Optional[str] = None
    iac_resource: Optional[str] = None
    code_snippet: Optional[str] = None
    recommendation: Optional[str] = None

    scanner_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanContext:
    """Context provided to scanner plugins during scan execution.

    Contains target paths, configuration, and scan settings needed
    by plugins to execute their scans.
    """

    project_root: Path
    paths: List[Path]
    enabled_domains: List[ScanDomain]
    config: "LucidScanConfig" = None  # type: ignore[assignment]
    ignore_patterns: Optional["IgnorePatterns"] = None

    def get_scanner_options(self, domain: str) -> Dict[str, Any]:
        """Get plugin-specific options for a domain.

        Args:
            domain: Domain name (sca, sast, iac, container).

        Returns:
            Dictionary of plugin-specific options.
        """
        if self.config is None:
            return {}
        # Handle legacy dict-based config for backwards compatibility
        if isinstance(self.config, dict):
            return self.config
        return self.config.get_scanner_options(domain)

    def get_exclude_patterns(self) -> List[str]:
        """Get ignore patterns for scanner exclude flags.

        Returns:
            List of patterns suitable for --exclude flags.
        """
        if self.ignore_patterns is None:
            return []
        return self.ignore_patterns.get_exclude_patterns()


@dataclass
class ScanMetadata:
    """Metadata about the scan execution."""

    lucidscan_version: str
    scan_started_at: str
    scan_finished_at: str
    duration_ms: int
    project_root: str
    scanners_used: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ScanSummary:
    """Summary statistics for scan results."""

    total: int = 0
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_scanner: Dict[str, int] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Aggregated result for a scan over one project or path set."""

    issues: List[UnifiedIssue] = field(default_factory=list)
    schema_version: str = "1.0"
    metadata: Optional[ScanMetadata] = None
    summary: Optional[ScanSummary] = None

    def compute_summary(self) -> ScanSummary:
        """Compute summary statistics from issues."""
        by_severity: Dict[str, int] = {}
        by_scanner: Dict[str, int] = {}

        for issue in self.issues:
            sev = issue.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            scanner = issue.scanner.value
            by_scanner[scanner] = by_scanner.get(scanner, 0) + 1

        return ScanSummary(
            total=len(self.issues),
            by_severity=by_severity,
            by_scanner=by_scanner,
        )


