"""Configuration data models for lucidscan.

Defines typed configuration classes that represent .lucidscan.yml structure.
Core fields are validated, while plugin-specific options are passed through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Default plugins per domain (used when not specified in config)
DEFAULT_PLUGINS: Dict[str, str] = {
    "sca": "trivy",
    "container": "trivy",
    "sast": "opengrep",
    "iac": "checkov",
}

# Valid severity values for fail_on
VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}


@dataclass
class OutputConfig:
    """Output formatting configuration."""

    format: str = "json"


@dataclass
class AIConfig:
    """AI enrichment configuration.

    Controls LLM-powered explanations for security issues.
    AI is always opt-in and requires explicit enablement via --ai flag
    or ai.enabled: true in config.
    """

    enabled: bool = False  # Opt-in, requires --ai flag or config
    provider: str = "openai"  # openai, anthropic, ollama
    model: str = ""  # Empty = use provider default
    api_key: str = ""  # API key (supports ${VAR} expansion)
    send_code_snippets: bool = True  # Include code in prompts
    base_url: Optional[str] = None  # Custom API endpoint (Ollama/self-hosted)
    temperature: float = 0.3  # Low for consistent explanations
    max_tokens: int = 500  # Limit explanation length
    cache_enabled: bool = True  # Enable on-disk caching
    prompt_version: str = "v1"  # Used in cache key for prompt invalidation


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
class LucidScanConfig:
    """Complete lucidscan configuration.

    Core fields are validated by the framework. Plugin-specific options
    under `scanners.*` are passed through without validation.

    Example .lucidscan.yml:
        fail_on: high
        ignore:
          - "tests/**"
        scanners:
          sca:
            enabled: true
            plugin: trivy
            ignore_unfixed: true  # Plugin-specific, passed through
    """

    # Core config (validated)
    fail_on: Optional[str] = None  # critical, high, medium, low
    ignore: List[str] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)

    # Scanner configs per domain (plugin-specific options passed through)
    scanners: Dict[str, ScannerDomainConfig] = field(default_factory=dict)

    # Enricher configs (plugin-specific options passed through)
    enrichers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Pipeline configuration (enricher ordering, parallelism)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

    # AI enrichment configuration
    ai: AIConfig = field(default_factory=AIConfig)

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
        """Get list of enabled domain names.

        Returns:
            List of domain names that are enabled in config.
        """
        return [domain for domain, cfg in self.scanners.items() if cfg.enabled]

    def get_plugin_for_domain(self, domain: str) -> str:
        """Get which plugin serves a domain.

        Args:
            domain: Domain name (sca, sast, iac, container).

        Returns:
            Plugin name, falling back to default if not specified.
        """
        domain_config = self.get_scanner_config(domain)
        if domain_config.plugin:
            return domain_config.plugin
        return DEFAULT_PLUGINS.get(domain, "")

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
