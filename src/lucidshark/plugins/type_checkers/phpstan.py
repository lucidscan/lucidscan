"""PHPStan type checker plugin.

PHPStan focuses on finding errors in code without actually running it.
It catches whole classes of bugs even before writing tests.
https://phpstan.org/
"""

from __future__ import annotations

import hashlib
import json
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


def _find_phpstan(project_root: Optional[Path] = None) -> Path:
    """Find phpstan binary.

    Checks:
    1. Project vendor/bin/phpstan (Composer local install)
    2. System PATH

    Args:
        project_root: Optional project root.

    Returns:
        Path to phpstan binary.

    Raises:
        FileNotFoundError: If phpstan is not installed.
    """
    if project_root:
        vendor_bin = project_root / "vendor" / "bin" / "phpstan"
        if vendor_bin.exists():
            return vendor_bin

    system = shutil.which("phpstan")
    if system:
        return Path(system)

    raise FileNotFoundError(
        "PHPStan is not installed. Install via: composer require --dev phpstan/phpstan"
    )


class PhpstanChecker(TypeCheckerPlugin):
    """PHPStan type checker plugin for PHP static analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "phpstan"

    @property
    def languages(self) -> List[str]:
        return ["php"]

    @property
    def supports_strict_mode(self) -> bool:
        return True

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            from lucidshark.plugins.utils import get_cli_version

            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        return _find_phpstan(self._project_root)

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        cmd = [
            str(binary),
            "analyse",
            "--error-format=json",
            "--no-progress",
            "--no-interaction",
        ]

        # Check for phpstan.neon or phpstan.neon.dist config
        has_config = any(
            (context.project_root / name).exists()
            for name in ("phpstan.neon", "phpstan.neon.dist", "phpstan.dist.neon")
        )

        if not has_config:
            # Without a config file, analyse the current directory
            cmd.append(".")

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        import subprocess

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="phpstan",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("phpstan timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message="phpstan timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run phpstan: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run phpstan: {e}",
            )
            return []

        issues = self._parse_output(result.stdout, context.project_root)
        LOGGER.info(f"phpstan found {len(issues)} issues")
        return issues

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse phpstan JSON output.

        phpstan --error-format=json produces:
        {
          "totals": {"errors": N, "file_errors": N},
          "files": {
            "/path/to/file.php": {
              "errors": N,
              "messages": [
                {"message": "...", "line": 10, "ignorable": true, "identifier": "..."}
              ]
            }
          },
          "errors": ["general errors"]
        }
        """
        if not output.strip():
            return []

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse phpstan JSON output")
            return []

        files = data.get("files", {})
        issues = []
        seen_ids = set()

        for file_path_str, file_data in files.items():
            messages = file_data.get("messages", [])
            for msg in messages:
                issue = self._message_to_issue(msg, file_path_str, project_root)
                if issue and issue.id not in seen_ids:
                    issues.append(issue)
                    seen_ids.add(issue.id)

        # Handle general errors (e.g., config issues)
        general_errors = data.get("errors", [])
        for error in general_errors:
            if isinstance(error, str):
                issue_id = (
                    f"phpstan-general-{hashlib.sha256(error.encode()).hexdigest()[:12]}"
                )
                if issue_id not in seen_ids:
                    issues.append(
                        UnifiedIssue(
                            id=issue_id,
                            domain=ToolDomain.TYPE_CHECKING,
                            source_tool="phpstan",
                            severity=Severity.HIGH,
                            rule_id="general_error",
                            title=error[:200],
                            description=error,
                            fixable=False,
                        )
                    )
                    seen_ids.add(issue_id)

        return issues

    def _message_to_issue(
        self, msg: dict, file_path_str: str, project_root: Path
    ) -> Optional[UnifiedIssue]:
        try:
            message_text = msg.get("message", "")
            line = msg.get("line")
            identifier = msg.get("identifier", "")

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path

            rule_id = identifier if identifier else "phpstan"
            title = f"[{rule_id}] {message_text}" if identifier else message_text

            issue_id = self._generate_issue_id(
                rule_id, file_path_str, line, message_text
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="phpstan",
                severity=Severity.HIGH,
                rule_id=rule_id,
                title=title,
                description=message_text,
                file_path=file_path,
                line_start=line,
                line_end=line,
                fixable=False,
                metadata={
                    "identifier": identifier,
                    "ignorable": msg.get("ignorable", True),
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse phpstan message: {e}")
            return None

    def _generate_issue_id(
        self, rule_id: str, file_path: str, line: Optional[int], message: str
    ) -> str:
        content = f"phpstan:{rule_id}:{file_path}:{line}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"phpstan-{hash_val}"
