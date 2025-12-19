"""Pytest configuration and fixtures for integration tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lucidscan.scanners.trivy import TrivyScanner
from lucidscan.scanners.opengrep import OpenGrepScanner
from lucidscan.scanners.checkov import CheckovScanner
from lucidscan.bootstrap.paths import LucidscanPaths


def _ensure_trivy_downloaded() -> bool:
    """Ensure Trivy binary is downloaded. Returns True if available."""
    scanner = TrivyScanner()
    try:
        scanner.ensure_binary()
        return True
    except Exception:
        return False


def _ensure_opengrep_downloaded() -> bool:
    """Ensure OpenGrep binary is downloaded. Returns True if available."""
    scanner = OpenGrepScanner()
    try:
        scanner.ensure_binary()
        return True
    except Exception:
        return False


def _is_trivy_in_path() -> bool:
    """Check if trivy is in PATH."""
    return shutil.which("trivy") is not None


def _is_opengrep_in_path() -> bool:
    """Check if opengrep is in PATH."""
    return shutil.which("opengrep") is not None


def _ensure_checkov_installed() -> bool:
    """Ensure Checkov is installed. Returns True if available."""
    scanner = CheckovScanner()
    try:
        scanner.ensure_binary()
        return True
    except Exception:
        return False


def _is_checkov_in_path() -> bool:
    """Check if checkov is in PATH."""
    return shutil.which("checkov") is not None


def _is_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# Download scanners at module load time so skipif markers work correctly
_trivy_available = _ensure_trivy_downloaded() or _is_trivy_in_path()
_opengrep_available = _ensure_opengrep_downloaded() or _is_opengrep_in_path()
_checkov_available = _ensure_checkov_installed() or _is_checkov_in_path()
_docker_available = _is_docker_available()

# Pytest markers for conditional test execution
trivy_available = pytest.mark.skipif(
    not _trivy_available,
    reason="Trivy binary not available and could not be downloaded"
)

opengrep_available = pytest.mark.skipif(
    not _opengrep_available,
    reason="OpenGrep binary not available and could not be downloaded"
)

checkov_available = pytest.mark.skipif(
    not _checkov_available,
    reason="Checkov not available and could not be installed"
)

docker_available = pytest.mark.skipif(
    not _docker_available,
    reason="Docker not available or not running"
)


@pytest.fixture
def project_root() -> Path:
    """Return the lucidscan project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def trivy_scanner() -> TrivyScanner:
    """Return a TrivyScanner instance."""
    return TrivyScanner()


@pytest.fixture
def opengrep_scanner() -> OpenGrepScanner:
    """Return an OpenGrepScanner instance."""
    return OpenGrepScanner()


@pytest.fixture
def ensure_trivy_binary(trivy_scanner: TrivyScanner) -> Path:
    """Ensure Trivy binary is downloaded and return its path."""
    return trivy_scanner.ensure_binary()


@pytest.fixture
def ensure_opengrep_binary(opengrep_scanner: OpenGrepScanner) -> Path:
    """Ensure OpenGrep binary is downloaded and return its path."""
    return opengrep_scanner.ensure_binary()


@pytest.fixture
def checkov_scanner() -> CheckovScanner:
    """Return a CheckovScanner instance."""
    return CheckovScanner()


@pytest.fixture
def ensure_checkov_binary(checkov_scanner: CheckovScanner) -> Path:
    """Ensure Checkov is installed and return its binary path."""
    return checkov_scanner.ensure_binary()
