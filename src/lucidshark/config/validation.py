"""Configuration validation for lucidshark.

Validates core configuration keys and warns on unknown keys.
Plugin-specific options are passed through without validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)


class ValidationSeverity(Enum):
    """Severity level for validation issues."""

    ERROR = "error"  # Config will fail at runtime
    WARNING = "warning"  # Likely mistake but config usable


@dataclass
class ConfigValidationIssue:
    """A validation issue for configuration with severity."""

    message: str
    source: str
    severity: ValidationSeverity
    key: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/MCP output.

        Returns:
            Dictionary with message, key, and optional suggestion.
        """
        result: Dict[str, Any] = {
            "message": self.message,
            "key": self.key,
        }
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


# Valid top-level keys (core config)
VALID_TOP_LEVEL_KEYS: Set[str] = {
    "version",
    "preset",
    "project",
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
    "linting",
    "type_checking",
    "security",
    "testing",
    "coverage",
    "duplication",
}

# Valid keys under pipeline domain sections (linting, type_checking, testing, coverage)
VALID_PIPELINE_DOMAIN_KEYS: Set[str] = {
    "enabled",
    "tools",
}

# Valid keys under pipeline.coverage section
VALID_PIPELINE_COVERAGE_KEYS: Set[str] = {
    "enabled",
    "tools",
    "threshold",
    "extra_args",  # Extra arguments to pass to Maven/Gradle
}

# Valid keys under pipeline.security section
VALID_PIPELINE_SECURITY_KEYS: Set[str] = {
    "enabled",
    "tools",
}

# Valid keys under pipeline.duplication section
VALID_PIPELINE_DUPLICATION_KEYS: Set[str] = {
    "enabled",
    "tools",
    "threshold",
    "min_lines",
    "min_chars",
    "exclude",
}

# Pipeline domains that require tools when enabled
PIPELINE_DOMAINS_REQUIRING_TOOLS: Set[str] = {
    "linting",
    "type_checking",
    "testing",
    "coverage",
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

# Valid fail_on domains (for dict format)
VALID_FAIL_ON_DOMAINS: Set[str] = {
    "linting",
    "type_checking",
    "security",
    "testing",
    "coverage",
    "duplication",
}

# Valid fail_on values per domain type
VALID_FAIL_ON_VALUES: Dict[str, Set[str]] = {
    "linting": {"error", "none"},
    "type_checking": {"error", "none"},
    "security": {"critical", "high", "medium", "low", "info", "none"},
    "testing": {"any", "none"},
    "coverage": {"any", "none", "below_threshold"},
    "duplication": {"any", "none", "above_threshold"},  # Can also be a percentage like "5%" - validated separately
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
    "timeout",
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

    # Runtime type check for defensive programming (data may not be dict at runtime)
    if not isinstance(data, dict):  # type: ignore[unreachable]
        warnings.append(ConfigValidationWarning(
            message=f"Config must be a mapping, got {type(data).__name__}",
            source=source,
        ))
        return warnings  # type: ignore[unreachable]

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

    # Validate fail_on (string or dict format)
    fail_on = data.get("fail_on")
    if fail_on is not None:
        if isinstance(fail_on, str):
            # Legacy string format - must be a valid severity
            if fail_on.lower() not in VALID_SEVERITIES:
                suggestion = _suggest_key(fail_on.lower(), VALID_SEVERITIES)
                warning = ConfigValidationWarning(
                    message=f"Invalid severity '{fail_on}' for 'fail_on'",
                    source=source,
                    key="fail_on",
                    suggestion=suggestion,
                )
                warnings.append(warning)
                _log_warning(warning)
        elif isinstance(fail_on, dict):
            # Dict format - validate each domain key and value
            for domain, value in fail_on.items():
                if domain not in VALID_FAIL_ON_DOMAINS:
                    suggestion = _suggest_key(domain, VALID_FAIL_ON_DOMAINS)
                    warning = ConfigValidationWarning(
                        message=f"Unknown domain '{domain}' in 'fail_on'",
                        source=source,
                        key=f"fail_on.{domain}",
                        suggestion=suggestion,
                    )
                    warnings.append(warning)
                    _log_warning(warning)
                elif not isinstance(value, str):
                    warnings.append(ConfigValidationWarning(
                        message=f"'fail_on.{domain}' must be a string, got {type(value).__name__}",
                        source=source,
                        key=f"fail_on.{domain}",
                    ))
                else:
                    valid_values = VALID_FAIL_ON_VALUES.get(domain, set())
                    if value.lower() not in valid_values:
                        warning = ConfigValidationWarning(
                            message=f"Invalid value '{value}' for 'fail_on.{domain}'. "
                                    f"Valid values: {', '.join(sorted(valid_values))}",
                            source=source,
                            key=f"fail_on.{domain}",
                        )
                        warnings.append(warning)
                        _log_warning(warning)
        else:
            warnings.append(ConfigValidationWarning(
                message=f"'fail_on' must be a string or mapping, got {type(fail_on).__name__}",
                source=source,
                key="fail_on",
            ))

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

            # Validate pipeline domain sections (linting, type_checking, testing, coverage)
            for domain in PIPELINE_DOMAINS_REQUIRING_TOOLS:
                domain_config = pipeline.get(domain)
                if domain_config is not None and isinstance(domain_config, dict):
                    # Check if enabled (default True if not specified)
                    is_enabled = domain_config.get("enabled", True)

                    # Validate keys based on domain type
                    if domain == "coverage":
                        valid_keys = VALID_PIPELINE_COVERAGE_KEYS
                    else:
                        valid_keys = VALID_PIPELINE_DOMAIN_KEYS

                    for key in domain_config.keys():
                        if key not in valid_keys:
                            suggestion = _suggest_key(key, valid_keys)
                            warning = ConfigValidationWarning(
                                message=f"Unknown key 'pipeline.{domain}.{key}'",
                                source=source,
                                key=f"pipeline.{domain}.{key}",
                                suggestion=suggestion,
                            )
                            warnings.append(warning)
                            _log_warning(warning)

                    # Check tools is specified when enabled
                    tools = domain_config.get("tools")
                    if is_enabled and tools is None:
                        warnings.append(ConfigValidationWarning(
                            message=f"'pipeline.{domain}.tools' is required when {domain} is enabled",
                            source=source,
                            key=f"pipeline.{domain}.tools",
                        ))
                    elif tools is not None and not isinstance(tools, list):
                        warnings.append(ConfigValidationWarning(
                            message=f"'pipeline.{domain}.tools' must be a list",
                            source=source,
                            key=f"pipeline.{domain}.tools",
                        ))

                    # Validate threshold for coverage
                    if domain == "coverage":
                        threshold = domain_config.get("threshold")
                        if threshold is not None and not isinstance(threshold, (int, float)):
                            warnings.append(ConfigValidationWarning(
                                message="'pipeline.coverage.threshold' must be a number",
                                source=source,
                                key="pipeline.coverage.threshold",
                            ))

            # Validate pipeline.security section
            security_config = pipeline.get("security")
            if security_config is not None and isinstance(security_config, dict):
                for key in security_config.keys():
                    if key not in VALID_PIPELINE_SECURITY_KEYS:
                        suggestion = _suggest_key(key, VALID_PIPELINE_SECURITY_KEYS)
                        warning = ConfigValidationWarning(
                            message=f"Unknown key 'pipeline.security.{key}'",
                            source=source,
                            key=f"pipeline.security.{key}",
                            suggestion=suggestion,
                        )
                        warnings.append(warning)
                        _log_warning(warning)

                # Validate tools is a list of dicts with name and domains
                tools = security_config.get("tools")
                if tools is not None:
                    if not isinstance(tools, list):
                        warnings.append(ConfigValidationWarning(
                            message="'pipeline.security.tools' must be a list",
                            source=source,
                            key="pipeline.security.tools",
                        ))
                    else:
                        for i, tool in enumerate(tools):
                            if isinstance(tool, dict):
                                if "name" not in tool:
                                    warnings.append(ConfigValidationWarning(
                                        message=f"'pipeline.security.tools[{i}]' must have a 'name' field",
                                        source=source,
                                        key=f"pipeline.security.tools[{i}].name",
                                    ))

            # Validate pipeline.duplication section
            duplication_config = pipeline.get("duplication")
            if duplication_config is not None and isinstance(duplication_config, dict):
                for key in duplication_config.keys():
                    if key not in VALID_PIPELINE_DUPLICATION_KEYS:
                        suggestion = _suggest_key(key, VALID_PIPELINE_DUPLICATION_KEYS)
                        warning = ConfigValidationWarning(
                            message=f"Unknown key 'pipeline.duplication.{key}'",
                            source=source,
                            key=f"pipeline.duplication.{key}",
                            suggestion=suggestion,
                        )
                        warnings.append(warning)
                        _log_warning(warning)

                # Validate threshold is a number
                threshold = duplication_config.get("threshold")
                if threshold is not None and not isinstance(threshold, (int, float)):
                    warnings.append(ConfigValidationWarning(
                        message="'pipeline.duplication.threshold' must be a number",
                        source=source,
                        key="pipeline.duplication.threshold",
                    ))

                # Validate exclude is a list
                exclude = duplication_config.get("exclude")
                if exclude is not None and not isinstance(exclude, list):
                    warnings.append(ConfigValidationWarning(
                        message="'pipeline.duplication.exclude' must be a list",
                        source=source,
                        key="pipeline.duplication.exclude",
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


def validate_config_file(config_path: Path) -> Tuple[bool, List[ConfigValidationIssue]]:
    """Validate a configuration file from disk.

    Checks file existence, YAML syntax, and configuration semantics.

    Args:
        config_path: Path to the configuration file.

    Returns:
        Tuple of (is_valid, issues) where is_valid is False if any errors exist.
    """
    issues: List[ConfigValidationIssue] = []
    source = str(config_path)

    # Check file exists
    if not config_path.exists():
        issues.append(ConfigValidationIssue(
            message=f"Configuration file not found: {config_path}",
            source=source,
            severity=ValidationSeverity.ERROR,
        ))
        return False, issues

    # Try to parse YAML
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        # Extract line number from YAML error if available
        error_msg = f"Invalid YAML syntax: {e}"
        issues.append(ConfigValidationIssue(
            message=error_msg,
            source=source,
            severity=ValidationSeverity.ERROR,
        ))
        return False, issues

    # Empty file is valid but warn
    if data is None:
        issues.append(ConfigValidationIssue(
            message="Configuration file is empty",
            source=source,
            severity=ValidationSeverity.WARNING,
        ))
        return True, issues

    # Validate config structure
    warnings = validate_config(data, source)

    # Convert warnings to issues
    # Type errors are ERROR severity, unknown keys are WARNING severity
    for warning in warnings:
        # Determine severity based on message content
        # Type mismatches and invalid values are errors
        is_error = any(phrase in warning.message for phrase in [
            "must be a",
            "Invalid severity",
            "Invalid value",
            "Config must be",
        ])

        issues.append(ConfigValidationIssue(
            message=warning.message,
            source=warning.source,
            severity=ValidationSeverity.ERROR if is_error else ValidationSeverity.WARNING,
            key=warning.key,
            suggestion=warning.suggestion,
        ))

    # Valid if no errors
    has_errors = any(issue.severity == ValidationSeverity.ERROR for issue in issues)
    return not has_errors, issues


@dataclass
class ValidationResult:
    """Result of config validation with categorized issues."""

    is_valid: bool
    config_path: Optional[Path]
    errors: List[ConfigValidationIssue]
    warnings: List[ConfigValidationIssue]
    error_message: Optional[str] = None


def validate_config_at_path(
    project_root: Path,
    config_path: Optional[str] = None,
) -> ValidationResult:
    """Find and validate a configuration file.

    This is a high-level helper that handles:
    1. Finding the config file (or using provided path)
    2. Validating it
    3. Categorizing issues into errors and warnings

    Args:
        project_root: Project root directory.
        config_path: Optional path to config file (relative to project root).
            If not provided, searches for lucidshark.yml in project root.

    Returns:
        ValidationResult with categorized issues.
    """
    from lucidshark.config.loader import find_project_config

    # Determine config path
    path: Optional[Path]
    if config_path:
        path = project_root / config_path
    else:
        path = find_project_config(project_root)

    if path is None:
        return ValidationResult(
            is_valid=False,
            config_path=None,
            errors=[],
            warnings=[],
            error_message="No configuration file found in project root",
        )

    if not path.exists():
        return ValidationResult(
            is_valid=False,
            config_path=path,
            errors=[],
            warnings=[],
            error_message=f"Configuration file not found: {path}",
        )

    is_valid, issues = validate_config_file(path)

    errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
    warnings = [i for i in issues if i.severity == ValidationSeverity.WARNING]

    return ValidationResult(
        is_valid=is_valid,
        config_path=path,
        errors=errors,
        warnings=warnings,
    )
