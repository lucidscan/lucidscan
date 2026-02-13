"""Checkov scanner plugin for IaC (Infrastructure as Code) scanning."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from lucidshark.plugins.scanners.base import ScannerPlugin
from lucidshark.core.models import ScanContext, ScanDomain, Severity, UnifiedIssue
from lucidshark.bootstrap.download import secure_urlopen
from lucidshark.bootstrap.paths import LucidsharkPaths
from lucidshark.bootstrap.platform import get_platform_info
from lucidshark.bootstrap.versions import get_tool_version
from lucidshark.core.logging import get_logger
from lucidshark.core.subprocess_runner import run_with_streaming, temporary_env

LOGGER = get_logger(__name__)


def _glob_to_regex(pattern: str) -> str:
    """Convert a gitignore-style glob pattern to a regex pattern.

    Checkov's Bicep runner (and possibly others) treats --skip-path
    values as regex patterns, so we need to convert glob patterns.

    Args:
        pattern: Gitignore-style glob pattern (e.g., ".venv/**", "*.tf").

    Returns:
        Equivalent regex pattern.
    """
    # Escape regex special characters except * and ?
    # These are the special chars in regex that need escaping
    result = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]

        if c == "*":
            # Check for ** (match anything including path separators)
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                result += ".*"
                i += 2
                continue
            else:
                # Single * matches anything except path separator
                result += "[^/]*"
        elif c == "?":
            # ? matches any single character except path separator
            result += "[^/]"
        elif c in r"\.^$+{}[]|()":
            # Escape regex special characters
            result += "\\" + c
        else:
            result += c

        i += 1

    return result

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("checkov")

# Checkov severity mapping to unified severity
CHECKOV_SEVERITY_MAP: Dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
    "INFO": Severity.INFO,
    "UNKNOWN": Severity.INFO,
}


# GitHub releases base URL (tag format: 3.2.499, no 'v' prefix)
CHECKOV_RELEASES_URL = "https://github.com/bridgecrewio/checkov/releases/download"


class CheckovScanner(ScannerPlugin):
    """Scanner plugin for Checkov (IaC scanning).

    Handles:
    - Infrastructure-as-Code scanning for Terraform, Kubernetes,
      CloudFormation, ARM templates, and more via `checkov`

    Binary management:
    - Downloads standalone binary from GitHub releases (no Python required)
    - Caches at {project}/.lucidshark/bin/checkov/{version}/
    """

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ) -> None:
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
        else:
            self._paths = LucidsharkPaths.default()

    @property
    def name(self) -> str:
        return "checkov"

    @property
    def domains(self) -> List[ScanDomain]:
        return [ScanDomain.IAC]

    def get_version(self) -> str:
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure the Checkov binary is available, downloading from GitHub if needed."""
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_name = "checkov.exe" if sys.platform == "win32" else "checkov"
        binary_path = binary_dir / binary_name

        if binary_path.exists():
            LOGGER.debug(f"Checkov binary found at {binary_path}")
            return binary_path

        LOGGER.info(f"Downloading Checkov v{self._version}...")
        self._download_binary(binary_dir)

        if not binary_path.exists():
            raise RuntimeError(f"Failed to download Checkov binary to {binary_path}")

        return binary_path

    def _download_binary(self, dest_dir: Path) -> None:
        """Download and extract Checkov binary for current platform from GitHub releases.

        Asset naming from bridgecrewio/checkov releases:
        checkov_{os}_{arch}.zip (no version in filename).
        arch: X86_64 (amd64), arm64. All platforms use .zip.
        On darwin/arm64 (Apple Silicon), request X86_64 so the binary runs under Rosetta 2.
        """
        platform_info = get_platform_info()
        is_windows = platform_info.os == "windows"

        # Map to Checkov release asset naming (checkov_linux_X86_64.zip, etc.)
        # Apple Silicon: no darwin_arm64 asset; use darwin_X86_64 (runs under Rosetta 2)
        if platform_info.os == "darwin" and platform_info.arch == "arm64":
            arch_name = "X86_64"
        else:
            arch_name = "X86_64" if platform_info.arch == "amd64" else "arm64"
        filename = f"checkov_{platform_info.os}_{arch_name}.zip"
        # Tag in GitHub releases is version without 'v' (e.g. 3.2.499)
        url = f"{CHECKOV_RELEASES_URL}/{self._version}/{filename}"

        LOGGER.debug(f"Downloading from {url}")

        dest_dir.mkdir(parents=True, exist_ok=True)

        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        tmp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp_path = Path(tmp_file.name)
        try:
            with secure_urlopen(url) as response:  # nosec B310 nosemgrep
                tmp_file.write(response.read())
            tmp_file.close()

            with zipfile.ZipFile(tmp_path, "r") as zf:
                for zip_member in zf.namelist():
                    member_path = (dest_dir / zip_member).resolve()
                    if not member_path.is_relative_to(dest_dir.resolve()):
                        raise ValueError(f"Path traversal detected: {zip_member}")
                zf.extractall(dest_dir)

            binary_name = "checkov.exe" if is_windows else "checkov"
            binary_path = dest_dir / binary_name
            # Archives may put binary in a subdir or with different name; normalize
            if not binary_path.exists():
                for p in dest_dir.rglob(binary_name):
                    if p.is_file():
                        p.rename(binary_path)
                        break
                else:
                    for p in dest_dir.rglob("checkov*"):
                        if p.is_file() and p.suffix in ("", ".exe"):
                            p.rename(binary_path)
                            break
            if binary_path.exists() and not is_windows:
                binary_path.chmod(0o755)
            LOGGER.info(f"Checkov v{self._version} installed to {binary_path}")

        finally:
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

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
            binary: Path to the Checkov entry point script.
            context: Scan context with project root and configuration.

        Returns:
            List of unified issues from the IaC scan.
        """
        # Get IaC-specific config options
        iac_config = context.get_scanner_options("iac")

        # Build command (binary is checkov.exe on Windows, checkov on Unix)
        # Use as_posix() for Windows compatibility (forward slashes)
        cmd = [
            str(binary),
            "--directory", context.project_root.as_posix(),
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

        # Apply ignore patterns from .lucidsharkignore and config
        # Convert glob patterns to regex since Checkov's Bicep runner
        # (and possibly others) treats --skip-path as regex
        exclude_patterns = context.get_exclude_patterns()
        for pattern in exclude_patterns:
            regex_pattern = _glob_to_regex(pattern)
            cmd.extend(["--skip-path", regex_pattern])

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            with temporary_env(self._get_scan_env()):
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="checkov",
                    stream_handler=context.stream_handler,
                    timeout=180,
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

        except subprocess.TimeoutExpired:
            LOGGER.warning("Checkov scan timed out after 180 seconds")
            return []
        except Exception as e:
            LOGGER.error(f"Checkov scan failed: {e}")
            return []

    def _get_scan_env(self) -> Dict[str, str]:
        """Get extra environment variables for the scan process."""
        # Disable telemetry/analytics
        return {
            "BC_SKIP_MAPPING": "TRUE",
            "CHECKOV_RUN_SCA_PACKAGE_SCAN": "false",
        }

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
                domain=ScanDomain.IAC,
                source_tool="checkov",
                severity=severity,
                rule_id=check_id,
                title=title,
                description=description,
                documentation_url=guideline,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                iac_resource=iac_resource,
                recommendation=recommendation,
                fixable=False,  # Checkov doesn't auto-fix
                metadata=scanner_metadata,
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
