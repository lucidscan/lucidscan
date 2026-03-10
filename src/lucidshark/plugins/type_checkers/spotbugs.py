"""SpotBugs type checker plugin.

SpotBugs is a static analysis tool for finding bugs in Java programs.
https://spotbugs.github.io/

SpotBugs is a managed tool - LucidShark auto-downloads it on first use.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import os
import shutil
import subprocess
import tempfile
import zipfile
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
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("spotbugs")

# SpotBugs priority to severity mapping
# 1 = High, 2 = Medium, 3 = Low, 4+ = Info
PRIORITY_SEVERITY_MAP = {
    1: Severity.HIGH,
    2: Severity.MEDIUM,
    3: Severity.LOW,
}

# SpotBugs category descriptions
CATEGORY_DESCRIPTIONS = {
    "BAD_PRACTICE": "Bad coding practice",
    "CORRECTNESS": "Probable bug - an apparent coding mistake",
    "MT_CORRECTNESS": "Multithreaded correctness issue",
    "PERFORMANCE": "Performance issue",
    "SECURITY": "Security vulnerability",
    "STYLE": "Dodgy code - code that is confusing or anomalous",
    "MALICIOUS_CODE": "Malicious code vulnerability",
    "I18N": "Internationalization issue",
    "EXPERIMENTAL": "Experimental warning",
}


class SpotBugsChecker(TypeCheckerPlugin):
    """SpotBugs type checker plugin for Java static analysis.

    SpotBugs is a managed tool - it is automatically downloaded from GitHub
    releases on first use. The binary is cached at:
    `.lucidshark/bin/spotbugs/{version}/spotbugs-{version}/`
    """

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ):
        """Initialize SpotBugsChecker.

        Args:
            version: SpotBugs version to use.
            project_root: Optional project root for tool installation.
        """
        self._project_root = project_root
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
        else:
            self._paths = LucidsharkPaths.default()

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "spotbugs"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["java"]

    @property
    def supports_strict_mode(self) -> bool:
        """SpotBugs supports effort levels (similar to strict mode)."""
        return True

    def get_version(self) -> str:
        """Get SpotBugs version."""
        return self._version

    def _check_java_available(self) -> Optional[Path]:
        """Check if Java is available.

        Returns:
            Path to java binary or None if not found.
        """
        java_path = shutil.which("java")
        return Path(java_path) if java_path else None

    def ensure_binary(self) -> Path:
        """Ensure SpotBugs is available, downloading if needed.

        SpotBugs is a managed tool - it is automatically downloaded from GitHub
        releases on first use. The binary is cached at:
        `.lucidshark/bin/spotbugs/{version}/spotbugs-{version}/`

        Returns:
            Path to SpotBugs directory containing the lib folder with spotbugs.jar.

        Raises:
            FileNotFoundError: If Java is not installed.
            RuntimeError: If SpotBugs cannot be downloaded.
        """
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        spotbugs_dir = binary_dir / f"spotbugs-{self._version}"
        jar_path = spotbugs_dir / "lib" / "spotbugs.jar"

        if jar_path.exists():
            LOGGER.debug(f"SpotBugs found at {spotbugs_dir}")
            return spotbugs_dir

        # Verify Java is available before downloading
        if not shutil.which("java"):
            raise FileNotFoundError(
                "Java is required to run SpotBugs but was not found. "
                "Install a JDK (e.g., OpenJDK 11+) and ensure 'java' is in PATH."
            )

        LOGGER.info(f"Downloading SpotBugs v{self._version}...")
        self._download_binary(binary_dir)

        if not jar_path.exists():
            raise RuntimeError(f"Failed to download SpotBugs to {jar_path}")

        return spotbugs_dir

    def _download_binary(self, dest_dir: Path) -> None:
        """Download and extract SpotBugs from GitHub releases.

        Args:
            dest_dir: Directory to extract SpotBugs into.
        """
        # Construct download URL
        # Format: https://github.com/spotbugs/spotbugs/releases/download/{VERSION}/spotbugs-{VERSION}.zip
        url = (
            f"https://github.com/spotbugs/spotbugs/releases/download/"
            f"{self._version}/spotbugs-{self._version}.zip"
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

            spotbugs_dir = dest_dir / f"spotbugs-{self._version}"
            LOGGER.info(f"SpotBugs v{self._version} installed to {spotbugs_dir}")

        finally:
            # Ensure file is closed before attempting to delete
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

    def _find_class_directories(self, project_root: Path) -> List[Path]:
        """Find compiled class directories in a Java project.

        Args:
            project_root: Project root directory.

        Returns:
            List of directories containing .class files.
        """
        class_dirs = []

        # Maven standard directories
        maven_targets = [
            "target/classes",
            "target/test-classes",
        ]

        # Gradle standard directories
        gradle_targets = [
            "build/classes/java/main",
            "build/classes/java/test",
            "build/classes/kotlin/main",
            "build/classes/kotlin/test",
        ]

        # Check Maven directories
        for target in maven_targets:
            target_path = project_root / target
            if target_path.exists():
                class_dirs.append(target_path)

        # Check Gradle directories
        for target in gradle_targets:
            target_path = project_root / target
            if target_path.exists():
                class_dirs.append(target_path)

        # Check for multi-module projects
        for child in project_root.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                for target in maven_targets + gradle_targets:
                    target_path = child / target
                    if target_path.exists():
                        class_dirs.append(target_path)

        return class_dirs

    def _find_source_directories(self, project_root: Path) -> List[Path]:
        """Find source directories in a Java project.

        Args:
            project_root: Project root directory.

        Returns:
            List of source directories.
        """
        source_dirs = []

        # Standard source directories
        standard_sources = [
            "src/main/java",
            "src/test/java",
            "src",
        ]

        for source in standard_sources:
            source_path = project_root / source
            if source_path.exists():
                source_dirs.append(source_path)

        return source_dirs

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run SpotBugs static analysis.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking issues.
        """
        try:
            spotbugs_dir = self.ensure_binary()
        except (FileNotFoundError, RuntimeError) as e:
            LOGGER.warning(str(e))
            return []

        java_path = self._check_java_available()
        if not java_path:
            LOGGER.warning("Java not found, skipping SpotBugs")
            return []

        # Find compiled class directories
        class_dirs = self._find_class_directories(context.project_root)
        if not class_dirs:
            LOGGER.warning(
                "No compiled Java classes found. "
                "Run 'mvn compile' or 'gradle build' first."
            )
            return []

        # Find source directories for better reporting
        source_dirs = self._find_source_directories(context.project_root)

        # Build command
        spotbugs_jar = spotbugs_dir / "lib" / "spotbugs.jar"
        cmd = [
            str(java_path),
            "-jar",
            str(spotbugs_jar),
            "-textui",
            "-xml:withMessages",
            "-effort:default",
        ]

        # Add exclude filter (custom or bundled default)
        exclude_filter = self._find_exclude_filter(context.project_root)
        if exclude_filter:
            cmd.extend(["-exclude", exclude_filter])

        # Add source path for better reporting
        if source_dirs:
            cmd.extend(["-sourcepath", os.pathsep.join(str(d) for d in source_dirs)])

        # Add auxiliary classpath if available (for better analysis)
        aux_classpath = self._find_aux_classpath(context.project_root)
        if aux_classpath:
            cmd.extend(["-auxclasspath", aux_classpath])

        # Add class directories to analyze
        for class_dir in class_dirs:
            cmd.append(str(class_dir))

        LOGGER.debug(f"Running: {' '.join(cmd[:10])}...")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="spotbugs",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("SpotBugs timed out after 300 seconds")
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run SpotBugs: {e}")
            return []

        # Parse XML output
        issues = self._parse_output(result.stdout, context.project_root, source_dirs)

        LOGGER.info(f"SpotBugs found {len(issues)} issues")
        return issues

    def _find_aux_classpath(self, project_root: Path) -> Optional[str]:
        """Find auxiliary classpath (dependencies) for better analysis.

        Args:
            project_root: Project root directory.

        Returns:
            Classpath string or None.
        """
        jars: List[Path] = []

        # Maven dependencies
        m2_repo = project_root / "target" / "dependency"
        if m2_repo.exists():
            jars.extend(m2_repo.glob("*.jar"))

        # Gradle dependencies (cached)
        gradle_cache = project_root / "build" / "libs"
        if gradle_cache.exists():
            jars.extend(gradle_cache.glob("*.jar"))

        if jars:
            return os.pathsep.join(str(j) for j in jars)
        return None

    def _find_exclude_filter(self, project_root: Path) -> Optional[str]:
        """Find SpotBugs exclude filter file.

        Searches for custom filter files in common locations, falling back
        to a bundled default filter that excludes noisy/low-value rules.

        Args:
            project_root: Project root directory.

        Returns:
            Path to exclude filter file, or None if unavailable.
        """
        # Check for custom filter files
        custom_configs = [
            "spotbugs-exclude.xml",
            "spotbugs-filter.xml",
            ".spotbugs/exclude.xml",
            "config/spotbugs/exclude.xml",
            "config/spotbugs/spotbugs-exclude.xml",
        ]

        for config in custom_configs:
            config_path = project_root / config
            if config_path.exists():
                LOGGER.debug(f"Using custom SpotBugs filter: {config_path}")
                return str(config_path)

        # Use bundled default exclude filter
        # Cache it to .lucidshark/config since SpotBugs needs a real file path
        cached_filter = self._paths.config_dir / "spotbugs-exclude.xml"
        if cached_filter.exists():
            return str(cached_filter)

        try:
            filter_resource = importlib.resources.files("lucidshark.data").joinpath(
                "spotbugs-exclude.xml"
            )
            filter_content = filter_resource.read_text(encoding="utf-8")

            # Cache to .lucidshark/config for SpotBugs to access
            cached_filter.parent.mkdir(parents=True, exist_ok=True)
            cached_filter.write_text(filter_content, encoding="utf-8")
            LOGGER.debug(f"Cached SpotBugs exclude filter to {cached_filter}")
            return str(cached_filter)
        except (ModuleNotFoundError, FileNotFoundError, TypeError) as e:
            # No filter available - SpotBugs will use all rules
            LOGGER.debug(f"Bundled SpotBugs filter not found ({e}), running without filter")
            return None

    def _parse_output(
        self,
        output: str,
        project_root: Path,
        source_dirs: List[Path],
    ) -> List[UnifiedIssue]:
        """Parse SpotBugs XML output.

        Args:
            output: XML output from SpotBugs.
            project_root: Project root directory.
            source_dirs: Source directories for path resolution.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        # Find the XML part (SpotBugs outputs some text before XML)
        xml_start = output.find("<?xml")
        if xml_start == -1:
            LOGGER.warning("No XML output from SpotBugs")
            return []

        xml_output = output[xml_start:]

        try:
            root = ET.fromstring(xml_output)
        except ET.ParseError as e:
            LOGGER.warning(f"Failed to parse SpotBugs XML output: {e}")
            return []

        issues = []

        for bug_instance in root.findall(".//BugInstance"):
            issue = self._bug_to_issue(bug_instance, project_root, source_dirs)
            if issue:
                issues.append(issue)

        return issues

    def _bug_to_issue(
        self,
        bug_elem: Element,
        project_root: Path,
        source_dirs: List[Path],
    ) -> Optional[UnifiedIssue]:
        """Convert SpotBugs BugInstance to UnifiedIssue.

        Args:
            bug_elem: XML BugInstance element.
            project_root: Project root directory.
            source_dirs: Source directories for path resolution.

        Returns:
            UnifiedIssue or None.
        """
        try:
            bug_type = bug_elem.get("type", "")
            category = bug_elem.get("category", "")
            priority = int(bug_elem.get("priority", "3"))
            rank = int(bug_elem.get("rank", "20"))

            # Get message
            long_message = bug_elem.find("LongMessage")
            short_message = bug_elem.find("ShortMessage")
            message = ""
            if long_message is not None and long_message.text:
                message = long_message.text
            elif short_message is not None and short_message.text:
                message = short_message.text

            # Get source location
            source_line = bug_elem.find(".//SourceLine")
            file_path = None
            line_start = None
            line_end = None

            if source_line is not None:
                source_path = source_line.get("sourcepath", "")
                start = source_line.get("start")
                end = source_line.get("end")

                if source_path:
                    # Try to find the file in source directories
                    for src_dir in source_dirs:
                        potential_path = src_dir / source_path
                        if potential_path.exists():
                            file_path = potential_path
                            break

                    # Fallback: just use relative path
                    if not file_path:
                        file_path = project_root / "src" / "main" / "java" / source_path

                if start:
                    line_start = int(start)
                if end:
                    line_end = int(end)

            # Get severity from priority
            severity = PRIORITY_SEVERITY_MAP.get(priority, Severity.INFO)

            # Adjust severity based on rank (scariness)
            # Ranks 1-4 are scariest, 5-9 are scary, 10-14 troubling, 15-20 of concern
            if rank <= 4 and severity != Severity.HIGH:
                severity = Severity.HIGH
            elif rank <= 9 and severity == Severity.LOW:
                severity = Severity.MEDIUM

            # Get category description
            category_desc = CATEGORY_DESCRIPTIONS.get(category, category)

            # Generate deterministic ID
            issue_id = self._generate_issue_id(
                bug_type,
                str(file_path) if file_path else "",
                line_start,
                message,
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="spotbugs",
                severity=severity,
                rule_id=bug_type,
                title=f"[{bug_type}] {message[:100]}"
                if len(message) > 100
                else f"[{bug_type}] {message}",
                description=message,
                documentation_url=f"https://spotbugs.readthedocs.io/en/stable/bugDescriptions.html#{bug_type}",
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                fixable=False,
                metadata={
                    "category": category,
                    "category_description": category_desc,
                    "priority": priority,
                    "rank": rank,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse SpotBugs bug instance: {e}")
            return None

    def _generate_issue_id(
        self,
        bug_type: str,
        file: str,
        line: Optional[int],
        message: str,
    ) -> str:
        """Generate deterministic issue ID.

        Args:
            bug_type: Bug type identifier.
            file: File path.
            line: Line number.
            message: Error message.

        Returns:
            Unique issue ID.
        """
        content = f"{bug_type}:{file}:{line or 0}:{message[:50]}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"spotbugs-{bug_type}-{hash_val}" if bug_type else f"spotbugs-{hash_val}"
