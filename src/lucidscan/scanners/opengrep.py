"""OpenGrep scanner plugin for SAST (Static Application Security Testing)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen

from lucidscan.scanners.base import ScannerPlugin
from lucidscan.core.models import ScanContext, ScanDomain, Severity, UnifiedIssue
from lucidscan.bootstrap.paths import LucidscanPaths
from lucidscan.bootstrap.platform import get_platform_info
from lucidscan.core.logging import get_logger

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidscan.scanners]
DEFAULT_VERSION = "1.12.1"

# OpenGrep severity mapping to unified severity
# OpenGrep/Semgrep uses: ERROR, WARNING, INFO
OPENGREP_SEVERITY_MAP: Dict[str, Severity] = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
    # Additional mappings for rule metadata
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}


class OpenGrepScanner(ScannerPlugin):
    """Scanner plugin for OpenGrep (SAST).

    Handles:
    - Static application security testing via `opengrep scan`

    Binary management:
    - Downloads from https://github.com/opengrep/opengrep/releases/
    - Caches at ~/.lucidscan/bin/opengrep/{version}/opengrep
    """

    def __init__(self, version: str = DEFAULT_VERSION) -> None:
        self._version = version
        self._paths = LucidscanPaths.default()

    @property
    def name(self) -> str:
        return "opengrep"

    @property
    def domains(self) -> List[ScanDomain]:
        return [ScanDomain.SAST]

    def get_version(self) -> str:
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure the OpenGrep binary is available, downloading if needed."""
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_name = self._get_binary_name()
        binary_path = binary_dir / binary_name

        if binary_path.exists():
            LOGGER.debug(f"OpenGrep binary found at {binary_path}")
            return binary_path

        LOGGER.info(f"Downloading OpenGrep v{self._version}...")
        self._download_binary(binary_dir)

        if not binary_path.exists():
            raise RuntimeError(f"Failed to download OpenGrep binary to {binary_path}")

        return binary_path

    def _get_binary_name(self) -> str:
        """Get the binary name for the current platform."""
        platform_info = get_platform_info()
        if platform_info.os == "windows":
            return "opengrep.exe"
        return "opengrep"

    def _download_binary(self, dest_dir: Path) -> None:
        """Download OpenGrep binary for current platform."""
        platform_info = get_platform_info()

        # Map platform to OpenGrep release naming
        # OpenGrep uses: opengrep_manylinux_x86, opengrep_osx_arm64, etc.
        if platform_info.os == "linux":
            os_name = "manylinux"
            arch_name = "x86" if platform_info.arch == "amd64" else "aarch64"
            filename = f"opengrep_{os_name}_{arch_name}"
        elif platform_info.os == "darwin":
            os_name = "osx"
            arch_name = "x86" if platform_info.arch == "amd64" else "arm64"
            filename = f"opengrep_{os_name}_{arch_name}"
        elif platform_info.os == "windows":
            filename = "opengrep_windows_x86.exe"
        else:
            raise RuntimeError(
                f"Unsupported platform: {platform_info.os}-{platform_info.arch}"
            )

        # Construct download URL
        url = f"https://github.com/opengrep/opengrep/releases/download/v{self._version}/{filename}"

        LOGGER.debug(f"Downloading from {url}")

        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Determine destination path
        binary_name = self._get_binary_name()
        binary_path = dest_dir / binary_name

        # Download binary directly (not an archive)
        try:
            with urlopen(url) as response:
                binary_path.write_bytes(response.read())

            # Make binary executable (not needed on Windows)
            if platform_info.os != "windows":
                binary_path.chmod(0o755)

            LOGGER.info(f"OpenGrep v{self._version} installed to {binary_path}")

        except Exception as e:
            # Clean up partial download
            if binary_path.exists():
                binary_path.unlink()
            raise RuntimeError(f"Failed to download OpenGrep: {e}") from e

    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        """Execute OpenGrep scan and return normalized issues.

        Args:
            context: Scan context containing target paths and configuration.

        Returns:
            List of unified issues found during the scan.
        """
        if ScanDomain.SAST not in context.enabled_domains:
            return []

        binary = self.ensure_binary()
        return self._run_sast_scan(binary, context)

    def _run_sast_scan(
        self, binary: Path, context: ScanContext
    ) -> List[UnifiedIssue]:
        """Run OpenGrep SAST scan.

        Args:
            binary: Path to the OpenGrep binary.
            context: Scan context with project root and configuration.

        Returns:
            List of unified issues from the SAST scan.
        """
        # Get SAST-specific config options
        sast_config = context.get_scanner_options("sast")

        # Get ruleset configuration
        ruleset_list = sast_config.get("ruleset", ["auto"])
        if isinstance(ruleset_list, list) and ruleset_list:
            ruleset = ruleset_list[0]  # Use first ruleset
        else:
            ruleset = "auto"

        cmd = [
            str(binary),
            "scan",
            "--json",
            "--quiet",
        ]

        # Add timeout if specified
        timeout = sast_config.get("timeout")
        if timeout:
            cmd.extend(["--timeout", str(timeout)])

        # Add ruleset if specified (auto uses default rules)
        if ruleset and ruleset != "auto":
            cmd.extend(["--config", ruleset])
        else:
            # Use default rules - OpenGrep auto-detects without explicit config
            cmd.extend(["--config", "auto"])

        # Apply ignore patterns from .lucidscanignore and config
        exclude_patterns = context.get_exclude_patterns()
        for pattern in exclude_patterns:
            cmd.extend(["--exclude", pattern])

        # Add target path
        cmd.append(str(context.project_root))

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                env=self._get_scan_env(),
            )

            # OpenGrep returns non-zero exit code when findings exist
            # This is expected behavior, not an error
            if result.returncode not in (0, 1) and result.stderr:
                LOGGER.warning(f"OpenGrep stderr: {result.stderr}")

            if not result.stdout.strip():
                LOGGER.debug("OpenGrep returned empty output")
                return []

            return self._parse_opengrep_json(result.stdout, context.project_root)

        except Exception as e:
            LOGGER.error(f"OpenGrep scan failed: {e}")
            return []

    def _get_scan_env(self) -> Dict[str, str]:
        """Get environment variables for the scan process."""
        env = os.environ.copy()
        # Disable telemetry/metrics
        env["SEMGREP_SEND_METRICS"] = "off"
        env["OPENGREP_SEND_METRICS"] = "off"
        return env

    def _parse_opengrep_json(
        self,
        json_output: str,
        project_root: Path,
    ) -> List[UnifiedIssue]:
        """Parse OpenGrep JSON output and convert to UnifiedIssue list.

        Args:
            json_output: Raw JSON string from OpenGrep.
            project_root: Project root path for relative path resolution.

        Returns:
            List of unified issues parsed from the JSON.
        """
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse OpenGrep JSON: {e}")
            return []

        issues: List[UnifiedIssue] = []

        # OpenGrep output structure: {"results": [...], "errors": [...]}
        results = data.get("results", [])

        for result in results:
            issue = self._result_to_unified_issue(result, project_root)
            if issue:
                issues.append(issue)

        # Log any errors from the scan
        errors = data.get("errors", [])
        for error in errors:
            LOGGER.warning(f"OpenGrep error: {error}")

        LOGGER.debug(f"Parsed {len(issues)} issues from OpenGrep output")
        return issues

    def _result_to_unified_issue(
        self,
        result: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a single OpenGrep result to a UnifiedIssue.

        Args:
            result: Result dict from OpenGrep JSON.
            project_root: Project root path for relative path resolution.

        Returns:
            UnifiedIssue or None if conversion fails.
        """
        try:
            # Extract basic fields
            rule_id = result.get("check_id", "unknown")
            path = result.get("path", "unknown")
            message = result.get("extra", {}).get("message", "No message")

            # Extract location information
            start = result.get("start", {})
            end = result.get("end", {})
            line_start = start.get("line", 1)
            line_end = end.get("line", line_start)
            col_start = start.get("col", 1)
            col_end = end.get("col", col_start)

            # Extract severity from extra metadata
            extra = result.get("extra", {})
            severity_str = extra.get("severity", "WARNING").upper()

            # Also check metadata for severity
            metadata = extra.get("metadata", {})
            if "severity" in metadata:
                severity_str = metadata["severity"].upper()

            severity = OPENGREP_SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            # Extract code snippet (the matched lines)
            lines = extra.get("lines", "")
            code_snippet = lines if isinstance(lines, str) else str(lines)

            # Generate deterministic issue ID
            issue_id = self._generate_issue_id(rule_id, path, line_start, col_start)

            # Build file path (relative or absolute)
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = project_root / path

            # Build title from rule ID
            title = self._format_title(rule_id, message)

            # Build description
            description = message
            if "metavars" in extra:
                # Add context about matched variables
                metavars = extra["metavars"]
                if metavars:
                    description += f"\n\nMatched values: {json.dumps(metavars, indent=2)}"

            # Build recommendation
            recommendation = metadata.get("fix", None)
            if not recommendation and "fix" in extra:
                recommendation = extra["fix"]

            # Build scanner metadata with raw OpenGrep data
            scanner_metadata: Dict[str, Any] = {
                "rule_id": rule_id,
                "line_start": line_start,
                "line_end": line_end,
                "col_start": col_start,
                "col_end": col_end,
                "severity_raw": severity_str,
                "fingerprint": result.get("extra", {}).get("fingerprint"),
                "engine_kind": extra.get("engine_kind"),
                "validation_state": extra.get("validation_state"),
            }

            # Add metadata fields if present
            if metadata:
                scanner_metadata["metadata"] = {
                    "cwe": metadata.get("cwe", []),
                    "owasp": metadata.get("owasp", []),
                    "references": metadata.get("references", []),
                    "category": metadata.get("category"),
                    "technology": metadata.get("technology", []),
                    "confidence": metadata.get("confidence"),
                }

            return UnifiedIssue(
                id=issue_id,
                scanner=ScanDomain.SAST,
                source_tool="opengrep",
                severity=severity,
                title=title,
                description=description,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                code_snippet=code_snippet,
                recommendation=recommendation,
                scanner_metadata=scanner_metadata,
            )

        except Exception as e:
            LOGGER.warning(f"Failed to convert OpenGrep result to UnifiedIssue: {e}")
            return None

    def _format_title(self, rule_id: str, message: str) -> str:
        """Format a human-readable title from rule ID and message.

        Args:
            rule_id: OpenGrep rule identifier.
            message: Rule message.

        Returns:
            Formatted title string.
        """
        # Shorten message if too long
        max_message_len = 80
        if len(message) > max_message_len:
            message = message[:max_message_len - 3] + "..."

        # Use rule ID as prefix for clarity
        return f"{rule_id}: {message}"

    def _generate_issue_id(
        self,
        rule_id: str,
        path: str,
        line: int,
        col: int,
    ) -> str:
        """Generate a deterministic issue ID for deduplication.

        Args:
            rule_id: OpenGrep rule identifier.
            path: File path.
            line: Line number.
            col: Column number.

        Returns:
            A stable hash-based ID string.
        """
        components = f"opengrep:{rule_id}:{path}:{line}:{col}"
        hash_digest = hashlib.sha256(components.encode()).hexdigest()[:16]
        return f"opengrep-{hash_digest}"
