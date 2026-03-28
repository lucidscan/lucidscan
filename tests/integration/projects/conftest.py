"""Pytest configuration and fixtures for project-based integration tests.

These tests run against realistic test projects with intentional issues.
Dependencies are auto-installed on first run.
"""

from __future__ import annotations

import os
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
    spotbugs_available,
    maven_available,
    cargo_available,
    clippy_available,
    tarpaulin_available,
    swift_available,
    swiftlint_available,
    swiftformat_available,
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
    "spotbugs_available",
    "maven_available",
    "cargo_available",
    "clippy_available",
    "tarpaulin_available",
    "swift_available",
    "swiftlint_available",
    "swiftformat_available",
    # Fixtures
    "python_project",
    "python_project_with_deps",
    "typescript_project",
    "typescript_project_with_deps",
    "java_project",
    "java_project_with_deps",
    "rust_project",
    "rust_project_compiled",
    "swift_project",
    "swift_project_compiled",
    # Helpers
    "run_lucidshark",
    "ScanResult",
]


# =============================================================================
# Scan result helpers
# =============================================================================


@dataclass
class ScanResult:
    """Result of running lucidshark CLI against a project."""

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


def run_lucidshark(
    project_path: Path,
    domains: list[str] | None = None,
    extra_args: list[str] | None = None,
    timeout: int = 300,
    all_files: bool = True,
) -> ScanResult:
    """Run lucidshark CLI against a project and return parsed results.

    Args:
        project_path: Path to the project to scan
        domains: List of domains to enable (e.g., ["linting", "type_checking"])
        extra_args: Additional CLI arguments
        timeout: Command timeout in seconds
        all_files: If True, scan all files (not just git-changed). Default True for tests.

    Returns:
        ScanResult with parsed output
    """
    import json

    # Find lucidshark: same dir as Python (venv Scripts/bin) or PATH, or run as module
    exe_dir = Path(sys.executable).parent
    lucidshark_bin = exe_dir / "lucidshark"
    if not lucidshark_bin.exists():
        which = shutil.which("lucidshark")
        if which:
            lucidshark_bin = Path(which)
        else:
            lucidshark_bin = None  # use python -m lucidshark

    if lucidshark_bin is not None:
        cmd = [str(lucidshark_bin), "scan", "--format", "json"]
    else:
        cmd = [sys.executable, "-m", "lucidshark", "scan", "--format", "json"]

    # By default, scan all files in integration tests (not just git-changed)
    if all_files:
        cmd.append("--all-files")

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
            elif domain == "testing":
                cmd.append("--testing")
            elif domain == "coverage":
                cmd.append("--coverage")
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
JAVA_PROJECT = PROJECTS_DIR / "java-webapp"
RUST_PROJECT = PROJECTS_DIR / "rust-cli"
SWIFT_PROJECT = PROJECTS_DIR / "swift-app"


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

    pip = venv_path / "bin" / "pip"

    # Upgrade pip (best-effort)
    subprocess.run(
        [str(pip), "install", "--upgrade", "pip"],
        capture_output=True,
        check=False,
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

    npm_bin = shutil.which("npm")
    if not npm_bin:
        pytest.skip("npm not found in PATH")

    result = subprocess.run(
        [npm_bin, "install"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "CI": "true"},  # Disable interactive prompts
    )

    if result.returncode != 0:
        print(f"[Setup] npm install failed: {result.stderr}")
        pytest.skip(f"npm install failed: {result.stderr[:200]}")

    print(f"[Setup] node_modules ready at {node_modules}")
    return node_modules


# =============================================================================
# Java project setup
# =============================================================================


def _setup_java_project(project_path: Path) -> Path:
    """Compile Java project with Maven.

    Returns the path to target/classes.
    """
    target_classes = project_path / "target" / "classes"

    if target_classes.exists():
        return target_classes

    # Check if Maven is available
    mvn = shutil.which("mvn")
    if not mvn:
        pytest.skip("Maven not available - cannot compile Java project")

    # Check if Java is available
    java = shutil.which("java")
    if not java:
        pytest.skip("Java not available - cannot compile Java project")

    print(f"\n[Setup] Running mvn compile in {project_path}...")

    result = subprocess.run(
        [mvn, "compile", "-q"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=120,
        shell=False,
    )

    if result.returncode != 0:
        print(f"[Setup] mvn compile failed: {result.stderr}")
        pytest.skip(f"Maven compile failed: {result.stderr[:200]}")

    print(f"[Setup] Java classes ready at {target_classes}")
    return target_classes


def _run_java_tests(project_path: Path) -> Path:
    """Run Java tests with Maven.

    Returns the path to target/surefire-reports.
    """
    surefire_reports = project_path / "target" / "surefire-reports"

    # Check if Maven is available
    mvn = shutil.which("mvn")
    if not mvn:
        pytest.skip("Maven not available - cannot run Java tests")

    print(f"\n[Setup] Running mvn test in {project_path}...")

    result = subprocess.run(
        [mvn, "test", "-q"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=180,
        shell=False,
    )

    # Tests might fail, but we still want the reports
    print(f"[Setup] Maven tests completed (exit code {result.returncode})")
    return surefire_reports


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


@pytest.fixture(scope="session")
def java_project() -> Path:
    """Return path to the Java test project (not compiled)."""
    return JAVA_PROJECT


@pytest.fixture(scope="session")
def java_project_with_deps(java_project: Path) -> Path:
    """Return Java project path after ensuring it's compiled with Maven."""
    _setup_java_project(java_project)
    return java_project


# =============================================================================
# Rust project setup
# =============================================================================


def _setup_rust_project(project_path: Path) -> Path:
    """Compile Rust project with cargo build.

    Returns the path to target/debug.
    """
    target_debug = project_path / "target" / "debug"

    if target_debug.exists():
        return target_debug

    # Check if cargo is available
    cargo = shutil.which("cargo")
    if not cargo:
        pytest.skip("cargo not available - cannot compile Rust project")

    print(f"\n[Setup] Running cargo build in {project_path}...")

    result = subprocess.run(
        [cargo, "build"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        print(f"[Setup] cargo build failed: {result.stderr}")
        pytest.skip(f"cargo build failed: {result.stderr[:200]}")

    print(f"[Setup] Rust project compiled at {target_debug}")
    return target_debug


@pytest.fixture(scope="session")
def rust_project() -> Path:
    """Return path to the Rust test project (not compiled)."""
    return RUST_PROJECT


@pytest.fixture(scope="session")
def rust_project_compiled(rust_project: Path) -> Path:
    """Return Rust project path after ensuring it's compiled with cargo."""
    _setup_rust_project(rust_project)
    return rust_project


# =============================================================================
# Swift project setup
# =============================================================================


def _setup_swift_project(project_path: Path) -> Path:
    """Compile Swift project with swift build.

    Returns the path to .build/debug.
    """
    build_debug = project_path / ".build" / "debug"

    if build_debug.exists():
        return build_debug

    # Check if swift is available
    swift = shutil.which("swift")
    if not swift:
        pytest.skip("swift not available - cannot compile Swift project")

    print(f"\n[Setup] Running swift build in {project_path}...")

    result = subprocess.run(
        [swift, "build"],
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        print(f"[Setup] swift build failed: {result.stderr}")
        pytest.skip(f"swift build failed: {result.stderr[:200]}")

    print(f"[Setup] Swift project compiled at {build_debug}")
    return build_debug


@pytest.fixture(scope="session")
def swift_project() -> Path:
    """Return path to the Swift test project (not compiled)."""
    return SWIFT_PROJECT


@pytest.fixture(scope="session")
def swift_project_compiled(swift_project: Path) -> Path:
    """Return Swift project path after ensuring it's compiled with swift."""
    _setup_swift_project(swift_project)
    return swift_project
