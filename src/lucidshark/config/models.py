"""Configuration data models for lucidshark.

Defines typed configuration classes that represent .lucidshark.yml structure.
Core fields are validated, while plugin-specific options are passed through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


# Default plugins per domain (used when not specified in config)
DEFAULT_PLUGINS: Dict[str, str] = {
    "sca": "trivy",
    "container": "trivy",
    "sast": "opengrep",
    "iac": "checkov",
}

# Valid severity values for fail_on
VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}

# Valid domain keys for fail_on dict format
VALID_FAIL_ON_DOMAINS = {
    "linting",
    "type_checking",
    "security",
    "testing",
    "coverage",
    "duplication",
    "formatting",
}

# Special fail_on values (not severities)
SPECIAL_FAIL_ON_VALUES = {"error", "any", "none", "below_threshold", "above_threshold"}


@dataclass
class IgnoreIssueEntry:
    """A single ignore_issues entry.

    Allows users to acknowledge specific rule IDs so they still appear
    in output but don't affect exit codes.

    The optional `paths` field limits the ignore to specific files matching
    gitignore-style patterns. If not specified or empty, the ignore applies
    globally.
    """

    rule_id: str
    reason: Optional[str] = None
    expires: Optional[str] = None  # ISO date string YYYY-MM-DD
    paths: Optional[List[str]] = None  # Gitignore-style patterns to limit scope


@dataclass
class FailOnConfig:
    """Failure threshold configuration.

    Supports per-domain thresholds for different scan types.
    Values can be severity levels (critical, high, medium, low, info)
    or special values (error, any, none).
    """

    linting: Optional[str] = None  # error, none
    type_checking: Optional[str] = None  # error, none
    security: Optional[str] = None  # critical, high, medium, low, info, none
    testing: Optional[str] = None  # any, none
    coverage: Optional[str] = None  # any, none
    duplication: Optional[str] = None  # percentage threshold (e.g., "5%"), any, none
    formatting: Optional[str] = None  # error, none

    def get_threshold(self, domain: str) -> Optional[str]:
        """Get threshold for a specific domain.

        Args:
            domain: Domain name (linting, type_checking, security, testing, coverage).

        Returns:
            Threshold value or None if not set.
        """
        return getattr(self, domain, None)


@dataclass
class OutputConfig:
    """Output formatting configuration."""

    format: str = "json"


@dataclass
class ToolConfig:
    """Configuration for a single tool."""

    name: str
    config: Optional[str] = None  # Path to tool-specific config
    strict: bool = False  # For type checkers
    domains: List[str] = field(default_factory=list)  # For security scanners
    options: Dict[str, Any] = field(default_factory=dict)  # Tool-specific options
    mandatory: bool = False  # If True, tool must run or scan fails


@dataclass
class DomainPipelineConfig:
    """Configuration for a pipeline domain (linting, type_checking, testing, etc.)."""

    enabled: bool = True
    tools: List[ToolConfig] = field(default_factory=list)
    exclude: List[str] = field(
        default_factory=list
    )  # Patterns to exclude from this domain
    # Scope for threshold check when using --base-branch:
    # "changed" - apply to changed files only (default)
    # "project" - apply to full project
    # "both" - fail if either changed files or full project exceeds threshold
    threshold_scope: str = "changed"
    command: Optional[str] = None  # Custom shell command to run instead of plugins
    pre_command: Optional[str] = (
        None  # Shell command to run before main command (e.g., cleanup)
    )
    post_command: Optional[str] = None  # Shell command to run after main command


@dataclass
class CoveragePipelineConfig:
    """Coverage-specific pipeline configuration."""

    enabled: bool = False
    threshold: int = 80
    # Scope for threshold check when using --base-branch:
    # "changed" - apply to changed files only (default)
    # "project" - apply to full project coverage
    # "both" - fail if either changed files or full project is below threshold
    threshold_scope: str = "changed"
    tools: List[ToolConfig] = field(default_factory=list)
    # Extra arguments to pass to Maven/Gradle when running coverage tests
    # e.g., ["-DskipITs", "-Ddocker.skip=true"]
    extra_args: List[str] = field(default_factory=list)
    exclude: List[str] = field(
        default_factory=list
    )  # Patterns to exclude from coverage
    command: Optional[str] = None  # Custom shell command to run coverage
    pre_command: Optional[str] = (
        None  # Shell command to run before coverage (e.g., cleanup)
    )
    post_command: Optional[str] = None  # Shell command to run after coverage


@dataclass
class DuplicationPipelineConfig:
    """Duplication detection pipeline configuration."""

    enabled: bool = False
    threshold: float = 10.0  # Max allowed duplication percentage
    # Scope for threshold check when using --base-branch:
    # "changed" - apply to changed files only (default)
    # "project" - apply to full project
    # "both" - fail if either changed files or full project exceeds threshold
    threshold_scope: str = "changed"
    min_lines: int = 4  # Minimum lines for a duplicate block
    min_chars: int = 3  # Minimum characters per line
    exclude: List[str] = field(
        default_factory=list
    )  # Patterns to exclude from duplication scan
    tools: List[ToolConfig] = field(default_factory=list)
    baseline: bool = False  # Only report NEW duplicates after first run
    cache: bool = True  # Cache processed files for faster re-runs
    use_git: bool = True  # Use git ls-files for file discovery when available


@dataclass
class PipelineConfig:
    """Pipeline execution configuration.

    Controls how the scan pipeline executes, including enricher
    ordering and parallelism settings.
    """

    # List of enricher names in execution order
    enrichers: List[str] = field(default_factory=list)

    # Maximum parallel scanner workers (used when not in sequential mode)
    max_workers: int = 4

    # Domain-specific configurations
    linting: Optional[DomainPipelineConfig] = None
    type_checking: Optional[DomainPipelineConfig] = None
    testing: Optional[DomainPipelineConfig] = None
    coverage: Optional[CoveragePipelineConfig] = None
    security: Optional[DomainPipelineConfig] = None
    duplication: Optional[DuplicationPipelineConfig] = None
    formatting: Optional[DomainPipelineConfig] = None

    def get_enabled_tool_names(self, domain: str) -> List[str]:
        """Get list of enabled tool names for a domain.

        Args:
            domain: Domain name (linting, type_checking, testing, security).

        Returns:
            List of tool names, or empty list if domain not configured.
        """
        domain_config = getattr(self, domain, None)
        if domain_config is None or not domain_config.enabled:
            return []
        return [tool.name for tool in domain_config.tools]

    def get_enabled_security_domains(self) -> List[str]:
        """Get list of security domains enabled via pipeline.security.tools.

        Extracts domains from each tool's domains list in pipeline.security.tools.

        Returns:
            List of unique domain names (sca, sast, iac, container).
        """
        if self.security is None or not self.security.enabled:
            return []
        domains: List[str] = []
        for tool in self.security.tools:
            for domain in tool.domains:
                if domain not in domains:
                    domains.append(domain)
        return domains

    def get_security_plugin_for_domain(self, domain: str) -> Optional[str]:
        """Get the plugin name configured for a security domain.

        Looks up which tool in pipeline.security.tools handles the given domain.

        Args:
            domain: Security domain name (sca, sast, iac, container).

        Returns:
            Plugin name if configured, None otherwise.
        """
        if self.security is None or not self.security.enabled:
            return None
        for tool in self.security.tools:
            if domain in tool.domains:
                return tool.name
        return None


@dataclass
class ScannerDomainConfig:
    """Configuration for a scanner domain (sca, sast, iac, container).

    The `enabled` and `plugin` fields are handled by the framework.
    All other fields in `options` are passed through to the plugin.
    """

    enabled: bool = True
    plugin: str = ""  # Plugin name, e.g., "trivy", "snyk". Empty = use default.
    options: Dict[str, Any] = field(default_factory=dict)  # Plugin-specific options


@dataclass
class ProjectConfig:
    """Project metadata configuration."""

    name: str = ""
    languages: List[str] = field(default_factory=list)


@dataclass
class SettingsConfig:
    """Global LucidShark settings."""

    strict_mode: bool = True  # All configured tools must run successfully


@dataclass
class OverviewConfig:
    """Configuration for quality overview generation.

    Controls QUALITY.md generation including which sections to include,
    history retention, and output paths.
    """

    enabled: bool = True
    file: str = "QUALITY.md"  # Output file path relative to project root
    history_file: str = ".lucidshark/quality-history.json"
    history_limit: int = 90  # Number of snapshots to retain

    # Domains to include in overview
    domains: List[str] = field(
        default_factory=lambda: [
            "linting",
            "type_checking",
            "formatting",
            "testing",
            "sast",
            "sca",
            "iac",
            "container",
            "coverage",
            "duplication",
        ]
    )

    # Section toggles
    health_score: bool = True
    domain_table: bool = True
    issue_breakdown: bool = True
    top_files: int = 5  # Number of top files to show (0 to disable)
    security_summary: bool = True
    coverage_breakdown: bool = True
    trend_chart: bool = True


@dataclass
class LucidSharkConfig:
    """Complete lucidshark configuration.

    Core fields are validated by the framework. Plugin-specific options
    under `scanners.*` are passed through without validation.

    Example .lucidshark.yml:
        fail_on: high
        ignore:
          - "tests/**"
        scanners:
          sca:
            enabled: true
            plugin: trivy
            ignore_unfixed: true  # Plugin-specific, passed through
    """

    # Project metadata
    project: ProjectConfig = field(default_factory=ProjectConfig)

    # Core config (validated)
    # fail_on can be a string (legacy) or FailOnConfig (per-domain thresholds)
    fail_on: Optional[Union[str, FailOnConfig]] = None
    ignore: List[str] = field(default_factory=list)
    ignore_issues: List[IgnoreIssueEntry] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)

    # Scanner configs per domain (plugin-specific options passed through)
    scanners: Dict[str, ScannerDomainConfig] = field(default_factory=dict)

    # Enricher configs (plugin-specific options passed through)
    enrichers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Pipeline configuration (enricher ordering, parallelism)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

    # Global settings
    settings: SettingsConfig = field(default_factory=SettingsConfig)

    # Overview configuration
    overview: OverviewConfig = field(default_factory=OverviewConfig)

    # Metadata (not from YAML, set by loader)
    _config_sources: List[str] = field(default_factory=list, repr=False)

    def get_scanner_config(self, domain: str) -> ScannerDomainConfig:
        """Get configuration for a domain, with defaults.

        Args:
            domain: Domain name (sca, sast, iac, container).

        Returns:
            ScannerDomainConfig for the domain, or a default if not configured.
        """
        return self.scanners.get(domain, ScannerDomainConfig())

    def get_enabled_domains(self) -> List[str]:
        """Get list of enabled security domain names.

        Checks both:
        1. Legacy scanners.{domain} config
        2. New pipeline.security.tools[*].domains config

        Returns:
            List of domain names that are enabled in config.
        """
        # Check legacy scanners config
        domains = [domain for domain, cfg in self.scanners.items() if cfg.enabled]

        # Also check pipeline.security.tools for domains
        pipeline_domains = self.pipeline.get_enabled_security_domains()
        for domain in pipeline_domains:
            if domain not in domains:
                domains.append(domain)

        return domains

    def get_all_configured_domains(self) -> List[str]:
        """Get list of all configured domain names (both tool and security).

        Returns domains that are explicitly enabled in the pipeline config.
        Tool domains: linting, type_checking, testing, coverage, duplication, formatting
        Security domains: sca, sast, iac, container

        Returns:
            List of domain names that are configured and enabled.
        """
        domains: List[str] = []

        # Check tool domains in pipeline config
        if self.pipeline.linting is not None and self.pipeline.linting.enabled:
            domains.append("linting")
        if (
            self.pipeline.type_checking is not None
            and self.pipeline.type_checking.enabled
        ):
            domains.append("type_checking")
        if self.pipeline.testing is not None and self.pipeline.testing.enabled:
            domains.append("testing")
        if self.pipeline.coverage is not None and self.pipeline.coverage.enabled:
            domains.append("coverage")
        if self.pipeline.duplication is not None and self.pipeline.duplication.enabled:
            domains.append("duplication")
        if self.pipeline.formatting is not None and self.pipeline.formatting.enabled:
            domains.append("formatting")

        # Add security domains
        domains.extend(self.get_enabled_domains())

        return domains

    def get_plugin_for_domain(self, domain: str) -> str:
        """Get which plugin serves a domain.

        Checks both:
        1. Legacy scanners.{domain}.plugin config
        2. New pipeline.security.tools[*].domains config

        Args:
            domain: Domain name (sca, sast, iac, container).

        Returns:
            Plugin name, falling back to default if not specified.
        """
        # Check legacy scanners config first
        domain_config = self.get_scanner_config(domain)
        if domain_config.plugin:
            return domain_config.plugin

        # Check pipeline.security.tools
        pipeline_plugin = self.pipeline.get_security_plugin_for_domain(domain)
        if pipeline_plugin:
            return pipeline_plugin

        # Fall back to defaults only if no config exists
        return DEFAULT_PLUGINS.get(domain, "")

    def get_plugins_for_domain(self, domain: str) -> List[str]:
        """Get ALL plugins that serve a domain (for defense-in-depth).

        Checks both:
        1. Legacy scanners.{domain}.plugin config
        2. New pipeline.security.tools[*] where domain is in tool.domains

        Args:
            domain: Domain name (sca, sast, iac, container).

        Returns:
            List of plugin names that handle this domain.
        """
        plugins: List[str] = []

        # Check legacy scanners config
        domain_config = self.get_scanner_config(domain)
        if domain_config.plugin and domain_config.plugin not in plugins:
            plugins.append(domain_config.plugin)

        # Check ALL tools in pipeline.security.tools for this domain
        if self.pipeline.security is not None and self.pipeline.security.enabled:
            for tool in self.pipeline.security.tools:
                if domain in tool.domains and tool.name not in plugins:
                    plugins.append(tool.name)

        # If no plugins configured, use default
        if not plugins:
            default = DEFAULT_PLUGINS.get(domain, "")
            if default:
                plugins.append(default)

        return plugins

    def get_fail_on_threshold(self, domain: str = "security") -> Optional[str]:
        """Get fail_on threshold for a specific domain.

        Handles both string (legacy) and FailOnConfig (per-domain) formats.

        Args:
            domain: Domain name (security, linting, type_checking, testing, coverage).
                   Defaults to "security" for backwards compatibility.

        Returns:
            Threshold value or None if not set.
        """
        if self.fail_on is None:
            return None
        if isinstance(self.fail_on, str):
            # Legacy string format applies to security domain only
            return self.fail_on if domain == "security" else None
        if isinstance(self.fail_on, FailOnConfig):
            return self.fail_on.get_threshold(domain)
        return None

    def get_scanner_options(self, domain: str) -> Dict[str, Any]:
        """Get plugin-specific options for a domain.

        These are all the options configured under scanners.<domain>
        except for `enabled` and `plugin`.

        Args:
            domain: Domain name (sca, sast, iac, container).

        Returns:
            Dictionary of plugin-specific options.
        """
        domain_config = self.get_scanner_config(domain)
        return domain_config.options
