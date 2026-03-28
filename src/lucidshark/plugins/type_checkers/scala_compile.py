"""Scala compiler type checker plugin.

Uses sbt compile, mvn compile, or gradle compileScala to run the Scala
compiler and extract type errors and warnings.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

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
from lucidshark.plugins.utils import find_scala_build_tool

LOGGER = get_logger(__name__)


class ScalaCompileChecker(TypeCheckerPlugin):
    """Scala compiler type checker plugin.

    Runs the Scala compiler via the project build tool (sbt, Maven, or Gradle)
    and parses compiler errors and warnings into UnifiedIssues.
    """

    def __init__(self, project_root: Optional[Path] = None, **kwargs) -> None:
        super().__init__(project_root=project_root, **kwargs)

    @property
    def name(self) -> str:
        return "scala_compile"

    @property
    def languages(self) -> List[str]:
        return ["scala"]

    @property
    def supports_strict_mode(self) -> bool:
        return False

    def _detect_build_system(self) -> Tuple[Path, str]:
        """Detect the Scala build system."""
        project_root = self._project_root or Path.cwd()
        return find_scala_build_tool(project_root)

    def get_version(self) -> str:
        try:
            binary, build_system = self._detect_build_system()
            return f"{build_system}-compile"
        except FileNotFoundError:
            return "unknown"

    def ensure_binary(self) -> Path:
        """Ensure build tool is available.

        Returns:
            Path to the build tool binary.

        Raises:
            FileNotFoundError: If no build tool is found.
        """
        binary, _ = self._detect_build_system()
        return binary

    def check(self, context: ScanContext) -> List[UnifiedIssue]:
        """Run Scala compilation and extract type errors.

        Args:
            context: Scan context with paths and configuration.

        Returns:
            List of type checking issues.
        """
        try:
            binary, build_system = self._detect_build_system()
        except FileNotFoundError as e:
            LOGGER.warning(str(e))
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.TOOL_NOT_INSTALLED,
                message=str(e),
                suggestion="Ensure build.sbt, pom.xml, or build.gradle exists",
            )
            return []

        if build_system == "sbt":
            return self._run_sbt_compile(binary, context)
        elif build_system == "maven":
            return self._run_maven_compile(binary, context)
        else:
            return self._run_gradle_compile(binary, context)

    def _run_sbt_compile(
        self, binary: Path, context: ScanContext
    ) -> List[UnifiedIssue]:
        """Run sbt compile and parse output."""
        cmd = [str(binary), "--no-colors", "compile"]

        output = self._run_compile_command(cmd, context, "sbt-compile")
        if output is None:
            return []

        return self._parse_scala_compiler_output(output, context.project_root)

    def _run_maven_compile(
        self, binary: Path, context: ScanContext
    ) -> List[UnifiedIssue]:
        """Run mvn compile and parse output."""
        cmd = [str(binary), "compile", "-B"]

        output = self._run_compile_command(cmd, context, "maven-compile")
        if output is None:
            return []

        return self._parse_scala_compiler_output(output, context.project_root)

    def _run_gradle_compile(
        self, binary: Path, context: ScanContext
    ) -> List[UnifiedIssue]:
        """Run gradle compileScala and parse output."""
        cmd = [str(binary), "compileScala", "--no-daemon"]

        output = self._run_compile_command(cmd, context, "gradle-compile")
        if output is None:
            return []

        return self._parse_scala_compiler_output(output, context.project_root)

    def _run_compile_command(
        self,
        cmd: List[str],
        context: ScanContext,
        tool_label: str,
    ) -> Optional[str]:
        """Run a compile command and return combined output."""
        try:
            result = run_with_streaming(
                cmd=cmd,
                cwd=context.project_root,
                tool_name=tool_label,
                stream_handler=context.stream_handler,
                timeout=300,
            )
            # Combine stdout and stderr (compiler output may go to either)
            return (result.stdout or "") + "\n" + (result.stderr or "")
        except subprocess.TimeoutExpired:
            LOGGER.warning(f"{tool_label} timed out after 300 seconds")
            context.record_skip(
                tool_name=self.name,
                domain=ToolDomain.TYPE_CHECKING,
                reason=SkipReason.EXECUTION_FAILED,
                message=f"{tool_label} timed out after 300 seconds",
            )
            return None
        except Exception as e:
            # Compile errors cause non-zero exit - we still want the output
            error_output = ""
            if hasattr(e, "stdout"):
                error_output += getattr(e, "stdout", "") or ""
            if hasattr(e, "stderr"):
                error_output += "\n" + (getattr(e, "stderr", "") or "")
            if error_output.strip():
                return error_output
            LOGGER.debug(f"{tool_label} completed with: {e}")
            return ""

    def _parse_scala_compiler_output(
        self, output: str, project_root: Path
    ) -> List[UnifiedIssue]:
        """Parse Scala compiler error/warning output.

        Scala compiler outputs diagnostics in the format:
        [error] /path/to/File.scala:10:5: type mismatch
        [warn] /path/to/File.scala:20:3: unused import
        """
        if not output.strip():
            return []

        issues = []

        # Pattern for scalac/sbt output:
        # [error] /path/File.scala:10:5: message
        # [warn] /path/File.scala:10:5: message
        # Also handles: /path/File.scala:10: error: message (scalac direct)
        patterns = [
            # sbt format: [error] file:line:col: message
            re.compile(
                r"\[(error|warn(?:ing)?)\]\s+(.+?\.scala):(\d+):(\d+):\s*(.*)"
            ),
            # sbt format: [error] file:line: message
            re.compile(
                r"\[(error|warn(?:ing)?)\]\s+(.+?\.scala):(\d+):\s*(.*)"
            ),
            # scalac direct: file:line: error: message
            re.compile(
                r"(.+?\.scala):(\d+):(\d+):\s*(error|warning):\s*(.*)"
            ),
            # scalac direct without column: file:line: error: message
            re.compile(
                r"(.+?\.scala):(\d+):\s*(error|warning):\s*(.*)"
            ),
        ]

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            for i, pattern in enumerate(patterns):
                match = pattern.match(line)
                if match:
                    if i == 0:
                        # sbt format with column
                        severity_str = match.group(1)
                        file_path_str = match.group(2)
                        line_num = int(match.group(3))
                        col_num = int(match.group(4))
                        message = match.group(5)
                    elif i == 1:
                        # sbt format without column
                        severity_str = match.group(1)
                        file_path_str = match.group(2)
                        line_num = int(match.group(3))
                        col_num = None
                        message = match.group(4)
                    elif i == 2:
                        # scalac direct with column
                        file_path_str = match.group(1)
                        line_num = int(match.group(2))
                        col_num = int(match.group(3))
                        severity_str = match.group(4)
                        message = match.group(5)
                    else:
                        # scalac direct without column
                        file_path_str = match.group(1)
                        line_num = int(match.group(2))
                        col_num = None
                        severity_str = match.group(3)
                        message = match.group(4)

                    issue = self._create_issue(
                        file_path_str, line_num, col_num, severity_str, message, project_root
                    )
                    if issue:
                        issues.append(issue)
                    break

        LOGGER.info(f"Scala compile found {len(issues)} issues")
        return issues

    def _create_issue(
        self,
        file_path_str: str,
        line_num: int,
        col_num: Optional[int],
        severity_str: str,
        message: str,
        project_root: Path,
    ) -> Optional[UnifiedIssue]:
        """Create a UnifiedIssue from compiler diagnostic."""
        severity_str = severity_str.lower()
        if severity_str == "error":
            severity = Severity.HIGH
        elif severity_str in ("warn", "warning"):
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        path = Path(file_path_str)
        if not path.is_absolute():
            path = project_root / path

        issue_id = self._generate_issue_id(file_path_str, line_num, message)

        return UnifiedIssue(
            id=issue_id,
            domain=ToolDomain.TYPE_CHECKING,
            source_tool="scala_compile",
            severity=severity,
            rule_id="compile_error" if severity == Severity.HIGH else "compile_warning",
            title=message[:120] if len(message) > 120 else message,
            description=message,
            file_path=path,
            line_start=line_num,
            line_end=line_num,
            column_start=col_num,
            fixable=False,
            metadata={
                "severity_raw": severity_str,
            },
        )

    def _generate_issue_id(self, file: str, line: int, message: str) -> str:
        content = f"scala_compile:{file}:{line}:{message[:50]}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"scala-compile-{hash_val}"
