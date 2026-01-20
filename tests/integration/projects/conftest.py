"""Pytest configuration and fixtures for project-based integration tests.

These tests run against realistic test projects with intentional issues.
Dependencies are auto-installed on first run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Re-export markers from parent conftest for convenient importing
from tests.integration.conftest import (
    trivy_available,
    opengrep_available,
    checkov_available,
    docker_available,
    ruff_available,
    biome_available,
    eslint_available,
    node_available,
    java_available,
    mypy_available,
    pyright_available,
    tsc_available,
    pytest_runner_available,
    jest_runner_available,
    coverage_py_available,
    nyc_available,
)

__all__ = [
    # Markers
    "trivy_available",
    "opengrep_available",
    "checkov_available",
    "docker_available",
    "ruff_available",
    "biome_available",
    "eslint_available",
    "node_available",
    "java_available",
    "mypy_available",
    "pyright_available",
    "tsc_available",
    "pytest_runner_available",
    "jest_runner_available",
    "coverage_py_available",
    "nyc_available",
    # Fixtures
    "python_project",
    "python_project_with_deps",
    "typescript_project",
    "typescript_project_with_deps",
    # Helpers
    "run_lucidscan",
    "ScanResult",
]


# =============================================================================
# Scan result helpers
# =============================================================================


@dataclass
class ScanResult:
    """Result of running lucidscan CLI against a project."""

    exit_code: int
    stdout: str
    stderr: str
    issues: list[dict]
    summary: dict

    @property
    def issue_count(self) -> int:
        """Return total number of issues found."""
        return len(self.issues)

    def issues_by_domain(self, domain: str) -> list[dict]:
        """Return issues filtered by domain."""
        return [i for i in self.issues if i.get("domain") == domain]

    def issues_by_rule(self, rule: str) -> list[dict]:
        """Return issues matching a rule pattern."""
        return [i for i in self.issues if rule in i.get("title", "")]

    def issues_by_severity(self, severity: str) -> list[dict]:
        """Return issues filtered by severity."""
        return [i for i in self.issues if i.get("severity") == severity]


def run_lucidscan(
    project_path: Path,
    domains: list[str] | None = None,
    extra_args: list[str] | None = None,
    timeout: int = 120,
) -> ScanResult:
    """Run lucidscan CLI against a project and return parsed results.

    Args:
        project_path: Path to the project to scan
        domains: List of domains to enable (e.g., ["linting", "type_checking"])
        extra_args: Additional CLI arguments
        timeout: Command timeout in seconds

    Returns:
        ScanResult with parsed output
    """
    import json

    # Find lucidscan in the same directory as the Python executable
    lucidscan_bin = Path(sys.executable).parent / "lucidscan"
    if not lucidscan_bin.exists():
        # Fall back to PATH
        lucidscan_bin = Path(shutil.which("lucidscan") or "lucidscan")

    cmd = [str(lucidscan_bin), "scan", "--format", "json"]

    if domains:
        for domain in domains:
            if domain == "linting":
                cmd.append("--linting")
            elif domain == "type_checking":
                cmd.append("--type-checking")
            elif domain == "sast":
                cmd.append("--sast")
            elif domain == "sca":
                cmd.append("--sca")
            elif domain == "iac":
                cmd.append("--iac")
            elif domain == "all":
                cmd.append("--all")

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(str(project_path))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=project_path,
    )

    # Parse JSON output
    issues = []
    summary = {}
    try:
        if result.stdout.strip():
            data = json.loads(result.stdout)
            issues = data.get("issues", [])
            summary = data.get("summary", {})
    except json.JSONDecodeError:
        pass

    return ScanResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        issues=issues,
        summary=summary,
    )


# =============================================================================
# Project paths
# =============================================================================

PROJECTS_DIR = Path(__file__).parent
PYTHON_PROJECT = PROJECTS_DIR / "python-webapp"
TYPESCRIPT_PROJECT = PROJECTS_DIR / "typescript-api"


# =============================================================================
# Python project setup
# =============================================================================


def _setup_python_venv(project_path: Path) -> Path:
    """Create venv and install dependencies for Python project.

    Returns the path to the venv.
    """
    venv_path = project_path / ".venv"

    if venv_path.exists():
        return venv_path

    print(f"\n[Setup] Creating Python venv at {venv_path}...")

    # Create venv
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_path)],
        check=True,
        capture_output=True,
    )

    # Determine pip path
    if sys.platform == "win32":
        pip = venv_path / "Scripts" / "pip"
    else:
        pip = venv_path / "bin" / "pip"

    # Upgrade pip
    subprocess.run(
        [str(pip), "install", "--upgrade", "pip"],
        capture_output=True,
        check=True,
    )

    # Install project dependencies (vulnerable deps for SCA testing)
    requirements = project_path / "requirements.txt"
    if requirements.exists():
        print(f"[Setup] Installing {requirements}...")
        subprocess.run(
            [str(pip), "install", "-r", str(requirements)],
            capture_output=True,
            check=True,
        )

    # Install dev dependencies (mypy, pytest, etc.)
    requirements_dev = project_path / "requirements-dev.txt"
    if requirements_dev.exists():
        print(f"[Setup] Installing {requirements_dev}...")
        subprocess.run(
            [str(pip), "install", "-r", str(requirements_dev)],
            capture_output=True,
            check=True,
        )

    print(f"[Setup] Python venv ready at {venv_path}")
    return venv_path


# =============================================================================
# TypeScript project setup
# =============================================================================


def _setup_node_modules(project_path: Path) -> Path:
    """Run npm install for TypeScript project.

    Returns the path to node_modules.
    """
    node_modules = project_path / "node_modules"

    if node_modules.exists():
        return node_modules

    # Check if npm is available
    if not shutil.which("npm"):
        pytest.skip("npm not available - cannot install TypeScript dependencies")

    print(f"\n[Setup] Running npm install in {project_path}...")

    result = subprocess.run(
        ["npm", "install"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print(f"[Setup] npm install failed: {result.stderr}")
        pytest.skip(f"npm install failed: {result.stderr[:200]}")

    print(f"[Setup] node_modules ready at {node_modules}")
    return node_modules


# =============================================================================
# Project fixtures
# =============================================================================


@pytest.fixture(scope="session")
def python_project() -> Path:
    """Return path to the Python test project (no deps installed)."""
    return PYTHON_PROJECT


@pytest.fixture(scope="session")
def python_project_with_deps(python_project: Path) -> Path:
    """Return Python project path after ensuring venv and dependencies are installed."""
    _setup_python_venv(python_project)
    return python_project


@pytest.fixture(scope="session")
def typescript_project() -> Path:
    """Return path to the TypeScript test project (no deps installed)."""
    return TYPESCRIPT_PROJECT


@pytest.fixture(scope="session")
def typescript_project_with_deps(typescript_project: Path) -> Path:
    """Return TypeScript project path after ensuring dependencies are installed."""
    _setup_node_modules(typescript_project)
    return typescript_project
