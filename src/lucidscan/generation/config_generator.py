"""Configuration file generator.

Generates lucidscan.yml configuration files based on detected project
characteristics and user choices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from lucidscan.detection import ProjectContext


@dataclass
class InitChoices:
    """User choices made during initialization."""

    # Linting
    linter: Optional[str] = None  # "ruff", "eslint", "biome", or None
    linter_config: Optional[str] = None  # Path to existing config or None

    # Type checking
    type_checker: Optional[str] = None  # "mypy", "pyright", "typescript", or None
    type_checker_strict: bool = False

    # Security
    security_enabled: bool = True
    security_tools: list[str] = field(default_factory=lambda: ["trivy", "opengrep"])

    # Testing
    test_runner: Optional[str] = None  # "pytest", "jest", or None
    coverage_enabled: bool = False
    coverage_threshold: int = 80

    # CI
    ci_platform: Optional[str] = None  # "github", "gitlab", "bitbucket", or None

    # Fail thresholds
    fail_on_linting: str = "error"  # "error", "warning", "none"
    fail_on_security: str = "high"  # "critical", "high", "medium", "low", "none"


class ConfigGenerator:
    """Generates lucidscan.yml configuration files."""

    def generate(
        self,
        context: ProjectContext,
        choices: InitChoices,
    ) -> str:
        """Generate lucidscan.yml content.

        Args:
            context: Detected project context.
            choices: User initialization choices.

        Returns:
            YAML string for lucidscan.yml.
        """
        config = self._build_config(context, choices)
        return self._to_yaml(config)

    def write(
        self,
        context: ProjectContext,
        choices: InitChoices,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Generate and write lucidscan.yml file.

        Args:
            context: Detected project context.
            choices: User initialization choices.
            output_path: Output file path (default: project_root/lucidscan.yml).

        Returns:
            Path to the written file.
        """
        if output_path is None:
            output_path = context.root / "lucidscan.yml"

        content = self.generate(context, choices)
        output_path.write_text(content)
        return output_path

    def _build_config(
        self,
        context: ProjectContext,
        choices: InitChoices,
    ) -> dict:
        """Build configuration dictionary.

        Args:
            context: Detected project context.
            choices: User initialization choices.

        Returns:
            Configuration dictionary.
        """
        config = {
            "version": 1,
            "project": self._build_project_section(context),
        }

        # Add pipeline section
        pipeline = {}

        # Linting
        if choices.linter:
            pipeline["linting"] = self._build_linting_section(choices)

        # Type checking
        if choices.type_checker:
            pipeline["type_checking"] = self._build_type_checking_section(choices)

        # Security
        if choices.security_enabled and choices.security_tools:
            pipeline["security"] = self._build_security_section(choices)

        # Testing
        if choices.test_runner:
            pipeline["testing"] = self._build_testing_section(choices)

        # Coverage
        if choices.coverage_enabled:
            pipeline["coverage"] = self._build_coverage_section(choices)

        if pipeline:
            config["pipeline"] = pipeline

        # Fail thresholds
        config["fail_on"] = self._build_fail_on_section(choices)

        # Ignore patterns
        config["ignore"] = self._build_ignore_patterns(context)

        return config

    def _build_project_section(self, context: ProjectContext) -> dict:
        """Build project section."""
        languages = [lang.name for lang in context.languages]
        return {
            "name": context.root.name,
            "languages": languages,
        }

    def _build_linting_section(self, choices: InitChoices) -> dict:
        """Build linting pipeline section."""
        tools: list[dict] = []
        section = {
            "enabled": True,
            "tools": tools,
        }

        tool: dict = {"name": choices.linter}
        if choices.linter_config:
            tool["config"] = choices.linter_config

        tools.append(tool)
        return section

    def _build_type_checking_section(self, choices: InitChoices) -> dict:
        """Build type checking pipeline section."""
        tools: list[dict] = []
        section = {
            "enabled": True,
            "tools": tools,
        }

        tool: dict = {"name": choices.type_checker}
        if choices.type_checker_strict:
            tool["strict"] = True

        tools.append(tool)
        return section

    def _build_security_section(self, choices: InitChoices) -> dict:
        """Build security pipeline section."""
        tools: list[dict] = []
        section = {
            "enabled": True,
            "tools": tools,
        }

        for tool_name in choices.security_tools:
            tool: dict = {"name": tool_name}

            # Add domains based on tool
            if tool_name == "trivy":
                tool["domains"] = ["sca"]
            elif tool_name == "opengrep":
                tool["domains"] = ["sast"]
            elif tool_name == "checkov":
                tool["domains"] = ["iac"]

            tools.append(tool)

        return section

    def _build_testing_section(self, choices: InitChoices) -> dict:
        """Build testing pipeline section."""
        section = {
            "enabled": True,
            "tools": [{"name": choices.test_runner}],
        }
        return section

    def _build_coverage_section(self, choices: InitChoices) -> dict:
        """Build coverage pipeline section."""
        return {
            "enabled": True,
            "threshold": choices.coverage_threshold,
        }

    def _build_fail_on_section(self, choices: InitChoices) -> dict:
        """Build fail_on thresholds section."""
        return {
            "linting": choices.fail_on_linting,
            "type_checking": "error",
            "security": choices.fail_on_security,
            "testing": "any",
            "coverage": "below_threshold" if choices.coverage_enabled else "none",
        }

    def _build_ignore_patterns(self, context: ProjectContext) -> list:
        """Build ignore patterns list."""
        patterns = [
            "**/__pycache__/**",
            "**/node_modules/**",
            "**/.venv/**",
            "**/venv/**",
            "**/dist/**",
            "**/build/**",
            "**/.git/**",
        ]

        # Add language-specific patterns
        if context.has_python:
            patterns.extend([
                "**/*.egg-info/**",
                "**/.pytest_cache/**",
                "**/.mypy_cache/**",
                "**/.ruff_cache/**",
            ])

        if context.has_javascript:
            patterns.extend([
                "**/coverage/**",
                "**/.next/**",
                "**/.nuxt/**",
            ])

        return patterns

    def _to_yaml(self, config: dict) -> str:
        """Convert config dict to YAML string.

        Args:
            config: Configuration dictionary.

        Returns:
            YAML string.
        """
        # Add header comment
        header = "# LucidScan Configuration\n# Generated by lucidscan init\n\n"

        yaml_content = yaml.dump(
            config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

        return header + yaml_content
