"""Biome linter plugin.

Biome is a fast linter and formatter for JavaScript, TypeScript, and more.
https://biomejs.dev/
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.bootstrap.download import download_file
from lucidshark.bootstrap.paths import LucidsharkPaths
from lucidshark.bootstrap.versions import get_tool_version
from lucidshark.core.logging import get_logger
from lucidshark.core.paths import resolve_node_bin
from lucidshark.core.models import (
    ScanContext,
    Severity,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.linters.base import FixResult, LinterPlugin

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("biome")

# Biome severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "info": Severity.LOW,
}


class BiomeLinter(LinterPlugin):
    """Biome linter plugin for JavaScript/TypeScript code analysis."""

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ):
        """Initialize BiomeLinter.

        Args:
            version: Biome version to use.
            project_root: Optional project root for tool installation.
        """
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
            self._project_root = project_root
        else:
            self._paths = LucidsharkPaths.default()
            self._project_root = None

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "biome"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["javascript", "typescript", "json"]

    @property
    def supports_fix(self) -> bool:
        """Biome supports auto-fix."""
        return True

    def get_version(self) -> str:
        """Get Biome version."""
        return self._version

    def _resolve_target_paths(self, context: ScanContext) -> List[str]:
        """Resolve target paths for linting/checking.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of path strings to check.
        """
        if context.paths:
            return [p.as_posix() for p in context.paths]

        src_dir = context.project_root / "src"
        if src_dir.exists():
            return [src_dir.as_posix()]

        return ["."]

    def ensure_binary(self) -> Path:
        """Ensure Biome binary is available.

        Downloads from GitHub releases if not present.

        Returns:
            Path to Biome binary.
        """
        # Check project node_modules first
        if self._project_root:
            node_biome = resolve_node_bin(self._project_root, "biome")
            if node_biome:
                return node_biome

        # Check system PATH
        biome_path = shutil.which("biome")
        if biome_path:
            return Path(biome_path)

        # Download binary
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_name = "biome.exe" if platform.system() == "Windows" else "biome"
        binary_path = binary_dir / binary_name

        if binary_path.exists():
            return binary_path

        LOGGER.info(f"Downloading Biome {self._version}...")
        binary_dir.mkdir(parents=True, exist_ok=True)

        archive_path = self._download_release(binary_dir)
        self._extract_binary(archive_path, binary_dir, binary_name)

        # Make executable on Unix
        if platform.system() != "Windows":
            binary_path.chmod(0o755)

        # Clean up archive
        archive_path.unlink(missing_ok=True)

        LOGGER.info(f"Biome {self._version} installed to {binary_dir}")
        return binary_path

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run Biome linting.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        binary = self.ensure_binary()

        # Build command
        cmd = [
            str(binary),
            "lint",
            "--reporter", "json",
        ]

        # Add paths to check
        cmd.extend(self._resolve_target_paths(context))

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="biome",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Biome lint timed out after 120 seconds")
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run Biome: {e}")
            return []

        # Parse output
        issues = self._parse_output(result.stdout, context.project_root)

        LOGGER.info(f"Biome found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply Biome auto-fixes.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            FixResult with statistics.
        """
        binary = self.ensure_binary()

        # Run without fix to count issues first
        pre_issues = self.lint(context)

        # Build fix command - Biome uses 'check --apply' for fixes
        cmd = [
            str(binary),
            "check",
            "--apply",
        ]

        cmd.extend(self._resolve_target_paths(context))

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="biome-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Biome fix timed out after 120 seconds")
            return FixResult()
        except Exception as e:
            LOGGER.error(f"Failed to run Biome fix: {e}")
            return FixResult()

        # Run lint again to get remaining issues
        post_issues = self.lint(context)

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

    def _download_release(self, target_dir: Path) -> Path:
        """Download Biome release archive.

        Args:
            target_dir: Directory to download to.

        Returns:
            Path to downloaded archive.
        """
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Map platform names for Biome releases
        if system == "darwin":
            platform_name = "darwin"
        elif system == "linux":
            platform_name = "linux"
        elif system == "windows":
            platform_name = "win32"
        else:
            platform_name = system

        # Map architecture
        if machine in ("x86_64", "amd64"):
            arch = "x64"
        elif machine in ("arm64", "aarch64"):
            arch = "arm64"
        else:
            arch = machine

        # Build download URL
        # Biome releases: biome-darwin-arm64, biome-linux-x64, etc.
        binary_name = f"biome-{platform_name}-{arch}"
        if system == "windows":
            binary_name += ".exe"

        # Biome 2.x changed the release URL format
        # 1.x: https://github.com/biomejs/biome/releases/download/cli/v{version}/...
        # 2.x: https://github.com/biomejs/biome/releases/download/@biomejs/biome@{version}/...
        major_version = int(self._version.split(".")[0])
        if major_version >= 2:
            url = f"https://github.com/biomejs/biome/releases/download/@biomejs/biome@{self._version}/{binary_name}"
        else:
            url = f"https://github.com/biomejs/biome/releases/download/cli/v{self._version}/{binary_name}"

        archive_path = target_dir / binary_name

        LOGGER.debug(f"Downloading from {url}")

        # Validate URL scheme and domain for security
        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        try:
            download_file(url, archive_path)  # nosec B310 nosemgrep
        except Exception as e:
            raise RuntimeError(f"Failed to download Biome: {e}") from e

        return archive_path

    def _extract_binary(self, archive_path: Path, target_dir: Path, binary_name: str) -> None:
        """Move/rename downloaded binary.

        Biome releases are standalone binaries, not archives.

        Args:
            archive_path: Path to downloaded binary.
            target_dir: Directory to place binary.
            binary_name: Target binary name.
        """
        target_path = target_dir / binary_name
        if archive_path != target_path:
            archive_path.rename(target_path)

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Biome JSON output.

        Args:
            output: JSON output from Biome.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse Biome output as JSON")
            return []

        issues = []
        diagnostics = data.get("diagnostics", [])

        for diagnostic in diagnostics:
            issue = self._diagnostic_to_issue(diagnostic, project_root)
            if issue:
                issues.append(issue)

        return issues

    def _diagnostic_to_issue(
        self,
        diagnostic: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert Biome diagnostic to UnifiedIssue.

        Args:
            diagnostic: Biome diagnostic dict.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            severity_str = diagnostic.get("severity", "error")
            message = diagnostic.get("message", "")
            # Handle structured message format
            if isinstance(message, list):
                message = " ".join(
                    m.get("content", "") if isinstance(m, dict) else str(m)
                    for m in message
                )

            category = diagnostic.get("category", "")
            location = diagnostic.get("location", {})

            # Get file path from location
            file_path_str = location.get("path", {}).get("file", "")

            # Get position info
            line_start = location.get("lineStart", 1)
            line_end = location.get("lineEnd", line_start)
            column_start = location.get("columnStart", 1)

            # Get severity
            severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            # Build file path
            file_path = Path(file_path_str) if file_path_str else Path("unknown")
            if not file_path.is_absolute() and file_path_str:
                file_path = project_root / file_path

            # Generate deterministic ID
            issue_id = self._generate_issue_id(
                category, file_path_str, line_start, column_start, message
            )

            # Build title
            title = f"[{category}] {message}" if category else message

            # Get column end
            column_end = location.get("columnEnd")

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="biome",
                severity=severity,
                rule_id=category or "unknown",
                title=title,
                description=message,
                documentation_url=f"https://biomejs.dev/linter/rules/{category.lower().replace('/', '-')}" if category else None,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                column_start=column_start,
                column_end=column_end,
                fixable=diagnostic.get("fixable", False),
                metadata={
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Biome diagnostic: {e}")
            return None

    def _generate_issue_id(
        self,
        category: str,
        file: str,
        line: int,
        column: int,
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            category: Rule category.
            file: File path.
            line: Line number.
            column: Column number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{category}:{file}:{line}:{column}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"biome-{category}-{hash_val}" if category else f"biome-{hash_val}"
