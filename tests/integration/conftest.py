"""Pytest configuration and fixtures for integration tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lucidshark.plugins.scanners.trivy import TrivyScanner
from lucidshark.plugins.scanners.opengrep import OpenGrepScanner
from lucidshark.plugins.scanners.checkov import CheckovScanner
from lucidshark.plugins.linters.ruff import RuffLinter
from lucidshark.plugins.linters.biome import BiomeLinter
from lucidshark.plugins.linters.eslint import ESLintLinter
from lucidshark.plugins.linters.checkstyle import CheckstyleLinter
from lucidshark.plugins.linters.pmd import PmdLinter
from lucidshark.plugins.type_checkers.mypy import MypyChecker
from lucidshark.plugins.type_checkers.pyright import PyrightChecker
from lucidshark.plugins.type_checkers.typescript import TypeScriptChecker
from lucidshark.plugins.test_runners.pytest import PytestRunner
from lucidshark.plugins.test_runners.jest import JestRunner
from lucidshark.plugins.coverage.coverage_py import CoveragePyPlugin
from lucidshark.plugins.coverage.istanbul import IstanbulPlugin
from lucidshark.plugins.type_checkers.spotbugs import SpotBugsChecker
from lucidshark.plugins.type_checkers.cargo_check import CargoCheckChecker
from lucidshark.plugins.test_runners.maven import MavenTestRunner
from lucidshark.plugins.test_runners.cargo import CargoTestRunner
from lucidshark.plugins.coverage.jacoco import JaCoCoPlugin
from lucidshark.plugins.coverage.tarpaulin import TarpaulinPlugin
from lucidshark.plugins.linters.clippy import ClippyLinter


def _ensure_trivy_downloaded() -> bool:
    """Ensure Trivy binary is downloaded. Returns True if available."""
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    scanner = TrivyScanner(project_root=root)
    try:
        scanner.ensure_binary()
        return True
    except Exception:
        return False


def _ensure_opengrep_downloaded() -> bool:
    """Ensure OpenGrep binary is downloaded. Returns True if available."""
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    scanner = OpenGrepScanner(project_root=root)
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
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    scanner = CheckovScanner(project_root=root)
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
    reason="Trivy binary not available and could not be downloaded",
)

opengrep_available = pytest.mark.skipif(
    not _opengrep_available,
    reason="OpenGrep binary not available and could not be downloaded",
)

checkov_available = pytest.mark.skipif(
    not _checkov_available, reason="Checkov not available and could not be installed"
)

docker_available = pytest.mark.skipif(
    not _docker_available, reason="Docker not available or not running"
)


@pytest.fixture
def project_root() -> Path:
    """Return the lucidshark project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def trivy_scanner() -> TrivyScanner:
    """Return a TrivyScanner instance (session-scoped for performance)."""
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    return TrivyScanner(project_root=root)


@pytest.fixture(scope="session")
def opengrep_scanner() -> OpenGrepScanner:
    """Return an OpenGrepScanner instance (session-scoped for performance)."""
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    return OpenGrepScanner(project_root=root)


@pytest.fixture(scope="session")
def ensure_trivy_binary(trivy_scanner: TrivyScanner) -> Path:
    """Ensure Trivy binary is downloaded and return its path."""
    return trivy_scanner.ensure_binary()


@pytest.fixture(scope="session")
def ensure_opengrep_binary(opengrep_scanner: OpenGrepScanner) -> Path:
    """Ensure OpenGrep binary is downloaded and return its path."""
    return opengrep_scanner.ensure_binary()


@pytest.fixture(scope="session")
def checkov_scanner() -> CheckovScanner:
    """Return a CheckovScanner instance (session-scoped for performance)."""
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    return CheckovScanner(project_root=root)


@pytest.fixture(scope="session")
def ensure_checkov_binary(checkov_scanner: CheckovScanner) -> Path:
    """Ensure Checkov is installed and return its binary path."""
    return checkov_scanner.ensure_binary()


# =============================================================================
# Linter availability checks
# =============================================================================


def _ensure_ruff_downloaded() -> bool:
    """Ensure Ruff binary is downloaded. Returns True if available."""
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    try:
        linter = RuffLinter(project_root=root)
        linter.ensure_binary()
        return True
    except Exception:
        return False


def _ensure_biome_downloaded() -> bool:
    """Ensure Biome binary is downloaded. Returns True if available."""
    # Use explicit project_root for consistent path resolution across platforms
    root = Path(__file__).parent.parent.parent
    try:
        linter = BiomeLinter(project_root=root)
        linter.ensure_binary()
        return True
    except Exception:
        return False


def _is_node_available() -> bool:
    """Check if Node.js is available."""
    return shutil.which("node") is not None


def _is_java_available() -> bool:
    """Check if Java is available."""
    return shutil.which("java") is not None


def _is_maven_available() -> bool:
    """Check if Maven is available (mvn or mvnw)."""
    return shutil.which("mvn") is not None


def _ensure_spotbugs_downloaded() -> bool:
    """Ensure SpotBugs is downloaded. Returns True if available.

    SpotBugs is a managed tool - it is automatically downloaded from GitHub
    releases on first use.
    """
    root = Path(__file__).parent.parent.parent
    try:
        checker = SpotBugsChecker(project_root=root)
        checker.ensure_binary()
        return True
    except Exception:
        return False


def _ensure_pmd_downloaded() -> bool:
    """Ensure PMD binary is downloaded. Returns True if available."""
    root = Path(__file__).parent.parent.parent
    try:
        linter = PmdLinter(project_root=root)
        linter.ensure_binary()
        return True
    except Exception:
        return False


def _ensure_checkstyle_downloaded() -> bool:
    """Ensure Checkstyle JAR is downloaded. Returns True if available."""
    root = Path(__file__).parent.parent.parent
    try:
        linter = CheckstyleLinter(project_root=root)
        linter.ensure_binary()
        return True
    except Exception:
        return False


# =============================================================================
# Type checker availability checks
# =============================================================================


def _ensure_mypy_available() -> bool:
    """Try to find mypy via ensure_binary. Returns True if available."""
    try:
        # Get project root for venv detection
        project_root = Path(__file__).parent.parent.parent
        checker = MypyChecker(project_root=project_root)
        checker.ensure_binary()
        return True
    except Exception:
        return shutil.which("mypy") is not None


def _ensure_pyright_available() -> bool:
    """Try to find pyright via ensure_binary and verify it can run."""
    try:
        project_root = Path(__file__).parent.parent.parent
        checker = PyrightChecker(project_root=project_root)
        binary = checker.ensure_binary()
        # Verify pyright can actually execute (not just that the binary path exists)
        result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _ensure_tsc_available() -> bool:
    """Try to find TypeScript compiler via ensure_binary. Returns True if available."""
    try:
        project_root = Path(__file__).parent.parent.parent
        checker = TypeScriptChecker(project_root=project_root)
        checker.ensure_binary()
        return True
    except Exception:
        return shutil.which("tsc") is not None


def _ensure_eslint_available() -> bool:
    """Try to find ESLint via ensure_binary. Returns True if available."""
    try:
        project_root = Path(__file__).parent.parent.parent
        linter = ESLintLinter(project_root=project_root)
        linter.ensure_binary()
        return True
    except Exception:
        return shutil.which("eslint") is not None


# Download/check tools at module load time so skipif markers work correctly
_ruff_available = _ensure_ruff_downloaded() or shutil.which("ruff") is not None
_biome_available = _ensure_biome_downloaded() or shutil.which("biome") is not None
_eslint_available = _ensure_eslint_available()
_node_available = _is_node_available()
_java_available = _is_java_available()
_mypy_available = _ensure_mypy_available()
_pyright_available = _ensure_pyright_available()
_tsc_available = _ensure_tsc_available()
_spotbugs_available = _java_available and _ensure_spotbugs_downloaded()
_pmd_available = _java_available and _ensure_pmd_downloaded()
_checkstyle_available = _java_available and _ensure_checkstyle_downloaded()
_maven_available = _java_available and _is_maven_available()


def _is_cargo_available() -> bool:
    """Check if cargo is available."""
    return shutil.which("cargo") is not None


def _can_cargo_compile() -> bool:
    """Check if cargo can actually compile and link code.

    This verifies the Rust toolchain is properly configured,
    including any system dependencies like Xcode on macOS.
    Uses `cargo test --no-run` to verify linking works (required for tests).
    """
    if not _is_cargo_available():
        return False

    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create minimal Cargo.toml
            (tmpdir_path / "Cargo.toml").write_text(
                '[package]\nname = "test"\nversion = "0.1.0"\nedition = "2021"\n'
            )

            # Create minimal lib.rs with a test
            src_dir = tmpdir_path / "src"
            src_dir.mkdir()
            (src_dir / "lib.rs").write_text(
                "pub fn test() {}\n\n#[test]\nfn it_works() {}\n"
            )

            # Try to compile tests (--no-run compiles but doesn't run)
            # This triggers linking, which catches Xcode license issues on macOS
            result = subprocess.run(
                ["cargo", "test", "--no-run"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
    except Exception:
        return False


def _is_clippy_available(cargo_can_compile: bool) -> bool:
    """Check if clippy is available.

    Args:
        cargo_can_compile: Pre-computed flag indicating if cargo can compile.
    """
    if not cargo_can_compile:
        return False
    try:
        result = subprocess.run(
            ["cargo", "clippy", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def _is_tarpaulin_available(cargo_can_compile: bool) -> bool:
    """Check if cargo-tarpaulin is available.

    Args:
        cargo_can_compile: Pre-computed flag indicating if cargo can compile.
    """
    if not cargo_can_compile:
        return False
    try:
        result = subprocess.run(
            ["cargo", "tarpaulin", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


_cargo_available_flag = _is_cargo_available()
_cargo_can_compile_flag = _can_cargo_compile()
_clippy_available_flag = _is_clippy_available(_cargo_can_compile_flag)
_tarpaulin_available_flag = _is_tarpaulin_available(_cargo_can_compile_flag)


# Pytest markers for Rust tools
cargo_available = pytest.mark.skipif(
    not _cargo_can_compile_flag,
    reason="cargo not available or cannot compile (check Rust toolchain setup)",
)

clippy_available = pytest.mark.skipif(
    not _clippy_available_flag, reason="cargo clippy not available"
)

tarpaulin_available = pytest.mark.skipif(
    not _tarpaulin_available_flag, reason="cargo-tarpaulin not available"
)


# Pytest markers for linters
ruff_available = pytest.mark.skipif(
    not _ruff_available, reason="Ruff binary not available and could not be downloaded"
)

biome_available = pytest.mark.skipif(
    not _biome_available,
    reason="Biome binary not available and could not be downloaded",
)

eslint_available = pytest.mark.skipif(
    not _eslint_available, reason="ESLint not available"
)

node_available = pytest.mark.skipif(not _node_available, reason="Node.js not available")

java_available = pytest.mark.skipif(not _java_available, reason="Java not available")

spotbugs_available = pytest.mark.skipif(
    not _spotbugs_available, reason="SpotBugs not available (requires Java and download)"
)

pmd_available = pytest.mark.skipif(
    not _pmd_available, reason="PMD not available (requires Java and download)"
)

checkstyle_available = pytest.mark.skipif(
    not _checkstyle_available,
    reason="Checkstyle not available (requires Java and download)",
)

maven_available = pytest.mark.skipif(
    not _maven_available, reason="Maven not available (requires Java and mvn)"
)

# Pytest markers for type checkers
mypy_available = pytest.mark.skipif(not _mypy_available, reason="mypy not available")

pyright_available = pytest.mark.skipif(
    not _pyright_available, reason="pyright not available"
)

tsc_available = pytest.mark.skipif(
    not _tsc_available, reason="TypeScript compiler (tsc) not available"
)


# =============================================================================
# Linter fixtures
# =============================================================================


@pytest.fixture
def ruff_linter(project_root: Path) -> RuffLinter:
    """Return a RuffLinter instance."""
    return RuffLinter(project_root=project_root)


@pytest.fixture
def biome_linter(project_root: Path) -> BiomeLinter:
    """Return a BiomeLinter instance."""
    return BiomeLinter(project_root=project_root)


@pytest.fixture
def eslint_linter(project_root: Path) -> ESLintLinter:
    """Return an ESLintLinter instance with project root for node_modules detection."""
    return ESLintLinter(project_root=project_root)


@pytest.fixture
def checkstyle_linter(project_root: Path) -> CheckstyleLinter:
    """Return a CheckstyleLinter instance."""
    return CheckstyleLinter(project_root=project_root)


@pytest.fixture
def pmd_linter(project_root: Path) -> PmdLinter:
    """Return a PmdLinter instance."""
    return PmdLinter(project_root=project_root)


@pytest.fixture
def ensure_ruff_binary(ruff_linter: RuffLinter) -> Path:
    """Ensure Ruff binary is downloaded and return its path."""
    return ruff_linter.ensure_binary()


@pytest.fixture
def ensure_biome_binary(biome_linter: BiomeLinter) -> Path:
    """Ensure Biome binary is downloaded and return its path."""
    return biome_linter.ensure_binary()


# =============================================================================
# Type checker fixtures
# =============================================================================


@pytest.fixture
def mypy_checker(project_root: Path) -> MypyChecker:
    """Return a MypyChecker instance with project root for venv detection."""
    return MypyChecker(project_root=project_root)


@pytest.fixture
def pyright_checker(project_root: Path) -> PyrightChecker:
    """Return a PyrightChecker instance with project root for venv detection."""
    return PyrightChecker(project_root=project_root)


@pytest.fixture
def typescript_checker(project_root: Path) -> TypeScriptChecker:
    """Return a TypeScriptChecker instance with project root for node_modules detection."""
    return TypeScriptChecker(project_root=project_root)


# =============================================================================
# Test runner availability checks
# =============================================================================


def _ensure_pytest_available() -> bool:
    """Try to find pytest via ensure_binary. Returns True if available."""
    try:
        project_root = Path(__file__).parent.parent.parent
        runner = PytestRunner(project_root=project_root)
        runner.ensure_binary()
        return True
    except Exception:
        return shutil.which("pytest") is not None


def _ensure_jest_available() -> bool:
    """Try to find jest via ensure_binary. Returns True if available."""
    try:
        project_root = Path(__file__).parent.parent.parent
        runner = JestRunner(project_root=project_root)
        runner.ensure_binary()
        return True
    except Exception:
        return shutil.which("jest") is not None


def _ensure_coverage_py_available() -> bool:
    """Try to find coverage via ensure_binary. Returns True if available."""
    try:
        project_root = Path(__file__).parent.parent.parent
        plugin = CoveragePyPlugin(project_root=project_root)
        plugin.ensure_binary()
        return True
    except Exception:
        return shutil.which("coverage") is not None


def _ensure_nyc_available() -> bool:
    """Try to find nyc via ensure_binary. Returns True if available."""
    try:
        project_root = Path(__file__).parent.parent.parent
        plugin = IstanbulPlugin(project_root=project_root)
        plugin.ensure_binary()
        return True
    except Exception:
        return shutil.which("nyc") is not None


# Check tool availability at module load time
_pytest_runner_available = _ensure_pytest_available()
_jest_runner_available = _ensure_jest_available()
_coverage_py_available = _ensure_coverage_py_available()
_nyc_available = _ensure_nyc_available()


# Pytest markers for test runners
pytest_runner_available = pytest.mark.skipif(
    not _pytest_runner_available, reason="pytest not available"
)

jest_runner_available = pytest.mark.skipif(
    not _jest_runner_available, reason="Jest not available"
)

# Pytest markers for coverage plugins
coverage_py_available = pytest.mark.skipif(
    not _coverage_py_available, reason="coverage.py not available"
)

nyc_available = pytest.mark.skipif(
    not _nyc_available, reason="NYC (Istanbul) not available"
)


# =============================================================================
# Test runner fixtures
# =============================================================================


@pytest.fixture
def py_test_runner(project_root: Path) -> PytestRunner:
    """Return a PytestRunner instance with project root for venv detection."""
    return PytestRunner(project_root=project_root)


@pytest.fixture
def jest_runner(project_root: Path) -> JestRunner:
    """Return a JestRunner instance with project root for node_modules detection."""
    return JestRunner(project_root=project_root)


# =============================================================================
# Coverage plugin fixtures
# =============================================================================


@pytest.fixture
def coverage_py_plugin(project_root: Path) -> CoveragePyPlugin:
    """Return a CoveragePyPlugin instance with project root for venv detection."""
    return CoveragePyPlugin(project_root=project_root)


@pytest.fixture
def istanbul_plugin(project_root: Path) -> IstanbulPlugin:
    """Return an IstanbulPlugin instance with project root for node_modules detection."""
    return IstanbulPlugin(project_root=project_root)


# =============================================================================
# Java plugin fixtures
# =============================================================================


@pytest.fixture
def spotbugs_checker(project_root: Path) -> SpotBugsChecker:
    """Return a SpotBugsChecker instance with project root."""
    return SpotBugsChecker(project_root=project_root)


@pytest.fixture
def java_webapp_project() -> Path:
    """Return the path to the sample Java webapp integration test project."""
    return Path(__file__).parent / "projects" / "java-webapp"


@pytest.fixture
def maven_runner(java_webapp_project: Path) -> MavenTestRunner:
    """Return a MavenTestRunner instance with Java webapp project root."""
    return MavenTestRunner(project_root=java_webapp_project)


@pytest.fixture
def jacoco_plugin(java_webapp_project: Path) -> JaCoCoPlugin:
    """Return a JaCoCoPlugin instance with Java webapp project root."""
    return JaCoCoPlugin(project_root=java_webapp_project)


# =============================================================================
# Rust plugin fixtures
# =============================================================================


@pytest.fixture
def clippy_linter(project_root: Path) -> ClippyLinter:
    """Return a ClippyLinter instance."""
    return ClippyLinter(project_root=project_root)


@pytest.fixture
def cargo_check_checker(project_root: Path) -> CargoCheckChecker:
    """Return a CargoCheckChecker instance."""
    return CargoCheckChecker(project_root=project_root)


@pytest.fixture
def cargo_test_runner(project_root: Path) -> CargoTestRunner:
    """Return a CargoTestRunner instance."""
    return CargoTestRunner(project_root=project_root)


@pytest.fixture
def tarpaulin_plugin(project_root: Path) -> TarpaulinPlugin:
    """Return a TarpaulinPlugin instance."""
    return TarpaulinPlugin(project_root=project_root)
