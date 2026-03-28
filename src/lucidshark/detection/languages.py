"""Language detection module.

Detects programming languages in a project by analyzing:
- File extensions
- Marker files (package.json, pyproject.toml, go.mod, etc.)
- Configuration files
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Directories to skip during detection
SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "env",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    "vendor",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    "htmlcov",
}

# File extension to language mapping
EXTENSION_MAP = {
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sc": "scala",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}

# Marker files that indicate a language
MARKER_FILES = {
    "python": [
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
    ],
    "javascript": ["package.json"],
    "typescript": ["tsconfig.json"],
    "go": ["go.mod"],
    "rust": ["Cargo.toml"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "scala": ["build.sbt"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
    "cpp": ["CMakeLists.txt"],
    "swift": ["Package.swift"],
}


@dataclass
class LanguageInfo:
    """Information about a detected language."""

    name: str
    """Language name (lowercase)."""

    version: Optional[str] = None
    """Detected version (if available)."""

    file_count: int = 0
    """Number of files with this language."""


def detect_languages(project_root: Path) -> list[LanguageInfo]:
    """Detect programming languages in a project.

    Args:
        project_root: Path to the project root directory.

    Returns:
        List of detected languages with metadata.
    """
    # Count files by extension
    extension_counts: dict[str, int] = {}

    for file_path in _walk_files(project_root):
        ext = file_path.suffix.lower()
        if ext in EXTENSION_MAP:
            lang = EXTENSION_MAP[ext]
            extension_counts[lang] = extension_counts.get(lang, 0) + 1

    # Check for marker files
    marker_languages = set()
    for lang, markers in MARKER_FILES.items():
        for marker in markers:
            if (project_root / marker).exists():
                marker_languages.add(lang)
                break

    # Combine results
    all_languages = set(extension_counts.keys()) | marker_languages

    # Build LanguageInfo objects
    results = []
    for lang in all_languages:
        info = LanguageInfo(
            name=lang,
            file_count=extension_counts.get(lang, 0),
            version=_detect_version(lang, project_root),
        )
        results.append(info)

    # Sort by file count (descending)
    results.sort(key=lambda x: x.file_count, reverse=True)

    return results


def _walk_files(root: Path, max_depth: int = 10) -> list[Path]:
    """Walk directory tree yielding files.

    Args:
        root: Root directory to walk.
        max_depth: Maximum recursion depth.

    Returns:
        List of file paths.
    """
    files = []

    def _walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return

        try:
            for item in path.iterdir():
                if item.is_dir():
                    if item.name not in SKIP_DIRS and not item.name.startswith("."):
                        _walk(item, depth + 1)
                elif item.is_file():
                    files.append(item)
        except PermissionError:
            pass

    _walk(root, 0)
    return files


def _detect_version(language: str, project_root: Path) -> Optional[str]:
    """Detect the version of a language from config files.

    Args:
        language: Language name.
        project_root: Project root directory.

    Returns:
        Version string or None.
    """
    if language == "python":
        return _detect_python_version(project_root)
    elif language == "typescript":
        return _detect_typescript_version(project_root)
    elif language == "go":
        return _detect_go_version(project_root)
    elif language == "rust":
        return _detect_rust_version(project_root)
    elif language == "java":
        return _detect_java_version(project_root)
    elif language == "scala":
        return _detect_scala_version(project_root)
    elif language == "swift":
        return _detect_swift_version(project_root)
    return None


def _detect_python_version(project_root: Path) -> Optional[str]:
    """Detect Python version from pyproject.toml or other files."""
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            # Look for requires-python
            match = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                version_spec = match.group(1)
                # Extract version number (e.g., ">=3.10" -> "3.10")
                version_match = re.search(r"(\d+\.\d+)", version_spec)
                if version_match:
                    return version_match.group(1)
        except Exception:
            pass

    # Check .python-version file
    python_version_file = project_root / ".python-version"
    if python_version_file.exists():
        try:
            version = python_version_file.read_text().strip()
            return (
                version.split(".")[0] + "." + version.split(".")[1]
                if "." in version
                else version
            )
        except Exception:
            pass

    return None


def _detect_typescript_version(project_root: Path) -> Optional[str]:
    """Detect TypeScript version from package.json."""
    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            import json

            data = json.loads(package_json.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "typescript" in deps:
                version = deps["typescript"]
                # Strip version prefix (^, ~, etc.)
                return re.sub(r"^[\^~>=<]+", "", version)
        except Exception:
            pass
    return None


def _detect_go_version(project_root: Path) -> Optional[str]:
    """Detect Go version from go.mod."""
    go_mod = project_root / "go.mod"
    if go_mod.exists():
        try:
            content = go_mod.read_text()
            match = re.search(r"^go\s+(\d+\.\d+)", content, re.MULTILINE)
            if match:
                return match.group(1)
        except Exception:
            pass
    return None


def _detect_rust_version(project_root: Path) -> Optional[str]:
    """Detect Rust edition from Cargo.toml."""
    cargo_toml = project_root / "Cargo.toml"
    if cargo_toml.exists():
        try:
            content = cargo_toml.read_text()
            match = re.search(r'edition\s*=\s*["\'](\d+)["\']', content)
            if match:
                return match.group(1)
        except Exception:
            pass
    return None


def _detect_java_version(project_root: Path) -> Optional[str]:
    """Detect Java version from pom.xml or build.gradle."""
    # Check pom.xml (Maven)
    pom_xml = project_root / "pom.xml"
    if pom_xml.exists():
        try:
            content = pom_xml.read_text()
            # Look for maven.compiler.source or java.version property
            match = re.search(
                r"<(?:maven\.compiler\.source|java\.version)>(\d+)</",
                content,
            )
            if match:
                return match.group(1)
            # Look for release property
            match = re.search(r"<release>(\d+)</release>", content)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Check build.gradle (Gradle)
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle_path = project_root / gradle_file
        if gradle_path.exists():
            try:
                content = gradle_path.read_text()
                # Look for sourceCompatibility or targetCompatibility
                match = re.search(
                    r"(?:source|target)Compatibility\s*=\s*['\"]?(?:JavaVersion\.VERSION_)?(\d+)",
                    content,
                )
                if match:
                    return match.group(1)
                # Look for toolchain languageVersion
                match = re.search(
                    r"languageVersion\.set\s*\(\s*JavaLanguageVersion\.of\s*\(\s*(\d+)\s*\)",
                    content,
                )
                if match:
                    return match.group(1)
            except Exception:
                pass

    # Check .java-version file
    java_version_file = project_root / ".java-version"
    if java_version_file.exists():
        try:
            version = java_version_file.read_text().strip()
            # Extract major version (e.g., "17.0.2" -> "17")
            match = re.match(r"(\d+)", version)
            if match:
                return match.group(1)
        except Exception:
            pass

    return None


def _detect_scala_version(project_root: Path) -> Optional[str]:
    """Detect Scala version from build.sbt or other config files.

    Args:
        project_root: Project root directory.

    Returns:
        Version string or None.
    """
    # Check build.sbt
    build_sbt = project_root / "build.sbt"
    if build_sbt.exists():
        try:
            content = build_sbt.read_text()
            # Match patterns like: scalaVersion := "3.3.1"
            # or: ThisBuild / scalaVersion := "2.13.12"
            match = re.search(
                r'scalaVersion\s*:=\s*["\'](\d+\.\d+(?:\.\d+)?)["\']', content
            )
            if match:
                return match.group(1)
        except Exception:
            pass

    # Check .scala-version file
    scala_version_file = project_root / ".scala-version"
    if scala_version_file.exists():
        try:
            version = scala_version_file.read_text().strip()
            match = re.match(r"(\d+\.\d+(?:\.\d+)?)", version)
            if match:
                return match.group(1)
        except Exception:
            pass

    return None


def _detect_swift_version(project_root: Path) -> Optional[str]:
    """Detect Swift tools version from Package.swift.

    Package.swift starts with a comment like:
        // swift-tools-version: 5.9
    """
    package_swift = project_root / "Package.swift"
    if package_swift.exists():
        try:
            content = package_swift.read_text()
            match = re.search(r"swift-tools-version:\s*(\d+\.\d+)", content)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Check .swift-version file
    swift_version_file = project_root / ".swift-version"
    if swift_version_file.exists():
        try:
            version = swift_version_file.read_text().strip()
            match = re.match(r"(\d+\.\d+)", version)
            if match:
                return match.group(1)
        except Exception:
            pass

    return None
