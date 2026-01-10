"""Tool configuration detection module.

Detects existing tool configurations for:
- Linters (Ruff, ESLint, Biome, etc.)
- Type checkers (mypy, TypeScript, Pyright, etc.)
- Formatters (Black, Prettier, etc.)
- Security scanners (Trivy, etc.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ToolConfig:
    """Detected tool configuration."""

    tool: str
    """Tool name (e.g., 'ruff', 'eslint')."""

    config_file: Optional[Path] = None
    """Path to the configuration file."""

    config_location: Optional[str] = None
    """Location type: 'file', 'pyproject.toml', 'package.json'."""


# Tool detection definitions
# Format: tool_name -> (config_files, pyproject_section, package_json_key)
TOOL_CONFIGS: Dict[str, Dict[str, Any]] = {
    # Python linters
    "ruff": {
        "files": ["ruff.toml", ".ruff.toml"],
        "pyproject_section": "tool.ruff",
    },
    "flake8": {
        "files": [".flake8", "setup.cfg", "tox.ini"],
        "pyproject_section": None,  # flake8 doesn't use pyproject.toml natively
    },
    "pylint": {
        "files": [".pylintrc", "pylintrc"],
        "pyproject_section": "tool.pylint",
    },
    "black": {
        "files": [".black.toml"],
        "pyproject_section": "tool.black",
    },
    "isort": {
        "files": [".isort.cfg"],
        "pyproject_section": "tool.isort",
    },

    # Python type checkers
    "mypy": {
        "files": ["mypy.ini", ".mypy.ini"],
        "pyproject_section": "tool.mypy",
    },
    "pyright": {
        "files": ["pyrightconfig.json"],
        "pyproject_section": "tool.pyright",
    },

    # Python test tools
    "pytest": {
        "files": ["pytest.ini", "setup.cfg"],
        "pyproject_section": "tool.pytest",
    },
    "coverage": {
        "files": [".coveragerc"],
        "pyproject_section": "tool.coverage",
    },

    # JavaScript/TypeScript linters
    "eslint": {
        "files": [
            ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.mjs",
            ".eslintrc.json", ".eslintrc.yaml", ".eslintrc.yml",
            "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
        ],
        "package_json_key": "eslintConfig",
    },
    "biome": {
        "files": ["biome.json", "biome.jsonc"],
    },
    "prettier": {
        "files": [
            ".prettierrc", ".prettierrc.json", ".prettierrc.yaml",
            ".prettierrc.yml", ".prettierrc.js", ".prettierrc.cjs",
            "prettier.config.js", "prettier.config.cjs",
        ],
        "package_json_key": "prettier",
    },

    # TypeScript
    "typescript": {
        "files": ["tsconfig.json"],
    },

    # Security scanners
    "trivy": {
        "files": [".trivy.yaml", "trivy.yaml"],
    },
    "semgrep": {
        "files": [".semgrep.yaml", ".semgrep.yml", "semgrep.yaml"],
    },
    "checkov": {
        "files": [".checkov.yaml", ".checkov.yml"],
    },

    # Other
    "pre-commit": {
        "files": [".pre-commit-config.yaml"],
    },
}


def detect_tools(project_root: Path) -> dict[str, ToolConfig]:
    """Detect existing tool configurations in a project.

    Args:
        project_root: Path to the project root directory.

    Returns:
        Dictionary mapping tool names to their configurations.
    """
    detected = {}

    # Load pyproject.toml if it exists
    pyproject_content = None
    pyproject_path = project_root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            pyproject_content = pyproject_path.read_text()
        except Exception:
            pass

    # Load package.json if it exists
    package_json_content = None
    package_json_path = project_root / "package.json"
    if package_json_path.exists():
        try:
            import json
            package_json_content = json.loads(package_json_path.read_text())
        except Exception:
            pass

    # Check each tool
    for tool_name, config in TOOL_CONFIGS.items():
        result = _check_tool(
            tool_name,
            config,
            project_root,
            pyproject_content,
            package_json_content,
        )
        if result:
            detected[tool_name] = result

    return detected


def _check_tool(
    tool_name: str,
    config: dict,
    project_root: Path,
    pyproject_content: Optional[str],
    package_json_content: Optional[dict],
) -> Optional[ToolConfig]:
    """Check if a specific tool is configured.

    Args:
        tool_name: Name of the tool.
        config: Tool configuration definition.
        project_root: Project root directory.
        pyproject_content: Content of pyproject.toml (if exists).
        package_json_content: Parsed package.json (if exists).

    Returns:
        ToolConfig if found, None otherwise.
    """
    # Check for standalone config files
    for config_file in config.get("files", []):
        file_path = project_root / config_file
        if file_path.exists():
            return ToolConfig(
                tool=tool_name,
                config_file=file_path,
                config_location="file",
            )

    # Check pyproject.toml section
    pyproject_section = config.get("pyproject_section")
    if pyproject_section and pyproject_content:
        # Convert section to regex pattern (e.g., "tool.ruff" -> [tool.ruff])
        section_pattern = pyproject_section.replace(".", r"\.")
        if re.search(rf"\[{section_pattern}(\.[^\]]+)?\]", pyproject_content):
            return ToolConfig(
                tool=tool_name,
                config_file=project_root / "pyproject.toml",
                config_location="pyproject.toml",
            )

    # Check package.json key
    package_key = config.get("package_json_key")
    if package_key and package_json_content:
        if package_key in package_json_content:
            return ToolConfig(
                tool=tool_name,
                config_file=project_root / "package.json",
                config_location="package.json",
            )

    return None
