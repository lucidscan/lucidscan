"""Configuration file loading and merging.

Handles loading configuration from YAML files with:
- Project-level config (.lucidshark.yml)
- Global config (~/.lucidshark/config/config.yml)
- Environment variable expansion (${VAR})
- Config merging with proper precedence
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from lucidshark.config.models import (
    CoveragePipelineConfig,
    DomainPipelineConfig,
    DuplicationPipelineConfig,
    FailOnConfig,
    LucidSharkConfig,
    OutputConfig,
    PipelineConfig,
    ProjectConfig,
    ScannerDomainConfig,
    ToolConfig,
)
from lucidshark.config.validation import validate_config
from lucidshark.core.logging import get_logger
from lucidshark.bootstrap.paths import get_lucidshark_home

LOGGER = get_logger(__name__)

# Config file names
PROJECT_CONFIG_NAMES = [".lucidshark.yml", ".lucidshark.yaml", "lucidshark.yml", "lucidshark.yaml"]
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
    preset: Optional[str] = None,
) -> LucidSharkConfig:
    """Load configuration with proper precedence.

    Precedence (highest to lowest):
    1. CLI flags (cli_overrides)
    2. Custom config file (cli_config_path) OR project config (.lucidshark.yml)
    3. Preset (if specified in config file or via CLI)
    4. Global config (~/.lucidshark/config/config.yml)
    5. Built-in defaults

    Args:
        project_root: Project root directory for finding .lucidshark.yml.
        cli_config_path: Optional path to custom config file (--config flag).
        cli_overrides: Dict of CLI flag overrides.
        preset: Optional preset name to use as base configuration.

    Returns:
        Merged LucidSharkConfig instance.

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

    # Layer 2: Preset (from CLI argument)
    # Note: Preset from config file is applied after loading the file
    if preset:
        preset_dict = _load_preset(preset)
        if preset_dict:
            merged = merge_configs(merged, preset_dict)
            sources.append(f"preset:{preset}")
            LOGGER.debug(f"Applied preset: {preset}")

    # Layer 3: Project or custom config
    project_dict: Dict[str, Any] = {}
    if cli_config_path:
        if not cli_config_path.exists():
            raise ConfigError(f"Config file not found: {cli_config_path}")
        try:
            project_dict = load_yaml_file(cli_config_path)
            validate_config(project_dict, source=str(cli_config_path))
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
                sources.append(f"project:{project_path}")
                LOGGER.debug(f"Loaded project config from {project_path}")
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {project_path}: {e}") from e

    # Check if project config specifies a preset (and CLI didn't already set one)
    config_preset = project_dict.get("preset")
    if config_preset and not preset:
        preset_dict = _load_preset(config_preset)
        if preset_dict:
            # Insert preset BEFORE project config overrides
            merged = merge_configs(merged, preset_dict)
            sources.insert(-1 if sources else 0, f"preset:{config_preset}")
            LOGGER.debug(f"Applied preset from config: {config_preset}")

    # Now merge project config on top
    if project_dict:
        # Remove 'preset' key before merging (it's metadata, not config)
        project_dict_clean = {k: v for k, v in project_dict.items() if k != "preset"}
        merged = merge_configs(merged, project_dict_clean)

    # Layer 4: CLI overrides
    if cli_overrides:
        merged = merge_configs(merged, cli_overrides)
        sources.append("cli")
        LOGGER.debug("Applied CLI overrides")

    # Convert to typed config
    config = dict_to_config(merged)
    config._config_sources = sources

    LOGGER.debug(f"Config loaded from sources: {sources}")
    return config


def _load_preset(preset_name: str) -> Optional[Dict[str, Any]]:
    """Load a preset configuration by name.

    Args:
        preset_name: Name of the preset (e.g., "python-strict").

    Returns:
        Preset configuration dict or None if not found.
    """
    try:
        from lucidshark.presets import get_preset
        preset_dict = get_preset(preset_name)
        if preset_dict is None:
            LOGGER.warning(f"Unknown preset: {preset_name}")
        return preset_dict
    except ImportError:
        LOGGER.warning("Presets module not available")
        return None


def find_project_config(project_root: Path) -> Optional[Path]:
    """Find config file in project root.

    Searches for .lucidshark.yml, .lucidshark.yaml, lucidshark.yml, lucidshark.yaml
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
    """Find global config at ~/.lucidshark/config/config.yml.

    Returns:
        Path to global config if it exists, None otherwise.
    """
    home = get_lucidshark_home()
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


def _parse_tool_config(tool_data: Dict[str, Any]) -> ToolConfig:
    """Parse a single tool configuration.

    Args:
        tool_data: Tool configuration dictionary.

    Returns:
        ToolConfig instance.
    """
    name = tool_data.get("name", "")
    config_path = tool_data.get("config")
    strict = tool_data.get("strict", False)
    domains = tool_data.get("domains", [])

    # Everything else is tool-specific options
    options = {
        k: v for k, v in tool_data.items()
        if k not in ("name", "config", "strict", "domains")
    }

    return ToolConfig(
        name=name,
        config=config_path,
        strict=strict,
        domains=domains,
        options=options,
    )


def _parse_domain_pipeline_config(
    domain_data: Optional[Dict[str, Any]]
) -> Optional[DomainPipelineConfig]:
    """Parse a domain pipeline configuration (linting, type_checking, etc.).

    Args:
        domain_data: Domain configuration dictionary or None.

    Returns:
        DomainPipelineConfig instance or None if not configured.
    """
    if domain_data is None:
        return None

    enabled = domain_data.get("enabled", True)
    tools_data = domain_data.get("tools", [])

    tools = []
    for tool_data in tools_data:
        if isinstance(tool_data, dict):
            tools.append(_parse_tool_config(tool_data))
        elif isinstance(tool_data, str):
            # Simple string format: just the tool name
            tools.append(ToolConfig(name=tool_data))

    return DomainPipelineConfig(enabled=enabled, tools=tools)


def _parse_coverage_pipeline_config(
    coverage_data: Optional[Dict[str, Any]]
) -> Optional[CoveragePipelineConfig]:
    """Parse coverage pipeline configuration.

    Args:
        coverage_data: Coverage configuration dictionary or None.

    Returns:
        CoveragePipelineConfig instance or None if not configured.
    """
    if coverage_data is None:
        return None

    # Parse tools the same way as _parse_domain_pipeline_config
    tools_data = coverage_data.get("tools", [])
    tools = []
    for tool_data in tools_data:
        if isinstance(tool_data, dict):
            tools.append(_parse_tool_config(tool_data))
        elif isinstance(tool_data, str):
            # Simple string format: just the tool name
            tools.append(ToolConfig(name=tool_data))

    return CoveragePipelineConfig(
        enabled=coverage_data.get("enabled", False),
        threshold=coverage_data.get("threshold", 80),
        tools=tools,
        extra_args=coverage_data.get("extra_args", []),
    )


def _parse_duplication_pipeline_config(
    duplication_data: Optional[Dict[str, Any]]
) -> Optional[DuplicationPipelineConfig]:
    """Parse duplication detection pipeline configuration.

    Args:
        duplication_data: Duplication configuration dictionary or None.

    Returns:
        DuplicationPipelineConfig instance or None if not configured.
    """
    if duplication_data is None:
        return None

    # Parse tools the same way as _parse_domain_pipeline_config
    tools_data = duplication_data.get("tools", [])
    tools = []
    for tool_data in tools_data:
        if isinstance(tool_data, dict):
            tools.append(_parse_tool_config(tool_data))
        elif isinstance(tool_data, str):
            # Simple string format: just the tool name
            tools.append(ToolConfig(name=tool_data))

    return DuplicationPipelineConfig(
        enabled=duplication_data.get("enabled", False),
        threshold=duplication_data.get("threshold", 10.0),
        min_lines=duplication_data.get("min_lines", 4),
        min_chars=duplication_data.get("min_chars", 3),
        exclude=duplication_data.get("exclude", []),
        tools=tools,
    )


def dict_to_config(data: Dict[str, Any]) -> LucidSharkConfig:
    """Convert validated dict to typed LucidSharkConfig.

    Args:
        data: Configuration dictionary.

    Returns:
        Typed LucidSharkConfig instance.
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
        linting=_parse_domain_pipeline_config(pipeline_data.get("linting")),
        type_checking=_parse_domain_pipeline_config(pipeline_data.get("type_checking")),
        testing=_parse_domain_pipeline_config(pipeline_data.get("testing")),
        coverage=_parse_coverage_pipeline_config(pipeline_data.get("coverage")),
        security=_parse_domain_pipeline_config(pipeline_data.get("security")),
        duplication=_parse_duplication_pipeline_config(pipeline_data.get("duplication")),
    )

    # Parse project config
    project_data = data.get("project", {})
    project = ProjectConfig(
        name=project_data.get("name", ""),
        languages=project_data.get("languages", []),
    )

    # Parse fail_on (string or dict format)
    fail_on_data = data.get("fail_on")
    fail_on: str | FailOnConfig | None = None
    if fail_on_data is not None:
        if isinstance(fail_on_data, str):
            # Legacy string format - keep as string
            fail_on = fail_on_data
        elif isinstance(fail_on_data, dict):
            # Dict format - convert to FailOnConfig
            fail_on = FailOnConfig(
                linting=fail_on_data.get("linting"),
                type_checking=fail_on_data.get("type_checking"),
                security=fail_on_data.get("security"),
                testing=fail_on_data.get("testing"),
                coverage=fail_on_data.get("coverage"),
                duplication=fail_on_data.get("duplication"),
            )

    return LucidSharkConfig(
        project=project,
        fail_on=fail_on,
        ignore=data.get("ignore", []),
        output=output,
        scanners=scanners,
        enrichers=enrichers,
        pipeline=pipeline,
    )


def get_default_config() -> LucidSharkConfig:
    """Get default configuration with no scanners enabled.

    Returns:
        Default LucidSharkConfig instance.
    """
    return LucidSharkConfig()
