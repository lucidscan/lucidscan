"""Configuration file loading and merging.

Handles loading configuration from YAML files with:
- Project-level config (.lucidscan.yml)
- Global config (~/.lucidscan/config/config.yml)
- Environment variable expansion (${VAR})
- Config merging with proper precedence
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from lucidscan.config.models import (
    AIConfig,
    DEFAULT_PLUGINS,
    LucidScanConfig,
    OutputConfig,
    PipelineConfig,
    ScannerDomainConfig,
)
from lucidscan.config.validation import validate_config
from lucidscan.core.logging import get_logger
from lucidscan.bootstrap.paths import get_lucidscan_home

LOGGER = get_logger(__name__)

# Config file names
PROJECT_CONFIG_NAMES = [".lucidscan.yml", ".lucidscan.yaml", "lucidscan.yml", "lucidscan.yaml"]
GLOBAL_CONFIG_NAME = "config.yml"

# Environment variable pattern: ${VAR} or ${VAR:-default}
ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")


class ConfigError(Exception):
    """Configuration loading or parsing error."""

    pass


def load_config(
    project_root: Path,
    cli_config_path: Optional[Path] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> LucidScanConfig:
    """Load configuration with proper precedence.

    Precedence (highest to lowest):
    1. CLI flags (cli_overrides)
    2. Custom config file (cli_config_path) OR project config (.lucidscan.yml)
    3. Global config (~/.lucidscan/config/config.yml)
    4. Built-in defaults

    Args:
        project_root: Project root directory for finding .lucidscan.yml.
        cli_config_path: Optional path to custom config file (--config flag).
        cli_overrides: Dict of CLI flag overrides.

    Returns:
        Merged LucidScanConfig instance.

    Raises:
        ConfigError: If specified config file doesn't exist or has parse errors.
    """
    sources: List[str] = []
    merged: Dict[str, Any] = {}

    # Layer 1: Global config
    global_path = find_global_config()
    if global_path and global_path.exists():
        try:
            global_dict = load_yaml_file(global_path)
            validate_config(global_dict, source=str(global_path))
            merged = merge_configs(merged, global_dict)
            sources.append(f"global:{global_path}")
            LOGGER.debug(f"Loaded global config from {global_path}")
        except Exception as e:
            LOGGER.warning(f"Failed to load global config: {e}")

    # Layer 2: Project or custom config
    if cli_config_path:
        if not cli_config_path.exists():
            raise ConfigError(f"Config file not found: {cli_config_path}")
        try:
            project_dict = load_yaml_file(cli_config_path)
            validate_config(project_dict, source=str(cli_config_path))
            merged = merge_configs(merged, project_dict)
            sources.append(f"custom:{cli_config_path}")
            LOGGER.debug(f"Loaded custom config from {cli_config_path}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {cli_config_path}: {e}") from e
    else:
        project_path = find_project_config(project_root)
        if project_path and project_path.exists():
            try:
                project_dict = load_yaml_file(project_path)
                validate_config(project_dict, source=str(project_path))
                merged = merge_configs(merged, project_dict)
                sources.append(f"project:{project_path}")
                LOGGER.debug(f"Loaded project config from {project_path}")
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {project_path}: {e}") from e

    # Layer 3: CLI overrides
    if cli_overrides:
        merged = merge_configs(merged, cli_overrides)
        sources.append("cli")
        LOGGER.debug("Applied CLI overrides")

    # Convert to typed config
    config = dict_to_config(merged)
    config._config_sources = sources

    LOGGER.debug(f"Config loaded from sources: {sources}")
    return config


def find_project_config(project_root: Path) -> Optional[Path]:
    """Find config file in project root.

    Searches for .lucidscan.yml, .lucidscan.yaml, lucidscan.yml, lucidscan.yaml
    in the project root directory.

    Args:
        project_root: Directory to search in.

    Returns:
        Path to config file if found, None otherwise.
    """
    for name in PROJECT_CONFIG_NAMES:
        config_path = project_root / name
        if config_path.exists():
            return config_path
    return None


def find_global_config() -> Optional[Path]:
    """Find global config at ~/.lucidscan/config/config.yml.

    Returns:
        Path to global config if it exists, None otherwise.
    """
    home = get_lucidscan_home()
    config_path = home / "config" / GLOBAL_CONFIG_NAME
    if config_path.exists():
        return config_path
    return None


def load_yaml_file(path: Path) -> Dict[str, Any]:
    """Load and parse a YAML config file.

    Performs environment variable expansion on string values.

    Args:
        path: Path to YAML file.

    Returns:
        Parsed dictionary.

    Raises:
        yaml.YAMLError: If YAML parsing fails.
        FileNotFoundError: If file doesn't exist.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    data = yaml.safe_load(content)

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ConfigError(f"Config file must be a YAML mapping, got {type(data).__name__}")

    # Expand environment variables
    return expand_env_vars(data)


def expand_env_vars(data: Any) -> Any:
    """Recursively expand environment variables in config values.

    Supports ${VAR} and ${VAR:-default} syntax.

    Args:
        data: Config data (dict, list, or scalar).

    Returns:
        Data with environment variables expanded.
    """
    if isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item) for item in data]
    elif isinstance(data, str):
        return ENV_VAR_PATTERN.sub(_env_var_replacer, data)
    else:
        return data


def _env_var_replacer(match: re.Match[str]) -> str:
    """Replace environment variable reference with its value."""
    var_name = match.group(1)
    default_value = match.group(2)

    value = os.environ.get(var_name)
    if value is not None:
        return value
    if default_value is not None:
        return default_value

    LOGGER.warning(f"Environment variable ${var_name} is not set and has no default")
    return ""


def merge_configs(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two config dicts, with overlay taking precedence.

    Rules:
    - Scalar values: overlay replaces base
    - Lists: overlay replaces base (no merging)
    - Dicts: recursive merge

    Args:
        base: Base configuration dictionary.
        overlay: Overlay configuration to merge on top.

    Returns:
        Merged configuration dictionary.
    """
    result = base.copy()

    for key, overlay_value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(overlay_value, dict):
            result[key] = merge_configs(result[key], overlay_value)
        else:
            result[key] = overlay_value

    return result


def dict_to_config(data: Dict[str, Any]) -> LucidScanConfig:
    """Convert validated dict to typed LucidScanConfig.

    Args:
        data: Configuration dictionary.

    Returns:
        Typed LucidScanConfig instance.
    """
    # Parse output config
    output_data = data.get("output", {})
    output = OutputConfig(
        format=output_data.get("format", "json"),
    )

    # Parse scanner configs
    scanners: Dict[str, ScannerDomainConfig] = {}
    scanners_data = data.get("scanners", {})

    for domain, domain_data in scanners_data.items():
        if not isinstance(domain_data, dict):
            continue

        # Extract framework-level keys
        enabled = domain_data.get("enabled", True)
        plugin = domain_data.get("plugin", "")

        # Everything else is plugin-specific options
        options = {k: v for k, v in domain_data.items() if k not in ("enabled", "plugin")}

        scanners[domain] = ScannerDomainConfig(
            enabled=enabled,
            plugin=plugin,
            options=options,
        )

    # Parse enrichers (passthrough for now)
    enrichers = data.get("enrichers", {})

    # Parse pipeline config
    pipeline_data = data.get("pipeline", {})
    pipeline = PipelineConfig(
        enrichers=pipeline_data.get("enrichers", []),
        max_workers=pipeline_data.get("max_workers", 4),
    )

    # Parse AI config
    ai_data = data.get("ai", {})
    ai = AIConfig(
        enabled=ai_data.get("enabled", False),
        provider=ai_data.get("provider", "openai"),
        model=ai_data.get("model", ""),
        api_key=ai_data.get("api_key", ""),
        send_code_snippets=ai_data.get("send_code_snippets", True),
        base_url=ai_data.get("base_url"),
        temperature=ai_data.get("temperature", 0.3),
        max_tokens=ai_data.get("max_tokens", 500),
        cache_enabled=ai_data.get("cache_enabled", True),
        prompt_version=ai_data.get("prompt_version", "v1"),
    )

    return LucidScanConfig(
        fail_on=data.get("fail_on"),
        ignore=data.get("ignore", []),
        output=output,
        scanners=scanners,
        enrichers=enrichers,
        pipeline=pipeline,
        ai=ai,
    )


def get_default_config() -> LucidScanConfig:
    """Get default configuration with no scanners enabled.

    Returns:
        Default LucidScanConfig instance.
    """
    return LucidScanConfig()
