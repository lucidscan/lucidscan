"""Ktlint linter plugin.

ktlint is an anti-bikeshedding Kotlin linter with built-in formatter.
https://pinterest.github.io/ktlint/
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
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
from lucidshark.plugins.linters.base import FixResult, LinterPlugin

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("ktlint")

# ktlint severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
}


class KtlintLinter(LinterPlugin):
    """Ktlint linter plugin for Kotlin code analysis.

    ktlint is a managed tool -- LucidShark auto-downloads the JAR on first use.
    """

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ) -> None:
        super().__init__(project_root=project_root)
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
        else:
            self._paths = LucidsharkPaths.default()

    @property
    def name(self) -> str:
        return "ktlint"

    @property
    def languages(self) -> List[str]:
        return ["kotlin"]

    @property
    def supports_fix(self) -> bool:
        return True

    def get_version(self) -> str:
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure ktlint JAR is available, downloading if needed.

        Returns:
            Path to the ktlint JAR.

        Raises:
            FileNotFoundError: If Java is not available.
            RuntimeError: If ktlint cannot be downloaded.
        """
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        jar_path = binary_dir / f"ktlint-{self._version}.jar"

        if jar_path.exists():
            LOGGER.debug(f"ktlint JAR found at {jar_path}")
            return jar_path

        if not shutil.which("java"):
            raise FileNotFoundError(
                "Java is required to run ktlint but was not found. "
                "Install a JDK (e.g., OpenJDK 11+) and ensure 'java' is in PATH."
            )

        LOGGER.info(f"Downloading ktlint v{self._version}...")
        self._download_binary(binary_dir)

        if not jar_path.exists():
            raise RuntimeError(f"Failed to download ktlint JAR to {jar_path}")

        return jar_path

    def _download_binary(self, dest_dir: Path) -> None:
        """Download ktlint JAR from GitHub releases."""
        url = (
            f"https://github.com/pinterest/ktlint/releases/download/"
            f"{self._version}/ktlint-{self._version}.jar"
        )

        LOGGER.debug(f"Downloading from {url}")
        dest_dir.mkdir(parents=True, exist_ok=True)

        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        jar_path = dest_dir / f"ktlint-{self._version}.jar"

        tmp_file = tempfile.NamedTemporaryFile(suffix=".jar", delete=False)
        tmp_path = Path(tmp_file.name)
        try:
            with secure_urlopen(url) as response:  # nosec B310 nosemgrep
                tmp_file.write(response.read())
            tmp_file.close()
            shutil.move(str(tmp_path), str(jar_path))
            LOGGER.info(f"ktlint v{self._version} installed to {jar_path}")
        finally:
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run ktlint linting checks.

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

        kotlin_files = self._find_kotlin_files(context)
        if not kotlin_files:
            LOGGER.info("No Kotlin files found to check")
            return []

        cmd = [
            "java",
            "-jar",
            str(jar_path),
            "--reporter=json",
        ]
        cmd.extend(kotlin_files)

        LOGGER.debug(f"Running: {' '.join(cmd[:10])}...")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ktlint",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("ktlint timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="ktlint timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run ktlint: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run ktlint: {e}",
            )
            return []

        issues = self._parse_output(result.stdout, context.project_root)
        LOGGER.info(f"ktlint found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        """Apply automatic fixes using ktlint --format."""
        pre_issues = self.lint(context)

        try:
            jar_path = self.ensure_binary()
        except (FileNotFoundError, RuntimeError) as e:
            LOGGER.warning(str(e))
            return FixResult()

        kotlin_files = self._find_kotlin_files(context)
        if not kotlin_files:
            return FixResult()

        cmd = [
            "java",
            "-jar",
            str(jar_path),
            "--format",
        ]
        cmd.extend(kotlin_files)

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="ktlint-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run ktlint fix: {e}")
            return FixResult()

        post_issues = self.lint(context)
        return self._calculate_fix_stats(pre_issues, post_issues)

    def _find_kotlin_files(self, context: ScanContext) -> List[str]:
        """Find Kotlin source files to check."""
        kotlin_files = []

        search_dirs = []
        if context.paths:
            search_dirs = list(context.paths)
        else:
            for src_dir in ["src", "src/main/kotlin", "src/test/kotlin",
                            "src/main/java", "src/test/java"]:
                src_path = context.project_root / src_dir
                if src_path.exists():
                    search_dirs.append(src_path)

        if not search_dirs:
            search_dirs = [context.project_root]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            if search_dir.is_file():
                if search_dir.suffix in (".kt", ".kts"):
                    if (
                        context.ignore_patterns is None
                        or not context.ignore_patterns.matches(
                            search_dir, context.project_root
                        )
                    ):
                        kotlin_files.append(str(search_dir))
            else:
                for ext in ("*.kt", "*.kts"):
                    for kt_file in search_dir.rglob(ext):
                        if (
                            context.ignore_patterns is None
                            or not context.ignore_patterns.matches(
                                kt_file, context.project_root
                            )
                        ):
                            kotlin_files.append(str(kt_file))

        return kotlin_files

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse ktlint JSON output.

        ktlint --reporter=json outputs an array of file objects:
        [{"file": "path", "errors": [{"line": 1, "column": 1, "message": "...", "rule": "..."}]}]
        """
        if not output or not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse ktlint JSON output")
            return []

        issues = []
        for file_entry in data:
            file_path_str = file_entry.get("file", "")
            errors = file_entry.get("errors", [])

            for error in errors:
                issue = self._error_to_issue(error, file_path_str, project_root)
                if issue:
                    issues.append(issue)

        return issues

    def _error_to_issue(
        self,
        error: dict,
        file_path_str: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert ktlint error to UnifiedIssue."""
        try:
            line = error.get("line", 0)
            column = error.get("column", 0)
            message = error.get("message", "")
            rule = error.get("rule", "")
            severity_str = error.get("severity", "error")

            severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            path = Path(file_path_str)
            if not path.is_absolute():
                path = project_root / path

            issue_id = self._generate_issue_id(rule, file_path_str, line, column, message)

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.LINTING,
                source_tool="ktlint",
                severity=severity,
                rule_id=rule or "unknown",
                title=f"[{rule}] {message}" if rule else message,
                description=message,
                documentation_url=f"https://pinterest.github.io/ktlint/{self._version}/rules/"
                if rule
                else None,
                file_path=path,
                line_start=line if line else None,
                line_end=line if line else None,
                column_start=column if column else None,
                fixable=True,
                metadata={
                    "rule": rule,
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse ktlint error: {e}")
            return None

    def _generate_issue_id(
        self,
        rule: str,
        file: str,
        line: int,
        column: int,
        message: str,
    ) -> str:
        content = f"{rule}:{file}:{line}:{column}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"ktlint-{rule}-{hash_val}" if rule else f"ktlint-{hash_val}"
