"""Package manager installer.

Adds development tools to package manager configuration files
(pyproject.toml, package.json).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from lucidscan.core.logging import get_logger
from lucidscan.detection import ProjectContext

LOGGER = get_logger(__name__)

# Tool to package mapping
PYTHON_PACKAGES: Dict[str, str] = {
    "ruff": "ruff>=0.8.0",
    "mypy": "mypy>=1.0",
    "pyright": "pyright>=1.1",
    "pytest": "pytest>=7.0",
    "pytest-cov": "pytest-cov>=4.0",
}

JAVASCRIPT_PACKAGES: Dict[str, str] = {
    "eslint": "eslint@^9.0.0",
    "biome": "@biomejs/biome@^1.0.0",
    "typescript": "typescript@^5.0.0",
    "jest": "jest@^29.0.0",
    "vitest": "vitest@^2.0.0",
}


class PackageInstaller:
    """Adds tools to package manager configuration files."""

    def install_tools(
        self,
        context: ProjectContext,
        tools: List[str],
    ) -> Dict[str, Path]:
        """Install tools to appropriate package files.

        Args:
            context: Detected project context.
            tools: List of tool names to install.

        Returns:
            Dict mapping tool name to the file it was added to.
        """
        installed: Dict[str, Path] = {}

        # Separate tools by language
        python_tools = [t for t in tools if t in PYTHON_PACKAGES]
        js_tools = [t for t in tools if t in JAVASCRIPT_PACKAGES]

        # Install Python tools
        if python_tools and context.has_python:
            pyproject = context.root / "pyproject.toml"
            requirements = context.root / "requirements-dev.txt"

            if pyproject.exists():
                added = self._add_to_pyproject(pyproject, python_tools)
                for tool in added:
                    installed[tool] = pyproject
            elif requirements.exists():
                added = self._add_to_requirements(requirements, python_tools)
                for tool in added:
                    installed[tool] = requirements
            else:
                # Create pyproject.toml if no package file exists
                added = self._create_pyproject(context.root, python_tools)
                for tool in added:
                    installed[tool] = context.root / "pyproject.toml"

        # Install JavaScript tools
        if js_tools and context.has_javascript:
            package_json = context.root / "package.json"

            if package_json.exists():
                added = self._add_to_package_json(package_json, js_tools)
                for tool in added:
                    installed[tool] = package_json
            else:
                # Create package.json if it doesn't exist
                added = self._create_package_json(context.root, js_tools)
                for tool in added:
                    installed[tool] = context.root / "package.json"

        return installed

    def _add_to_pyproject(
        self,
        pyproject_path: Path,
        tools: List[str],
    ) -> List[str]:
        """Add tools to pyproject.toml dev dependencies.

        Args:
            pyproject_path: Path to pyproject.toml.
            tools: Tools to add.

        Returns:
            List of tools that were added.
        """
        content = pyproject_path.read_text()
        added = []

        # Check which tools are already present
        packages_to_add = []
        for tool in tools:
            package = PYTHON_PACKAGES.get(tool)
            if package:
                # Check if already in file (simple check)
                tool_name = package.split(">=")[0].split("[")[0]
                if tool_name not in content:
                    packages_to_add.append(package)
                    added.append(tool)

        if not packages_to_add:
            return added

        # Check if [project.optional-dependencies] exists
        if "[project.optional-dependencies]" in content:
            # Check if dev section exists
            if re.search(r'\[project\.optional-dependencies\].*?dev\s*=', content, re.DOTALL):
                # Add to existing dev list
                content = self._append_to_dev_deps(content, packages_to_add)
            else:
                # Add dev section after [project.optional-dependencies]
                dev_section = f'\ndev = [\n  {self._format_deps(packages_to_add)}\n]'
                content = content.replace(
                    "[project.optional-dependencies]",
                    f"[project.optional-dependencies]{dev_section}"
                )
        elif "[project]" in content:
            # Add optional-dependencies section
            deps_section = f'\n[project.optional-dependencies]\ndev = [\n  {self._format_deps(packages_to_add)}\n]\n'
            # Find a good place to insert (after dependencies if exists, or at end)
            if "dependencies = [" in content:
                # Find end of dependencies section
                match = re.search(r'dependencies\s*=\s*\[.*?\]', content, re.DOTALL)
                if match:
                    insert_pos = match.end()
                    content = content[:insert_pos] + deps_section + content[insert_pos:]
            else:
                # Add at end of [project] section
                content += deps_section
        else:
            # No project section, add one
            content += f'\n[project.optional-dependencies]\ndev = [\n  {self._format_deps(packages_to_add)}\n]\n'

        pyproject_path.write_text(content)
        LOGGER.info(f"Added {len(added)} tools to {pyproject_path}")
        return added

    def _append_to_dev_deps(self, content: str, packages: List[str]) -> str:
        """Append packages to existing dev dependencies list."""
        # Find the dev = [...] section and append
        pattern = r'(dev\s*=\s*\[)(.*?)(\])'

        def replacer(match):
            existing = match.group(2).strip()
            if existing and not existing.endswith(","):
                existing += ","
            new_deps = self._format_deps(packages)
            return f'{match.group(1)}{existing}\n  {new_deps}\n{match.group(3)}'

        return re.sub(pattern, replacer, content, flags=re.DOTALL)

    def _format_deps(self, packages: List[str]) -> str:
        """Format packages as TOML array items."""
        return ",\n  ".join(f'"{pkg}"' for pkg in packages)

    def _add_to_requirements(
        self,
        requirements_path: Path,
        tools: List[str],
    ) -> List[str]:
        """Add tools to requirements-dev.txt.

        Args:
            requirements_path: Path to requirements file.
            tools: Tools to add.

        Returns:
            List of tools that were added.
        """
        content = requirements_path.read_text()
        added = []

        for tool in tools:
            package = PYTHON_PACKAGES.get(tool)
            if package:
                tool_name = package.split(">=")[0]
                if tool_name not in content:
                    content += f"\n{package}"
                    added.append(tool)

        if added:
            requirements_path.write_text(content.strip() + "\n")
            LOGGER.info(f"Added {len(added)} tools to {requirements_path}")

        return added

    def _create_pyproject(
        self,
        project_root: Path,
        tools: List[str],
    ) -> List[str]:
        """Create pyproject.toml with dev dependencies.

        Args:
            project_root: Project root directory.
            tools: Tools to add.

        Returns:
            List of tools that were added.
        """
        packages = [PYTHON_PACKAGES[t] for t in tools if t in PYTHON_PACKAGES]

        content = f'''[project]
name = "{project_root.name}"
version = "0.3.0"
requires-python = ">=3.10"

[project.optional-dependencies]
dev = [
  {self._format_deps(packages)}
]

[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"
'''

        pyproject_path = project_root / "pyproject.toml"
        pyproject_path.write_text(content)
        LOGGER.info(f"Created {pyproject_path}")
        return tools

    def _add_to_package_json(
        self,
        package_json_path: Path,
        tools: List[str],
    ) -> List[str]:
        """Add tools to package.json devDependencies.

        Args:
            package_json_path: Path to package.json.
            tools: Tools to add.

        Returns:
            List of tools that were added.
        """
        content = package_json_path.read_text()
        data = json.loads(content)
        added = []

        if "devDependencies" not in data:
            data["devDependencies"] = {}

        for tool in tools:
            package = JAVASCRIPT_PACKAGES.get(tool)
            if package:
                # Parse package name and version
                if "@" in package and not package.startswith("@"):
                    name, version = package.rsplit("@", 1)
                elif package.startswith("@"):
                    # Scoped package like @biomejs/biome@^1.0.0
                    parts = package.split("@")
                    name = f"@{parts[1]}"
                    version = parts[2] if len(parts) > 2 else "latest"
                else:
                    name = package
                    version = "latest"

                if name not in data["devDependencies"]:
                    data["devDependencies"][name] = version
                    added.append(tool)

        if added:
            package_json_path.write_text(
                json.dumps(data, indent=2) + "\n"
            )
            LOGGER.info(f"Added {len(added)} tools to {package_json_path}")

        return added

    def _create_package_json(
        self,
        project_root: Path,
        tools: List[str],
    ) -> List[str]:
        """Create package.json with devDependencies.

        Args:
            project_root: Project root directory.
            tools: Tools to add.

        Returns:
            List of tools that were added.
        """
        data = {
            "name": project_root.name,
            "version": "1.0.0",
            "devDependencies": {},
        }

        for tool in tools:
            package = JAVASCRIPT_PACKAGES.get(tool)
            if package:
                if "@" in package and not package.startswith("@"):
                    name, version = package.rsplit("@", 1)
                elif package.startswith("@"):
                    parts = package.split("@")
                    name = f"@{parts[1]}"
                    version = parts[2] if len(parts) > 2 else "latest"
                else:
                    name = package
                    version = "latest"
                data["devDependencies"][name] = version  # type: ignore[index]

        package_json_path = project_root / "package.json"
        package_json_path.write_text(json.dumps(data, indent=2) + "\n")
        LOGGER.info(f"Created {package_json_path}")
        return tools
