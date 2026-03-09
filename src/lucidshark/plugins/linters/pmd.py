"""PMD linter plugin.

PMD is a source code analyzer for Java that finds common programming flaws
like unused variables, empty catch blocks, unnecessary object creation, etc.
https://pmd.github.io/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.bootstrap.download import secure_urlopen
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
from lucidshark.plugins.linters.base import LinterPlugin

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("pmd")

# PMD priority mapping to unified severity
# PMD priorities: 1=highest, 5=lowest
PRIORITY_SEVERITY_MAP: Dict[int, Severity] = {
    1: Severity.CRITICAL,
    2: Severity.HIGH,
    3: Severity.MEDIUM,
    4: Severity.LOW,
    5: Severity.INFO,
}


class PmdLinter(LinterPlugin):
    """PMD linter plugin for Java static analysis."""

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ) -> None:
        """Initialize PmdLinter.

        Args:
            version: PMD version to use.
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
        return "pmd"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["java"]

    @property
    def supports_fix(self) -> bool:
        """PMD does not support auto-fix."""
        return False

    def get_version(self) -> str:
        """Get PMD version."""
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure PMD is available, downloading if needed.

        Returns:
            Path to the PMD binary script.

        Raises:
            FileNotFoundError: If Java is not available.
            RuntimeError: If PMD cannot be downloaded.
        """
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_path = binary_dir / f"pmd-bin-{self._version}" / "bin" / "pmd"

        if binary_path.exists():
            LOGGER.debug(f"PMD binary found at {binary_path}")
            return binary_path

        # Verify Java is available before downloading
        if not shutil.which("java"):
            raise FileNotFoundError(
                "Java is required to run PMD but was not found. "
                "Install a JDK (e.g., OpenJDK 11+) and ensure 'java' is in PATH."
            )

        LOGGER.info(f"Downloading PMD v{self._version}...")
        self._download_binary(binary_dir)

        if not binary_path.exists():
            raise RuntimeError(f"Failed to download PMD binary to {binary_path}")

        return binary_path

    def _download_binary(self, dest_dir: Path) -> None:
        """Download and extract PMD for current platform.

        Args:
            dest_dir: Directory to extract PMD into.
        """
        # Construct download URL
        url = (
            f"https://github.com/pmd/pmd/releases/download/"
            f"pmd_releases/{self._version}/pmd-dist-{self._version}-bin.zip"
        )

        LOGGER.debug(f"Downloading from {url}")

        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Validate URL scheme and domain for security
        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        # Download and extract
        tmp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp_path = Path(tmp_file.name)
        try:
            with secure_urlopen(url) as response:  # nosec B310 nosemgrep
                tmp_file.write(response.read())
            tmp_file.close()

            # Extract zip safely (prevent path traversal)
            with zipfile.ZipFile(tmp_path, "r") as zf:
                for zip_info in zf.infolist():
                    # Validate each member path to prevent traversal attacks
                    member_path = (dest_dir / zip_info.filename).resolve()
                    if not member_path.is_relative_to(dest_dir.resolve()):
                        raise ValueError(
                            f"Path traversal detected: {zip_info.filename}"
                        )
                    zf.extract(zip_info, path=dest_dir)

            # Make bin/pmd executable
            binary_path = dest_dir / f"pmd-bin-{self._version}" / "bin" / "pmd"
            if binary_path.exists():
                binary_path.chmod(0o755)
            LOGGER.info(f"PMD v{self._version} installed to {binary_path}")

        finally:
            # Ensure file is closed before attempting to delete
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run PMD linting checks.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        try:
            binary = self.ensure_binary()
        except (FileNotFoundError, RuntimeError) as e:
            LOGGER.warning(str(e))
            return []

        # Find Java source files
        java_files = self._find_java_files(context)
        if not java_files:
            LOGGER.info("No Java files found to check with PMD")
            return []

        # Determine ruleset
        ruleset = self._find_ruleset_config(context.project_root)

        # Write file list to temp file for precise targeting.
        # Using --file-list instead of -d (directories) ensures PMD only
        # scans the exact files that passed our gitignore filtering.
        file_list_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        )
        file_list_path = Path(file_list_file.name)
        try:
            for f in java_files:
                file_list_file.write(f + "\n")
            file_list_file.close()

            # Build command
            cmd = [
                str(binary),
                "check",
                "--file-list",
                str(file_list_path),
                "-R",
                ruleset,
                "-f",
                "json",
                "--no-fail-on-violation",
            ]

            LOGGER.debug(f"Running: {' '.join(cmd[:10])}...")

            try:
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="pmd",
                    stream_handler=context.stream_handler,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("PMD timed out after 120 seconds")
                return []
            except Exception as e:
                LOGGER.error(f"Failed to run PMD: {e}")
                return []
        finally:
            file_list_path.unlink(missing_ok=True)

        # Parse JSON output
        issues = self._parse_output(result.stdout, context.project_root)

        LOGGER.info(f"PMD found {len(issues)} issues")
        return issues

    def _find_ruleset_config(self, project_root: Path) -> str:
        """Find PMD ruleset configuration file.

        Args:
            project_root: Project root directory.

        Returns:
            Path to ruleset file or built-in ruleset name.
        """
        custom_configs = [
            "pmd-ruleset.xml",
            "pmd.xml",
            "ruleset.xml",
            ".pmd/rulesets.xml",
            "config/pmd/pmd.xml",
            "config/pmd/ruleset.xml",
        ]

        for config in custom_configs:
            config_path = project_root / config
            if config_path.exists():
                return str(config_path)

        # Use PMD built-in quickstart ruleset (118 rules)
        return "rulesets/java/quickstart.xml"

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
        """Parse PMD JSON output.

        Args:
            output: JSON output from PMD.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            LOGGER.warning(f"Failed to parse PMD JSON output: {e}")
            return []

        issues = []

        for file_entry in data.get("files", []):
            file_path = file_entry.get("filename", "")

            for violation in file_entry.get("violations", []):
                issue = self._violation_to_issue(violation, file_path, project_root)
                if issue:
                    issues.append(issue)

        return issues

    def _violation_to_issue(
        self,
        violation: Dict[str, Any],
        file_path: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert PMD violation to UnifiedIssue.

        Args:
            violation: PMD violation dictionary.
            file_path: File path from parent file entry.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            rule = violation.get("rule", "")
            ruleset = violation.get("ruleset", "")
            priority = violation.get("priority", 3)
            description = violation.get("description", "")
            begin_line = violation.get("beginline")
            begin_column = violation.get("begincolumn")
            end_line = violation.get("endline")
            external_info_url = violation.get("externalInfoUrl")

            # Get severity from priority
            severity = PRIORITY_SEVERITY_MAP.get(priority, Severity.MEDIUM)

            # Build file path
            path = Path(file_path)
            if not path.is_absolute():
                path = project_root / path

            # Parse line/column
            line_num = int(begin_line) if begin_line is not None else None
            col_num = int(begin_column) if begin_column is not None else None
            end_line_num = int(end_line) if end_line is not None else None

            # Generate deterministic ID
            issue_id = self._generate_issue_id(
                rule, file_path, line_num, col_num, description
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="pmd",
                severity=severity,
                rule_id=rule or "unknown",
                title=f"[{rule}] {description}" if rule else description,
                description=description,
                documentation_url=external_info_url,
                file_path=path,
                line_start=line_num,
                line_end=end_line_num,
                column_start=col_num,
                fixable=False,
                metadata={
                    "ruleset": ruleset,
                    "priority": priority,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse PMD violation: {e}")
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
            rule: Rule name.
            file: File path.
            line: Line number.
            column: Column number.
            message: Violation message.

        Returns:
            Unique issue ID.
        """
        content = f"{rule}:{file}:{line or 0}:{column or 0}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"pmd-{rule}-{hash_val}" if rule else f"pmd-{hash_val}"
