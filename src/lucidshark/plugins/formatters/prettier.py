"""Prettier formatter plugin.

Wraps `prettier` for JavaScript, TypeScript, CSS, JSON, and Markdown formatting.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import List

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.paths import resolve_node_bin
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.formatters.base import FormatterPlugin
from lucidshark.plugins.linters.base import FixResult
from lucidshark.plugins.utils import get_cli_version

LOGGER = get_logger(__name__)

PRETTIER_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".css", ".json", ".md"}


class PrettierFormatter(FormatterPlugin):
    """Prettier formatter plugin for JS/TS/CSS/JSON/Markdown formatting."""

    @property
    def name(self) -> str:
        return "prettier"

    @property
    def languages(self) -> List[str]:
        return ["javascript", "typescript", "css", "json", "markdown"]

    def get_version(self) -> str:
        try:
            binary = self.ensure_binary()
            return get_cli_version(binary)
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        # Check project node_modules first
        if self._project_root:
            node_binary = resolve_node_bin(self._project_root, "prettier")
            if node_binary:
                return node_binary

        # Check system PATH
        system_binary = shutil.which("prettier")
        if system_binary:
            return Path(system_binary)

        raise FileNotFoundError(
            "Prettier is not installed. Install it with:\n"
            "  npm install --save-dev prettier\n"
            "  OR\n"
            "  yarn add --dev prettier"
        )

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        cmd = [str(binary), "--check"]

        paths = self._resolve_paths(context, PRETTIER_EXTENSIONS, fallback_to_cwd=True)
        if not paths:
            LOGGER.debug("No files to format-check with Prettier")
            return []

        cmd.extend(paths)

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="prettier",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Prettier check timed out after 120 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message="Prettier check timed out after 120 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run prettier: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.FORMATTING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run prettier: {e}",
            )
            return []

        if result.returncode == 0:
            return []

        # Parse output: prettier outputs file paths that aren't formatted
        issues = []
        stdout = result.stdout.strip() if result.stdout else ""
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # prettier --check outputs "[warn] path/to/file.js" for unformatted files
            file_path_str = line
            if line.startswith("[warn]"):
                file_path_str = line.replace("[warn]", "").strip()
            if not file_path_str:
                continue
            # Skip info/summary lines that aren't file paths
            if any(
                file_path_str.startswith(prefix)
                for prefix in (
                    "Checking formatting",
                    "All matched",
                    "Code style issues",
                )
            ):
                continue

            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = context.project_root / file_path

            content = f"prettier:{file_path_str}"
            hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]

            issues.append(
                UnifiedIssue(
                    id=f"prettier-format-{hash_val}",
                    domain=ToolDomain.FORMATTING,
                    source_tool="prettier",
                    severity=Severity.LOW,
                    rule_id="format",
                    title=f"File needs formatting: {file_path_str}",
                    description=f"File {file_path_str} does not match Prettier style.",
                    file_path=file_path,
                    fixable=True,
                    suggested_fix="Run prettier --write to fix formatting.",
                )
            )

        LOGGER.info(f"Prettier found {len(issues)} issues")
        return issues

    def fix(self, context: ScanContext) -> FixResult:
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return FixResult()

        cmd = [str(binary), "--write"]

        paths = self._resolve_paths(context, PRETTIER_EXTENSIONS, fallback_to_cwd=True)
        if not paths:
            return FixResult()

        cmd.extend(paths)

        try:
            run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="prettier-fix",
                stream_handler=context.stream_handler,
                timeout=120,
            )
        except Exception as e:
            LOGGER.error(f"Failed to run prettier --write: {e}")
            return FixResult()

        # Domain runner calls check() after fix to get remaining issues
        return FixResult()
