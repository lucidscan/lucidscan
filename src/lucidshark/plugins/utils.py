"""Shared utilities for plugins.

Common helper functions to reduce code duplication across plugins.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from lucidshark.core.models import Severity, ToolDomain, UnifiedIssue
from lucidshark.core.paths import resolve_node_bin

# Import tomllib (Python 3.11+) or tomli (Python 3.10)
try:
    if sys.version_info >= (3, 11):
        import tomllib

        _tomllib: Any = tomllib
    else:
        import tomli  # type: ignore[import-untyped]

        _tomllib = tomli
except ImportError:
    _tomllib = None


def get_cli_version(
    binary: Path,
    version_flag: str = "--version",
    parser: Optional[Callable[[str], str]] = None,
    timeout: int = 30,
) -> str:
    """Get version from a CLI tool.

    Args:
        binary: Path to the binary.
        version_flag: Flag to get version (default: --version).
        parser: Optional function to parse version from output.
                If None, returns stripped stdout.
        timeout: Command timeout in seconds.

    Returns:
        Version string or 'unknown' if unable to determine.
    """
    try:
        result = subprocess.run(
            [str(binary), version_flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if parser:
                parsed = parser(output)
                # Return "unknown" if parser returns empty/falsy result
                return parsed if parsed else "unknown"
            return output if output else "unknown"
    except Exception:
        pass
    return "unknown"


def ensure_node_binary(
    project_root: Optional[Path],
    binary_name: str,
    install_instructions: str,
) -> Path:
    """Ensure a Node.js binary is available.

    Checks for the binary in:
    1. Project's node_modules/.bin/
    2. System PATH (globally installed)

    Args:
        project_root: Optional project root for local installation.
        binary_name: Name of the binary (e.g., 'eslint', 'nyc').
        install_instructions: Instructions to show if not installed.

    Returns:
        Path to the binary.

    Raises:
        FileNotFoundError: If the binary is not installed.
    """
    # Check project node_modules first
    if project_root:
        node_binary = resolve_node_bin(project_root, binary_name)
        if node_binary:
            return node_binary

    # Check system PATH
    system_binary = shutil.which(binary_name)
    if system_binary:
        return Path(system_binary)

    raise FileNotFoundError(install_instructions)


def ensure_python_binary(
    project_root: Optional[Path],
    binary_name: str,
    install_instructions: str,
) -> Path:
    """Ensure a Python binary is available.

    Checks for the binary in:
    1. Project's .venv/bin/
    2. System PATH

    Args:
        project_root: Optional project root for venv.
        binary_name: Name of the binary (e.g., 'pytest', 'mypy').
        install_instructions: Instructions to show if not installed.

    Returns:
        Path to the binary.

    Raises:
        FileNotFoundError: If the binary is not installed.
    """
    # Check project venv first
    if project_root:
        venv_binary = project_root / ".venv" / "bin" / binary_name
        if venv_binary.exists():
            return venv_binary

    # Check system PATH
    system_binary = shutil.which(binary_name)
    if system_binary:
        return Path(system_binary)

    raise FileNotFoundError(install_instructions)


def resolve_src_paths(
    context_paths: Optional[List[Path]],
    project_root: Path,
    default_subdir: str = "src",
) -> List[str]:
    """Resolve target paths with fallback to src directory.

    Args:
        context_paths: Explicit paths from context, or None.
        project_root: Project root directory.
        default_subdir: Default subdirectory to check (default: 'src').

    Returns:
        List of path strings to scan.
    """
    if context_paths:
        return [p.as_posix() for p in context_paths]

    src_dir = project_root / default_subdir
    if src_dir.exists():
        return [src_dir.as_posix()]

    return ["."]


def find_java_build_tool(project_root: Path) -> Tuple[Path, str]:
    """Find Java build tool (Gradle or Maven).

    Checks for build tools in order of preference:
    1. Gradle wrapper (gradlew)
    2. Maven wrapper (mvnw)
    3. System Gradle (if build.gradle exists)
    4. System Maven (if pom.xml exists)

    Args:
        project_root: Project root directory.

    Returns:
        Tuple of (binary_path, build_system_name).

    Raises:
        FileNotFoundError: If no build system is found.
    """
    # Check for Gradle wrapper first (preferred)
    gradlew = project_root / "gradlew"
    if gradlew.exists():
        return gradlew, "gradle"

    # Check for Maven wrapper
    mvnw = project_root / "mvnw"
    if mvnw.exists():
        return mvnw, "maven"

    # Check for build.gradle (Gradle project)
    if (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists():
        gradle_path = shutil.which("gradle")
        if gradle_path:
            return Path(gradle_path), "gradle"

    # Check for pom.xml (Maven project)
    if (project_root / "pom.xml").exists():
        mvn_path = shutil.which("mvn")
        if mvn_path:
            return Path(mvn_path), "maven"

    raise FileNotFoundError(
        "No build system found. Ensure pom.xml (Maven) or build.gradle (Gradle) exists."
    )


def detect_source_directory(project_root: Path) -> Optional[str]:
    """Detect the Python source directory for coverage measurement.

    Checks (in order):
    1. ``src/<package>/`` layout (with ``__init__.py``)
    2. Flat ``<project_name>/`` layout at project root
    3. ``[tool.setuptools.packages.find] where = [...]`` in pyproject.toml

    Args:
        project_root: Project root directory.

    Returns:
        Source directory path relative to project root, or None if it
        cannot be determined.
    """
    # Check common src/ layout
    src_dir = project_root / "src"
    if src_dir.exists() and src_dir.is_dir():
        # Look for a package inside src/
        for child in src_dir.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                return str(child.relative_to(project_root))
        # Fallback to src/ itself
        return "src"

    # Check for package at root level (same name as project directory)
    project_name = project_root.name.replace("-", "_")
    package_dir = project_root / project_name
    if package_dir.exists() and (package_dir / "__init__.py").exists():
        return project_name

    # Check pyproject.toml for package configuration
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists() and _tomllib is not None:
        try:
            with open(pyproject, "rb") as f:
                data = _tomllib.load(f)
            # Check [tool.setuptools.packages.find] where = [...]
            packages = (
                data.get("tool", {}).get("setuptools", {}).get("packages", {})
            )
            if isinstance(packages, dict):
                # Handle nested: [tool.setuptools.packages.find] where = [...]
                find = packages.get("find", {})
                if isinstance(find, dict) and "where" in find:
                    where = find["where"]
                    if isinstance(where, list) and where:
                        return where[0]
                # Handle flat: [tool.setuptools.packages] where = [...]
                if "where" in packages:
                    where = packages["where"]
                    if isinstance(where, list) and where:
                        return where[0]
        except Exception:
            pass

    return None


def coverage_has_source_config(project_root: Path) -> bool:
    """Check whether the project already configures coverage source directories.

    Looks for ``source`` in ``[tool.coverage.run]`` inside pyproject.toml,
    or in a ``.coveragerc`` / ``setup.cfg`` ``[coverage:run]`` section.

    Args:
        project_root: Project root directory.

    Returns:
        True if an explicit source configuration was found.
    """
    # Check pyproject.toml [tool.coverage.run] source
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists() and _tomllib is not None:
        try:
            with open(pyproject, "rb") as f:
                data = _tomllib.load(f)
            source = (
                data.get("tool", {})
                .get("coverage", {})
                .get("run", {})
                .get("source")
            )
            if source:
                return True
        except Exception:
            pass

    # Check .coveragerc
    coveragerc = project_root / ".coveragerc"
    if coveragerc.exists():
        try:
            import configparser

            cfg = configparser.ConfigParser()
            cfg.read(str(coveragerc))
            if cfg.has_option("run", "source"):
                return True
        except Exception:
            pass

    # Check setup.cfg [coverage:run]
    setup_cfg = project_root / "setup.cfg"
    if setup_cfg.exists():
        try:
            import configparser

            cfg = configparser.ConfigParser()
            cfg.read(str(setup_cfg))
            if cfg.has_option("coverage:run", "source"):
                return True
        except Exception:
            pass

    return False


def create_coverage_threshold_issue(
    source_tool: str,
    percentage: float,
    threshold: float,
    total_lines: int,
    covered_lines: int,
    missing_lines: int,
) -> UnifiedIssue:
    """Create a UnifiedIssue for coverage below threshold.

    Args:
        source_tool: Name of the coverage tool (e.g., 'jacoco', 'coverage.py').
        percentage: Actual coverage percentage.
        threshold: Required coverage threshold.
        total_lines: Total number of lines.
        covered_lines: Number of covered lines.
        missing_lines: Number of uncovered lines.

    Returns:
        UnifiedIssue for coverage failure.
    """
    # Determine severity based on how far below threshold
    if percentage < 50:
        severity = Severity.HIGH
    elif percentage < threshold - 10:
        severity = Severity.MEDIUM
    else:
        severity = Severity.LOW

    gap = threshold - percentage

    # Generate deterministic ID
    content = f"{source_tool}:coverage:{percentage:.2f}:{threshold:.2f}"
    hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
    issue_id = f"{source_tool}-coverage-{hash_val}"

    return UnifiedIssue(
        id=issue_id,
        domain=ToolDomain.COVERAGE,
        source_tool=source_tool,
        severity=severity,
        rule_id="coverage_below_threshold",
        title=f"Coverage {percentage:.1f}% is below threshold {threshold}%",
        description=(
            f"Project coverage is {percentage:.1f}%, which is {gap:.1f}% below "
            f"the required threshold of {threshold}%. "
            f"{missing_lines} lines are not covered."
        ),
        recommendation=f"Add tests to cover at least {gap:.1f}% more of the codebase.",
        file_path=None,  # Project-level issue
        line_start=None,
        line_end=None,
        fixable=False,
        metadata={
            "coverage_percentage": round(percentage, 2),
            "threshold": threshold,
            "total_lines": total_lines,
            "covered_lines": covered_lines,
            "missing_lines": missing_lines,
            "gap_percentage": round(gap, 2),
        },
    )
