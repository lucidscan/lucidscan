"""Detekt type checker plugin.

detekt is a static code analysis tool for Kotlin that finds code smells,
complexity issues, and potential bugs.
https://detekt.dev/

detekt is a managed tool - LucidShark auto-downloads it on first use.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import defusedxml.ElementTree as ET  # type: ignore[import-untyped]
from xml.etree.ElementTree import Element

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
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("detekt")

# detekt severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "info": Severity.LOW,
}

# detekt issue type categories
CATEGORY_DESCRIPTIONS = {
    "complexity": "Code complexity issue",
    "coroutines": "Coroutine usage issue",
    "empty-blocks": "Empty block detected",
    "exceptions": "Exception handling issue",
    "naming": "Naming convention violation",
    "performance": "Performance issue",
    "potential-bugs": "Potential bug detected",
    "style": "Code style issue",
}


class DetektChecker(TypeCheckerPlugin):
    """Detekt type checker plugin for Kotlin static analysis.

    detekt is a managed tool - it is automatically downloaded from GitHub
    releases on first use. The JAR is cached at:
    `.lucidshark/bin/detekt/{version}/`
    """

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ):
        self._project_root = project_root
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
        else:
            self._paths = LucidsharkPaths.default()

    @property
    def name(self) -> str:
        return "detekt"

    @property
    def languages(self) -> List[str]:
        return ["kotlin"]

    @property
    def supports_strict_mode(self) -> bool:
        return True

    def get_version(self) -> str:
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure detekt CLI JAR is available, downloading if needed.

        Returns:
            Path to the detekt-cli all-in-one JAR.

        Raises:
            FileNotFoundError: If Java is not available.
            RuntimeError: If detekt cannot be downloaded.
        """
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        jar_path = binary_dir / f"detekt-cli-{self._version}-all.jar"

        if jar_path.exists():
            LOGGER.debug(f"detekt JAR found at {jar_path}")
            return jar_path

        if not shutil.which("java"):
            raise FileNotFoundError(
                "Java is required to run detekt but was not found. "
                "Install a JDK (e.g., OpenJDK 11+) and ensure 'java' is in PATH."
            )

        LOGGER.info(f"Downloading detekt v{self._version}...")
        self._download_binary(binary_dir)

        if not jar_path.exists():
            raise RuntimeError(f"Failed to download detekt JAR to {jar_path}")

        return jar_path

    def _download_binary(self, dest_dir: Path) -> None:
        """Download detekt CLI JAR from GitHub releases."""
        url = (
            f"https://github.com/detekt/detekt/releases/download/"
            f"v{self._version}/detekt-cli-{self._version}-all.jar"
        )

        LOGGER.debug(f"Downloading from {url}")
        dest_dir.mkdir(parents=True, exist_ok=True)

        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        jar_path = dest_dir / f"detekt-cli-{self._version}-all.jar"

        tmp_file = tempfile.NamedTemporaryFile(suffix=".jar", delete=False)
        tmp_path = Path(tmp_file.name)
        try:
            with secure_urlopen(url) as response:  # nosec B310 nosemgrep
                tmp_file.write(response.read())
            tmp_file.close()
            shutil.move(str(tmp_path), str(jar_path))
            LOGGER.info(f"detekt v{self._version} installed to {jar_path}")
        finally:
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run detekt static analysis.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking issues.
        """
        try:
            jar_path = self.ensure_binary()
        except (FileNotFoundError, RuntimeError) as e:
            LOGGER.warning(str(e))
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
            )
            return []

        # Find Kotlin source directories
        source_dirs = self._find_source_directories(context)
        if not source_dirs:
            LOGGER.info("No Kotlin source directories found")
            return []

        # Find custom config
        config_file = self._find_config_file(context.project_root)

        # Build command
        with tempfile.NamedTemporaryFile(
            suffix=".xml", delete=False
        ) as report_file:
            report_path = Path(report_file.name)

        try:
            cmd = [
                "java",
                "-jar",
                str(jar_path),
                "--input",
                ",".join(str(d) for d in source_dirs),
                "--report",
                f"xml:{report_path}",
            ]

            if config_file:
                cmd.extend(["--config", config_file])

            LOGGER.debug(f"Running: {' '.join(cmd[:10])}...")

            try:
                run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="detekt",
                    stream_handler=context.stream_handler,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("detekt timed out after 300 seconds")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.TYPE_CHECKING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message="detekt timed out after 300 seconds",
                )
                return []
            except Exception as e:
                LOGGER.error(f"Failed to run detekt: {e}")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.TYPE_CHECKING,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Failed to run detekt: {e}",
                )
                return []

            # Parse XML report
            if report_path.exists():
                xml_output = report_path.read_text(encoding="utf-8")
                issues = self._parse_output(xml_output, context.project_root)
            else:
                issues = []

        finally:
            report_path.unlink(missing_ok=True)

        LOGGER.info(f"detekt found {len(issues)} issues")
        return issues

    def _find_source_directories(self, context: ScanContext) -> List[Path]:
        """Find Kotlin source directories."""
        source_dirs = []

        if context.paths:
            return [p for p in context.paths if p.exists()]

        standard_sources = [
            "src/main/kotlin",
            "src/test/kotlin",
            "src/main/java",
            "src/test/java",
            "src",
        ]

        for source in standard_sources:
            source_path = context.project_root / source
            if source_path.exists():
                source_dirs.append(source_path)

        return source_dirs

    def _find_config_file(self, project_root: Path) -> Optional[str]:
        """Find detekt configuration file."""
        custom_configs = [
            "detekt.yml",
            "detekt.yaml",
            ".detekt.yml",
            "config/detekt/detekt.yml",
            "config/detekt.yml",
        ]

        for config in custom_configs:
            config_path = project_root / config
            if config_path.exists():
                return str(config_path)

        return None

    def _parse_output(
        self,
        output: str,
        project_root: Path,
    ) -> List[UnifiedIssue]:
        """Parse detekt checkstyle-format XML output."""
        if not output.strip():
            return []

        try:
            root = ET.fromstring(output)
        except ET.ParseError as e:
            LOGGER.warning(f"Failed to parse detekt XML output: {e}")
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
        error_elem: Element,
        file_path: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert detekt error element to UnifiedIssue."""
        try:
            line = error_elem.get("line")
            column = error_elem.get("column")
            severity_str = error_elem.get("severity", "warning")
            message = error_elem.get("message", "")
            source = error_elem.get("source", "")

            # Extract rule name from source (e.g., "detekt.complexity.LongMethod")
            rule = source.split(".")[-1] if source else ""
            category = source.split(".")[-2] if source and "." in source else ""

            severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            path = Path(file_path)
            if not path.is_absolute():
                path = project_root / path

            line_num = int(line) if line else None
            col_num = int(column) if column else None

            category_desc = CATEGORY_DESCRIPTIONS.get(category, category)

            issue_id = self._generate_issue_id(
                rule, file_path, line_num, col_num, message
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="detekt",
                severity=severity,
                rule_id=rule or "unknown",
                title=f"[{rule}] {message}" if rule else message,
                description=message,
                documentation_url=f"https://detekt.dev/docs/rules/{category}#{rule.lower()}"
                if rule and category
                else None,
                file_path=path,
                line_start=line_num,
                line_end=line_num,
                column_start=col_num,
                fixable=False,
                metadata={
                    "source": source,
                    "category": category,
                    "category_description": category_desc,
                    "severity_raw": severity_str,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse detekt error: {e}")
            return None

    def _generate_issue_id(
        self,
        rule: str,
        file: str,
        line: Optional[int],
        column: Optional[int],
        message: str,
    ) -> str:
        content = f"{rule}:{file}:{line or 0}:{column or 0}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"detekt-{rule}-{hash_val}" if rule else f"detekt-{hash_val}"
