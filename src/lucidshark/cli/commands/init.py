"""Init command implementation.

Configure AI tools (Claude Code) to use LucidShark via MCP.
"""

from __future__ import annotations

import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    from lucidshark.config.models import LucidSharkConfig

from lucidshark.cli.commands import Command
from lucidshark.cli.exit_codes import EXIT_SUCCESS, EXIT_INVALID_USAGE
from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)

# MCP server arguments for LucidShark
LUCIDSHARK_MCP_ARGS = ["serve", "--mcp"]

# Claude skill content for proactive lucidshark usage
LUCIDSHARK_SKILL_CONTENT = """---
name: lucidshark
description: "PROACTIVE code quality scanning. Run after writing/editing code, fixing bugs, adding features, refactoring, before commits. Auto-run - don't wait for user to ask."
---

# LucidShark Code Quality Scanner

Run scans proactively after code changes. Don't wait for user to ask.

## When to Scan

| Trigger | Action |
|---------|--------|
| After editing code | `scan(fix=true)` |
| After fixing bugs | `scan(fix=true)` to verify no new issues |
| After adding features | Scan before reporting done |
| Before commits | `scan(domains=["all"])` |
| User says "check/scan/lint/quality/errors" | Run appropriate scan |

**Skip scanning** if user explicitly says "don't scan" or "skip checks".

## Smart Domain Selection

Pick domains based on what files changed — don't always scan everything:

| Files Changed | Recommended Domains |
|---|---|
| `.py` | `["linting", "type_checking"]` |
| `.js`, `.ts`, `.tsx`, `.jsx` | `["linting", "type_checking"]` |
| `.rs` | `["linting", "type_checking", "testing"]` |
| `.go` | `["linting", "type_checking"]` |
| `.java`, `.kt` | `["linting", "type_checking"]` |
| `Dockerfile`, `docker-compose.*` | `["container"]` |
| `.tf`, `.yaml`/`.yml` (k8s/CloudFormation) | `["iac"]` |
| `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod` | `["sca"]` |
| Auth, crypto, input handling, SQL code | `["sast"]` |
| Mixed / many file types / before commit | `["all"]` |

## Commands

| Command | Use Case |
|---------|----------|
| `scan(fix=true)` | Default after code changes (auto-fixes linting) |
| `scan(domains=[...], fix=true)` | Targeted scan with auto-fix for specific domains |
| `scan(domains=["all"])` | Full scan before commits or PRs |
| `scan(all_files=true)` | Scan entire project, not just changed files |
| `check_file(file_path="...")` | Quick check on a single file |

**Default:** Scans only uncommitted changes. Use `all_files=true` for full project.

## Fixing Issues

1. `scan(fix=true)` - Auto-fixes linting issues
2. `get_fix_instructions(issue_id)` - Detailed guidance for manual fixes
3. `apply_fix(issue_id)` - Apply auto-fix for specific issue
4. Re-scan after fixes to confirm resolution

## Workflow

1. Make code changes → 2. `scan(fix=true)` → 3. Fix remaining issues → 4. Re-scan if needed → 5. Report done

**Task is complete when scan shows zero issues.**

## Setup & Config

| Command | Purpose |
|---------|---------|
| `get_status()` | Show configuration and cached issues |
| `autoconfigure()` | Guide for creating lucidshark.yml |
| `validate_config()` | Validate configuration file |
| `get_help()` | Full documentation |
"""

# CLAUDE.md section for always-in-context proactive scanning instructions
# This is the most impactful integration point because CLAUDE.md is loaded
# into Claude's system prompt for every conversation.
LUCIDSHARK_CLAUDE_MD_SECTION = """\

<!-- lucidshark:start - managed by lucidshark init, do not edit manually -->
## LucidShark - Code Quality Scanning

LucidShark is available as an MCP tool (`mcp__lucidshark__scan`). Run it **proactively** after code changes — do not wait for the user to ask.

### Automatic Scan Triggers

You MUST run a scan in these situations without being asked:

1. **After editing/writing code files** — run `mcp__lucidshark__scan(fix=true)` with targeted domains (see table below)
2. **After fixing a bug** — scan to verify the fix didn't introduce new issues
3. **Before reporting any task as complete** — always scan your changes before saying "done"
4. **Before creating a commit** — run `mcp__lucidshark__scan(domains=["all"])` for a comprehensive check
5. **After refactoring** — scan to catch regressions or style issues introduced

### Smart Domain Selection

Choose scan domains based on the file types you changed. Targeted scans are fast — prefer them over scanning everything:

| Files you edited | Domains to use |
|---|---|
| Python (`.py`) | `domains=["linting", "type_checking"]` |
| JavaScript/TypeScript (`.js`, `.ts`, `.tsx`, `.jsx`) | `domains=["linting", "type_checking"]` |
| Rust (`.rs`) | `domains=["linting", "type_checking"]` |
| Go (`.go`) | `domains=["linting", "type_checking"]` |
| Java/Kotlin (`.java`, `.kt`) | `domains=["linting", "type_checking"]` |
| Dockerfile / docker-compose | `domains=["container"]` |
| Terraform / K8s / IaC YAML | `domains=["iac"]` |
| Dependency files (`package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`) | `domains=["sca"]` |
| Security-sensitive code (auth, crypto, SQL, input handling) | `domains=["sast"]` |
| Multiple file types or before commit/PR | `domains=["all"]` |

### Quick Reference

- **Fast scan after edits**: `mcp__lucidshark__scan(fix=true)` — auto-fixes linting, scans only changed files
- **Targeted scan**: `mcp__lucidshark__scan(domains=["linting", "type_checking"], fix=true)` — pick relevant domains
- **Pre-commit full scan**: `mcp__lucidshark__scan(domains=["all"])` — checks everything
- **Single file check**: `mcp__lucidshark__check_file(file_path="path/to/file")` — quick check on one file
- **Fix guidance**: `mcp__lucidshark__get_fix_instructions(issue_id="...")` — detailed fix steps for an issue

### When NOT to Scan

- User explicitly says "don't scan", "skip checks", or "no linting"
- You only read/explored code without making any changes
- You only edited non-code files (markdown, docs, comments-only)
<!-- lucidshark:end -->
"""


class InitCommand(Command):
    """Configure AI tools to use LucidShark via MCP."""

    def __init__(self, version: str):
        """Initialize InitCommand.

        Args:
            version: Current lucidshark version string.
        """
        self._version = version

    @property
    def name(self) -> str:
        """Command identifier."""
        return "init"

    def execute(self, args: Namespace, config: "LucidSharkConfig | None" = None) -> int:
        """Execute the init command.

        Args:
            args: Parsed command-line arguments.
            config: Optional LucidShark configuration (unused).

        Returns:
            Exit code.
        """
        # Determine which tools to configure
        configure_claude = getattr(args, "claude_code", False)
        configure_all = getattr(args, "init_all", False)

        if configure_all:
            configure_claude = True

        if not configure_claude:
            print("No AI tool specified. Use --claude-code or --all.")
            print("\nRun 'lucidshark init --help' for more options.")
            return EXIT_INVALID_USAGE

        dry_run = getattr(args, "dry_run", False)
        force = getattr(args, "force", False)
        remove = getattr(args, "remove", False)

        success = True

        if configure_claude:
            if not self._setup_claude_code(dry_run, force, remove):
                success = False

        if success and not dry_run:
            print("\nRestart your AI tool to apply changes.")

        return EXIT_SUCCESS if success else EXIT_INVALID_USAGE

    def _setup_claude_code(
        self,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
    ) -> bool:
        """Configure Claude Code MCP settings in project .mcp.json.

        Args:
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing config.
            remove: If True, remove LucidShark from config.

        Returns:
            True if successful.
        """
        print("Configuring Claude Code (.mcp.json)...")

        config_path = self._get_claude_code_config_path()
        if config_path is None:
            print("  Could not determine Claude Code config location.")
            return False

        mcp_success = self._configure_mcp_tool(
            tool_name="Claude Code",
            config_path=config_path,
            config_key="mcpServers",
            dry_run=dry_run,
            force=force,
            remove=remove,
            use_portable_path=True,  # .mcp.json is version controlled
        )

        # Configure Claude skill
        skill_success = self._configure_claude_skill(
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

        # Configure CLAUDE.md with proactive scanning instructions
        claude_md_success = self._configure_claude_md(
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

        return mcp_success and skill_success and claude_md_success

    def _find_lucidshark_path(self, portable: bool = False) -> Optional[str]:
        """Find the lucidshark executable path.

        Searches in order:
        1. Local binary in project root (./lucidshark) - for standalone installs
        2. PATH via shutil.which (only if not portable)
        3. Same directory as current Python interpreter (for venv installs)
        4. Scripts directory on Windows

        Args:
            portable: If True, return a relative path suitable for version control.

        Returns:
            Path to lucidshark executable, or None if not found.
        """
        cwd = Path.cwd()

        # First check for local binary in project root (standalone install)
        if sys.platform == "win32":
            local_binary = cwd / "lucidshark.exe"
        else:
            local_binary = cwd / "lucidshark"

        if local_binary.exists() and local_binary.is_file():
            # For local binary, always return relative path
            return "./lucidshark.exe" if sys.platform == "win32" else "./lucidshark"

        # Then try PATH (only if not looking for portable path)
        if not portable:
            lucidshark_path = shutil.which("lucidshark")
            if lucidshark_path:
                return lucidshark_path

        # Try to find in the same directory as the Python interpreter
        # This handles venv installations where lucidshark isn't in global PATH
        python_dir = Path(sys.executable).parent

        if sys.platform == "win32":
            # On Windows, check both Scripts and the python directory
            candidates = [
                python_dir / "lucidshark.exe",
                python_dir / "Scripts" / "lucidshark.exe",
            ]
        else:
            # On Unix-like systems
            candidates = [
                python_dir / "lucidshark",
            ]

        for candidate in candidates:
            if candidate.exists():
                if portable:
                    # Try to make it relative to cwd for version control
                    try:
                        relative = candidate.relative_to(cwd)
                        return str(relative)
                    except ValueError:
                        # Not relative to cwd, can't use portable path
                        pass
                else:
                    return str(candidate)

        # For portable, fall back to just "lucidshark"
        if portable:
            return None

        return None

    def _build_mcp_config(self, lucidshark_path: Optional[str]) -> dict:
        """Build MCP server configuration.

        Args:
            lucidshark_path: Full path to lucidshark executable, or None.

        Returns:
            MCP server configuration dict.
        """
        command = lucidshark_path if lucidshark_path else "lucidshark"
        return {
            "command": command,
            "args": LUCIDSHARK_MCP_ARGS.copy(),
        }

    def _configure_mcp_tool(
        self,
        tool_name: str,
        config_path: Path,
        config_key: str,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
        use_portable_path: bool = False,
    ) -> bool:
        """Configure an MCP-compatible tool.

        Args:
            tool_name: Name of the tool for display.
            config_path: Path to the config file.
            config_key: Key in the config for MCP servers.
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing config.
            remove: If True, remove LucidShark from config.
            use_portable_path: If True, use relative path for version control.

        Returns:
            True if successful.
        """
        # Find lucidshark executable
        lucidshark_path = self._find_lucidshark_path(portable=use_portable_path)
        if lucidshark_path:
            print(f"  Using lucidshark command: {lucidshark_path}")
        elif not dry_run:
            print("  Warning: 'lucidshark' command not found in PATH or venv.")
            print("  Using 'lucidshark' as command (must be in PATH at runtime).")

        # Read existing config
        config, error = self._read_json_config(config_path)
        if error and not remove:
            # For new config, start fresh
            config = {}

        # Get or create the MCP servers section
        mcp_servers = config.get(config_key, {})

        if remove:
            # Remove LucidShark from config
            if "lucidshark" in mcp_servers:
                if dry_run:
                    print(f"  Would remove lucidshark from {config_path}")
                else:
                    del mcp_servers["lucidshark"]
                    config[config_key] = mcp_servers
                    if not mcp_servers:
                        del config[config_key]
                    self._write_json_config(config_path, config)
                    print(f"  Removed lucidshark from {config_path}")
            else:
                print(f"  lucidshark not found in {config_path}")
            return True

        # Check if LucidShark is already configured
        if "lucidshark" in mcp_servers and not force:
            print(f"  LucidShark already configured in {config_path}")
            print("  Use --force to overwrite.")
            return True

        # Add LucidShark config with found path
        mcp_config = self._build_mcp_config(lucidshark_path)
        mcp_servers["lucidshark"] = mcp_config
        config[config_key] = mcp_servers

        if dry_run:
            print(f"  Would write to {config_path}:")
            print(f"    {json.dumps(config, indent=2)}")
            return True

        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Write config
        success = self._write_json_config(config_path, config)
        if success:
            print(f"  Added lucidshark to {config_path}")
            self._print_available_tools()
        return success

    def _configure_claude_skill(
        self,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
    ) -> bool:
        """Configure Claude skill for lucidshark.

        Creates a skill file at .claude/skills/lucidshark/SKILL.md

        Args:
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing skill.
            remove: If True, remove lucidshark skill.

        Returns:
            True if successful.
        """
        skill_dir = Path.cwd() / ".claude" / "skills" / "lucidshark"
        skill_file = skill_dir / "SKILL.md"

        print("Configuring Claude skill...")

        if remove:
            if skill_file.exists():
                if dry_run:
                    print(f"  Would remove {skill_file}")
                else:
                    try:
                        skill_file.unlink()
                        # Remove directory if empty
                        if skill_dir.exists() and not any(skill_dir.iterdir()):
                            skill_dir.rmdir()
                        print("  Removed lucidshark skill")
                    except Exception as e:
                        print(f"  Error removing skill: {e}")
                        return False
            else:
                print("  Lucidshark skill not found")
            return True

        if skill_file.exists() and not force:
            print(f"  Lucidshark skill already exists at {skill_file}")
            print("  Use --force to overwrite.")
            return True

        if dry_run:
            print(f"  Would create skill at {skill_file}")
            return True

        # Ensure directory exists
        skill_dir.mkdir(parents=True, exist_ok=True)

        try:
            skill_file.write_text(LUCIDSHARK_SKILL_CONTENT.lstrip(), encoding="utf-8")
            print(f"  Created lucidshark skill at {skill_file}")
            return True
        except Exception as e:
            print(f"  Error creating skill: {e}")
            return False

    def _configure_claude_md(
        self,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
    ) -> bool:
        """Configure CLAUDE.md with LucidShark proactive scanning instructions.

        CLAUDE.md is loaded into Claude's system prompt for every conversation,
        making it the most reliable way to ensure proactive scanning behavior.
        Uses HTML comment markers to manage the LucidShark section so it can
        be updated or removed without affecting user content.

        Args:
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing LucidShark section.
            remove: If True, remove LucidShark section from CLAUDE.md.

        Returns:
            True if successful.
        """
        claude_md_path = Path.cwd() / "CLAUDE.md"
        start_marker = "<!-- lucidshark:start"
        end_marker = "<!-- lucidshark:end -->"

        print("Configuring CLAUDE.md...")

        # Read existing content
        existing_content = ""
        if claude_md_path.exists():
            try:
                existing_content = claude_md_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  Error reading {claude_md_path}: {e}")
                return False

        has_section = start_marker in existing_content and end_marker in existing_content

        if remove:
            if has_section:
                if dry_run:
                    print(f"  Would remove LucidShark section from {claude_md_path}")
                else:
                    new_content = self._remove_managed_section(
                        existing_content, start_marker, end_marker
                    )
                    try:
                        # If only whitespace remains, remove the file
                        if new_content.strip():
                            claude_md_path.write_text(new_content, encoding="utf-8")
                            print(f"  Removed LucidShark section from {claude_md_path}")
                        else:
                            claude_md_path.unlink()
                            print(f"  Removed {claude_md_path} (was empty after removal)")
                    except Exception as e:
                        print(f"  Error updating {claude_md_path}: {e}")
                        return False
            else:
                print(f"  LucidShark section not found in {claude_md_path}")
            return True

        if has_section and not force:
            print(f"  LucidShark section already exists in {claude_md_path}")
            print("  Use --force to overwrite.")
            return True

        if dry_run:
            action = "update" if has_section else "create"
            print(f"  Would {action} LucidShark section in {claude_md_path}")
            return True

        # Build new content
        if has_section:
            # Replace existing section
            new_content = self._replace_managed_section(
                existing_content,
                start_marker,
                end_marker,
                LUCIDSHARK_CLAUDE_MD_SECTION,
            )
        else:
            # Append to existing content (or create new file)
            new_content = existing_content.rstrip() + "\n" + LUCIDSHARK_CLAUDE_MD_SECTION

        try:
            claude_md_path.write_text(new_content, encoding="utf-8")
            action = "Updated" if has_section else "Added"
            print(f"  {action} LucidShark section in {claude_md_path}")
            return True
        except Exception as e:
            print(f"  Error writing {claude_md_path}: {e}")
            return False

    @staticmethod
    def _remove_managed_section(content: str, start_marker: str, end_marker: str) -> str:
        """Remove a managed section delimited by markers from content.

        Args:
            content: The full file content.
            start_marker: Start of the managed section (prefix match).
            end_marker: End of the managed section (exact line match).

        Returns:
            Content with the managed section removed.
        """
        lines = content.split("\n")
        result = []
        in_section = False
        for line in lines:
            if not in_section and start_marker in line:
                in_section = True
                continue
            if in_section and end_marker in line:
                in_section = False
                continue
            if not in_section:
                result.append(line)
        return "\n".join(result)

    @staticmethod
    def _replace_managed_section(
        content: str, start_marker: str, end_marker: str, new_section: str
    ) -> str:
        """Replace a managed section delimited by markers with new content.

        Args:
            content: The full file content.
            start_marker: Start of the managed section (prefix match).
            end_marker: End of the managed section (exact line match).
            new_section: New content to insert (includes its own markers).

        Returns:
            Content with the managed section replaced.
        """
        lines = content.split("\n")
        result = []
        in_section = False
        section_inserted = False
        for line in lines:
            if not in_section and start_marker in line:
                in_section = True
                if not section_inserted:
                    result.append(new_section.rstrip())
                    section_inserted = True
                continue
            if in_section and end_marker in line:
                in_section = False
                continue
            if not in_section:
                result.append(line)
        return "\n".join(result)

    def _get_claude_code_config_path(self) -> Optional[Path]:
        """Get the Claude Code MCP config file path.

        Returns:
            Path to .mcp.json at project root.
        """
        # Claude Code project-scoped MCP servers in .mcp.json
        return Path.cwd() / ".mcp.json"

    def _read_json_config(self, path: Path) -> Tuple[Dict[str, Any], Optional[str]]:
        """Read a JSON config file.

        Args:
            path: Path to the config file.

        Returns:
            Tuple of (config dict, error message or None).
        """
        if not path.exists():
            return {}, f"Config file does not exist: {path}"

        try:
            with open(path, "r") as f:
                content = f.read().strip()
                if not content:
                    return {}, None
                return json.loads(content), None
        except json.JSONDecodeError as e:
            return {}, f"Invalid JSON in {path}: {e}"
        except Exception as e:
            return {}, f"Error reading {path}: {e}"

    def _write_json_config(self, path: Path, config: Dict[str, Any]) -> bool:
        """Write a JSON config file.

        Args:
            path: Path to the config file.
            config: Configuration dictionary.

        Returns:
            True if successful.
        """
        try:
            with open(path, "w") as f:
                json.dump(config, f, indent=2)
                f.write("\n")
            return True
        except Exception as e:
            print(f"  Error writing {path}: {e}")
            return False

    def _print_available_tools(self) -> None:
        """Print available MCP tools."""
        print("\n  Available MCP tools:")
        print("    - scan: Run quality checks on the codebase")
        print("    - check_file: Check a specific file")
        print("    - get_fix_instructions: Get detailed fix guidance")
        print("    - apply_fix: Auto-fix linting issues")
        print("    - get_status: Show LucidShark configuration")
        print("    - autoconfigure: Get instructions for generating lucidshark.yml (MCP only)")
