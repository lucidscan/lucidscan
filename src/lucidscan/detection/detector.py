"""Main codebase detector orchestrating all detection modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lucidscan.detection.languages import detect_languages, LanguageInfo
from lucidscan.detection.frameworks import detect_frameworks
from lucidscan.detection.tools import detect_tools, ToolConfig
from lucidscan.detection.ci import detect_ci_systems


@dataclass
class ProjectContext:
    """Detected project characteristics.

    This dataclass holds all information detected about a project,
    including languages, frameworks, existing tools, and CI systems.
    """

    root: Path
    """Project root directory."""

    languages: list[LanguageInfo] = field(default_factory=list)
    """Detected programming languages with metadata."""

    package_managers: list[str] = field(default_factory=list)
    """Detected package managers (pip, npm, cargo, etc.)."""

    frameworks: list[str] = field(default_factory=list)
    """Detected frameworks (fastapi, react, django, etc.)."""

    existing_tools: dict[str, ToolConfig] = field(default_factory=dict)
    """Existing tool configurations found in the project."""

    ci_systems: list[str] = field(default_factory=list)
    """Detected CI/CD systems (github_actions, gitlab_ci, etc.)."""

    test_frameworks: list[str] = field(default_factory=list)
    """Detected test frameworks (pytest, jest, etc.)."""

    @property
    def primary_language(self) -> Optional[str]:
        """Get the primary language (by file count).

        Returns:
            Primary language name or None if no languages detected.
        """
        if not self.languages:
            return None
        return max(self.languages, key=lambda lang: lang.file_count).name

    @property
    def has_python(self) -> bool:
        """Check if project has Python code."""
        return any(lang.name == "python" for lang in self.languages)

    @property
    def has_javascript(self) -> bool:
        """Check if project has JavaScript/TypeScript code."""
        return any(lang.name in ("javascript", "typescript") for lang in self.languages)

    @property
    def has_go(self) -> bool:
        """Check if project has Go code."""
        return any(lang.name == "go" for lang in self.languages)


class CodebaseDetector:
    """Orchestrates codebase detection.

    This class coordinates all detection modules to build a complete
    ProjectContext for a given project directory.
    """

    def detect(self, project_root: Path) -> ProjectContext:
        """Detect project characteristics.

        Args:
            project_root: Path to the project root directory.

        Returns:
            ProjectContext with detected information.
        """
        project_root = project_root.resolve()

        # Detect languages first as other detectors may use this info
        languages = detect_languages(project_root)

        # Extract package managers from language detection
        package_managers = self._extract_package_managers(languages, project_root)

        # Detect frameworks based on dependencies
        frameworks, test_frameworks = detect_frameworks(project_root)

        # Detect existing tool configurations
        existing_tools = detect_tools(project_root)

        # Detect CI systems
        ci_systems = detect_ci_systems(project_root)

        return ProjectContext(
            root=project_root,
            languages=languages,
            package_managers=package_managers,
            frameworks=frameworks,
            existing_tools=existing_tools,
            ci_systems=ci_systems,
            test_frameworks=test_frameworks,
        )

    def _extract_package_managers(
        self,
        languages: list[LanguageInfo],
        project_root: Path,
    ) -> list[str]:
        """Extract package managers from detected languages and files.

        Args:
            languages: Detected languages.
            project_root: Project root directory.

        Returns:
            List of detected package manager names.
        """
        managers = []

        # Python package managers
        if any(lang.name == "python" for lang in languages):
            if (project_root / "pyproject.toml").exists():
                managers.append("pip")
            elif (project_root / "requirements.txt").exists():
                managers.append("pip")
            elif (project_root / "Pipfile").exists():
                managers.append("pipenv")
            elif (project_root / "poetry.lock").exists():
                managers.append("poetry")

        # JavaScript/TypeScript package managers
        if any(lang.name in ("javascript", "typescript") for lang in languages):
            if (project_root / "package-lock.json").exists():
                managers.append("npm")
            elif (project_root / "yarn.lock").exists():
                managers.append("yarn")
            elif (project_root / "pnpm-lock.yaml").exists():
                managers.append("pnpm")
            elif (project_root / "package.json").exists():
                managers.append("npm")  # Default

        # Go
        if any(lang.name == "go" for lang in languages):
            if (project_root / "go.mod").exists():
                managers.append("go")

        # Rust
        if any(lang.name == "rust" for lang in languages):
            if (project_root / "Cargo.toml").exists():
                managers.append("cargo")

        return managers
