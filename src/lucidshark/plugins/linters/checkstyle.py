"""Checkstyle linter plugin.

Checkstyle is a development tool to help programmers write Java code
that adheres to a coding standard.
https://checkstyle.org/
"""

from __future__ import annotations

import hashlib
import importlib.resources  # nosemgrep: python37-compatibility-importlib2 (requires-python>=3.10)
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from lucidshark.bootstrap.download import secure_urlopen
from lucidshark.bootstrap.paths import LucidsharkPaths
from lucidshark.bootstrap.versions import get_tool_version
from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.linters.base import LinterPlugin

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("checkstyle")

# Checkstyle severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "info": Severity.LOW,
    "ignore": Severity.INFO,
}


class CheckstyleLinter(LinterPlugin):
    """Checkstyle linter plugin for Java code analysis."""

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ) -> None:
        """Initialize CheckstyleLinter.

        Args:
            version: Checkstyle version to use.
            project_root: Optional project root for binary cache.
        """
        super().__init__(project_root=project_root)
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
        else:
            self._paths = LucidsharkPaths.default()

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "checkstyle"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["java"]

    @property
    def supports_fix(self) -> bool:
        """Checkstyle does not support auto-fix."""
        return False

    def get_version(self) -> str:
        """Get Checkstyle version."""
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure Checkstyle JAR is available, downloading if needed.

        Returns:
            Path to the Checkstyle all-in-one JAR.

        Raises:
            FileNotFoundError: If Java is not available.
            RuntimeError: If Checkstyle cannot be downloaded.
        """
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        jar_path = binary_dir / f"checkstyle-{self._version}-all.jar"

        if jar_path.exists():
            LOGGER.debug(f"Checkstyle JAR found at {jar_path}")
            return jar_path

        # Verify Java is available before downloading
        if not shutil.which("java"):
            raise FileNotFoundError(
                "Java is required to run Checkstyle but was not found. "
                "Install a JDK (e.g., OpenJDK 11+) and ensure 'java' is in PATH."
            )

        LOGGER.info(f"Downloading Checkstyle v{self._version}...")
        self._download_binary(binary_dir)

        if not jar_path.exists():
            raise RuntimeError(f"Failed to download Checkstyle JAR to {jar_path}")

        return jar_path

    def _download_binary(self, dest_dir: Path) -> None:
        """Download Checkstyle all-in-one JAR from GitHub releases.

        Args:
            dest_dir: Directory to save the JAR into.
        """
        # Construct download URL
        # Format: https://github.com/checkstyle/checkstyle/releases/download/checkstyle-{VERSION}/checkstyle-{VERSION}-all.jar
        url = (
            f"https://github.com/checkstyle/checkstyle/releases/download/"
            f"checkstyle-{self._version}/checkstyle-{self._version}-all.jar"
        )

        LOGGER.debug(f"Downloading from {url}")

        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Validate URL scheme and domain for security
        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        jar_path = dest_dir / f"checkstyle-{self._version}-all.jar"

        # Download JAR directly (no extraction needed)
        tmp_file = tempfile.NamedTemporaryFile(suffix=".jar", delete=False)
        tmp_path = Path(tmp_file.name)
        try:
            with secure_urlopen(url) as response:  # nosec B310 nosemgrep
                tmp_file.write(response.read())
            tmp_file.close()

            # Move to final location
            shutil.move(str(tmp_path), str(jar_path))
            LOGGER.info(f"Checkstyle v{self._version} installed to {jar_path}")

        finally:
            # Ensure file is closed before attempting to delete
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run Checkstyle linting checks.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        try:
            jar_path = self.ensure_binary()
        except (FileNotFoundError, RuntimeError) as e:
            LOGGER.warning(str(e))
            return []

        # Determine config file
        config_file = self._find_config_file(context.project_root)

        # Find Java source files
        java_files = self._find_java_files(context)
        if not java_files:
            LOGGER.info("No Java files found to check")
            return []

        # Write file list to temp file for precise targeting
        file_list_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        )
        file_list_path = Path(file_list_file.name)
        try:
            for f in java_files:
                file_list_file.write(f + "\n")
            file_list_file.close()

            # Build command for java -jar execution
            cmd = [
                "java",
                "-jar",
                str(jar_path),
                "-c",
                config_file,
                "-f",
                "xml",
            ]
            cmd.extend(java_files)

            LOGGER.debug(f"Running: {' '.join(cmd[:10])}...")

            try:
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="checkstyle",
                    stream_handler=context.stream_handler,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("Checkstyle timed out after 120 seconds")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.LINTING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message="Checkstyle timed out after 120 seconds",
                )
                return []
            except Exception as e:
                LOGGER.error(f"Failed to run Checkstyle: {e}")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.LINTING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Failed to run Checkstyle: {e}",
                )
                return []
        finally:
            file_list_path.unlink(missing_ok=True)

        # Parse XML output
        issues = self._parse_output(result.stdout, context.project_root)

        LOGGER.info(f"Checkstyle found {len(issues)} issues")
        return issues

    def _find_config_file(self, project_root: Path) -> str:
        """Find Checkstyle configuration file.

        Args:
            project_root: Project root directory.

        Returns:
            Path to config file or bundled config path.
        """
        # Check for custom config files
        custom_configs = [
            "checkstyle.xml",
            ".checkstyle.xml",
            "config/checkstyle/checkstyle.xml",
            "config/checkstyle.xml",
        ]

        for config in custom_configs:
            config_path = project_root / config
            if config_path.exists():
                return str(config_path)

        # Use bundled google_checks configuration
        # Cache it to .lucidshark/config since Checkstyle needs a real file path
        cached_config = self._paths.config_dir / "checkstyle-google.xml"
        if cached_config.exists():
            return str(cached_config)

        try:
            config_resource = importlib.resources.files("lucidshark.data").joinpath(
                "checkstyle-google.xml"
            )
            config_content = config_resource.read_text(encoding="utf-8")

            # Cache to .lucidshark/config for Checkstyle to access
            cached_config.parent.mkdir(parents=True, exist_ok=True)
            cached_config.write_text(config_content, encoding="utf-8")
            LOGGER.debug(f"Cached Checkstyle config to {cached_config}")
            return str(cached_config)
        except (ModuleNotFoundError, FileNotFoundError, TypeError) as e:
            # Fallback to built-in google_checks if bundled config unavailable
            LOGGER.debug(
                f"Bundled Checkstyle config not found ({e}), using /google_checks.xml"
            )
            return "/google_checks.xml"

    def _find_java_files(self, context: ScanContext) -> List[str]:
        """Find Java source files to check.

        Args:
            context: Scan context.

        Returns:
            List of Java file paths.
        """
        java_files = []

        # Search in specified paths or common Java directories
        search_dirs = []
        if context.paths:
            search_dirs = list(context.paths)
        else:
            # Common Java source directories
            for src_dir in ["src", "src/main/java", "src/test/java"]:
                src_path = context.project_root / src_dir
                if src_path.exists():
                    search_dirs.append(src_path)

        if not search_dirs:
            search_dirs = [context.project_root]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for java_file in search_dir.rglob("*.java"):
                # Check if file should be excluded using proper gitignore matching
                if (
                    context.ignore_patterns is None
                    or not context.ignore_patterns.matches(
                        java_file, context.project_root
                    )
                ):
                    java_files.append(str(java_file))

        return java_files

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Checkstyle XML output.

        Args:
            output: XML output from Checkstyle.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            root = ET.fromstring(output)
        except ET.ParseError as e:
            LOGGER.warning(f"Failed to parse Checkstyle XML output: {e}")
            return []

        issues = []

        for file_elem in root.findall(".//file"):
            file_path = file_elem.get("name", "")

            for error_elem in file_elem.findall("error"):
                issue = self._error_to_issue(error_elem, file_path, project_root)
                if issue:
                    issues.append(issue)

        return issues

    def _error_to_issue(
        self,
        error_elem: ET.Element,
        file_path: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert Checkstyle error element to UnifiedIssue.

        Args:
            error_elem: XML error element.
            file_path: File path from parent file element.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            line = error_elem.get("line")
            column = error_elem.get("column")
            severity_str = error_elem.get("severity", "error")
            message = error_elem.get("message", "")
            source = error_elem.get("source", "")

            # Extract rule name from source (e.g., "com.puppycrawl...WhitespaceAfterCheck")
            rule = source.split(".")[-1] if source else ""

            # Get severity
            severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            # Build file path
            path = Path(file_path)
            if not path.is_absolute():
                path = project_root / path

            # Parse line/column
            line_num = int(line) if line else None
            col_num = int(column) if column else None

            # Generate deterministic ID
            issue_id = self._generate_issue_id(
                rule, file_path, line_num, col_num, message
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="checkstyle",
                severity=severity,
                rule_id=rule or "unknown",
                title=f"[{rule}] {message}" if rule else message,
                description=message,
                documentation_url=f"https://checkstyle.org/checks.html#{rule}"
                if rule
                else None,
                file_path=path,
                line_start=line_num,
                line_end=line_num,
                column_start=col_num,
                fixable=False,  # Checkstyle doesn't support auto-fix
                metadata={
                    "source": source,
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Checkstyle error: {e}")
            return None

    def _generate_issue_id(
        self,
        rule: str,
        file: str,
        line: Optional[int],
        column: Optional[int],
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            rule: Check/rule name.
            file: File path.
            line: Line number.
            column: Column number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{rule}:{file}:{line or 0}:{column or 0}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"checkstyle-{rule}-{hash_val}" if rule else f"checkstyle-{hash_val}"
