"""Configuration validation for lucidscan.

Validates core configuration keys and warns on unknown keys.
Plugin-specific options are passed through without validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from typing import Any, Dict, List, Optional, Set

from lucidscan.core.logging import get_logger

LOGGER = get_logger(__name__)

# Valid top-level keys (core config)
VALID_TOP_LEVEL_KEYS: Set[str] = {
    "fail_on",
    "ignore",
    "output",
    "scanners",
    "enrichers",
    "pipeline",
    "ai",
}

# Valid keys under output section
VALID_OUTPUT_KEYS: Set[str] = {
    "format",
}

# Valid keys under pipeline section
VALID_PIPELINE_KEYS: Set[str] = {
    "enrichers",
    "max_workers",
}

# Valid keys under scanners.<domain> (framework-level, not plugin-specific)
VALID_SCANNER_DOMAIN_KEYS: Set[str] = {
    "enabled",
    "plugin",
    # Everything else is plugin-specific and passed through
}

# Valid domain names
VALID_DOMAINS: Set[str] = {
    "sca",
    "sast",
    "iac",
    "container",
}

# Valid severity values
VALID_SEVERITIES: Set[str] = {
    "critical",
    "high",
    "medium",
    "low",
    "info",
}

# Valid keys under ai section
VALID_AI_KEYS: Set[str] = {
    "enabled",
    "provider",
    "model",
    "api_key",
    "send_code_snippets",
    "base_url",
    "temperature",
    "max_tokens",
    "cache_enabled",
    "prompt_version",
}

# Valid AI providers
VALID_AI_PROVIDERS: Set[str] = {
    "openai",
    "anthropic",
    "ollama",
}


@dataclass
class ConfigValidationWarning:
    """A validation warning for configuration."""

    message: str
    source: str
    key: Optional[str] = None
    suggestion: Optional[str] = None


def validate_config(
    data: Dict[str, Any],
    source: str,
) -> List[ConfigValidationWarning]:
    """Validate configuration dictionary.

    Warns on unknown core keys but allows plugin-specific options to pass through.
    Does not raise exceptions - returns warnings instead.

    Args:
        data: Config dictionary to validate.
        source: Source file path for warning messages.

    Returns:
        List of validation warnings.
    """
    warnings: List[ConfigValidationWarning] = []

    if not isinstance(data, dict):
        warnings.append(ConfigValidationWarning(
            message=f"Config must be a mapping, got {type(data).__name__}",
            source=source,
        ))
        return warnings

    # Check top-level keys
    for key in data.keys():
        if key not in VALID_TOP_LEVEL_KEYS:
            suggestion = _suggest_key(key, VALID_TOP_LEVEL_KEYS)
            warning = ConfigValidationWarning(
                message=f"Unknown top-level key '{key}'",
                source=source,
                key=key,
                suggestion=suggestion,
            )
            warnings.append(warning)
            _log_warning(warning)

    # Validate fail_on
    fail_on = data.get("fail_on")
    if fail_on is not None:
        if not isinstance(fail_on, str):
            warnings.append(ConfigValidationWarning(
                message=f"'fail_on' must be a string, got {type(fail_on).__name__}",
                source=source,
                key="fail_on",
            ))
        elif fail_on.lower() not in VALID_SEVERITIES:
            suggestion = _suggest_key(fail_on.lower(), VALID_SEVERITIES)
            warning = ConfigValidationWarning(
                message=f"Invalid severity '{fail_on}' for 'fail_on'",
                source=source,
                key="fail_on",
                suggestion=suggestion,
            )
            warnings.append(warning)
            _log_warning(warning)

    # Validate ignore
    ignore = data.get("ignore")
    if ignore is not None:
        if not isinstance(ignore, list):
            warnings.append(ConfigValidationWarning(
                message=f"'ignore' must be a list, got {type(ignore).__name__}",
                source=source,
                key="ignore",
            ))

    # Validate output section
    output = data.get("output")
    if output is not None:
        if not isinstance(output, dict):
            warnings.append(ConfigValidationWarning(
                message=f"'output' must be a mapping, got {type(output).__name__}",
                source=source,
                key="output",
            ))
        else:
            for key in output.keys():
                if key not in VALID_OUTPUT_KEYS:
                    suggestion = _suggest_key(key, VALID_OUTPUT_KEYS)
                    warning = ConfigValidationWarning(
                        message=f"Unknown key 'output.{key}'",
                        source=source,
                        key=f"output.{key}",
                        suggestion=suggestion,
                    )
                    warnings.append(warning)
                    _log_warning(warning)

    # Validate scanners section
    scanners = data.get("scanners")
    if scanners is not None:
        if not isinstance(scanners, dict):
            warnings.append(ConfigValidationWarning(
                message=f"'scanners' must be a mapping, got {type(scanners).__name__}",
                source=source,
                key="scanners",
            ))
        else:
            for domain, domain_config in scanners.items():
                # Warn on unknown domains (but allow them)
                if domain not in VALID_DOMAINS:
                    suggestion = _suggest_key(domain, VALID_DOMAINS)
                    warning = ConfigValidationWarning(
                        message=f"Unknown scanner domain '{domain}'",
                        source=source,
                        key=f"scanners.{domain}",
                        suggestion=suggestion,
                    )
                    warnings.append(warning)
                    _log_warning(warning)

                if isinstance(domain_config, dict):
                    # Validate enabled type
                    enabled = domain_config.get("enabled")
                    if enabled is not None and not isinstance(enabled, bool):
                        warnings.append(ConfigValidationWarning(
                            message=f"'scanners.{domain}.enabled' must be a boolean",
                            source=source,
                            key=f"scanners.{domain}.enabled",
                        ))

                    # Validate plugin type
                    plugin = domain_config.get("plugin")
                    if plugin is not None and not isinstance(plugin, str):
                        warnings.append(ConfigValidationWarning(
                            message=f"'scanners.{domain}.plugin' must be a string",
                            source=source,
                            key=f"scanners.{domain}.plugin",
                        ))

                    # Other keys are plugin-specific and not validated

    # Validate pipeline section
    pipeline = data.get("pipeline")
    if pipeline is not None:
        if not isinstance(pipeline, dict):
            warnings.append(ConfigValidationWarning(
                message=f"'pipeline' must be a mapping, got {type(pipeline).__name__}",
                source=source,
                key="pipeline",
            ))
        else:
            for key in pipeline.keys():
                if key not in VALID_PIPELINE_KEYS:
                    suggestion = _suggest_key(key, VALID_PIPELINE_KEYS)
                    warning = ConfigValidationWarning(
                        message=f"Unknown key 'pipeline.{key}'",
                        source=source,
                        key=f"pipeline.{key}",
                        suggestion=suggestion,
                    )
                    warnings.append(warning)
                    _log_warning(warning)

            # Validate enrichers is a list
            enrichers = pipeline.get("enrichers")
            if enrichers is not None and not isinstance(enrichers, list):
                warnings.append(ConfigValidationWarning(
                    message="'pipeline.enrichers' must be a list",
                    source=source,
                    key="pipeline.enrichers",
                ))

            # Validate max_workers is an integer
            max_workers = pipeline.get("max_workers")
            if max_workers is not None and not isinstance(max_workers, int):
                warnings.append(ConfigValidationWarning(
                    message="'pipeline.max_workers' must be an integer",
                    source=source,
                    key="pipeline.max_workers",
                ))

    # Validate ai section
    ai = data.get("ai")
    if ai is not None:
        if not isinstance(ai, dict):
            warnings.append(ConfigValidationWarning(
                message=f"'ai' must be a mapping, got {type(ai).__name__}",
                source=source,
                key="ai",
            ))
        else:
            for key in ai.keys():
                if key not in VALID_AI_KEYS:
                    suggestion = _suggest_key(key, VALID_AI_KEYS)
                    warning = ConfigValidationWarning(
                        message=f"Unknown key 'ai.{key}'",
                        source=source,
                        key=f"ai.{key}",
                        suggestion=suggestion,
                    )
                    warnings.append(warning)
                    _log_warning(warning)

            # Validate enabled type
            enabled = ai.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                warnings.append(ConfigValidationWarning(
                    message="'ai.enabled' must be a boolean",
                    source=source,
                    key="ai.enabled",
                ))

            # Validate provider
            provider = ai.get("provider")
            if provider is not None:
                if not isinstance(provider, str):
                    warnings.append(ConfigValidationWarning(
                        message="'ai.provider' must be a string",
                        source=source,
                        key="ai.provider",
                    ))
                elif provider.lower() not in VALID_AI_PROVIDERS:
                    suggestion = _suggest_key(provider.lower(), VALID_AI_PROVIDERS)
                    warning = ConfigValidationWarning(
                        message=f"Unknown AI provider '{provider}'",
                        source=source,
                        key="ai.provider",
                        suggestion=suggestion,
                    )
                    warnings.append(warning)
                    _log_warning(warning)

            # Validate send_code_snippets type
            send_code = ai.get("send_code_snippets")
            if send_code is not None and not isinstance(send_code, bool):
                warnings.append(ConfigValidationWarning(
                    message="'ai.send_code_snippets' must be a boolean",
                    source=source,
                    key="ai.send_code_snippets",
                ))

            # Validate cache_enabled type
            cache_enabled = ai.get("cache_enabled")
            if cache_enabled is not None and not isinstance(cache_enabled, bool):
                warnings.append(ConfigValidationWarning(
                    message="'ai.cache_enabled' must be a boolean",
                    source=source,
                    key="ai.cache_enabled",
                ))

            # Validate temperature is a number
            temperature = ai.get("temperature")
            if temperature is not None and not isinstance(temperature, (int, float)):
                warnings.append(ConfigValidationWarning(
                    message="'ai.temperature' must be a number",
                    source=source,
                    key="ai.temperature",
                ))

            # Validate max_tokens is an integer
            max_tokens = ai.get("max_tokens")
            if max_tokens is not None and not isinstance(max_tokens, int):
                warnings.append(ConfigValidationWarning(
                    message="'ai.max_tokens' must be an integer",
                    source=source,
                    key="ai.max_tokens",
                ))

    return warnings


def _suggest_key(invalid_key: str, valid_keys: Set[str]) -> Optional[str]:
    """Suggest a valid key for a potential typo.

    Args:
        invalid_key: The invalid key entered.
        valid_keys: Set of valid keys.

    Returns:
        Closest matching valid key, or None if no good match.
    """
    matches = get_close_matches(invalid_key, list(valid_keys), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _log_warning(warning: ConfigValidationWarning) -> None:
    """Log a validation warning."""
    msg = f"{warning.message} in {warning.source}"
    if warning.suggestion:
        msg += f" (did you mean '{warning.suggestion}'?)"
    LOGGER.warning(msg)
