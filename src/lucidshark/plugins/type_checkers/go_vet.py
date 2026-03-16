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
from lucidshark.core.subprocess_runner import run_with_streaming, temporary_env
from lucidshark.plugins.go_utils import (
    ensure_go_in_path,
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

        # Ensure 'go' command is in PATH
        env_vars = ensure_go_in_path()

        try:
            with temporary_env(env_vars):
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

        # go vet -json: In Go 1.19+, JSON goes to stderr. In Go 1.20+, JSON goes to stdout.
        # Text errors may go to either stream depending on Go version.
        stderr = result.stderr or ""
        stdout = result.stdout or ""

        # Check if command actually ran (non-zero exit code from go vet means issues found)
        LOGGER.debug(f"go vet exited with code {result.returncode}")
        LOGGER.debug(f"go vet stderr length: {len(stderr)} chars")
        LOGGER.debug(f"go vet stdout length: {len(stdout)} chars")
        LOGGER.debug(f"go vet stderr (first 1000 chars): {stderr[:1000]}")
        LOGGER.debug(f"go vet stdout (first 1000 chars): {stdout[:1000]}")

        # Log output for debugging if we got output but no issues
        if stderr.strip():
            LOGGER.debug("go vet stderr has content")
        if stdout.strip():
            LOGGER.debug("go vet stdout has content")

        # Try JSON parsing on both stderr and stdout (Go version dependent)
        # In newer Go versions, JSON goes to stdout; in older versions, stderr
        issues = []

        if stdout.strip():
            LOGGER.debug("Trying to parse stdout as JSON first (Go 1.20+)")
            issues = self._parse_json_output(stdout, context.project_root)
            LOGGER.debug(f"Parsed {len(issues)} issues from stdout JSON")

        if not issues and stderr.strip():
            LOGGER.debug(
                "No issues from stdout, trying to parse stderr as JSON (Go 1.19)"
            )
            issues = self._parse_json_output(stderr, context.project_root)
            LOGGER.debug(f"Parsed {len(issues)} issues from stderr JSON")

        # Fallback: parse text-format output from stderr
        if not issues and stderr.strip():
            LOGGER.debug(
                "JSON parsing returned no issues, trying text parsing on stderr"
            )
            text_issues = self._parse_text_output(stderr, context.project_root)
            LOGGER.debug(f"Parsed {len(text_issues)} issues from stderr text")
            issues = text_issues

        # Fallback: parse text-format output from stdout
        if not issues and stdout.strip():
            LOGGER.debug("Still no issues, trying text parsing on stdout")
            stdout_text_issues = self._parse_text_output(stdout, context.project_root)
            LOGGER.debug(f"Parsed {len(stdout_text_issues)} issues from stdout text")
            issues.extend(stdout_text_issues)

        LOGGER.info(f"go vet found {len(issues)} issues")
        return issues

    def _parse_json_output(self, output: str, project_root: Path) -> List[UnifiedIssue]:
        """Parse go vet -json output.

        The JSON format is one object per package:
        {
          "example.com/pkg": {
            "printf": [
              {"posn": "file.go:42:15", "message": "..."}
            ]
          }
        }

        go vet -json may output multiple JSON objects including empty {} objects.

        Args:
            output: Raw output from go vet -json (stderr or stdout).
            project_root: Project root directory.

        Returns:
            List of UnifiedIssue objects.
        """
        if not output.strip():
            LOGGER.debug("Output is empty, no JSON to parse")
            return []

        issues: List[UnifiedIssue] = []
        seen_ids: set = set()

        # go vet -json may output multiple JSON objects (one per package + empty ones),
        # not necessarily as a single valid JSON document. Extract all objects.
        json_objects = self._extract_json_objects(output)
        LOGGER.debug(f"Extracted {len(json_objects)} JSON objects from output")

        for obj_idx, data in enumerate(json_objects):
            if not isinstance(data, dict):
                LOGGER.debug(f"Object #{obj_idx} is not a dict, skipping")
                continue

            # Empty dicts {} are valid but contain no issues
            if not data:
                LOGGER.debug(f"Object #{obj_idx} is empty dict, skipping")
                continue

            LOGGER.debug(
                f"Processing object #{obj_idx} with {len(data)} top-level keys"
            )

            # Each top-level key is a package path, value is a dict of
            # analyzer_name -> list of findings.
            for pkg_path, analyzers in data.items():
                if not isinstance(analyzers, dict):
                    LOGGER.debug(
                        f"Package {pkg_path} analyzers is not a dict: {type(analyzers)}"
                    )
                    continue

                LOGGER.debug(f"Package {pkg_path} has {len(analyzers)} analyzers")

                for analyzer_name, findings in analyzers.items():
                    if not isinstance(findings, list):
                        LOGGER.debug(
                            f"Analyzer {analyzer_name} findings is not a list: {type(findings)}"
                        )
                        continue

                    LOGGER.debug(
                        f"Analyzer {analyzer_name} has {len(findings)} findings"
                    )

                    for finding in findings:
                        issue = self._finding_to_issue(
                            analyzer_name, finding, project_root
                        )
                        if issue and issue.id not in seen_ids:
                            issues.append(issue)
                            seen_ids.add(issue.id)
                            LOGGER.debug(f"Added issue: {issue.title}")

        LOGGER.debug(f"Total issues parsed from JSON: {len(issues)}")
        return issues

    def _extract_json_objects(self, text: str) -> list:
        """Extract JSON objects from text that may contain multiple root objects.

        Uses a brace-depth counter to split concatenated JSON objects.
        go vet -json outputs multiple JSON objects, including empty {} objects,
        so we extract all of them and filter later.

        Args:
            text: Raw text possibly containing multiple JSON objects.

        Returns:
            List of parsed JSON objects (may include empty dicts).
        """
        objects = []

        # First, try parsing the entire text as a single JSON object.
        try:
            obj = json.loads(text)
            # Always return the object, even if empty - filtering happens later
            LOGGER.debug(
                f"Parsed entire text as single JSON object: {len(str(obj))} chars"
            )
            return [obj]
        except json.JSONDecodeError:
            LOGGER.debug(
                "Could not parse entire text as single JSON, trying brace-balanced extraction"
            )

        # Fall back to brace-balanced extraction.
        # go vet -json outputs multiple JSON objects (including empty {})
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
                        LOGGER.debug(
                            f"Extracted JSON object #{len(objects)}: {len(candidate)} chars"
                        )
                    except json.JSONDecodeError as e:
                        LOGGER.debug(f"Failed to parse JSON candidate: {e}")
                    start = None

        LOGGER.debug(f"Extracted {len(objects)} total JSON objects via brace-balancing")
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

            # Make path relative to project root
            # Resolve symlinks and normalize paths to handle .. components
            if file_path:
                p = Path(file_path)
                # Resolve both the file path and project root to handle symlinks
                # (e.g., /tmp -> /private/tmp on macOS)
                resolved_root = project_root.resolve()
                if p.is_absolute():
                    # For absolute paths, resolve and make relative if inside project
                    try:
                        resolved_file = p.resolve()
                        p = resolved_file.relative_to(resolved_root)
                    except ValueError:
                        # Path is outside project root, keep as-is
                        pass
                else:
                    # For relative paths, resolve relative to project root to normalize .. components
                    try:
                        resolved_file = (resolved_root / p).resolve()
                        p = resolved_file.relative_to(resolved_root)
                    except ValueError:
                        # Path is outside project root, keep resolved absolute
                        p = resolved_file
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
            # Resolve symlinks and normalize paths to handle .. components
            p = Path(file_str)
            resolved_root = project_root.resolve()
            if p.is_absolute():
                try:
                    # Resolve symlinks for both paths
                    resolved_file = p.resolve()
                    # Try to make it relative to project root
                    p = resolved_file.relative_to(resolved_root)
                except ValueError:
                    # Path is outside project root, keep as-is
                    pass
            else:
                # For relative paths, resolve relative to project root to normalize .. components
                try:
                    resolved_file = (resolved_root / p).resolve()
                    p = resolved_file.relative_to(resolved_root)
                except ValueError:
                    # Path is outside project root, keep resolved absolute
                    p = resolved_file
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
