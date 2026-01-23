from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

if TYPE_CHECKING:
    from lucidshark.config.ignore import IgnorePatterns
    from lucidshark.config.models import LucidSharkConfig
    from lucidshark.core.streaming import StreamHandler


class ScanDomain(str, Enum):
    """Scanning domains supported by lucidshark (security-focused)."""

    SCA = "sca"
    CONTAINER = "container"
    IAC = "iac"
    SAST = "sast"


class ToolDomain(str, Enum):
    """All tool domains supported by lucidshark pipeline.

    This enum covers all types of tools in the quality pipeline:
    linting, type checking, security scanning, testing, coverage, and duplication.
    """

    LINTING = "linting"
    TYPE_CHECKING = "type_checking"
    SECURITY = "security"
    TESTING = "testing"
    COVERAGE = "coverage"
    DUPLICATION = "duplication"


# Type alias for any domain type (ScanDomain or ToolDomain)
DomainType = Union[ScanDomain, ToolDomain]

# Mapping from domain string names to enum values
_DOMAIN_MAP: Dict[str, DomainType] = {
    # Tool domains
    "linting": ToolDomain.LINTING,
    "type_checking": ToolDomain.TYPE_CHECKING,
    "testing": ToolDomain.TESTING,
    "coverage": ToolDomain.COVERAGE,
    "duplication": ToolDomain.DUPLICATION,
    # Security/scan domains
    "sast": ScanDomain.SAST,
    "sca": ScanDomain.SCA,
    "iac": ScanDomain.IAC,
    "container": ScanDomain.CONTAINER,
}


def parse_domain(name: str) -> Optional[DomainType]:
    """Parse a domain name string to a DomainType enum.

    Args:
        name: Domain name (e.g., "linting", "sast", "sca").

    Returns:
        DomainType enum value, or None if not found.
    """
    return _DOMAIN_MAP.get(name.lower())


def parse_domains(names: List[str]) -> List[DomainType]:
    """Parse multiple domain name strings to DomainType enums.

    Unknown domain names are skipped with a warning.

    Args:
        names: List of domain names.

    Returns:
        List of DomainType enum values.
    """
    from lucidshark.core.logging import get_logger

    logger = get_logger(__name__)
    result: List[DomainType] = []

    for name in names:
        domain = parse_domain(name)
        if domain is not None:
            result.append(domain)
        else:
            logger.warning(f"Unknown domain: {name}")

    return result


class Severity(str, Enum):
    """Unified severity levels used across all scanners."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class UnifiedIssue:
    """Normalized issue representation shared by all tools.

    This unified schema handles issues from all domains:
    - Linting: code style and quality issues
    - Type checking: type errors and warnings
    - Security (SAST/SCA/IaC/Container): vulnerabilities and misconfigurations
    - Testing: test failures
    - Coverage: coverage gaps
    """

    # Core identification
    id: str
    domain: DomainType  # The domain category (linting, sast, sca, etc.)
    source_tool: str  # The actual tool (ruff, trivy, mypy, etc.)
    severity: Severity

    # Content
    rule_id: str  # Rule identifier (E501, CVE-2024-1234, CKV_AWS_1)
    title: str
    description: str
    recommendation: Optional[str] = None
    documentation_url: Optional[str] = None

    # Location
    file_path: Optional[Path] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    column_start: Optional[int] = None
    column_end: Optional[int] = None
    code_snippet: Optional[str] = None

    # Fix information
    fixable: bool = False
    suggested_fix: Optional[str] = None

    # Domain-specific fields
    dependency: Optional[str] = None  # For SCA (e.g., "lodash@4.17.20")
    iac_resource: Optional[str] = None  # For IaC (e.g., "aws_s3_bucket.public")

    # Extensibility
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanContext:
    """Context provided to scanner plugins during scan execution.

    Contains target paths, configuration, and scan settings needed
    by plugins to execute their scans.
    """

    project_root: Path
    paths: List[Path]
    enabled_domains: Sequence[DomainType]
    config: "LucidSharkConfig" = None  # type: ignore[assignment]
    ignore_patterns: Optional["IgnorePatterns"] = None
    stream_handler: Optional["StreamHandler"] = None
    # Coverage result populated after coverage analysis (for MCP/CLI access)
    coverage_result: Any = None
    # Duplication result populated after duplication analysis (for MCP/CLI access)
    duplication_result: Any = None

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

    @classmethod
    def create(
        cls,
        project_root: Path,
        config: "LucidSharkConfig",
        enabled_domains: Sequence[DomainType],
        files: Optional[List[str]] = None,
        all_files: bool = False,
        stream_handler: Optional["StreamHandler"] = None,
    ) -> "ScanContext":
        """Create a ScanContext with path determination and ignore filtering.

        This factory method handles the common pattern of:
        1. Determining which paths to scan (specific files, all files, or changed files)
        2. Loading and applying ignore patterns
        3. Building the context

        Args:
            project_root: Project root directory.
            config: LucidShark configuration.
            enabled_domains: List of domains to scan.
            files: Optional list of specific files to scan (relative or absolute).
            all_files: If True, scan entire project.
            stream_handler: Optional handler for streaming output.

        Returns:
            Configured ScanContext instance.
        """
        from lucidshark.config.ignore import filter_paths_with_ignore
        from lucidshark.core.paths import determine_scan_paths

        paths = determine_scan_paths(project_root, files, all_files)
        paths, ignore_patterns = filter_paths_with_ignore(
            paths, project_root, config.ignore
        )

        return cls(
            project_root=project_root,
            paths=paths,
            enabled_domains=enabled_domains,
            config=config,
            ignore_patterns=ignore_patterns,
            stream_handler=stream_handler,
        )


@dataclass
class ScanMetadata:
    """Metadata about the scan execution."""

    lucidshark_version: str
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
class CoverageSummary:
    """Summary of coverage analysis results."""

    coverage_percentage: float = 0.0
    threshold: float = 80.0
    total_lines: int = 0
    covered_lines: int = 0
    missing_lines: int = 0
    passed: bool = True
    # Test statistics
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0


@dataclass
class DuplicationSummary:
    """Summary of code duplication analysis results."""

    files_analyzed: int = 0
    total_lines: int = 0
    duplicate_blocks: int = 0
    duplicate_lines: int = 0
    duplication_percent: float = 0.0
    threshold: float = 10.0  # Default max allowed duplication %
    passed: bool = True


@dataclass
class ScanResult:
    """Aggregated result for a scan over one project or path set."""

    issues: List[UnifiedIssue] = field(default_factory=list)
    schema_version: str = "1.0"
    metadata: Optional[ScanMetadata] = None
    summary: Optional[ScanSummary] = None
    coverage_summary: Optional[CoverageSummary] = None
    duplication_summary: Optional[DuplicationSummary] = None

    def compute_summary(self) -> ScanSummary:
        """Compute summary statistics from issues."""
        by_severity: Dict[str, int] = {}
        by_domain: Dict[str, int] = {}

        for issue in self.issues:
            sev = issue.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            domain = issue.domain.value
            by_domain[domain] = by_domain.get(domain, 0) + 1

        return ScanSummary(
            total=len(self.issues),
            by_severity=by_severity,
            by_scanner=by_domain,  # Keep field name for backwards compatibility
        )


