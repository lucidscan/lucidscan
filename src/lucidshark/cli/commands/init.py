"""Init command implementation.

Configure AI tools (Claude Code, Cursor) to use LucidShark via MCP.
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

## Commands

| Command | Use Case |
|---------|----------|
| `scan(fix=true)` | Default after code changes (auto-fixes linting) |
| `scan(domains=["all"])` | Full scan before commits |
| `scan(all_files=true)` | Scan entire project, not just changed files |
| `check_file(file_path="...")` | Check single file |

**Domains:** `linting`, `type_checking`, `sast`, `sca`, `iac`, `container`, `testing`, `coverage`, `duplication`, `all`

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

# Cursor rules for proactive lucidshark usage
LUCIDSHARK_CURSOR_RULES = """---
description: "PROACTIVE code quality scanning. Run after writing/editing code, fixing bugs, adding features, refactoring, before commits. Auto-run - don't wait for user to ask."
globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.tsx", "**/*.jsx", "**/*.java", "**/*.go", "**/*.rs"]
alwaysApply: true
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

## Commands

| Command | Use Case |
|---------|----------|
| `scan(fix=true)` | Default after code changes (auto-fixes linting) |
| `scan(domains=["all"])` | Full scan before commits |
| `scan(all_files=true)` | Scan entire project, not just changed files |
| `check_file(file_path="...")` | Check single file |

**Domains:** `linting`, `type_checking`, `sast`, `sca`, `iac`, `container`, `testing`, `coverage`, `duplication`, `all`

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
        configure_cursor = getattr(args, "cursor", False)
        configure_all = getattr(args, "init_all", False)

        if configure_all:
            configure_claude = True
            configure_cursor = True

        if not configure_claude and not configure_cursor:
            print("No AI tool specified. Use --claude-code, --cursor, or --all.")
            print("\nRun 'lucidshark init --help' for more options.")
            return EXIT_INVALID_USAGE

        dry_run = getattr(args, "dry_run", False)
        force = getattr(args, "force", False)
        remove = getattr(args, "remove", False)

        success = True

        if configure_claude:
            if not self._setup_claude_code(dry_run, force, remove):
                success = False

        if configure_cursor:
            if not self._setup_cursor(dry_run, force, remove):
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

        # Also configure Claude skill
        skill_success = self._configure_claude_skill(
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

        return mcp_success and skill_success

    def _setup_cursor(
        self,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
    ) -> bool:
        """Configure Cursor MCP settings.

        Args:
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing config.
            remove: If True, remove LucidShark from config.

        Returns:
            True if successful.
        """
        print("Configuring Cursor...")

        config_path = self._get_cursor_config_path()
        if config_path is None:
            print("  Could not determine Cursor config location.")
            return False

        mcp_success = self._configure_mcp_tool(
            tool_name="Cursor",
            config_path=config_path,
            config_key="mcpServers",
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

        # Configure Cursor rules for automatic scanning
        rules_success = self._configure_cursor_rules(
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

        return mcp_success and rules_success

    def _find_lucidshark_path(self, portable: bool = False) -> Optional[str]:
        """Find the lucidshark executable path.

        Searches in order:
        1. PATH via shutil.which
        2. Same directory as current Python interpreter (for venv installs)
        3. Scripts directory on Windows

        Args:
            portable: If True, return a relative path suitable for version control.

        Returns:
            Path to lucidshark executable, or None if not found.
        """
        # First try PATH (only if not looking for portable path)
        if not portable:
            lucidshark_path = shutil.which("lucidshark")
            if lucidshark_path:
                return lucidshark_path

        # Try to find in the same directory as the Python interpreter
        # This handles venv installations where lucidshark isn't in global PATH
        python_dir = Path(sys.executable).parent
        cwd = Path.cwd()

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
            skill_file.write_text(LUCIDSHARK_SKILL_CONTENT.lstrip())
            print(f"  Created lucidshark skill at {skill_file}")
            return True
        except Exception as e:
            print(f"  Error creating skill: {e}")
            return False

    def _configure_cursor_rules(
        self,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
    ) -> bool:
        """Configure Cursor rules for automatic scanning.

        Args:
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing rules.
            remove: If True, remove lucidshark rules.

        Returns:
            True if successful.
        """
        rules_dir = Path.cwd() / ".cursor" / "rules"
        rules_file = rules_dir / "lucidshark.mdc"

        print("Configuring Cursor rules...")

        if remove:
            if rules_file.exists():
                if dry_run:
                    print(f"  Would remove {rules_file}")
                else:
                    rules_file.unlink()
                    print(f"  Removed {rules_file}")
            else:
                print(f"  LucidShark rules not found at {rules_file}")
            return True

        if rules_file.exists() and not force:
            print(f"  LucidShark rules already exist at {rules_file}")
            print("  Use --force to overwrite.")
            return True

        if dry_run:
            print(f"  Would create {rules_file}")
            return True

        rules_dir.mkdir(parents=True, exist_ok=True)
        try:
            rules_file.write_text(LUCIDSHARK_CURSOR_RULES.lstrip())
            print(f"  Created {rules_file}")
            return True
        except Exception as e:
            print(f"  Error writing {rules_file}: {e}")
            return False

    def _get_claude_code_config_path(self) -> Optional[Path]:
        """Get the Claude Code MCP config file path.

        Returns:
            Path to .mcp.json at project root.
        """
        # Claude Code project-scoped MCP servers in .mcp.json
        return Path.cwd() / ".mcp.json"

    def _get_cursor_config_path(self) -> Optional[Path]:
        """Get the Cursor MCP config file path.

        Returns:
            Path to config file or None if not determinable.
        """
        home = Path.home()

        if sys.platform == "win32":
            # Windows: %USERPROFILE%\.cursor\mcp.json
            return home / ".cursor" / "mcp.json"
        elif sys.platform == "darwin":
            # macOS: ~/.cursor/mcp.json
            return home / ".cursor" / "mcp.json"
        else:
            # Linux: ~/.cursor/mcp.json
            return home / ".cursor" / "mcp.json"

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
        print("    - autoconfigure: Get instructions for generating lucidshark.yml")
