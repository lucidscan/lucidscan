"""Ruff linter plugin.

Ruff is an extremely fast Python linter written in Rust.
https://github.com/astral-sh/ruff
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.bootstrap.download import download_file
from lucidshark.bootstrap.paths import LucidsharkPaths
from lucidshark.bootstrap.versions import get_tool_version
from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.linters.base import LinterPlugin, FixResult

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("ruff")

# Python file extensions that Ruff supports
PYTHON_EXTENSIONS = {".py", ".pyi", ".pyw"}

# Ruff severity mapping
# Ruff outputs: E=error, W=warning, F=flake8, I=isort, etc.
# We map based on rule category
SEVERITY_MAP = {
    "E": Severity.MEDIUM,   # pycodestyle error
    "W": Severity.LOW,      # pycodestyle warning
    "F": Severity.MEDIUM,   # pyflakes
    "I": Severity.LOW,      # isort
    "N": Severity.LOW,      # pep8-naming
    "D": Severity.LOW,      # pydocstyle
    "UP": Severity.LOW,     # pyupgrade
    "YTT": Severity.MEDIUM, # flake8-2020
    "ANN": Severity.LOW,    # flake8-annotations
    "ASYNC": Severity.MEDIUM,
    "S": Severity.HIGH,     # flake8-bandit (security)
    "BLE": Severity.MEDIUM, # flake8-blind-except
    "FBT": Severity.LOW,    # flake8-boolean-trap
    "B": Severity.MEDIUM,   # flake8-bugbear
    "A": Severity.LOW,      # flake8-builtins
    "COM": Severity.LOW,    # flake8-commas
    "C4": Severity.LOW,     # flake8-comprehensions
    "DTZ": Severity.MEDIUM, # flake8-datetimez
    "T10": Severity.HIGH,   # flake8-debugger
    "DJ": Severity.MEDIUM,  # flake8-django
    "EM": Severity.LOW,     # flake8-errmsg
    "EXE": Severity.LOW,    # flake8-executable
    "FA": Severity.LOW,     # flake8-future-annotations
    "ISC": Severity.LOW,    # flake8-implicit-str-concat
    "ICN": Severity.LOW,    # flake8-import-conventions
    "LOG": Severity.LOW,    # flake8-logging
    "G": Severity.LOW,      # flake8-logging-format
    "INP": Severity.LOW,    # flake8-no-pep420
    "PIE": Severity.LOW,    # flake8-pie
    "T20": Severity.LOW,    # flake8-print
    "PYI": Severity.LOW,    # flake8-pyi
    "PT": Severity.LOW,     # flake8-pytest-style
    "Q": Severity.LOW,      # flake8-quotes
    "RSE": Severity.LOW,    # flake8-raise
    "RET": Severity.LOW,    # flake8-return
    "SLF": Severity.MEDIUM, # flake8-self
    "SLOT": Severity.LOW,   # flake8-slots
    "SIM": Severity.LOW,    # flake8-simplify
    "TID": Severity.LOW,    # flake8-tidy-imports
    "TCH": Severity.LOW,    # flake8-type-checking
    "INT": Severity.LOW,    # flake8-gettext
    "ARG": Severity.LOW,    # flake8-unused-arguments
    "PTH": Severity.LOW,    # flake8-use-pathlib
    "TD": Severity.INFO,    # flake8-todos
    "FIX": Severity.INFO,   # flake8-fixme
    "ERA": Severity.LOW,    # eradicate
    "PD": Severity.LOW,     # pandas-vet
    "PGH": Severity.LOW,    # pygrep-hooks
    "PL": Severity.MEDIUM,  # Pylint
    "TRY": Severity.LOW,    # tryceratops
    "FLY": Severity.LOW,    # flynt
    "NPY": Severity.MEDIUM, # NumPy
    "PERF": Severity.LOW,   # Perflint
    "FURB": Severity.LOW,   # refurb
    "RUF": Severity.MEDIUM, # Ruff-specific
}


class RuffLinter(LinterPlugin):
    """Ruff linter plugin for Python code analysis."""

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ):
        """Initialize RuffLinter.

        Args:
            version: Ruff version to use.
            project_root: Optional project root for tool installation.
        """
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
        else:
            self._paths = LucidsharkPaths.default()

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "ruff"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["python"]

    @property
    def supports_fix(self) -> bool:
        """Ruff supports auto-fix."""
        return True

    def get_version(self) -> str:
        """Get Ruff version."""
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure Ruff binary is available.

        Downloads from GitHub releases if not present.

        Returns:
            Path to Ruff binary.
        """
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_name = "ruff.exe" if platform.system() == "Windows" else "ruff"
        binary_path = binary_dir / binary_name

        if binary_path.exists():
            return binary_path

        # Download binary
        LOGGER.info(f"Downloading Ruff {self._version}...")
        binary_dir.mkdir(parents=True, exist_ok=True)

        archive_path = self._download_release(binary_dir)
        self._extract_binary(archive_path, binary_dir, binary_name)

        # Make executable on Unix
        if platform.system() != "Windows":
            binary_path.chmod(0o755)

        # Clean up archive
        archive_path.unlink(missing_ok=True)

        LOGGER.info(f"Ruff {self._version} installed to {binary_dir}")
        return binary_path

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run Ruff linting.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        binary = self.ensure_binary()

        # Build command
        cmd = [
            str(binary),
            "check",
            "--output-format", "json",
        ]

        # Filter and add paths to check
        # Only include Python files; also drop any path that matches ignore patterns
        # (defensive so ignored paths are never passed to Ruff, including on Windows)
        if context.paths:
            paths_to_use = context.paths
            if context.ignore_patterns is not None:
                paths_to_use = [
                    p for p in paths_to_use
                    if not context.ignore_patterns.matches(p, context.project_root)
                ]
            paths = self._filter_paths(paths_to_use, context.project_root)
        else:
            paths = ["."]

        # If no valid paths after filtering, skip linting
        if not paths:
            LOGGER.debug("No Python files to lint")
            return []

        cmd.extend(paths)

        # Add exclude patterns using --extend-exclude to preserve Ruff's defaults
        # (--exclude would replace all defaults like .git, .venv, __pycache__, etc.)
        for pattern in self._get_ruff_exclude_patterns(context):
            cmd.extend(["--extend-exclude", pattern])

        # Run Ruff
        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ruff",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Ruff lint timed out after 120 seconds")
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run Ruff: {e}")
            return []

        # Parse output
        issues = self._parse_output(result.stdout, context.project_root)

        LOGGER.info(f"Ruff found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply Ruff auto-fixes.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            FixResult with statistics.
        """
        binary = self.ensure_binary()

        # Run without fix to count issues first
        pre_issues = self.lint(context)

        # Build fix command
        cmd = [
            str(binary),
            "check",
            "--fix",
            "--output-format", "json",
        ]

        # Filter and add paths (same ignore filtering as lint)
        if context.paths:
            paths_to_use = context.paths
            if context.ignore_patterns is not None:
                paths_to_use = [
                    p for p in paths_to_use
                    if not context.ignore_patterns.matches(p, context.project_root)
                ]
            paths = self._filter_paths(paths_to_use, context.project_root)
        else:
            paths = ["."]

        # If no valid paths after filtering, skip fix
        if not paths:
            LOGGER.debug("No Python files to fix")
            return FixResult()

        cmd.extend(paths)

        # Add exclude patterns using --extend-exclude to preserve Ruff's defaults
        for pattern in self._get_ruff_exclude_patterns(context):
            cmd.extend(["--extend-exclude", pattern])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ruff-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Ruff fix timed out after 120 seconds")
            return FixResult()
        except Exception as e:
            LOGGER.error(f"Failed to run Ruff fix: {e}")
            return FixResult()

        # Parse remaining issues
        post_issues = self._parse_output(result.stdout, context.project_root)

        # Calculate stats
        files_modified = len(set(
            str(issue.file_path)
            for issue in pre_issues
            if issue not in post_issues
        ))

        return FixResult(
            files_modified=files_modified,
            issues_fixed=len(pre_issues) - len(post_issues),
            issues_remaining=len(post_issues),
        )

    @staticmethod
    def _simplify_exclude_pattern(pattern: str) -> str:
        """Simplify a gitignore-style glob into a form Ruff handles on all platforms.

        Ruff's CLI ``--extend-exclude`` uses globset for matching.  On Windows,
        patterns containing ``**`` and forward slashes may fail to match paths
        discovered with native backslash separators (known Ruff issue).

        In gitignore semantics a bare name (e.g. ``.lucidshark``) matches that
        name at **any depth**, which is equivalent to ``**/.lucidshark/**``.
        Stripping the ``**/`` wrapper produces a simpler pattern that Ruff's
        globset can match reliably on every platform.

        Transformations applied (in order):
        - ``**/<name>/**`` → ``<name>``
        - ``**/<name>``    → ``<name>``
        - ``<path>/**``    → ``<path>``
        - everything else  → kept as-is, with backslashes normalised to ``/``
        """
        # Normalise separators first
        p = pattern.replace("\\", "/")

        # Strip leading **/ (matches any depth prefix)
        if p.startswith("**/"):
            p = p[3:]

        # Strip trailing /** (matches any depth suffix)
        if p.endswith("/**"):
            p = p[:-3]

        return p

    def _get_ruff_exclude_patterns(self, context: ScanContext) -> List[str]:
        """Get exclude patterns for Ruff, simplified for cross-platform reliability.

        Simplifies gitignore-style globs (e.g. ``**/.venv/**``) into bare
        directory names (e.g. ``.venv``) that Ruff's globset can match
        regardless of path separator conventions on the host OS.

        Args:
            context: Scan context with ignore patterns.

        Returns:
            List of patterns to pass to ``--extend-exclude``.
        """
        raw = context.get_exclude_patterns()
        seen: set[str] = set()
        result: list[str] = []
        for pattern in raw:
            simplified = self._simplify_exclude_pattern(pattern)
            if simplified and simplified not in seen:
                result.append(simplified)
                seen.add(simplified)
        return result

    def _filter_paths(
        self,
        paths: List[Path],
        project_root: Path,
    ) -> List[str]:
        """Filter paths to only include Python files.

        Directories are passed through as-is (Ruff will handle them).
        Files are filtered to only include supported extensions.

        Args:
            paths: List of paths to filter.
            project_root: Project root directory.

        Returns:
            List of filtered path strings.
        """
        filtered = []
        for path in paths:
            if path.is_dir():
                # Directories are passed through - Ruff will find Python files
                # Use as_posix() for Windows compatibility (forward slashes)
                filtered.append(path.as_posix())
            elif path.suffix.lower() in PYTHON_EXTENSIONS:
                # Only include files with Python extensions
                filtered.append(path.as_posix())
            else:
                LOGGER.debug(f"Skipping non-Python file: {path}")
        return filtered

    def _download_release(self, target_dir: Path) -> Path:
        """Download Ruff release archive.

        Args:
            target_dir: Directory to download to.

        Returns:
            Path to downloaded archive.
        """
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Map platform names
        if system == "darwin":
            system = "apple-darwin"
        elif system == "linux":
            system = "unknown-linux-gnu"
        elif system == "windows":
            system = "pc-windows-msvc"

        # Map architecture
        if machine in ("x86_64", "amd64"):
            arch = "x86_64"
        elif machine in ("arm64", "aarch64"):
            arch = "aarch64"
        else:
            arch = machine

        # Build download URL
        ext = "zip" if platform.system() == "Windows" else "tar.gz"
        filename = f"ruff-{arch}-{system}.{ext}"
        url = f"https://github.com/astral-sh/ruff/releases/download/{self._version}/{filename}"

        archive_path = target_dir / filename

        LOGGER.debug(f"Downloading from {url}")

        # Validate URL scheme and domain for security
        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        try:
            download_file(url, archive_path)  # nosec B310 nosemgrep
        except Exception as e:
            raise RuntimeError(f"Failed to download Ruff: {e}") from e

        return archive_path

    def _extract_binary(self, archive_path: Path, target_dir: Path, binary_name: str) -> None:
        """Extract binary from archive.

        Args:
            archive_path: Path to archive file.
            target_dir: Directory to extract to.
            binary_name: Name of the binary file.
        """
        if str(archive_path).endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.namelist():
                    if member.endswith(binary_name):
                        # Extract to target dir
                        zf.extract(member, target_dir)
                        # Move from subdirectory if needed
                        extracted = target_dir / member
                        if extracted.parent != target_dir:
                            extracted.rename(target_dir / binary_name)
                        break
        else:
            with tarfile.open(archive_path, "r:gz") as tf:
                for tarinfo in tf.getmembers():
                    if tarinfo.name.endswith(binary_name):
                        tarinfo.name = binary_name
                        tf.extract(tarinfo, target_dir)
                        break

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Ruff JSON output.

        Args:
            output: JSON output from Ruff.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            violations = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse Ruff output as JSON")
            return []

        if not isinstance(violations, list):
            LOGGER.warning(f"Expected list from Ruff, got {type(violations).__name__}")
            return []

        issues = []
        for violation in violations:
            if not isinstance(violation, dict):
                LOGGER.warning(f"Skipping non-dict violation: {type(violation).__name__}")
                continue
            issue = self._violation_to_issue(violation, project_root)
            if issue:
                issues.append(issue)

        return issues

    def _violation_to_issue(
        self,
        violation: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert Ruff violation to UnifiedIssue.

        Args:
            violation: Ruff violation dict.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            code = violation.get("code", "")
            message = violation.get("message", "")
            filename = violation.get("filename", "")
            location = violation.get("location") or {}

            # Get severity based on rule category
            severity = self._get_severity(code)

            # Generate deterministic ID
            issue_id = self._generate_issue_id(code, filename, location, message)

            file_path = Path(filename)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            # Extract code snippet if available
            code_snippet = None
            source_line = violation.get("source")
            if source_line:
                code_snippet = source_line

            # Extract fix information
            fix_info = violation.get("fix") or {}
            is_fixable = fix_info.get("applicability") == "safe" or bool(fix_info.get("edits"))
            fix_message = fix_info.get("message")

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="ruff",
                severity=severity,
                rule_id=code,
                title=f"{code}: {message}",
                description=message,
                documentation_url=violation.get("url"),
                file_path=file_path,
                line_start=location.get("row"),
                line_end=location.get("row"),
                column_start=location.get("column"),
                column_end=violation.get("end_location", {}).get("column"),
                code_snippet=code_snippet,
                fixable=is_fixable,
                suggested_fix=fix_message,
                recommendation=fix_message,
                metadata={
                    "noqa_row": violation.get("noqa_row"),
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse violation: {e}")
            return None

    def _get_severity(self, code: str) -> Severity:
        """Get severity for a Ruff rule code.

        Args:
            code: Ruff rule code (e.g., 'E501', 'F401').

        Returns:
            Severity level.
        """
        # Extract category prefix (letters before numbers)
        prefix = ""
        for char in code:
            if char.isalpha():
                prefix += char
            else:
                break

        return SEVERITY_MAP.get(prefix, Severity.MEDIUM)

    def _generate_issue_id(
        self,
        code: str,
        filename: str,
        location: Dict[str, int],
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            code: Rule code.
            filename: File path.
            location: Line/column info.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{code}:{filename}:{location.get('row', 0)}:{location.get('column', 0)}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"ruff-{code}-{hash_val}"
