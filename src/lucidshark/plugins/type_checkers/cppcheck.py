"""Cppcheck type checker plugin.

Cppcheck is a static analysis tool for C/C++ code that detects bugs,
undefined behavior, and dangerous coding constructs that the compiler
does not catch.
https://cppcheck.sourceforge.io/
"""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
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
from lucidshark.core.subprocess_runner import run_with_streaming, temporary_env
from lucidshark.plugins.cpp_utils import (
    CPP_EXTENSIONS,
    ensure_cpp_tools_in_path,
    find_build_dir,
    find_cppcheck,
    generate_issue_id,
    get_tool_version,
)
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin

LOGGER = get_logger(__name__)

# Cppcheck severity to LucidShark severity mapping
CPPCHECK_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "style": Severity.LOW,
    "performance": Severity.MEDIUM,
    "portability": Severity.MEDIUM,
    "information": Severity.LOW,
}

# Regex for parsing cppcheck text output:
#   [file.cpp:42]: (error) Null pointer dereference
_TEXT_RE = re.compile(r"^\[(.+?):(\d+)\]:\s+\((\w+)\)\s+(.+)$")


class CppcheckChecker(TypeCheckerPlugin):
    """Cppcheck static analysis plugin for C/C++ code."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        self._project_root = project_root

    @property
    def name(self) -> str:
        return "cppcheck"

    @property
    def languages(self) -> List[str]:
        return ["c", "c++"]

    @property
    def supports_strict_mode(self) -> bool:
        return True

    def get_version(self) -> str:
        return get_tool_version(find_cppcheck)

    def ensure_binary(self) -> Path:
        return find_cppcheck()

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run cppcheck static analysis.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking / static analysis issues.
        """
        try:
            binary = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        # Determine target paths
        targets = self._get_targets(context)
        if not targets:
            LOGGER.debug("No C/C++ files to check")
            return []

        cmd = [
            str(binary),
            "--enable=all",
            "--xml",
            "--xml-version=2",
            "--suppress=missingIncludeSystem",
            "--suppress=unmatchedSuppression",
            "--inline-suppr",
        ]

        # Use compile_commands.json if available
        build_dir = find_build_dir(context.project_root)
        if build_dir:
            compile_db = build_dir / "compile_commands.json"
            if compile_db.exists():
                cmd.append(f"--project={compile_db}")
            else:
                cmd.extend(targets)
        else:
            cmd.extend(targets)

        LOGGER.debug(f"Running: {' '.join(cmd[:6])}...")

        env_vars = ensure_cpp_tools_in_path()

        try:
            with temporary_env(env_vars):
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="cppcheck",
                    stream_handler=context.stream_handler,
                    timeout=300,
                )
        except subprocess.TimeoutExpired:
            LOGGER.warning("cppcheck timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message="cppcheck timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run cppcheck: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run cppcheck: {e}",
            )
            return []

        # cppcheck XML output goes to stderr
        stderr = result.stderr or ""
        stdout = result.stdout or ""

        # Try XML parsing first (from stderr)
        issues = self._parse_xml_output(stderr, context.project_root)

        # Fallback to text parsing if XML fails
        if not issues and stdout.strip():
            issues = self._parse_text_output(stdout, context.project_root)

        LOGGER.info(f"cppcheck found {len(issues)} issues")
        return issues

    def _get_targets(self, context: ScanContext) -> List[str]:
        """Get target paths for cppcheck.

        Args:
            context: Scan context.

        Returns:
            List of path strings to scan.
        """
        if context.paths:
            targets = []
            for path in context.paths:
                if path.is_dir():
                    targets.append(str(path))
                elif path.suffix.lower() in CPP_EXTENSIONS:
                    targets.append(str(path))
            return targets

        # Default: scan project root
        return [str(context.project_root)]

    def _parse_xml_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse cppcheck XML version 2 output.

        Args:
            output: Raw XML output from cppcheck (typically stderr).
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip() or "<?xml" not in output:
            return []

        # Extract XML portion (skip non-XML lines)
        xml_start = output.find("<?xml")
        if xml_start < 0:
            return []

        xml_content = output[xml_start:]

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            LOGGER.warning(f"Failed to parse cppcheck XML output: {e}")
            return []

        issues = []
        seen_ids = set()

        errors = root.find("errors")
        if errors is None:
            return []

        for error in errors.findall("error"):
            issue = self._xml_error_to_issue(error, project_root)
            if issue and issue.id not in seen_ids:
                issues.append(issue)
                seen_ids.add(issue.id)

        return issues

    def _xml_error_to_issue(
        self, error: ET.Element, project_root: Path
    ) -> Optional[UnifiedIssue]:
        """Convert a cppcheck XML error element to UnifiedIssue.

        Args:
            error: XML error element.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            error_id = error.get("id", "")
            severity_str = error.get("severity", "")
            msg = error.get("msg", "")
            verbose = error.get("verbose", msg)
            cwe = error.get("cwe", "")

            # Skip informational/suppressed messages
            if severity_str == "information" and "missingInclude" in error_id:
                return None

            # Get location from first <location> element
            location = error.find("location")
            file_str = ""
            line_num = None
            col_num = None

            if location is not None:
                file_str = location.get("file", "")
                line_str = location.get("line", "")
                col_str = location.get("column", "")
                line_num = int(line_str) if line_str else None
                col_num = int(col_str) if col_str else None

            # Skip if no file (project-level informational messages)
            if not file_str:
                return None

            # Resolve file path
            file_path = Path(file_str)
            resolved_root = project_root.resolve()
            if not file_path.is_absolute():
                file_path = (resolved_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            severity = CPPCHECK_SEVERITY.get(severity_str, Severity.MEDIUM)

            title = f"[{error_id}] {msg}"

            issue_id = generate_issue_id(
                "cppcheck",
                error_id,
                str(file_path),
                line_num,
                col_num,
                msg,
            )

            doc_url = "https://cppcheck.sourceforge.io/devinfo/doxyoutput/errormessage_8h.html"

            metadata = {
                "cppcheck_id": error_id,
                "cppcheck_severity": severity_str,
            }
            if cwe:
                metadata["cwe"] = cwe

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="cppcheck",
                severity=severity,
                rule_id=error_id,
                title=title,
                description=verbose,
                documentation_url=doc_url,
                file_path=file_path,
                line_start=line_num,
                line_end=line_num,
                column_start=col_num,
                fixable=False,
                metadata=metadata,
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse cppcheck error: {e}")
            return None

    def _parse_text_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Fallback: parse cppcheck text output.

        Args:
            output: Raw text output from cppcheck.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            return []

        issues = []
        seen_ids = set()

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            match = _TEXT_RE.match(line)
            if not match:
                continue

            file_str = match.group(1)
            line_num = int(match.group(2))
            severity_str = match.group(3)
            message = match.group(4)

            file_path = Path(file_str)
            resolved_root = project_root.resolve()
            if not file_path.is_absolute():
                file_path = (resolved_root / file_path).resolve()
            else:
                file_path = file_path.resolve()

            severity = CPPCHECK_SEVERITY.get(severity_str, Severity.MEDIUM)
            title = f"[{severity_str}] {message}"

            issue_id = generate_issue_id(
                "cppcheck",
                severity_str,
                str(file_path),
                line_num,
                None,
                message,
            )

            if issue_id in seen_ids:
                continue
            seen_ids.add(issue_id)

            issues.append(
                UnifiedIssue(
                    id=issue_id,
                    domain=ToolDomain.TYPE_CHECKING,
                    source_tool="cppcheck",
                    severity=severity,
                    rule_id=severity_str,
                    title=title,
                    description=message,
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    fixable=False,
                    metadata={
                        "cppcheck_severity": severity_str,
                    },
                )
            )

        return issues
