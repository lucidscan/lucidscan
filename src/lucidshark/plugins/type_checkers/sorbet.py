"""Sorbet type checker plugin.

Sorbet is a fast, powerful type checker for Ruby.
https://sorbet.org/
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import List, Optional

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

# Sorbet error code ranges to severity
# 1000-1999: parse errors (MEDIUM)
# 2000-2999: resolver errors (HIGH)
# 3000-3999: namer errors (MEDIUM)
# 4000-4999: unknown constant (MEDIUM)
# 5000-5999: constant resolution (MEDIUM)
# 6000-6999: type checking errors (HIGH)
# 7000-7999: type errors (HIGH)
ERROR_CODE_SEVERITY = {
    range(1000, 2000): Severity.MEDIUM,
    range(2000, 3000): Severity.HIGH,
    range(3000, 4000): Severity.MEDIUM,
    range(4000, 5000): Severity.MEDIUM,
    range(5000, 6000): Severity.MEDIUM,
    range(6000, 7000): Severity.HIGH,
    range(7000, 8000): Severity.HIGH,
}


def _get_severity_for_code(code: int) -> Severity:
    """Map Sorbet error code to severity."""
    for code_range, severity in ERROR_CODE_SEVERITY.items():
        if code in code_range:
            return severity
    return Severity.MEDIUM


class SorbetChecker(TypeCheckerPlugin):
    """Sorbet type checker plugin for Ruby code analysis."""

    def __init__(self, project_root: Optional[Path] = None):
        super().__init__(project_root=project_root)

    @property
    def name(self) -> str:
        return "sorbet"

    @property
    def languages(self) -> List[str]:
        return ["ruby"]

    @property
    def supports_strict_mode(self) -> bool:
        return True

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            from lucidshark.plugins.utils import get_cli_version

            return get_cli_version(
                binary,
                parser=lambda s: s.strip().split()[-1] if s.strip() else "unknown",
            )
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Find the Sorbet binary (srb).

        Checks for srb in:
        1. Project binstubs (bin/srb)
        2. System PATH

        Returns:
            Path to srb binary.

        Raises:
            FileNotFoundError: If Sorbet is not installed.
        """
        if self._project_root:
            binstub = self._project_root / "bin" / "srb"
            if binstub.exists():
                return binstub

        system_binary = shutil.which("srb")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "Sorbet is not installed. Install it with:\n"
            "  gem install sorbet sorbet-runtime\n"
            "  OR add to your Gemfile:\n"
            "  gem 'sorbet', group: :development\n"
            "  gem 'sorbet-runtime'"
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
                suggestion="gem install sorbet sorbet-runtime",
            )
            return []

        # Check for sorbet config directory
        sorbet_dir = context.project_root / "sorbet"
        if not sorbet_dir.exists():
            LOGGER.warning("No sorbet/ directory found; skipping Sorbet type checking")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.NO_APPLICABLE_FILES,
                message="No sorbet/ directory found. Run 'srb init' to set up Sorbet.",
            )
            return []

        cmd = [str(binary), "tc", "--no-error-colors"]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="sorbet",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run Sorbet: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run Sorbet: {e}",
            )
            return []

        output = result.stdout or result.stderr or ""
        issues = self._parse_output(output, context.project_root)

        LOGGER.info(f"Sorbet found {len(issues)} issues")
        return issues

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Sorbet text output.

        Sorbet output format:
            file.rb:10: message https://srb.help/CODE
        """
        if not output or not output.strip():
            return []

        issues = []
        # Pattern: file.rb:LINE: message https://srb.help/CODE
        error_pattern = re.compile(
            r"^(.+?):(\d+):\s+(.+?)\s+https://srb\.help/(\d+)\s*$"
        )
        # Simpler pattern without URL: file.rb:LINE: message
        simple_pattern = re.compile(r"^(.+?):(\d+):\s+(.+)$")

        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Skip summary lines and non-error lines
            if line.startswith("Errors:") or line.startswith("No errors"):
                continue
            if line.startswith(" ") or line.startswith("\t"):
                continue

            match = error_pattern.match(line)
            if match:
                file_str, line_num, message, code = match.groups()
                issue = self._create_issue(
                    file_str, int(line_num), message, int(code), project_root
                )
                if issue:
                    issues.append(issue)
                continue

            match = simple_pattern.match(line)
            if match:
                file_str, line_num, message = match.groups()
                # Try to extract code from message
                code_match = re.search(r"\b(\d{4})\b", message)
                code = int(code_match.group(1)) if code_match else 0
                issue = self._create_issue(
                    file_str, int(line_num), message, code, project_root
                )
                if issue:
                    issues.append(issue)

        return issues

    def _create_issue(
        self,
        file_str: str,
        line_num: int,
        message: str,
        code: int,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        try:
            severity = _get_severity_for_code(code) if code else Severity.MEDIUM
            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            issue_id = self._generate_issue_id(code, file_str, line_num, message)
            rule_id = str(code) if code else "unknown"
            doc_url = f"https://srb.help/{code}" if code else None

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="sorbet",
                severity=severity,
                rule_id=rule_id,
                title=f"[{code}] {message}" if code else message,
                description=message,
                documentation_url=doc_url,
                file_path=file_path,
                line_start=line_num,
                line_end=line_num,
                fixable=False,
                metadata={
                    "error_code": code,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse Sorbet error: {e}")
            return None

    def _generate_issue_id(
        self,
        code: int,
        file: str,
        line: int,
        message: str,
    ) -> str:
        content = f"{code}:{file}:{line}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"sorbet-{code}-{hash_val}" if code else f"sorbet-{hash_val}"
