"""Scalafix linter plugin.

Scalafix is a refactoring and linting tool for Scala.
https://scalacenter.github.io/scalafix/
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
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
from lucidshark.plugins.linters.base import LinterPlugin

LOGGER = get_logger(__name__)

# Scalafix severity mapping
SEVERITY_MAP = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "info": Severity.LOW,
}


class ScalafixLinter(LinterPlugin):
    """Scalafix linter plugin for Scala code analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        super().__init__(project_root=project_root, **kwargs)

    @property
    def name(self) -> str:
        return "scalafix"

    @property
    def languages(self) -> List[str]:
        return ["scala"]

    @property
    def supports_fix(self) -> bool:
        return True

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                # Output like "0.11.1" or "scalafix 0.11.1"
                match = re.search(r"(\d+\.\d+\.\d+)", output)
                if match:
                    return match.group(1)
                return output if output else "unknown"
        except Exception:
            pass
        return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure Scalafix is available on PATH.

        Returns:
            Path to the scalafix binary.

        Raises:
            FileNotFoundError: If scalafix is not installed.
        """
        system_binary = shutil.which("scalafix")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "scalafix is not installed. Install it with:\n"
            "  cs install scalafix\n"
            "or add sbt-scalafix plugin to your build."
        )

    def lint(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run Scalafix linting checks.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of linting issues.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.LINTING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
                suggestion="Install scalafix: cs install scalafix",
            )
            return []

        # Find Scala source files
        scala_files = self._find_scala_files(context)
        if not scala_files:
            LOGGER.info("No Scala files found to check")
            return []

        # Build command: scalafix --check <files>
        cmd = [str(binary), "--check"] + scala_files

        LOGGER.debug(f"Running: {' '.join(cmd[:10])}...")

        stdout = self._run_linter_command(cmd, context, timeout=120)
        if stdout is None:
            return []

        # Parse output
        issues = self._parse_output(stdout, context.project_root)

        LOGGER.info(f"Scalafix found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext):
        """Apply Scalafix automatic fixes."""
        from lucidshark.plugins.linters.base import FixResult

        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        scala_files = self._find_scala_files(context)
        if not scala_files:
            return FixResult()

        # Get pre-fix issues
        pre_issues = self.lint(context)

        # Run scalafix without --check to apply fixes
        cmd = [str(binary)] + scala_files

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="scalafix-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run scalafix fix: {e}")
            return FixResult()

        # Get post-fix issues
        post_issues = self.lint(context)

        return self._calculate_fix_stats(pre_issues, post_issues)

    def _find_scala_files(self, context: ScanContext) -> List[str]:
        """Find Scala source files to check."""
        scala_files = []

        search_dirs = []
        if context.paths:
            search_dirs = list(context.paths)
        else:
            # Prefer specific Scala source directories over generic "src"
            for src_dir in ["src/main/scala", "src/test/scala"]:
                src_path = context.project_root / src_dir
                if src_path.exists():
                    search_dirs.append(src_path)
            if not search_dirs:
                src_path = context.project_root / "src"
                if src_path.exists():
                    search_dirs.append(src_path)

        if not search_dirs:
            search_dirs = [context.project_root]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            if search_dir.is_file():
                if search_dir.suffix in (".scala", ".sc"):
                    if (
                        context.ignore_patterns is None
                        or not context.ignore_patterns.matches(
                            search_dir, context.project_root
                        )
                    ):
                        scala_files.append(str(search_dir))
            else:
                for ext in ("*.scala", "*.sc"):
                    for scala_file in search_dir.rglob(ext):
                        if (
                            context.ignore_patterns is None
                            or not context.ignore_patterns.matches(
                                scala_file, context.project_root
                            )
                        ):
                            scala_files.append(str(scala_file))

        return scala_files

    def _parse_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse Scalafix output.

        Scalafix outputs diagnostics in the format:
        <file>:<line>:<column>: <severity>: [<rule>] <message>
        or simpler formats depending on the rule.
        """
        if not output.strip():
            return []

        issues = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            issue = self._parse_line(line, project_root)
            if issue:
                issues.append(issue)

        return issues

    def _parse_line(self, line: str, project_root: Path) -> Optional[UnifiedIssue]:
        """Parse a single Scalafix output line."""
        # Pattern: file.scala:10:5: error: [RuleName] message
        match = re.match(
            r"^(.+?):(\d+):(\d+):\s*(error|warning|info):\s*(?:\[(\w+)\]\s*)?(.*)",
            line,
        )
        if not match:
            # Simpler pattern: file.scala:10: error: message
            match = re.match(
                r"^(.+?):(\d+):\s*(error|warning|info):\s*(?:\[(\w+)\]\s*)?(.*)",
                line,
            )
            if match:
                file_path_str = match.group(1)
                line_num = int(match.group(2))
                col_num = None
                severity_str = match.group(3)
                rule = match.group(4) or ""
                message = match.group(5)
            else:
                return None
        else:
            file_path_str = match.group(1)
            line_num = int(match.group(2))
            col_num = int(match.group(3))
            severity_str = match.group(4)
            rule = match.group(5) or ""
            message = match.group(6)

        severity = SEVERITY_MAP.get(severity_str, Severity.MEDIUM)

        path = Path(file_path_str)
        if not path.is_absolute():
            path = project_root / path

        issue_id = self._generate_issue_id(rule, file_path_str, line_num, message)

        return UnifiedIssue(
            id=issue_id,
            domain=ToolDomain.LINTING,
            source_tool="scalafix",
            severity=severity,
            rule_id=rule or "scalafix",
            title=f"[{rule}] {message}" if rule else message,
            description=message,
            file_path=path,
            line_start=line_num,
            line_end=line_num,
            column_start=col_num,
            fixable=True,
            metadata={
                "severity_raw": severity_str,
            },
        )

    def _generate_issue_id(
        self, rule: str, file: str, line: int, message: str
    ) -> str:
        content = f"{rule}:{file}:{line}:{message}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"scalafix-{hash_val}"
