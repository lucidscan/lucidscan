"""Setup command implementation.

Configure AI tools (Claude Code, Cursor) to use LucidScan via MCP.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from lucidscan.cli.commands import Command
from lucidscan.cli.exit_codes import EXIT_SUCCESS, EXIT_INVALID_USAGE
from lucidscan.core.logging import get_logger

LOGGER = get_logger(__name__)

# MCP server arguments for LucidScan
LUCIDSCAN_MCP_ARGS = ["serve", "--mcp"]

# Instructions to add to CLAUDE.md for proactive lucidscan usage
LUCIDSCAN_CLAUDE_MD_INSTRUCTIONS = """
## Code Quality with LucidScan

Use the lucidscan MCP tools to maintain code quality:

- **After writing or modifying code**: Run `scan` to check for linting, type errors, and security issues
- **Before committing**: Run `scan` with all domains to ensure code quality
- **When fixing issues**: Use `get_fix_instructions` to get detailed guidance, then `apply_fix` for auto-fixable issues

Available scan domains: `linting`, `type_checking`, `security`, `testing`, `coverage`, `all`
"""

LUCIDSCAN_CLAUDE_MD_MARKER = "## Code Quality with LucidScan"


class SetupCommand(Command):
    """Configure AI tools to use LucidScan via MCP."""

    def __init__(self, version: str):
        """Initialize SetupCommand.

        Args:
            version: Current lucidscan version string.
        """
        self._version = version

    @property
    def name(self) -> str:
        """Command identifier."""
        return "setup"

    def execute(self, args: Namespace) -> int:
        """Execute the setup command.

        Args:
            args: Parsed command-line arguments.

        Returns:
            Exit code.
        """
        # Determine which tools to configure
        configure_claude = getattr(args, "claude_code", False)
        configure_cursor = getattr(args, "cursor", False)
        configure_all = getattr(args, "setup_all", False)

        if configure_all:
            configure_claude = True
            configure_cursor = True

        if not configure_claude and not configure_cursor:
            print("No AI tool specified. Use --claude-code, --cursor, or --all.")
            print("\nRun 'lucidscan setup --help' for more options.")
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
            remove: If True, remove LucidScan from config.

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

        # Also configure CLAUDE.md with instructions
        claude_md_success = self._configure_claude_md(
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

        return mcp_success and claude_md_success

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
            remove: If True, remove LucidScan from config.

        Returns:
            True if successful.
        """
        print("Configuring Cursor...")

        config_path = self._get_cursor_config_path()
        if config_path is None:
            print("  Could not determine Cursor config location.")
            return False

        return self._configure_mcp_tool(
            tool_name="Cursor",
            config_path=config_path,
            config_key="mcpServers",
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

    def _find_lucidscan_path(self, portable: bool = False) -> Optional[str]:
        """Find the lucidscan executable path.

        Searches in order:
        1. PATH via shutil.which
        2. Same directory as current Python interpreter (for venv installs)
        3. Scripts directory on Windows

        Args:
            portable: If True, return a relative path suitable for version control.

        Returns:
            Path to lucidscan executable, or None if not found.
        """
        # First try PATH (only if not looking for portable path)
        if not portable:
            lucidscan_path = shutil.which("lucidscan")
            if lucidscan_path:
                return lucidscan_path

        # Try to find in the same directory as the Python interpreter
        # This handles venv installations where lucidscan isn't in global PATH
        python_dir = Path(sys.executable).parent
        cwd = Path.cwd()

        if sys.platform == "win32":
            # On Windows, check both Scripts and the python directory
            candidates = [
                python_dir / "lucidscan.exe",
                python_dir / "Scripts" / "lucidscan.exe",
            ]
        else:
            # On Unix-like systems
            candidates = [
                python_dir / "lucidscan",
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

        # For portable, fall back to just "lucidscan"
        if portable:
            return None

        return None

    def _build_mcp_config(self, lucidscan_path: Optional[str]) -> dict:
        """Build MCP server configuration.

        Args:
            lucidscan_path: Full path to lucidscan executable, or None.

        Returns:
            MCP server configuration dict.
        """
        command = lucidscan_path if lucidscan_path else "lucidscan"
        return {
            "command": command,
            "args": LUCIDSCAN_MCP_ARGS.copy(),
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
            remove: If True, remove LucidScan from config.
            use_portable_path: If True, use relative path for version control.

        Returns:
            True if successful.
        """
        # Find lucidscan executable
        lucidscan_path = self._find_lucidscan_path(portable=use_portable_path)
        if lucidscan_path:
            print(f"  Using lucidscan command: {lucidscan_path}")
        elif not dry_run:
            print("  Warning: 'lucidscan' command not found in PATH or venv.")
            print("  Using 'lucidscan' as command (must be in PATH at runtime).")

        # Read existing config
        config, error = self._read_json_config(config_path)
        if error and not remove:
            # For new config, start fresh
            config = {}

        # Get or create the MCP servers section
        mcp_servers = config.get(config_key, {})

        if remove:
            # Remove LucidScan from config
            if "lucidscan" in mcp_servers:
                if dry_run:
                    print(f"  Would remove lucidscan from {config_path}")
                else:
                    del mcp_servers["lucidscan"]
                    config[config_key] = mcp_servers
                    if not mcp_servers:
                        del config[config_key]
                    self._write_json_config(config_path, config)
                    print(f"  Removed lucidscan from {config_path}")
            else:
                print(f"  lucidscan not found in {config_path}")
            return True

        # Check if LucidScan is already configured
        if "lucidscan" in mcp_servers and not force:
            print(f"  LucidScan already configured in {config_path}")
            print(f"  Use --force to overwrite.")
            return True

        # Add LucidScan config with found path
        mcp_config = self._build_mcp_config(lucidscan_path)
        mcp_servers["lucidscan"] = mcp_config
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
            print(f"  Added lucidscan to {config_path}")
            self._print_available_tools()
        return success

    def _configure_claude_md(
        self,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
    ) -> bool:
        """Configure CLAUDE.md with lucidscan instructions.

        Args:
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing instructions.
            remove: If True, remove lucidscan instructions.

        Returns:
            True if successful.
        """
        claude_md_path = Path.cwd() / ".claude" / "CLAUDE.md"

        print("Configuring CLAUDE.md...")

        # Read existing content
        existing_content = ""
        if claude_md_path.exists():
            try:
                existing_content = claude_md_path.read_text()
            except Exception as e:
                print(f"  Error reading {claude_md_path}: {e}")
                return False

        has_lucidscan_section = LUCIDSCAN_CLAUDE_MD_MARKER in existing_content

        if remove:
            if has_lucidscan_section:
                if dry_run:
                    print(f"  Would remove lucidscan instructions from {claude_md_path}")
                else:
                    # Remove the lucidscan section
                    new_content = self._remove_lucidscan_section(existing_content)
                    try:
                        claude_md_path.write_text(new_content)
                        print(f"  Removed lucidscan instructions from {claude_md_path}")
                    except Exception as e:
                        print(f"  Error writing {claude_md_path}: {e}")
                        return False
            else:
                print(f"  Lucidscan instructions not found in {claude_md_path}")
            return True

        if has_lucidscan_section and not force:
            print(f"  Lucidscan instructions already in {claude_md_path}")
            print("  Use --force to overwrite.")
            return True

        # Build new content
        if has_lucidscan_section:
            # Replace existing section
            new_content = self._remove_lucidscan_section(existing_content)
            new_content = new_content.rstrip() + LUCIDSCAN_CLAUDE_MD_INSTRUCTIONS
        else:
            # Append to existing content
            new_content = existing_content.rstrip() + LUCIDSCAN_CLAUDE_MD_INSTRUCTIONS

        if dry_run:
            print(f"  Would add lucidscan instructions to {claude_md_path}")
            return True

        # Ensure directory exists
        claude_md_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            claude_md_path.write_text(new_content)
            print(f"  Added lucidscan instructions to {claude_md_path}")
            return True
        except Exception as e:
            print(f"  Error writing {claude_md_path}: {e}")
            return False

    def _remove_lucidscan_section(self, content: str) -> str:
        """Remove the lucidscan section from CLAUDE.md content.

        Args:
            content: The current CLAUDE.md content.

        Returns:
            Content with lucidscan section removed.
        """
        lines = content.split("\n")
        new_lines = []
        in_lucidscan_section = False

        for line in lines:
            if line.strip() == LUCIDSCAN_CLAUDE_MD_MARKER.strip():
                in_lucidscan_section = True
                continue
            if in_lucidscan_section:
                # Check if we've hit another section (line starting with ##)
                if line.startswith("## ") and LUCIDSCAN_CLAUDE_MD_MARKER.strip() not in line:
                    in_lucidscan_section = False
                    new_lines.append(line)
                # Skip lines in the lucidscan section
                continue
            new_lines.append(line)

        return "\n".join(new_lines)

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
        print("    - get_status: Show LucidScan configuration")
