"""Gosec scanner plugin for Go-specific SAST (Static Application Security Testing).

Gosec inspects Go source code for security problems by scanning the Go AST.
It provides Go-specific vulnerability detection with CWE references.
https://github.com/securego/gosec
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from lucidshark.bootstrap.download import secure_urlopen
from lucidshark.bootstrap.paths import LucidsharkPaths
from lucidshark.bootstrap.platform import get_platform_info
from lucidshark.bootstrap.validation import (
    is_binary_for_current_platform,
    remove_stale_binary_dir,
)
from lucidshark.bootstrap.versions import get_tool_version
from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    ScanDomain,
    Severity,
    SkipReason,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.go_utils import find_go, has_go_mod
from lucidshark.plugins.scanners.base import ScannerPlugin

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("gosec", default="2.21.4")

# Gosec severity mapping to unified severity
# Gosec uses: HIGH, MEDIUM, LOW
GOSEC_SEVERITY_MAP: Dict[str, Severity] = {
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}

# Gosec confidence mapping — used to adjust severity
GOSEC_CONFIDENCE_MAP: Dict[str, str] = {
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}

# Gosec rule descriptions for enriched issue output
GOSEC_RULE_DESCRIPTIONS: Dict[str, str] = {
    # Credentials & secrets
    "G101": "Hard-coded credentials",
    # Network
    "G102": "Bind to all interfaces",
    # Unsafe
    "G103": "Audit use of unsafe block",
    "G104": "Audit errors not checked",
    # SSH
    "G106": "Audit use of ssh.InsecureIgnoreHostKey",
    # SSRF / HTTP
    "G107": "URL provided to HTTP request as taint input",
    "G108": "Profiling endpoint automatically exposed",
    # Integer overflow
    "G109": "Potential integer overflow",
    # Decompression bomb
    "G110": "Potential DoS via decompression bomb",
    # Directory traversal
    "G111": "Potential directory traversal",
    # Slowloris
    "G112": "Potential slowloris attack",
    # Math/big
    "G113": "Usage of Rat.SetString in math/big",
    # Net/http serve
    "G114": "Use of net/http serve function that has no support for setting timeouts",
    # SQL injection
    "G201": "SQL query construction using format string",
    "G202": "SQL query construction using string concatenation",
    # XSS / template injection
    "G203": "Use of unescaped data in HTML templates",
    # Command injection
    "G204": "Audit use of command execution",
    # File permissions
    "G301": "Poor file permissions used when creating a directory",
    "G302": "Poor file permissions used with chmod",
    "G303": "Creating tempfile using a predictable path",
    "G304": "File path provided as taint input",
    "G305": "File traversal when extracting zip/tar archive",
    "G306": "Poor file permissions used when writing to a new file",
    "G307": "Poor file permissions used with os.Create",
    # Cryptography
    "G401": "Use of weak cryptographic primitive",
    "G402": "TLS with InsecureSkipVerify set to true",
    "G403": "Ensure minimum RSA key length of 2048 bits",
    "G404": "Insecure random number source (math/rand instead of crypto/rand)",
    # Import blocklist
    "G501": "Import blocklist: crypto/md5",
    "G502": "Import blocklist: crypto/des",
    "G503": "Import blocklist: crypto/rc4",
    "G504": "Import blocklist: net/http/cgi",
    "G505": "Import blocklist: crypto/sha1",
    # Memory safety
    "G601": "Implicit memory aliasing in for loop",
    "G602": "Slice access out of bounds",
}


class GosecScanner(ScannerPlugin):
    """Scanner plugin for Gosec (Go SAST).

    Handles:
    - Go-specific static application security testing via `gosec`
    - CWE-mapped vulnerability detection for Go code

    Binary management:
    - Downloads from https://github.com/securego/gosec/releases/
    - Caches at {project}/.lucidshark/bin/gosec/{version}/gosec
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
        return "gosec"

    @property
    def domains(self) -> List[ScanDomain]:
        return [ScanDomain.SAST]

    def get_version(self) -> str:
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure the gosec binary is available, downloading if needed."""
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_name = self._get_binary_name()
        binary_path = binary_dir / binary_name

        if binary_path.exists():
            if is_binary_for_current_platform(binary_path):
                LOGGER.debug(f"Gosec binary found at {binary_path}")
                return binary_path
            remove_stale_binary_dir(binary_dir, "gosec")

        LOGGER.info(f"Downloading gosec v{self._version}...")
        self._download_binary(binary_dir)

        if not binary_path.exists():
            raise RuntimeError(f"Failed to download gosec binary to {binary_path}")

        return binary_path

    def _get_binary_name(self) -> str:
        """Get the binary name for the current platform."""
        return "gosec"

    def _download_binary(self, dest_dir: Path) -> None:
        """Download and extract gosec binary for current platform."""
        platform_info = get_platform_info()

        os_name = {
            "darwin": "darwin",
            "linux": "linux",
        }.get(platform_info.os)

        arch_name = {
            "amd64": "amd64",
            "arm64": "arm64",
        }.get(platform_info.arch)

        if not os_name or not arch_name:
            raise RuntimeError(
                f"Unsupported platform: {platform_info.os}-{platform_info.arch}"
            )

        # Gosec release naming: gosec_2.21.4_linux_amd64.tar.gz
        filename = f"gosec_{self._version}_{os_name}_{arch_name}.tar.gz"
        url = f"https://github.com/securego/gosec/releases/download/v{self._version}/{filename}"

        LOGGER.debug(f"Downloading from {url}")

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Validate URL scheme and domain for security
        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        tmp_file = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        tmp_path = Path(tmp_file.name)
        try:
            with secure_urlopen(url) as response:  # nosec B310 nosemgrep
                tmp_file.write(response.read())
            tmp_file.close()

            # Extract tarball safely (prevent path traversal)
            with tarfile.open(tmp_path, "r:gz") as tar:
                for tar_member in tar.getmembers():
                    member_path = (dest_dir / tar_member.name).resolve()
                    if not member_path.is_relative_to(dest_dir.resolve()):
                        raise ValueError(f"Path traversal detected: {tar_member.name}")
                    tar.extract(tar_member, path=dest_dir)

            # Make binary executable
            binary_path = dest_dir / "gosec"
            if binary_path.exists():
                binary_path.chmod(0o755)
            LOGGER.info(f"Gosec v{self._version} installed to {binary_path}")

        finally:
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        """Execute gosec scan and return normalized issues.

        Args:
            context: Scan context containing target paths and configuration.

        Returns:
            List of unified issues found during the scan.
        """
        if ScanDomain.SAST not in context.enabled_domains:
            return []

        # Gosec is Go-specific — skip if no go.mod
        if not has_go_mod(context.project_root):
            LOGGER.debug("Skipping gosec: no go.mod found")
            context.record_skip(
                tool_name=self.name,
                domain=ScanDomain.SAST,
                reason=SkipReason.NO_APPLICABLE_FILES,
                message="No go.mod found — gosec requires a Go project",
            )
            return []

        # Verify Go is available (gosec needs Go toolchain)
        try:
            find_go()
        except FileNotFoundError:
            LOGGER.debug("Skipping gosec: Go not available")
            context.record_skip(
                tool_name=self.name,
                domain=ScanDomain.SAST,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message="Go not found — gosec requires the Go toolchain",
            )
            return []

        binary = self.ensure_binary()
        return self._run_sast_scan(binary, context)

    def _run_sast_scan(self, binary: Path, context: ScanContext) -> List[UnifiedIssue]:
        """Run gosec SAST scan.

        Args:
            binary: Path to the gosec binary.
            context: Scan context with project root and configuration.

        Returns:
            List of unified issues from the SAST scan.
        """
        cmd = [
            str(binary),
            "-fmt=json",
            "-quiet",
            "-stdout",
        ]

        # Apply exclude patterns
        # Note: gosec -exclude-dir expects simple directory names, not glob patterns.
        # Convert glob patterns to directory names by extracting static parts.
        exclude_patterns = context.get_exclude_patterns()
        if exclude_patterns:
            gosec_dirs = self._convert_patterns_to_dirs(exclude_patterns)
            if gosec_dirs:
                cmd.extend(["-exclude-dir", ",".join(gosec_dirs)])

        # Scan all packages
        cmd.append("./...")

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="gosec",
                stream_handler=context.stream_handler,
                timeout=300,
            )

            # Gosec returns exit code 0 for no findings, 1 for findings
            # Exit code 2+ indicates errors
            # Also check for panic in stderr which indicates a crash
            if result.returncode not in (0, 1):
                error_msg = f"Gosec exited with code {result.returncode}"
                if result.stderr:
                    LOGGER.error(f"Gosec stderr: {result.stderr}")
                    error_msg += f": {result.stderr[:500]}"
                context.record_skip(
                    tool_name=self.name,
                    domain=ScanDomain.SAST,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=error_msg,
                )
                return []

            if result.stderr and ("panic:" in result.stderr or "fatal error:" in result.stderr):
                LOGGER.error(f"Gosec crashed: {result.stderr[:500]}")
                context.record_skip(
                    tool_name=self.name,
                    domain=ScanDomain.SAST,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Gosec crashed: {result.stderr[:500]}",
                )
                return []

            if not result.stdout.strip():
                LOGGER.debug("Gosec returned empty output")
                return []

            return self._parse_gosec_json(result.stdout, context.project_root)

        except subprocess.TimeoutExpired:
            LOGGER.warning("Gosec scan timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ScanDomain.SAST,
                reason=SkipReason.EXECUTION_FAILED,
                message="Gosec scan timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Gosec scan failed: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ScanDomain.SAST,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Gosec scan failed: {e}",
            )
            return []

    def _convert_patterns_to_dirs(self, patterns: List[str]) -> List[str]:
        """Convert glob patterns to simple directory names for gosec.

        gosec's -exclude-dir flag expects simple directory names (e.g., "vendor", ".git"),
        not glob patterns. This method extracts static directory components from patterns.

        Args:
            patterns: List of gitignore-style glob patterns.

        Returns:
            List of simple directory names safe for gosec -exclude-dir.
        """
        dirs = set()
        for pattern in patterns:
            # Remove leading/trailing slashes and wildcards
            clean = pattern.strip("/").replace("*", "")
            # Split on / and extract non-empty static parts
            parts = [p for p in clean.split("/") if p and not p.startswith("*")]
            # Add each static directory component
            for part in parts:
                if part and part not in (".", ".."):
                    dirs.add(part)
        return sorted(dirs)

    def _parse_gosec_json(
        self,
        json_output: str,
        project_root: Path,
    ) -> List[UnifiedIssue]:
        """Parse gosec JSON output and convert to UnifiedIssue list.

        Args:
            json_output: Raw JSON string from gosec.
            project_root: Project root path for relative path resolution.

        Returns:
            List of unified issues parsed from the JSON.
        """
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse gosec JSON: {e}")
            return []

        issues: List[UnifiedIssue] = []

        # Gosec output: {"Golang errors": {...}, "Issues": [...], "Stats": {...}}
        raw_issues = data.get("Issues", [])

        for raw_issue in raw_issues:
            issue = self._result_to_unified_issue(raw_issue, project_root)
            if issue:
                issues.append(issue)

        # Log any Go compilation errors
        golang_errors = data.get("Golang errors", {})
        if golang_errors:
            for pkg, errs in golang_errors.items():
                LOGGER.warning(f"Gosec Go error in {pkg}: {errs}")

        stats = data.get("Stats", {})
        LOGGER.debug(
            f"Parsed {len(issues)} issues from gosec output "
            f"(files={stats.get('files', '?')}, found={stats.get('found', '?')})"
        )
        return issues

    def _result_to_unified_issue(
        self,
        result: Dict[str, Any],
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a single gosec result to a UnifiedIssue.

        Args:
            result: Result dict from gosec JSON Issues array.
            project_root: Project root path for relative path resolution.

        Returns:
            UnifiedIssue or None if conversion fails.
        """
        try:
            rule_id = result.get("rule_id", "unknown")
            severity_str = result.get("severity", "MEDIUM").upper()
            confidence_str = result.get("confidence", "MEDIUM").upper()
            details = result.get("details", "No details")
            file_path_str = result.get("file", "unknown")
            code_snippet = result.get("code", "")
            line_str = result.get("line", "0")
            col_str = result.get("column", "0")
            nosec = result.get("nosec", False)

            # Parse line/column (gosec returns them as strings)
            line = int(line_str) if line_str else 0
            col = int(col_str) if col_str else 0

            # Map severity
            severity = GOSEC_SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

            # Build file path (relative or absolute)
            file_path = Path(file_path_str)
            if file_path.is_absolute():
                # Make relative to project root if possible
                try:
                    file_path = file_path.relative_to(project_root)
                    file_path = project_root / file_path
                except ValueError:
                    pass  # Keep absolute if not under project root
            else:
                file_path = project_root / file_path_str

            # Generate deterministic issue ID
            issue_id = self._generate_issue_id(rule_id, file_path_str, line, col)

            # Build title
            rule_desc = GOSEC_RULE_DESCRIPTIONS.get(rule_id, "")
            title = self._format_title(rule_id, rule_desc or details)

            # Build description
            description = details
            if rule_desc and rule_desc != details:
                description = f"{rule_desc}: {details}"

            # Extract CWE info
            cwe = result.get("cwe", {})
            cwe_id = cwe.get("id", "") if isinstance(cwe, dict) else ""
            cwe_url = cwe.get("url", "") if isinstance(cwe, dict) else ""

            # Build recommendation
            recommendation = None
            if rule_id in GOSEC_RULE_DESCRIPTIONS:
                recommendation = f"Review and fix: {GOSEC_RULE_DESCRIPTIONS[rule_id]}"

            # Build documentation URL from CWE
            documentation_url = cwe_url if cwe_url else None

            # Build scanner metadata
            scanner_metadata: Dict[str, Any] = {
                "rule_id": rule_id,
                "confidence": confidence_str,
                "nosec": nosec,
                "line": line,
                "column": col,
            }
            if cwe_id:
                scanner_metadata["cwe"] = {"id": cwe_id, "url": cwe_url}

            # Handle suppressed findings
            suppressions = result.get("suppressions", None)
            if suppressions:
                scanner_metadata["suppressions"] = suppressions

            return UnifiedIssue(
                id=issue_id,
                domain=ScanDomain.SAST,
                source_tool="gosec",
                severity=severity,
                rule_id=rule_id,
                title=title,
                description=description,
                documentation_url=documentation_url,
                file_path=file_path,
                line_start=line,
                line_end=line,
                column_start=col if col else None,
                column_end=None,
                code_snippet=code_snippet,
                recommendation=recommendation,
                fixable=False,
                suggested_fix=None,
                metadata=scanner_metadata,
            )

        except Exception as e:
            LOGGER.warning(f"Failed to convert gosec result to UnifiedIssue: {e}")
            return None

    def _format_title(self, rule_id: str, message: str) -> str:
        """Format a human-readable title from rule ID and message.

        Args:
            rule_id: Gosec rule identifier (e.g., G101, G201).
            message: Rule message or description.

        Returns:
            Formatted title string.
        """
        max_message_len = 80
        if len(message) > max_message_len:
            message = message[: max_message_len - 3] + "..."
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
            rule_id: Gosec rule identifier.
            path: File path.
            line: Line number.
            col: Column number.

        Returns:
            A stable hash-based ID string.
        """
        components = f"gosec:{rule_id}:{path}:{line}:{col}"
        hash_digest = hashlib.sha256(components.encode()).hexdigest()[:16]
        return f"gosec-{hash_digest}"
