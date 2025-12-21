"""Trivy scanner plugin for SCA and container scanning."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tempfile
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
DEFAULT_VERSION = "0.68.1"

# Trivy severity mapping to unified severity
TRIVY_SEVERITY_MAP: Dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
    "UNKNOWN": Severity.INFO,
}


class TrivyScanner(ScannerPlugin):
    """Scanner plugin for Trivy (SCA and container scanning).

    Handles:
    - SCA scans via `trivy fs`
    - Container scans via `trivy image`

    Binary management:
    - Downloads from https://github.com/aquasecurity/trivy/releases/
    - Caches at ~/.lucidscan/bin/trivy/{version}/trivy
    - Uses cache directory at ~/.lucidscan/cache/trivy/
    """

    def __init__(self, version: str = DEFAULT_VERSION) -> None:
        self._version = version
        self._paths = LucidscanPaths.default()

    @property
    def name(self) -> str:
        return "trivy"

    @property
    def domains(self) -> List[ScanDomain]:
        return [ScanDomain.SCA, ScanDomain.CONTAINER]

    def get_version(self) -> str:
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure the Trivy binary is available, downloading if needed."""
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_path = binary_dir / "trivy"

        if binary_path.exists():
            LOGGER.debug(f"Trivy binary found at {binary_path}")
            return binary_path

        LOGGER.info(f"Downloading Trivy v{self._version}...")
        self._download_binary(binary_dir)

        if not binary_path.exists():
            raise RuntimeError(f"Failed to download Trivy binary to {binary_path}")

        return binary_path

    def _download_binary(self, dest_dir: Path) -> None:
        """Download and extract Trivy binary for current platform."""
        platform_info = get_platform_info()

        # Map platform to Trivy release naming
        os_name = {
            "darwin": "macOS",
            "linux": "Linux",
            "windows": "Windows",
        }.get(platform_info.os)

        arch_name = {
            "amd64": "64bit",
            "arm64": "ARM64",
        }.get(platform_info.arch)

        if not os_name or not arch_name:
            raise RuntimeError(
                f"Unsupported platform: {platform_info.os}-{platform_info.arch}"
            )

        # Construct download URL
        # Example: trivy_0.68.1_Linux-64bit.tar.gz
        filename = f"trivy_{self._version}_{os_name}-{arch_name}.tar.gz"
        url = f"https://github.com/aquasecurity/trivy/releases/download/v{self._version}/{filename}"

        LOGGER.debug(f"Downloading from {url}")

        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Download and extract
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            try:
                with urlopen(url) as response:
                    tmp_file.write(response.read())

                # Extract tarball
                with tarfile.open(tmp_path, "r:gz") as tar:
                    tar.extractall(path=dest_dir)

                # Make binary executable
                binary_path = dest_dir / "trivy"
                if binary_path.exists():
                    binary_path.chmod(0o755)
                    LOGGER.info(f"Trivy v{self._version} installed to {binary_path}")

            finally:
                tmp_path.unlink(missing_ok=True)

    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        """Execute Trivy scan and return normalized issues.

        Args:
            context: Scan context containing target paths and configuration.

        Returns:
            List of unified issues found during the scan.
        """
        binary = self.ensure_binary()
        cache_dir = self._paths.plugin_cache_dir(self.name)
        cache_dir.mkdir(parents=True, exist_ok=True)

        issues: List[UnifiedIssue] = []

        # Determine which scan types to run based on enabled domains
        if ScanDomain.SCA in context.enabled_domains:
            issues.extend(self._run_fs_scan(binary, context, cache_dir))

        if ScanDomain.CONTAINER in context.enabled_domains:
            # Container scanning uses image targets from config
            container_config = context.get_scanner_options("container")
            image_targets = container_config.get("images", [])
            for image in image_targets:
                issues.extend(self._run_image_scan(binary, image, cache_dir))

        return issues

    def _run_fs_scan(
        self, binary: Path, context: ScanContext, cache_dir: Path
    ) -> List[UnifiedIssue]:
        """Run trivy fs scan for SCA.

        Args:
            binary: Path to the Trivy binary.
            context: Scan context with project root and configuration.
            cache_dir: Path to the Trivy cache directory.

        Returns:
            List of unified issues from the filesystem scan.
        """
        # Get SCA-specific config options
        sca_config = context.get_scanner_options("sca")

        cmd = [
            str(binary),
            "fs",
            "--cache-dir", str(cache_dir),
            "--format", "json",
            "--quiet",
            "--scanners", "vuln",
        ]

        # Apply config options
        if sca_config.get("ignore_unfixed", False):
            cmd.append("--ignore-unfixed")

        if sca_config.get("skip_db_update", False):
            cmd.append("--skip-db-update")

        severity = sca_config.get("severity")
        if severity and isinstance(severity, list):
            cmd.extend(["--severity", ",".join(severity)])

        # Apply ignore patterns from .lucidscanignore and config
        exclude_patterns = context.get_exclude_patterns()
        for pattern in exclude_patterns:
            # Trivy uses --skip-dirs for directory patterns
            if pattern.endswith("/") or pattern.endswith("/**"):
                dir_pattern = pattern.rstrip("/*")
                cmd.extend(["--skip-dirs", dir_pattern])
            else:
                # For file patterns, use --skip-files
                cmd.extend(["--skip-files", pattern])

        cmd.append(str(context.project_root))

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0 and result.stderr:
                LOGGER.warning(f"Trivy stderr: {result.stderr}")

            if not result.stdout.strip():
                LOGGER.debug("Trivy returned empty output")
                return []

            return self._parse_trivy_json(result.stdout, ScanDomain.SCA)

        except Exception as e:
            LOGGER.error(f"Trivy fs scan failed: {e}")
            return []

    def _run_image_scan(
        self, binary: Path, image: str, cache_dir: Path
    ) -> List[UnifiedIssue]:
        """Run trivy image scan for container scanning.

        Args:
            binary: Path to the Trivy binary.
            image: Container image reference (e.g., 'nginx:latest').
            cache_dir: Path to the Trivy cache directory.

        Returns:
            List of unified issues from the container scan.
        """
        cmd = [
            str(binary),
            "image",
            "--cache-dir", str(cache_dir),
            "--format", "json",
            "--quiet",
            "--scanners", "vuln",
            image,
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0 and result.stderr:
                LOGGER.warning(f"Trivy stderr: {result.stderr}")

            if not result.stdout.strip():
                LOGGER.debug(f"Trivy returned empty output for image {image}")
                return []

            return self._parse_trivy_json(
                result.stdout, ScanDomain.CONTAINER, image_ref=image
            )

        except Exception as e:
            LOGGER.error(f"Trivy image scan failed for {image}: {e}")
            return []

    def _parse_trivy_json(
        self,
        json_output: str,
        domain: ScanDomain,
        image_ref: Optional[str] = None,
    ) -> List[UnifiedIssue]:
        """Parse Trivy JSON output and convert to UnifiedIssue list.

        Args:
            json_output: Raw JSON string from Trivy.
            domain: The scan domain (SCA or CONTAINER).
            image_ref: Container image reference (for container scans).

        Returns:
            List of unified issues parsed from the JSON.
        """
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse Trivy JSON: {e}")
            return []

        issues: List[UnifiedIssue] = []

        # Trivy output structure: {"Results": [...]}
        results = data.get("Results", [])

        for result in results:
            target = result.get("Target", "unknown")
            target_type = result.get("Type", "unknown")
            vulnerabilities = result.get("Vulnerabilities") or []

            for vuln in vulnerabilities:
                issue = self._vuln_to_unified_issue(
                    vuln, domain, target, target_type, image_ref
                )
                if issue:
                    issues.append(issue)

        LOGGER.debug(f"Parsed {len(issues)} issues from Trivy output")
        return issues

    def _vuln_to_unified_issue(
        self,
        vuln: Dict[str, Any],
        domain: ScanDomain,
        target: str,
        target_type: str,
        image_ref: Optional[str] = None,
    ) -> Optional[UnifiedIssue]:
        """Convert a single Trivy vulnerability to a UnifiedIssue.

        Args:
            vuln: Vulnerability dict from Trivy JSON.
            domain: The scan domain.
            target: Target file or layer.
            target_type: Type of target (e.g., 'npm', 'pip', 'alpine').
            image_ref: Container image reference (for container scans).

        Returns:
            UnifiedIssue or None if conversion fails.
        """
        try:
            vuln_id = vuln.get("VulnerabilityID", "UNKNOWN")
            pkg_name = vuln.get("PkgName", "unknown")
            installed_version = vuln.get("InstalledVersion", "unknown")
            fixed_version = vuln.get("FixedVersion", "")
            severity_str = vuln.get("Severity", "UNKNOWN").upper()
            title = vuln.get("Title", f"Vulnerability in {pkg_name}")
            description = vuln.get("Description", "No description available.")

            # Map severity
            severity = TRIVY_SEVERITY_MAP.get(severity_str, Severity.INFO)

            # Generate deterministic issue ID
            issue_id = self._generate_issue_id(
                vuln_id, pkg_name, installed_version, target
            )

            # Build dependency string
            dependency = f"{pkg_name}@{installed_version}"
            if target_type:
                dependency = f"{dependency} ({target_type})"

            # Build recommendation
            recommendation = None
            if fixed_version:
                recommendation = f"Upgrade {pkg_name} to version {fixed_version}"

            # Determine file path
            file_path = Path(target) if target and domain == ScanDomain.SCA else None

            # Build scanner metadata with raw Trivy data
            scanner_metadata: Dict[str, Any] = {
                "vulnerability_id": vuln_id,
                "pkg_name": pkg_name,
                "installed_version": installed_version,
                "fixed_version": fixed_version,
                "target": target,
                "target_type": target_type,
                "references": vuln.get("References", []),
                "cvss": vuln.get("CVSS", {}),
                "cwe_ids": vuln.get("CweIDs", []),
                "published_date": vuln.get("PublishedDate"),
                "last_modified_date": vuln.get("LastModifiedDate"),
            }

            if image_ref:
                scanner_metadata["image_ref"] = image_ref

            return UnifiedIssue(
                id=issue_id,
                scanner=domain,
                source_tool="trivy",
                severity=severity,
                title=f"{vuln_id}: {title}",
                description=description,
                file_path=file_path,
                dependency=dependency,
                recommendation=recommendation,
                scanner_metadata=scanner_metadata,
            )

        except Exception as e:
            LOGGER.warning(f"Failed to convert vulnerability to UnifiedIssue: {e}")
            return None

    def _generate_issue_id(
        self,
        vuln_id: str,
        pkg_name: str,
        version: str,
        target: str,
    ) -> str:
        """Generate a deterministic issue ID for deduplication.

        Args:
            vuln_id: Vulnerability ID (e.g., CVE-2021-1234).
            pkg_name: Package name.
            version: Installed version.
            target: Target file or layer.

        Returns:
            A stable hash-based ID string.
        """
        components = f"trivy:{vuln_id}:{pkg_name}:{version}:{target}"
        hash_digest = hashlib.sha256(components.encode()).hexdigest()[:16]
        return f"trivy-{hash_digest}"
