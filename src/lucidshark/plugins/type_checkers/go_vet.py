"""Go vet type checker plugin.

Uses `go vet -json` to detect correctness issues in Go code such as
format string mismatches, lock copying, unreachable code, and other
problems that the Go compiler does not catch.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.go_utils import (
    find_go,
    generate_issue_id,
    get_go_version,
    has_go_mod,
    parse_go_error_position,
)
from lucidshark.plugins.type_checkers.base import TypeCheckerPlugin

LOGGER = get_logger(__name__)

# Analyzer name to severity mapping.
# High = correctness issues that are almost certainly bugs.
# Medium = suspicious code that may be intentional but is usually wrong.
ANALYZER_SEVERITY: Dict[str, Severity] = {
    # High - correctness issues
    "assign": Severity.HIGH,
    "atomic": Severity.HIGH,
    "bools": Severity.HIGH,
    "buildtag": Severity.HIGH,
    "cgocall": Severity.HIGH,
    "composites": Severity.MEDIUM,
    "copylocks": Severity.HIGH,
    "directive": Severity.MEDIUM,
    "errorsas": Severity.HIGH,
    "httpresponse": Severity.HIGH,
    "ifaceassert": Severity.HIGH,
    "loopclosure": Severity.HIGH,
    "lostcancel": Severity.HIGH,
    "nilfunc": Severity.HIGH,
    "printf": Severity.HIGH,
    "shift": Severity.HIGH,
    "sigchanyzer": Severity.MEDIUM,
    "slog": Severity.MEDIUM,
    "stdmethods": Severity.HIGH,
    "stringintconv": Severity.MEDIUM,
    "structtag": Severity.MEDIUM,
    "testinggoroutine": Severity.HIGH,
    "tests": Severity.MEDIUM,
    "unmarshal": Severity.HIGH,
    "unreachable": Severity.MEDIUM,
    "unsafeptr": Severity.HIGH,
    "unusedresult": Severity.HIGH,
}

# Regex for parsing text-format vet output lines:
#   ./main.go:42:15: printf: Sprintf format %d has arg s of wrong type string
_TEXT_ERROR_RE = re.compile(r"^(.+\.go):(\d+):(\d+):\s+(.+)$")


class GoVetChecker(TypeCheckerPlugin):
    """Go vet plugin for Go type checking and static analysis."""

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        """Initialize GoVetChecker.

        Args:
            project_root: Optional project root for tool resolution.
        """
        self._project_root = project_root

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "go_vet"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return ["go"]

    @property
    def supports_strict_mode(self) -> bool:
        """Go vet does not have a strict mode."""
        return False

    def get_version(self) -> str:
        """Get Go version."""
        return get_go_version()

    def ensure_binary(self) -> Path:
        """Ensure go binary is available.

        Returns:
            Path to go binary.

        Raises:
            FileNotFoundError: If go is not available.
        """
        return find_go()

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run go vet for type checking and static analysis.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking issues.
        """
        try:
            go_bin = self.ensure_binary()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            return []

        # Require go.mod
        if not has_go_mod(context.project_root):
            LOGGER.info("No go.mod found, skipping go vet")
            return []

        cmd = [
            str(go_bin),
            "vet",
            "-json",
            "./...",
        ]

        LOGGER.debug(f"Running: {' '.join(cmd)}")

        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name="go-vet",
                stream_handler=context.stream_handler,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("go vet timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message="go vet timed out after 300 seconds",
            )
            return []
        except Exception as e:
            LOGGER.error(f"Failed to run go vet: {e}")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"Failed to run go vet: {e}",
            )
            return []

        # go vet -json writes JSON to stderr; text errors also go to stderr
        stderr = result.stderr or ""
        stdout = result.stdout or ""

        # Check if command actually ran (non-zero exit code from go vet means issues found)
        if result.returncode != 0:
            LOGGER.debug(f"go vet exited with code {result.returncode}")

        # Log output for debugging if we got output but no issues
        if stderr.strip():
            LOGGER.debug(f"go vet stderr length: {len(stderr)} chars")
        if stdout.strip():
            LOGGER.debug(f"go vet stdout length: {len(stdout)} chars")

        issues = self._parse_json_output(stderr, context.project_root)
        if not issues and stderr.strip():
            # Fallback: parse text-format stderr
            LOGGER.debug("JSON parsing returned no issues, trying text parsing")
            issues = self._parse_text_output(stderr, context.project_root)

        # Also try stdout as a fallback (some go versions may output there)
        if not issues and stdout.strip():
            LOGGER.debug("Trying to parse stdout for issues")
            stdout_issues = self._parse_text_output(stdout, context.project_root)
            issues.extend(stdout_issues)

        LOGGER.info(f"go vet found {len(issues)} issues")
        return issues

    def _parse_json_output(self, stderr: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse go vet -json output from stderr.

        The JSON format is one object per package:
        {
          "example.com/pkg": {
            "printf": [
              {"posn": "file.go:42:15", "message": "..."}
            ]
          }
        }

        Args:
            stderr: Raw stderr from go vet -json.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not stderr.strip():
            return []

        issues: List[UnifiedIssue] = []
        seen_ids: set = set()

        # go vet -json may output multiple JSON objects (one per package),
        # not necessarily as a single valid JSON document. Try parsing as
        # one blob first, then fall back to line-by-line / brace-balanced.
        json_objects = self._extract_json_objects(stderr)

        for data in json_objects:
            if not isinstance(data, dict):
                continue

            # Each top-level key is a package path, value is a dict of
            # analyzer_name -> list of findings.
            for _pkg_path, analyzers in data.items():
                if not isinstance(analyzers, dict):
                    continue

                for analyzer_name, findings in analyzers.items():
                    if not isinstance(findings, list):
                        continue

                    for finding in findings:
                        issue = self._finding_to_issue(
                            analyzer_name, finding, project_root
                        )
                        if issue and issue.id not in seen_ids:
                            issues.append(issue)
                            seen_ids.add(issue.id)

        return issues

    def _extract_json_objects(self, text: str) -> list:
        """Extract JSON objects from text that may contain multiple root objects.

        Uses a brace-depth counter to split concatenated JSON objects.

        Args:
            text: Raw text possibly containing multiple JSON objects.

        Returns:
            List of parsed JSON objects.
        """
        objects = []

        # First, try parsing the entire text as a single JSON object.
        try:
            obj = json.loads(text)
            return [obj]
        except json.JSONDecodeError:
            pass

        # Fall back to brace-balanced extraction.
        depth = 0
        start = None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        objects.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = None

        return objects

    def _finding_to_issue(
        self,
        analyzer_name: str,
        finding: dict,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Convert a single go vet finding to a UnifiedIssue.

        Args:
            analyzer_name: Name of the vet analyzer (e.g., "printf").
            finding: Finding dict with "posn" and "message" keys.
            project_root: Project root directory.

        Returns:
            UnifiedIssue or None.
        """
        try:
            posn = finding.get("posn", "")
            message = finding.get("message", "")

            if not message:
                return None

            file_path, line, column = parse_go_error_position(posn)

            # Make path relative to project root if absolute
            if file_path:
                p = Path(file_path)
                if p.is_absolute():
                    try:
                        p = p.relative_to(project_root)
                    except ValueError:
                        pass
                file_path = str(p)

            severity = ANALYZER_SEVERITY.get(analyzer_name, Severity.MEDIUM)
            title = f"[{analyzer_name}] {message}"

            issue_id = generate_issue_id(
                "go-vet",
                analyzer_name,
                file_path or "",
                line,
                column,
                message,
            )

            return UnifiedIssue(
                id=issue_id,
                domain=ToolDomain.TYPE_CHECKING,
                source_tool="go_vet",
                severity=severity,
                rule_id=analyzer_name,
                title=title,
                description=message,
                file_path=Path(file_path) if file_path else None,
                line_start=line,
                line_end=line,
                column_start=column,
                column_end=None,
                fixable=False,
                metadata={
                    "analyzer": analyzer_name,
                },
            )
        except Exception as e:
            LOGGER.warning(f"Failed to parse go vet finding: {e}")
            return None

    def _parse_text_output(self, stderr: str, project_root: Path) -> List[UnifiedIssue]:
        """Fallback: parse text-format stderr from go vet.

        Matches lines like:
            ./main.go:42:15: printf: Sprintf format %d has arg s of wrong type string

        Args:
            stderr: Raw stderr from go vet.
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not stderr.strip():
            return []

        issues: List[UnifiedIssue] = []
        seen_ids: set = set()

        for raw_line in stderr.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = _TEXT_ERROR_RE.match(line)
            if not match:
                continue

            file_str = match.group(1)
            line_num = int(match.group(2))
            col_num = int(match.group(3))
            message = match.group(4)

            # Make path relative to project root
            p = Path(file_str)
            if p.is_absolute():
                try:
                    p = p.relative_to(project_root)
                except ValueError:
                    pass
            file_path = str(p)

            # Try to extract analyzer name from the message.
            # Common format: "analyzer_name: actual message"
            analyzer_name = ""
            colon_idx = message.find(":")
            if colon_idx > 0:
                candidate = message[:colon_idx].strip()
                # Analyzer names are simple identifiers (no spaces)
                if re.match(r"^[a-z][a-z0-9]*$", candidate):
                    analyzer_name = candidate
                    message = message[colon_idx + 1 :].strip()

            severity = ANALYZER_SEVERITY.get(analyzer_name, Severity.MEDIUM)
            title = f"[{analyzer_name}] {message}" if analyzer_name else message
            rule_id = analyzer_name if analyzer_name else "vet"

            issue_id = generate_issue_id(
                "go-vet",
                rule_id,
                file_path,
                line_num,
                col_num,
                message,
            )

            if issue_id in seen_ids:
                continue
            seen_ids.add(issue_id)

            issues.append(
                UnifiedIssue(
                    id=issue_id,
                    domain=ToolDomain.TYPE_CHECKING,
                    source_tool="go_vet",
                    severity=severity,
                    rule_id=rule_id,
                    title=title,
                    description=message,
                    file_path=Path(file_path),
                    line_start=line_num,
                    line_end=line_num,
                    column_start=col_num,
                    column_end=None,
                    fixable=False,
                    metadata={
                        "analyzer": analyzer_name or "unknown",
                    },
                )
            )

        return issues
