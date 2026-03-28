"""Duplo duplication detection plugin.

lucidshark-duplo is a Rust-based code duplication detector that supports
multiple languages including Python, JavaScript, TypeScript, Rust, Java, C/C++.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import List, Optional
import pathspec

from lucidshark.bootstrap.download import secure_urlopen
from lucidshark.bootstrap.paths import LucidsharkPaths
from lucidshark.bootstrap.platform import get_platform_info
from lucidshark.bootstrap.validation import (
    is_binary_for_current_platform,
    remove_stale_binary_dir,
)
from lucidshark.bootstrap.versions import get_tool_version
from lucidshark.core.git import is_git_repo
from lucidshark.core.logging import get_logger
from lucidshark.core.models import (
    ScanContext,
    Severity,
    SkipReason,
    ToolDomain,
    UnifiedIssue,
)
from lucidshark.core.subprocess_runner import run_with_streaming
from lucidshark.plugins.duplication.base import (
    DuplicateBlock,
    DuplicationPlugin,
    DuplicationResult,
)

LOGGER = get_logger(__name__)

# Default version from pyproject.toml [tool.lucidshark.tools]
DEFAULT_VERSION = get_tool_version("duplo")

# Supported file extensions per language
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".rs": "rust",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".cpp": "c++",
    ".cxx": "c++",
    ".cc": "c++",
    ".h": "c",
    ".hpp": "c++",
    ".hxx": "c++",
    ".cs": "csharp",
    ".go": "go",
    ".scala": "scala",
    ".sc": "scala",
    ".rb": "ruby",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".vb": "vb",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
}


class DuploPlugin(DuplicationPlugin):
    """Duplo duplication detection plugin."""

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        project_root: Optional[Path] = None,
    ):
        """Initialize DuploPlugin.

        Args:
            version: Duplo version to use.
            project_root: Optional project root for tool installation.
        """
        super().__init__(project_root)
        self._version = version
        if project_root:
            self._paths = LucidsharkPaths.for_project(project_root)
        else:
            self._paths = LucidsharkPaths.default()

    @property
    def name(self) -> str:
        """Plugin identifier."""
        return "duplo"

    @property
    def languages(self) -> List[str]:
        """Supported languages."""
        return [
            "python",
            "rust",
            "java",
            "javascript",
            "typescript",
            "c",
            "c++",
            "csharp",
            "go",
            "scala",
            "ruby",
            "erlang",
            "vb",
            "html",
            "css",
        ]

    def get_version(self) -> str:
        """Get Duplo version."""
        return self._version

    def ensure_binary(self) -> Path:
        """Ensure Duplo binary is available.

        Downloads from GitHub releases if not present.

        Returns:
            Path to Duplo binary.
        """
        binary_dir = self._paths.plugin_bin_dir(self.name, self._version)
        binary_path = binary_dir / "lucidshark-duplo"

        if binary_path.exists():
            if is_binary_for_current_platform(binary_path):
                LOGGER.debug(f"Duplo binary found at {binary_path}")
                return binary_path
            remove_stale_binary_dir(binary_dir, "lucidshark-duplo")

        LOGGER.info(f"Downloading lucidshark-duplo v{self._version}...")
        self._download_binary(binary_dir)

        if not binary_path.exists():
            raise RuntimeError(f"Failed to download Duplo binary to {binary_path}")

        return binary_path

    def _get_baseline_path(self) -> Path:
        """Get the path for the duplo baseline file.

        Returns:
            Path to the baseline JSON file.
        """
        return self._paths.plugin_cache_dir("duplo") / "baseline.json"

    def _get_cache_dir(self) -> Path:
        """Get the cache directory for duplo file processing.

        Returns:
            Path to the file cache directory.
        """
        return self._paths.plugin_cache_dir("duplo") / "file-cache"

    def detect_duplication(
        self,
        context: ScanContext,
        threshold: float = 10.0,
        min_lines: int = 4,
        min_chars: int = 3,
        exclude_patterns: Optional[List[str]] = None,
        use_baseline: bool = False,
        use_cache: bool = True,
        use_git: bool = True,
    ) -> DuplicationResult:
        """Run duplication detection on the entire project.

        Note: Always scans the entire project to detect cross-file duplicates,
        regardless of paths in context.

        Args:
            context: Scan context with project root.
            threshold: Maximum allowed duplication percentage.
            min_lines: Minimum lines for a duplicate block.
            min_chars: Minimum characters per line.
            exclude_patterns: Additional patterns to exclude from duplication scan.
            use_baseline: If True, track known duplicates and only report new ones.
            use_cache: If True, cache processed files for faster re-runs.
            use_git: If True, use git ls-files for file discovery when in a git repo.

        Returns:
            DuplicationResult with statistics and issues.
        """
        binary = self.ensure_binary()

        # Determine if we can use git mode
        in_git_repo = use_git and is_git_repo(context.project_root)

        # Use the raw --git flag only when there are no exclude patterns
        # to apply.  Both duplication-specific patterns (e.g. "tests/**")
        # and global ignore patterns from lucidshark.yml may reference
        # paths tracked by git, so when either is present we fall back to
        # git ls-files + filtering — still using git for file discovery,
        # but with pattern matching applied on top.
        has_exclude_patterns = bool(exclude_patterns) or bool(
            context.get_exclude_patterns()
        )
        use_git_flag = in_git_repo and not has_exclude_patterns

        file_list_path: Optional[Path] = None

        if use_git_flag:
            LOGGER.debug("Using git mode for file discovery")
        elif in_git_repo:
            # In a git repo but we have exclude patterns (global and/or
            # duplication-specific) — collect via git ls-files and filter
            # so exclusions are honoured.
            LOGGER.debug("Using git ls-files with exclude filtering")
            all_exclude_patterns = list(context.get_exclude_patterns())
            if exclude_patterns:
                all_exclude_patterns.extend(exclude_patterns)
            source_files = self._collect_git_files_filtered(
                context,
                all_exclude_patterns,
            )
            if not source_files:
                LOGGER.debug("No source files found for duplication detection")
                return DuplicationResult(threshold=threshold)

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                for file_path in source_files:
                    f.write(f"{file_path}\n")
                file_list_path = Path(f.name)
        else:
            # Collect all source files in project (always full scan)
            source_files = self._collect_source_files(context, exclude_patterns)

            if not source_files:
                LOGGER.debug("No source files found for duplication detection")
                return DuplicationResult(threshold=threshold)

            # Write file list to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                for file_path in source_files:
                    f.write(f"{file_path}\n")
                file_list_path = Path(f.name)

        try:
            # Build command
            # lucidshark-duplo <files|--git> <output> [options]
            # Using "-" as output means stdout
            cmd = [str(binary)]

            if use_git_flag:
                cmd.append("--git")
            else:
                assert file_list_path is not None
                cmd.append(str(file_list_path))

            cmd.extend(
                [
                    "-",  # Output to stdout
                    "--json",
                    "--min-lines",
                    str(min_lines),
                    "--min-chars",
                    str(min_chars),
                ]
            )

            # Append cache flags
            if use_cache:
                cache_dir = self._get_cache_dir()
                cache_dir.mkdir(parents=True, exist_ok=True)
                cmd.extend(["--cache", "--cache-dir", str(cache_dir)])

            # Append baseline flags
            if use_baseline:
                baseline_path = self._get_baseline_path()
                baseline_path.parent.mkdir(parents=True, exist_ok=True)
                if baseline_path.exists():
                    LOGGER.info("Comparing against baseline for known duplicates")
                    cmd.extend(["--baseline", str(baseline_path)])
                else:
                    LOGGER.info("No baseline found, establishing baseline on first run")
                cmd.extend(["--save-baseline", str(baseline_path)])

            LOGGER.debug(f"Running: {' '.join(cmd)}")

            try:
                result = run_with_streaming(
                    cmd=cmd,
                    cwd=context.project_root,
                    tool_name="duplo",
                    stream_handler=context.stream_handler,
                    timeout=300,  # 5 minutes for large projects
                )
            except subprocess.TimeoutExpired:
                LOGGER.warning("Duplo timed out after 300 seconds")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.DUPLICATION,
                    reason=SkipReason.EXECUTION_FAILED,
                    message="Duplo timed out after 300 seconds",
                )
                return DuplicationResult(threshold=threshold, execution_failed=True)
            except Exception as e:
                LOGGER.error(f"Failed to run Duplo: {e}")
                context.record_skip(
                    tool_name=self.name,
                    domain=ToolDomain.DUPLICATION,
                    reason=SkipReason.EXECUTION_FAILED,
                    message=f"Failed to run Duplo: {e}",
                )
                return DuplicationResult(threshold=threshold, execution_failed=True)

            # Parse JSON output
            return self._parse_output(
                result.stdout,
                context.project_root,
                threshold,
            )

        finally:
            # Clean up temp file
            if file_list_path is not None:
                file_list_path.unlink(missing_ok=True)

    def _collect_git_files_filtered(
        self,
        context: ScanContext,
        exclude_patterns: List[str],
    ) -> List[Path]:
        """Collect source files via ``git ls-files``, applying exclude patterns.

        This is used when we're in a git repo but need to honour exclude
        patterns that the duplo ``--git`` flag cannot apply.

        Args:
            context: Scan context.
            exclude_patterns: Combined list of exclude patterns to apply.

        Returns:
            List of source file paths.
        """
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=context.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            LOGGER.warning("git ls-files failed, falling back to file walk")
            return self._collect_source_files(context, exclude_patterns)

        source_files = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            path = context.project_root / line
            if not path.is_file():
                continue
            if self._should_exclude(line, exclude_patterns):
                continue
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                source_files.append(path)

        LOGGER.debug(
            f"Found {len(source_files)} source files via git ls-files (filtered)"
        )
        return source_files

    def _collect_source_files(
        self,
        context: ScanContext,
        extra_exclude_patterns: Optional[List[str]] = None,
    ) -> List[Path]:
        """Collect all source files in the project.

        Always scans entire project for duplication detection to catch
        cross-file duplicates.

        Args:
            context: Scan context.
            extra_exclude_patterns: Additional patterns to exclude (from duplication config).

        Returns:
            List of source file paths.
        """
        source_files = []
        exclude_patterns = context.get_exclude_patterns()
        if extra_exclude_patterns:
            exclude_patterns = list(exclude_patterns) + list(extra_exclude_patterns)

        for path in context.project_root.rglob("*"):
            if not path.is_file():
                continue

            # Skip excluded patterns
            relative_path = str(path.relative_to(context.project_root))
            if self._should_exclude(relative_path, exclude_patterns):
                continue

            # Check if supported file type
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                source_files.append(path)

        LOGGER.debug(
            f"Found {len(source_files)} source files for duplication detection"
        )
        return source_files

    def _should_exclude(self, path: str, patterns: List[str]) -> bool:
        """Check if path should be excluded using gitignore-style patterns.

        Args:
            path: Relative path to check (forward slashes).
            patterns: List of gitignore-style exclude patterns.

        Returns:
            True if path should be excluded.
        """
        # Always exclude common directories
        default_excludes = [
            ".git/**",
            "**/node_modules/**",
            "**/__pycache__/**",
            "**/.venv/**",
            "**/venv/**",
            "**/target/**",
            "**/build/**",
            "**/dist/**",
            "**/.lucidshark/**",
        ]

        all_patterns = default_excludes + list(patterns)

        # Use pathspec for proper gitignore-style matching (supports **)
        spec = pathspec.PathSpec.from_lines(
            "gitignore",
            all_patterns,
        )

        # Normalize path to forward slashes for pathspec
        normalized_path = path.replace("\\", "/")
        return spec.match_file(normalized_path)

    def _download_binary(self, dest_dir: Path) -> None:
        """Download and extract Duplo binary for current platform.

        Args:
            dest_dir: Directory to download and extract to.
        """
        platform_info = get_platform_info()

        # Map platform to Duplo release naming
        # Format: lucidshark-duplo-{os}-{arch}.tar.gz
        # Examples:
        #   lucidshark-duplo-macos-x86_64.tar.gz
        #   lucidshark-duplo-macos-aarch64.tar.gz
        #   lucidshark-duplo-linux-x86_64.tar.gz
        os_name = {
            "darwin": "macos",
            "linux": "linux",
        }.get(platform_info.os)

        arch_name = {
            "amd64": "x86_64",
            "arm64": "aarch64",
        }.get(platform_info.arch)

        if not os_name or not arch_name:
            raise RuntimeError(
                f"Unsupported platform: {platform_info.os}-{platform_info.arch}"
            )

        # Construct download URL
        filename = f"lucidshark-duplo-{os_name}-{arch_name}.tar.gz"
        url = f"https://github.com/toniantunovi/lucidshark-duplo/releases/download/v{self._version}/{filename}"

        LOGGER.debug(f"Downloading from {url}")

        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Validate URL scheme and domain for security
        if not url.startswith("https://github.com/"):
            raise ValueError(f"Invalid download URL: {url}")

        # Download and extract
        binary_name = "lucidshark-duplo"
        tmp_file = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        tmp_path = Path(tmp_file.name)

        try:
            with secure_urlopen(url) as response:  # nosec B310 nosemgrep
                tmp_file.write(response.read())
            tmp_file.close()

            # Extract tarball safely (prevent path traversal)
            with tarfile.open(tmp_path, "r:gz") as tar:
                for tar_member in tar.getmembers():
                    # Validate each member path to prevent traversal attacks
                    member_path = (dest_dir / tar_member.name).resolve()
                    if not member_path.is_relative_to(dest_dir.resolve()):
                        raise ValueError(f"Path traversal detected: {tar_member.name}")
                    # Extract only the binary
                    if (
                        tar_member.name.endswith(binary_name)
                        or tar_member.name == binary_name
                    ):
                        tar_member.name = binary_name
                        tar.extract(tar_member, path=dest_dir)
                        break

            # Make binary executable
            binary_path = dest_dir / binary_name
            if binary_path.exists():
                binary_path.chmod(0o755)
            LOGGER.info(f"lucidshark-duplo v{self._version} installed to {binary_path}")

        finally:
            # Ensure file is closed before attempting to delete
            if not tmp_file.closed:
                tmp_file.close()
            tmp_path.unlink(missing_ok=True)

    def _parse_output(
        self,
        output: str,
        project_root: Path,
        threshold: float,
    ) -> DuplicationResult:
        """Parse Duplo JSON output.

        Args:
            output: JSON output from Duplo.
            project_root: Project root directory.
            threshold: Maximum allowed duplication percentage.

        Returns:
            DuplicationResult with statistics and issues.
        """
        if not output.strip():
            return DuplicationResult(threshold=threshold)

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse Duplo output as JSON")
            return DuplicationResult(threshold=threshold)

        # Extract summary
        summary = data.get("summary", {})
        duplicates_data = data.get("duplicates", [])

        # Parse duplicate blocks
        duplicates = []
        issues = []

        for dup in duplicates_data:
            file1_info = dup.get("file1", {})
            file2_info = dup.get("file2", {})
            lines = dup.get("lines", [])

            file1_path = Path(file1_info.get("path", ""))
            file2_path = Path(file2_info.get("path", ""))

            # Make paths absolute if relative
            if not file1_path.is_absolute():
                file1_path = project_root / file1_path
            if not file2_path.is_absolute():
                file2_path = project_root / file2_path

            block = DuplicateBlock(
                file1=file1_path,
                file2=file2_path,
                start_line1=file1_info.get("start_line", 1),
                end_line1=file1_info.get("end_line", 1),
                start_line2=file2_info.get("start_line", 1),
                end_line2=file2_info.get("end_line", 1),
                line_count=dup.get("line_count", 0),
                code_snippet="\n".join(lines[:5]) if lines else None,  # First 5 lines
            )
            duplicates.append(block)

            # Create UnifiedIssue for each duplicate block
            issue = self._block_to_issue(block, project_root)
            issues.append(issue)

        result = DuplicationResult(
            files_analyzed=summary.get("files_analyzed", 0),
            total_lines=summary.get("total_lines", 0),
            duplicate_blocks=summary.get("duplicate_blocks", len(duplicates)),
            duplicate_lines=summary.get("duplicate_lines", 0),
            threshold=threshold,
            duplicates=duplicates,
            issues=issues,
        )

        LOGGER.info(
            f"Duplo found {result.duplicate_blocks} duplicate blocks "
            f"({result.duplication_percent:.1f}% duplication)"
        )

        return result

    def _block_to_issue(
        self,
        block: DuplicateBlock,
        project_root: Path,
    ) -> UnifiedIssue:
        """Convert a duplicate block to a UnifiedIssue.

        Args:
            block: Duplicate block to convert.
            project_root: Project root directory.

        Returns:
            UnifiedIssue representing the duplicate.
        """
        # Generate deterministic ID
        content = (
            f"{block.file1}:{block.start_line1}:"
            f"{block.file2}:{block.start_line2}:{block.line_count}"
        )
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        issue_id = f"duplo-{hash_val}"

        # Make file2 path relative for display
        try:
            file2_rel = block.file2.relative_to(project_root)
        except ValueError:
            file2_rel = block.file2

        return UnifiedIssue(
            id=issue_id,
            domain=ToolDomain.DUPLICATION,
            source_tool="duplo",
            severity=Severity.LOW,  # Default to LOW for duplicates
            rule_id="DUPLICATE",
            title=f"Code duplicate: {block.line_count} lines",
            description=(
                f"Duplicate code block found between this file "
                f"(lines {block.start_line1}-{block.end_line1}) and "
                f"{file2_rel} (lines {block.start_line2}-{block.end_line2})"
            ),
            file_path=block.file1,
            line_start=block.start_line1,
            line_end=block.end_line1,
            code_snippet=block.code_snippet,
            recommendation=(
                "Consider extracting this code into a shared function or module "
                "to reduce duplication and improve maintainability."
            ),
            metadata={
                "duplicate_file": str(file2_rel),
                "duplicate_line_start": block.start_line2,
                "duplicate_line_end": block.end_line2,
                "line_count": block.line_count,
            },
        )
