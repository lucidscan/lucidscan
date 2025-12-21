"""Checkov scanner plugin for IaC (Infrastructure as Code) scanning."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidscan.scanners.base import ScannerPlugin
from lucidscan.core.models import ScanContext, ScanDomain, Severity, UnifiedIssue
from lucidscan.bootstrap.paths import LucidscanPaths
from lucidscan.core.logging import get_logger

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidscan.scanners]
DEFAULT_VERSION = "3.2.495"

# Checkov severity mapping to unified severity
CHECKOV_SEVERITY_MAP: Dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
    "INFO": Severity.INFO,
    "UNKNOWN": Severity.INFO,
}


class CheckovScanner(ScannerPlugin):
    """Scanner plugin for Checkov (IaC scanning).

    Handles:
    - Infrastructure-as-Code scanning for Terraform, Kubernetes,
      CloudFormation, ARM templates, and more via `checkov`

    Binary management:
    - Installs via pip into a virtual environment
    - Caches at ~/.lucidscan/bin/checkov/{version}/venv/
    """

    def __init__(self, version: str = DEFAULT_VERSION) -> None:
        self._version = version
        self._paths = LucidscanPaths.default()

    @property
    def name(self) -> str:
        return "checkov"

    @property
    def domains(self) -> List[ScanDomain]:
        return [ScanDomain.IAC]

    def get_version(self) -> str:
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure the Checkov binary is available, installing if needed.

        Checkov is a Python package, so we install it into a dedicated
        virtual environment to avoid conflicts with system packages.

        Returns:
            Path to the checkov binary in the virtual environment.
        """
        venv_dir = self._paths.plugin_bin_dir(self.name, self._version) / "venv"
        binary_path = self._get_binary_path(venv_dir)

        if binary_path.exists():
            LOGGER.debug(f"Checkov binary found at {binary_path}")
            return binary_path

        LOGGER.info(f"Installing Checkov v{self._version}...")
        self._install_checkov(venv_dir)

        if not binary_path.exists():
            raise RuntimeError(f"Failed to install Checkov to {binary_path}")

        return binary_path

    def _get_binary_path(self, venv_dir: Path) -> Path:
        """Get the path to the checkov binary in the virtual environment."""
        # On Windows, binaries are in Scripts/, on Unix in bin/
        if sys.platform == "win32":
            return venv_dir / "Scripts" / "checkov.exe"
        return venv_dir / "bin" / "checkov"

    def _get_pip_path(self, venv_dir: Path) -> Path:
        """Get the path to pip in the virtual environment."""
        if sys.platform == "win32":
            return venv_dir / "Scripts" / "pip.exe"
        return venv_dir / "bin" / "pip"

    def _install_checkov(self, venv_dir: Path) -> None:
        """Install Checkov into a virtual environment.

        Args:
            venv_dir: Path to the virtual environment directory.
        """
        # Create parent directories
        venv_dir.parent.mkdir(parents=True, exist_ok=True)

        # Create virtual environment
        LOGGER.debug(f"Creating virtual environment at {venv_dir}")
        venv.create(venv_dir, with_pip=True)

        # Install checkov
        pip_path = self._get_pip_path(venv_dir)

        try:
            # Upgrade pip first to avoid issues
            subprocess.run(
                [str(pip_path), "install", "--upgrade", "pip"],
                capture_output=True,
                check=True,
            )

            # Install specific version of checkov
            package_spec = f"checkov=={self._version}"
            LOGGER.debug(f"Installing {package_spec}")

            result = subprocess.run(
                [str(pip_path), "install", package_spec],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                LOGGER.error(f"pip install failed: {result.stderr}")
                raise RuntimeError(f"Failed to install checkov: {result.stderr}")

            LOGGER.info(f"Checkov v{self._version} installed to {venv_dir}")

        except subprocess.CalledProcessError as e:
            # Clean up failed installation
            if venv_dir.exists():
                import shutil
                shutil.rmtree(venv_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to install Checkov: {e}") from e

    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        """Execute Checkov scan and return normalized issues.

        Args:
            context: Scan context containing target paths and configuration.

        Returns:
            List of unified issues found during the scan.
        """
        if ScanDomain.IAC not in context.enabled_domains:
            return []

        binary = self.ensure_binary()
        return self._run_iac_scan(binary, context)

    def _run_iac_scan(
        self, binary: Path, context: ScanContext
    ) -> List[UnifiedIssue]:
        """Run Checkov IaC scan.

        Args:
            binary: Path to the Checkov binary.
            context: Scan context with project root and configuration.

        Returns:
            List of unified issues from the IaC scan.
        """
        # Get IaC-specific config options
        iac_config = context.get_scanner_options("iac")

        # Build command
        cmd = [
            str(binary),
            "--directory", str(context.project_root),
            "--output", "json",
            "--quiet",
            "--compact",
        ]

        # Add framework filter if specified in config
        frameworks = iac_config.get("framework", [])
        if frameworks:
            for framework in frameworks:
                cmd.extend(["--framework", framework])

        # Add skip checks if specified
        skip_checks = iac_config.get("skip_checks", [])
        if skip_checks:
            cmd.extend(["--skip-check", ",".join(skip_checks)])

        # Apply ignore patterns from .lucidscanignore and config
        exclude_patterns = context.get_exclude_patterns()
        for pattern in exclude_patterns:
            cmd.extend(["--skip-path", pattern])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                env=self._get_scan_env(),
            )

            # Checkov returns non-zero exit code when findings exist
            # Exit code 1 means findings found (expected)
            # Exit code 2 means error
            if result.returncode == 2 and result.stderr:
                LOGGER.warning(f"Checkov stderr: {result.stderr}")

            if not result.stdout.strip():
                LOGGER.debug("Checkov returned empty output")
                return []

            return self._parse_checkov_json(result.stdout, context.project_root)

        except Exception as e:
            LOGGER.error(f"Checkov scan failed: {e}")
            return []

    def _get_scan_env(self) -> Dict[str, str]:
        """Get environment variables for the scan process."""
        import os
        env = os.environ.copy()
        # Disable telemetry/analytics
        env["BC_SKIP_MAPPING"] = "TRUE"
        env["CHECKOV_RUN_SCA_PACKAGE_SCAN"] = "false"
        return env

    def _parse_checkov_json(
        self,
        json_output: str,
        project_root: Path,
    ) -> List[UnifiedIssue]:
        """Parse Checkov JSON output and convert to UnifiedIssue list.

        Args:
            json_output: Raw JSON string from Checkov.
            project_root: Project root path for relative path resolution.

        Returns:
            List of unified issues parsed from the JSON.
        """
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse Checkov JSON: {e}")
            return []

        issues: List[UnifiedIssue] = []

        # Checkov can output a list of results (one per framework) or a single result
        if isinstance(data, list):
            results_list = data
        else:
            results_list = [data]

        for framework_result in results_list:
            # Skip if not a dict (could be error message)
            if not isinstance(framework_result, dict):
                continue

            # Get the check type (framework)
            check_type = framework_result.get("check_type", "unknown")

            # Process failed checks
            results = framework_result.get("results", {})
            failed_checks = results.get("failed_checks", [])

            for check in failed_checks:
                issue = self._check_to_unified_issue(check, check_type, project_root)
                if issue:
                    issues.append(issue)

        LOGGER.debug(f"Parsed {len(issues)} issues from Checkov output")
        return issues

    def _check_to_unified_issue(
        self,
        check: Dict[str, Any],
        check_type: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a single Checkov failed check to a UnifiedIssue.

        Args:
            check: Failed check dict from Checkov JSON.
            check_type: The framework/check type (e.g., 'terraform', 'kubernetes').
            project_root: Project root path for relative path resolution.

        Returns:
            UnifiedIssue or None if conversion fails.
        """
        try:
            # Extract basic fields
            check_id = check.get("check_id", "UNKNOWN")
            check_name = check.get("check", "Unknown check")
            file_path_str = check.get("file_path", "")
            resource = check.get("resource", "")
            guideline = check.get("guideline", "")

            # Extract line numbers
            file_line_range = check.get("file_line_range", [])
            line_start = file_line_range[0] if len(file_line_range) > 0 else None
            line_end = file_line_range[1] if len(file_line_range) > 1 else line_start

            # Extract severity (Checkov includes severity in some checks)
            severity_str = check.get("severity", "MEDIUM")
            if severity_str is None:
                severity_str = "MEDIUM"
            severity = CHECKOV_SEVERITY_MAP.get(severity_str.upper(), Severity.MEDIUM)

            # Generate deterministic issue ID
            issue_id = self._generate_issue_id(
                check_id, file_path_str, resource, line_start
            )

            # Build file path
            file_path = None
            if file_path_str:
                # Remove leading slash if present (Checkov sometimes includes it)
                clean_path = file_path_str.lstrip("/")
                file_path = project_root / clean_path

            # Build title
            title = f"{check_id}: {check_name}"

            # Build description
            description = check_name
            if resource:
                description += f"\n\nResource: {resource}"

            # Build recommendation
            recommendation = None
            if guideline:
                recommendation = f"See: {guideline}"

            # Build IaC resource string
            iac_resource = resource if resource else None

            # Build scanner metadata
            scanner_metadata: Dict[str, Any] = {
                "check_id": check_id,
                "check_type": check_type,
                "resource": resource,
                "resource_address": check.get("resource_address"),
                "guideline": guideline,
                "severity_raw": severity_str,
                "bc_check_id": check.get("bc_check_id"),
                "evaluations": check.get("evaluations"),
                "check_class": check.get("check_class"),
            }

            return UnifiedIssue(
                id=issue_id,
                scanner=ScanDomain.IAC,
                source_tool="checkov",
                severity=severity,
                title=title,
                description=description,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                iac_resource=iac_resource,
                recommendation=recommendation,
                scanner_metadata=scanner_metadata,
            )

        except Exception as e:
            LOGGER.warning(f"Failed to convert Checkov check to UnifiedIssue: {e}")
            return None

    def _generate_issue_id(
        self,
        check_id: str,
        file_path: str,
        resource: str,
        line: Optional[int],
    ) -> str:
        """Generate a deterministic issue ID for deduplication.

        Args:
            check_id: Checkov check identifier (e.g., CKV_AWS_123).
            file_path: File path.
            resource: Resource identifier.
            line: Line number (optional).

        Returns:
            A stable hash-based ID string.
        """
        line_str = str(line) if line is not None else ""
        components = f"checkov:{check_id}:{file_path}:{resource}:{line_str}"
        hash_digest = hashlib.sha256(components.encode()).hexdigest()[:16]
        return f"checkov-{hash_digest}"
