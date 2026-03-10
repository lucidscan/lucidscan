"""Tool validation for LucidShark.

Validates that all configured tools are installed before running scans.
Auto-downloadable tools (security scanners and duplo) are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from lucidshark.config.models import LucidSharkConfig
from lucidshark.core.logging import get_logger
from lucidshark.plugins.discovery import (
    COVERAGE_ENTRY_POINT_GROUP,
    DUPLICATION_ENTRY_POINT_GROUP,
    FORMATTER_ENTRY_POINT_GROUP,
    LINTER_ENTRY_POINT_GROUP,
    TEST_RUNNER_ENTRY_POINT_GROUP,
    TYPE_CHECKER_ENTRY_POINT_GROUP,
    get_plugin,
)

LOGGER = get_logger(__name__)


# Tools that LucidShark downloads automatically - no manual install required
AUTO_DOWNLOADABLE_TOOLS = frozenset(
    {
        "trivy",
        "opengrep",
        "checkov",
        "duplo",
        "pmd",
        "checkstyle",
        "spotbugs",
    }
)


# Install instructions for manually installed tools
INSTALL_INSTRUCTIONS: Dict[str, str] = {
    # Linters
    "ruff": "pip install ruff",
    "eslint": "npm install -g eslint",
    "biome": "npm install -g @biomejs/biome",
    "clippy": "rustup component add clippy",
    # Type checkers
    "mypy": "pip install mypy",
    "pyright": "pip install pyright",
    "typescript": "npm install -g typescript",
    "cargo_check": "Included with Rust toolchain (rustup)",
    # Note: spotbugs is now a managed tool (auto-downloaded) and not listed here
    # Test runners
    "pytest": "pip install pytest",
    "jest": "npm install jest",
    "karma": "npm install karma",
    "playwright": "npm install @playwright/test",
    "maven": "brew install maven (macOS) or download from maven.apache.org",
    "cargo": "Included with Rust toolchain (rustup)",
    # Coverage
    "coverage_py": "pip install coverage pytest-cov",
    "istanbul": "npm install nyc",
    "jacoco": "Maven/Gradle plugin (configured in pom.xml/build.gradle)",
    "tarpaulin": "cargo install cargo-tarpaulin",
    # Formatters
    "ruff_format": "pip install ruff",
    "prettier": "npm install -g prettier",
    "rustfmt": "rustup component add rustfmt",
    "google_java_format": "Download from github.com/google/google-java-format",
    # Note: checkstyle and pmd are managed tools (auto-downloaded) and not listed here
}


@dataclass
class ToolValidationError:
    """A single tool validation error."""

    tool_name: str
    domain: str
    reason: str
    install_instruction: Optional[str]


@dataclass
class ToolValidationResult:
    """Result of tool validation."""

    success: bool
    errors: List[ToolValidationError]


def _get_entry_point_group(domain: str) -> Optional[str]:
    """Map domain name to entry point group."""
    mapping = {
        "linting": LINTER_ENTRY_POINT_GROUP,
        "type_checking": TYPE_CHECKER_ENTRY_POINT_GROUP,
        "testing": TEST_RUNNER_ENTRY_POINT_GROUP,
        "coverage": COVERAGE_ENTRY_POINT_GROUP,
        "duplication": DUPLICATION_ENTRY_POINT_GROUP,
        "formatting": FORMATTER_ENTRY_POINT_GROUP,
    }
    return mapping.get(domain)


def _validate_tool(
    tool_name: str,
    domain: str,
    project_root: Path,
) -> Optional[ToolValidationError]:
    """Validate a single tool is available.

    Args:
        tool_name: Name of the tool to validate.
        domain: Domain the tool belongs to (linting, type_checking, etc.).
        project_root: Project root directory.

    Returns:
        ToolValidationError if tool is not available, None otherwise.
    """
    # Skip auto-downloadable tools
    if tool_name in AUTO_DOWNLOADABLE_TOOLS:
        LOGGER.debug(f"Skipping auto-downloadable tool: {tool_name}")
        return None

    # Get the entry point group for this domain
    entry_point_group = _get_entry_point_group(domain)
    if not entry_point_group:
        LOGGER.debug(f"Unknown domain for validation: {domain}")
        return None

    # Get the plugin
    plugin = get_plugin(entry_point_group, tool_name, project_root=project_root)
    if plugin is None:
        return ToolValidationError(
            tool_name=tool_name,
            domain=domain,
            reason=f"Plugin '{tool_name}' not found",
            install_instruction=INSTALL_INSTRUCTIONS.get(tool_name),
        )

    # Try to ensure the binary is available
    try:
        plugin.ensure_binary()
        LOGGER.debug(f"Tool validated: {tool_name}")
        return None
    except FileNotFoundError as e:
        # Extract the error message for a cleaner reason
        reason = str(e).split("\n")[0] if "\n" in str(e) else str(e)
        return ToolValidationError(
            tool_name=tool_name,
            domain=domain,
            reason=reason,
            install_instruction=INSTALL_INSTRUCTIONS.get(tool_name),
        )
    except Exception as e:
        return ToolValidationError(
            tool_name=tool_name,
            domain=domain,
            reason=f"Validation failed: {e}",
            install_instruction=INSTALL_INSTRUCTIONS.get(tool_name),
        )


def validate_configured_tools(
    config: LucidSharkConfig,
    project_root: Path,
    enabled_domains: Optional[List[str]] = None,
) -> ToolValidationResult:
    """Validate all configured tools are available.

    Only validates tools explicitly configured in lucidshark.yml.
    Skips auto-downloadable tools (trivy, opengrep, checkov, duplo).

    Args:
        config: LucidShark configuration.
        project_root: Project root directory.
        enabled_domains: Optional list of domains to validate. If None,
            validates all configured domains.

    Returns:
        ToolValidationResult with success status and any errors.
    """
    errors: List[ToolValidationError] = []

    # Domain configurations and their tool lists
    domain_configs = [
        ("linting", config.pipeline.linting),
        ("type_checking", config.pipeline.type_checking),
        ("testing", config.pipeline.testing),
        ("coverage", config.pipeline.coverage),
        ("duplication", config.pipeline.duplication),
        ("formatting", config.pipeline.formatting),
    ]

    for domain_name, domain_config in domain_configs:
        # Skip if domain filtering is active and this domain isn't included
        if enabled_domains is not None and domain_name not in enabled_domains:
            continue

        # Skip if domain is not configured or not enabled
        if domain_config is None or not domain_config.enabled:
            continue

        # Skip if no tools explicitly configured
        if not domain_config.tools:
            continue

        # Validate each configured tool
        for tool_config in domain_config.tools:
            error = _validate_tool(tool_config.name, domain_name, project_root)
            if error:
                errors.append(error)

    return ToolValidationResult(
        success=len(errors) == 0,
        errors=errors,
    )


def format_validation_errors(errors: List[ToolValidationError]) -> str:
    """Format validation errors for display.

    Args:
        errors: List of validation errors.

    Returns:
        Formatted error message string.
    """
    lines = [
        "Error: Missing required tools",
        "",
        "The following tools are configured but not installed:",
        "",
    ]

    for error in errors:
        lines.append(f"  [{error.domain}] {error.tool_name}")
        if error.install_instruction:
            lines.append(f"    Install: {error.install_instruction}")
        lines.append("")

    lines.append("Please install the missing tools and try again.")
    lines.append("")
    lines.append("Note: Security tools (trivy, opengrep, checkov), duplo, pmd, checkstyle,")
    lines.append("and spotbugs are downloaded automatically - no manual installation required.")

    return "\n".join(lines)
