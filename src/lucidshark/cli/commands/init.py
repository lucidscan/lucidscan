"""Init command implementation.

IMPORTANT DISTINCTION:
- `lucidshark init` = Configure Claude Code/IDE to use LucidShark (MCP server, skills, hooks)
- `autoconfigure` (MCP tool) = Generate lucidshark.yml configuration for your project

This command (init) sets up the Claude Code integration so Claude can call LucidShark.
It does NOT generate lucidshark.yml - use the autoconfigure MCP tool for that.

Configure AI tools (Claude Code) to use LucidShark.
Supports both CLI-first (recommended) and optional MCP modes.
"""

from __future__ import annotations

import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from lucidshark.config.models import LucidSharkConfig

from lucidshark.cli.commands import Command
from lucidshark.cli.exit_codes import EXIT_INVALID_USAGE, EXIT_SUCCESS
from lucidshark.core.logging import get_logger

LOGGER = get_logger(__name__)

# MCP server arguments for LucidShark
# IMPORTANT: --path . ensures the server runs in the project directory, not the
# directory where LucidShark is installed. This fixes BUG-GO-005 where MCP tools
# were running from the wrong working directory.
LUCIDSHARK_MCP_ARGS = ["serve", "--mcp", "--path", "."]

# Claude skill content for proactive lucidshark usage
LUCIDSHARK_SKILL_CONTENT = """---
name: lucidshark
description: "Unified code quality and security scanner: linting, type checking, formatting, security (SAST/SCA/IaC/container), testing, coverage, duplication. Run proactively after code changes."
---

# LucidShark - Unified Code Quality and Security Scanner

Run scans proactively after code changes. Don't wait for user to ask.

## IMPORTANT: Init vs Autoconfigure

**Two different commands, two different purposes:**

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `lucidshark init` | Configure Claude Code integration (`.mcp.json`, `.claude/` files) | Once per project, to enable MCP tools |
| `mcp__lucidshark__autoconfigure` | Generate `lucidshark.yml` configuration | When user asks to "autoconfigure lucidshark" or "set up lucidshark config" |

**User says** "autoconfigure lucidshark" → **Call** `mcp__lucidshark__autoconfigure` MCP tool (NOT `lucidshark init`)

## What It Can Do

| Domain | What It Does | Tools |
|--------|--------------|-------|
| **linting** | Style issues, code smells, auto-fix | Ruff, ESLint, Biome, Clippy, Checkstyle, PMD |
| **type_checking** | Type errors, static analysis | mypy, Pyright, tsc, SpotBugs, cargo check |
| **sast** | Security vulnerabilities in code | OpenGrep |
| **sca** | Dependency vulnerabilities | Trivy |
| **iac** | Infrastructure misconfigurations | Checkov |
| **container** | Container image vulnerabilities | Trivy |
| **testing** | Run tests, report failures | pytest, Jest, Karma, Playwright, JUnit, cargo test |
| **coverage** | Code coverage analysis | coverage.py, Istanbul, JaCoCo, Tarpaulin |
| **formatting** | Code formatting checks, auto-fix | ruff format, Prettier, rustfmt |
| **duplication** | Detect code clones | Duplo |

## When to Scan

| Trigger | MCP Tool | CLI Alternative |
|---------|----------|-----------------|
| After editing code | `mcp__lucidshark__scan(fix=true)` | `lucidshark scan --fix --format ai` |
| After fixing bugs | `mcp__lucidshark__scan(fix=true)` | `lucidshark scan --fix --format ai` |
| User asks to run tests | `mcp__lucidshark__scan(domains=["testing"])` | `lucidshark scan --testing --format ai` |
| User asks about coverage | `mcp__lucidshark__scan(domains=["testing","coverage"])` | `lucidshark scan --testing --coverage --format ai` |
| Security concerns | `mcp__lucidshark__scan(domains=["sast","sca"])` | `lucidshark scan --sast --sca --format ai` |
| Before commits | `mcp__lucidshark__scan(domains=["all"])` | `lucidshark scan --all --format ai` |

**Skip scanning** if user explicitly says "don't scan" or "skip checks".

## Smart Domain Selection

Pick domains based on what files changed:

| Files Changed | MCP domains | CLI flags |
|---|---|---|
| `.py`, `.js`, `.ts`, `.rs`, `.go`, `.java`, `.kt` | `["linting","type_checking","formatting"]` | `--linting --type-checking --formatting` |
| `Dockerfile`, `docker-compose.*` | `["container"]` | `--container` |
| `.tf`, `.yaml`/`.yml` (k8s/CloudFormation) | `["iac"]` | `--iac` |
| `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod` | `["sca"]` | `--sca` |
| Auth, crypto, input handling, SQL code | `["sast"]` | `--sast` |
| Mixed / many file types / before commit | `["all"]` | `--all` |

## MCP Tools

```
mcp__lucidshark__scan(fix=true)                                # Default: auto-fix + changed files
mcp__lucidshark__scan(domains=["linting","type_checking"])      # Targeted domains
mcp__lucidshark__scan(domains=["testing"])                      # Run tests
mcp__lucidshark__scan(domains=["testing","coverage"])           # Tests + coverage
mcp__lucidshark__scan(domains=["sast","sca"])                   # Security scan
mcp__lucidshark__scan(domains=["all"])                          # Full scan
mcp__lucidshark__scan(files=["path/to/file.py"])                # Specific files
mcp__lucidshark__scan(all_files=true)                           # All files (not just changed)
mcp__lucidshark__check_file(file_path="path/to/file.py")       # Check single file
mcp__lucidshark__get_fix_instructions(issue_id="ISSUE_ID")     # Get fix details
mcp__lucidshark__apply_fix(issue_id="ISSUE_ID")                # Auto-fix an issue
```

## CLI Commands

```bash
# Default after code changes (auto-fixes linting)
lucidshark scan --fix --format ai

# Run tests
lucidshark scan --testing --format ai

# Check test coverage (requires testing)
lucidshark scan --testing --coverage --format ai

# Security scan (code + dependencies)
lucidshark scan --sast --sca --format ai

# Full scan including tests, coverage, duplication
lucidshark scan --all --format ai

# Scan specific files
lucidshark scan --files path/to/file.py --format ai

# PR/CI: filter to files changed since main, with strict thresholds
lucidshark scan --all --base-branch origin/main \\
  --coverage-threshold-scope both \\
  --duplication-threshold-scope both
```

**Default:** Scans only uncommitted changes. Use `--all-files` for full project.

## Threshold Scope for CI/PR Workflows

When using `--base-branch` for incremental PR checks:

| Scope | Behavior |
|-------|----------|
| `changed` (default) | Threshold applies to changed files only. **Warning:** Can let project-wide metrics creep up over time. |
| `project` | Threshold applies to full project. |
| `both` | Threshold applies to both. Fail if **either** exceeds threshold. **Recommended for strict quality gates.** |

```bash
# Prevent duplication/coverage from creeping up over time
lucidshark scan --all --base-branch origin/main \\
  --duplication-threshold-scope both \\
  --coverage-threshold-scope both
```

## Workflow

1. Make code changes
2. Run `mcp__lucidshark__scan(fix=true)` or `lucidshark scan --fix --format ai`
3. Fix remaining issues
4. Re-scan if needed
5. Report done

**Task is complete when scan shows zero issues.**
"""

# CLAUDE.md section for always-in-context proactive scanning instructions
# This is the most impactful integration point because CLAUDE.md is loaded
# into Claude's system prompt for every conversation.
# Directive-first: behavioral instructions, MCP tools primary, CLI fallback.
LUCIDSHARK_CLAUDE_MD_SECTION = """\

<!-- lucidshark:start - managed by lucidshark init, do not edit manually -->
## LucidShark — REQUIRED: Scan After Every Code Change

**CRITICAL DISTINCTION**:
- **`lucidshark init`** = Configure Claude Code/IDE integration (`.mcp.json`, `.claude/` files). Run this ONCE per project.
- **`mcp__lucidshark__autoconfigure`** = Generate `lucidshark.yml` configuration (detect languages, install tools, configure scanners). Use when user asks to "autoconfigure lucidshark" or "set up lucidshark configuration".

**IMPORTANT**: You MUST run LucidShark scans after editing code files. Do NOT skip scanning to save time. Do NOT report a task as complete without scanning first. This overrides any default behavior to minimize tool calls.

### When to Scan (REQUIRED)

- **After every code edit** — scan immediately after using Edit, Write, or NotebookEdit on code files
- **Before reporting any task as done** — a task is NOT complete until scan shows zero issues
- **Before creating commits** — run a full scan with `domains=["all"]`
- **After fixing bugs** — verify the fix didn't introduce new issues

### How to Scan

**CRITICAL**: By default, LucidShark only scans **git-changed files**. If no code files have changed, no issues will be reported. Use `all_files=true` (MCP) or `--all-files` (CLI) to scan the entire project.

**MCP tools (preferred):**
```
mcp__lucidshark__scan(fix=true)                          # after edits (auto-fix + changed files)
mcp__lucidshark__scan(domains=["linting","type_checking"]) # targeted scan
mcp__lucidshark__scan(domains=["testing"])                # run tests
mcp__lucidshark__scan(domains=["all"])                    # full scan (before commits)
mcp__lucidshark__scan(files=["path/to/file.py"])          # specific files
mcp__lucidshark__scan(all_files=true)                     # scan ENTIRE project (not just changed)
mcp__lucidshark__scan(all_files=true, domains=["all"])    # full project scan, all domains
```

**CLI alternative:** `lucidshark scan --fix --format ai` (use `--linting --type-checking`, `--testing`, `--all`, `--files`, `--all-files` flags)

### Important Flags

| Flag | Purpose |
|------|---------|
| `--all` | Enable all scan **domains** (linting, sca, sast, etc.) |
| `--all-files` | Scan **entire project**, not just git-changed files |

### Domain Selection

- **`.py` `.js` `.ts` `.rs` `.go` `.java` `.kt`** → `["linting", "type_checking", "formatting"]`
- **Dockerfile / docker-compose** → `["container"]`
- **Terraform / K8s / IaC YAML** → `["iac"]`
- **`package.json` `requirements.txt` `Cargo.toml`** → `["sca"]`
- **Auth, crypto, SQL code** → `["sast"]`
- **Before commit or mixed changes** → `["all"]`

### When NOT to Scan

- User explicitly says "don't scan", "skip checks", or "no linting"
- You only read/explored code without making any changes
- You only edited non-code files (markdown, docs, comments-only)
<!-- lucidshark:end -->
"""

# Claude Code hooks configuration for .claude/settings.json
# PostToolUse hook on Edit/Write/NotebookEdit echoes a scan reminder
# after every code edit, providing a persistent nudge in context.
LUCIDSHARK_HOOKS_CONFIG: Dict[str, Any] = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Edit|Write|NotebookEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "echo '[LucidShark] Code modified — scan before completing"
                            " task (mcp__lucidshark__scan or lucidshark scan"
                            " --fix --format ai)'"
                        ),
                    }
                ],
            }
        ]
    }
}


class InitCommand(Command):
    """Configure Claude Code/IDE integration for LucidShark.

    This sets up .mcp.json, .claude/skills/, .claude/CLAUDE.md, and .claude/settings.json
    so Claude Code can use LucidShark's MCP tools.

    This does NOT generate lucidshark.yml - use `mcp__lucidshark__autoconfigure` for that.
    """

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
        # Claude Code is the default (and currently only) target
        configure_claude = True

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

        # Configure Claude Code hooks for scan reminders
        hooks_success = self._configure_claude_hooks(
            dry_run=dry_run,
            force=force,
            remove=remove,
        )

        return mcp_success and skill_success and claude_md_success and hooks_success

    def _find_lucidshark_path(self, portable: bool = False) -> Optional[str]:
        """Find the lucidshark executable path.

        Searches in order:
        1. Local binary in project root (./lucidshark) - for standalone installs
        2. PATH via shutil.which (only if not portable)
        3. Same directory as current Python interpreter (for venv installs)

        Args:
            portable: If True, return a relative path suitable for version control.

        Returns:
            Path to lucidshark executable, or None if not found.
        """
        cwd = Path.cwd()

        # First check for local binary in project root (standalone install)
        local_binary = cwd / "lucidshark"

        if local_binary.exists() and local_binary.is_file():
            # For local binary, always return relative path
            return "./lucidshark"

        # Then try PATH (only if not looking for portable path)
        if not portable:
            lucidshark_path = shutil.which("lucidshark")
            if lucidshark_path:
                return lucidshark_path

        # Try to find in the same directory as the Python interpreter
        # This handles venv installations where lucidshark isn't in global PATH
        python_dir = Path(sys.executable).parent

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
        claude_md_path = Path.cwd() / ".claude" / "CLAUDE.md"
        start_marker = "<!-- lucidshark:start"
        end_marker = "<!-- lucidshark:end -->"

        print("Configuring .claude/CLAUDE.md...")

        # Read existing content
        existing_content = ""
        if claude_md_path.exists():
            try:
                existing_content = claude_md_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  Error reading {claude_md_path}: {e}")
                return False

        has_section = (
            start_marker in existing_content and end_marker in existing_content
        )

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
                            print(
                                f"  Removed {claude_md_path} (was empty after removal)"
                            )
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
            new_content = (
                existing_content.rstrip() + "\n" + LUCIDSHARK_CLAUDE_MD_SECTION
            )

        try:
            claude_md_path.parent.mkdir(parents=True, exist_ok=True)
            claude_md_path.write_text(new_content, encoding="utf-8")
            action = "Updated" if has_section else "Added"
            print(f"  {action} LucidShark section in {claude_md_path}")
            return True
        except Exception as e:
            print(f"  Error writing {claude_md_path}: {e}")
            return False

    def _configure_claude_hooks(
        self,
        dry_run: bool = False,
        force: bool = False,
        remove: bool = False,
    ) -> bool:
        """Configure Claude Code hooks and enabled MCP servers in .claude/settings.json.

        Adds a PostToolUse hook that echoes a scan reminder after every
        code edit (Edit, Write, NotebookEdit). This provides a persistent
        nudge in Claude's context to run scans.

        Also adds "lucidshark" to the enabledMcpjsonServers array to enable
        the MCP server from .mcp.json.

        Args:
            dry_run: If True, only show what would be done.
            force: If True, overwrite existing hooks.
            remove: If True, remove LucidShark hooks and enabled server entry.

        Returns:
            True if successful.
        """
        settings_path = Path.cwd() / ".claude" / "settings.json"
        hooks_key = "hooks"
        enabled_mcp_key = "enabledMcpjsonServers"

        print("Configuring Claude Code hooks (.claude/settings.json)...")

        # Read existing settings
        existing_settings: Dict[str, Any] = {}
        if settings_path.exists():
            try:
                content = settings_path.read_text(encoding="utf-8").strip()
                if content:
                    existing_settings = json.loads(content)
            except (json.JSONDecodeError, Exception) as e:
                print(f"  Error reading {settings_path}: {e}")
                if not remove:
                    return False

        has_hooks = hooks_key in existing_settings and self._has_lucidshark_hooks(
            existing_settings.get(hooks_key, {})
        )
        has_enabled_server = self._has_lucidshark_in_enabled_servers(
            existing_settings.get(enabled_mcp_key, [])
        )

        if remove:
            changes_made = False
            if has_hooks:
                if dry_run:
                    print(f"  Would remove LucidShark hooks from {settings_path}")
                else:
                    self._remove_lucidshark_hooks(existing_settings)
                    changes_made = True
            else:
                print(f"  LucidShark hooks not found in {settings_path}")

            if has_enabled_server:
                if dry_run:
                    print(
                        f"  Would remove lucidshark from enabledMcpjsonServers in {settings_path}"
                    )
                else:
                    self._remove_from_enabled_mcp_servers(existing_settings)
                    changes_made = True
            else:
                print(
                    f"  lucidshark not found in enabledMcpjsonServers in {settings_path}"
                )

            if changes_made and not dry_run:
                # If settings is now empty (or only has empty structures), clean up
                if not existing_settings or existing_settings == {}:
                    try:
                        settings_path.unlink()
                        print(f"  Removed {settings_path} (was empty after removal)")
                    except Exception as e:
                        print(f"  Error removing {settings_path}: {e}")
                        return False
                else:
                    success = self._write_json_config(settings_path, existing_settings)
                    if success:
                        print(f"  Removed LucidShark configuration from {settings_path}")
                    return success
            return True

        if has_hooks and has_enabled_server and not force:
            print(f"  LucidShark already configured in {settings_path}")
            print("  Use --force to overwrite.")
            return True

        if dry_run:
            action = "update" if (has_hooks or has_enabled_server) else "create"
            print(f"  Would {action} LucidShark configuration in {settings_path}")
            return True

        # Merge hooks into existing settings, preserving non-LucidShark hooks
        new_settings = dict(existing_settings)

        # Configure hooks
        # Remove any existing LucidShark hooks first so we don't duplicate
        if has_hooks:
            self._remove_lucidshark_hooks(new_settings)
        # Merge: add LucidShark PostToolUse hooks alongside existing hooks
        existing_hooks = new_settings.get(hooks_key, {})
        new_hooks = LUCIDSHARK_HOOKS_CONFIG[hooks_key]
        for event_type, hook_groups in new_hooks.items():
            if event_type in existing_hooks:
                existing_hooks[event_type].extend(hook_groups)
            else:
                existing_hooks[event_type] = list(hook_groups)
        new_settings[hooks_key] = existing_hooks

        # Configure enabledMcpjsonServers
        self._add_to_enabled_mcp_servers(new_settings)

        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            success = self._write_json_config(settings_path, new_settings)
            if success:
                action = "Updated" if (has_hooks or has_enabled_server) else "Added"
                print(f"  {action} LucidShark configuration in {settings_path}")
            return success
        except Exception as e:
            print(f"  Error writing {settings_path}: {e}")
            return False

    @staticmethod
    def _has_lucidshark_hooks(hooks: Dict[str, Any]) -> bool:
        """Check if hooks config contains LucidShark hooks.

        Args:
            hooks: The hooks configuration dict.

        Returns:
            True if LucidShark hooks are present.
        """
        post_tool_use = hooks.get("PostToolUse", [])
        for hook_group in post_tool_use:
            matcher = hook_group.get("matcher", "")
            if "Edit" in matcher and "Write" in matcher and "NotebookEdit" in matcher:
                for hook in hook_group.get("hooks", []):
                    if "LucidShark" in hook.get("command", ""):
                        return True
        return False

    @staticmethod
    def _remove_lucidshark_hooks(settings: Dict[str, Any]) -> None:
        """Remove LucidShark hooks from settings in-place.

        Args:
            settings: The settings dict to modify.
        """
        hooks = settings.get("hooks", {})
        post_tool_use = hooks.get("PostToolUse", [])

        # Filter out LucidShark hook groups
        filtered = []
        for hook_group in post_tool_use:
            matcher = hook_group.get("matcher", "")
            is_lucidshark = (
                "Edit" in matcher
                and "Write" in matcher
                and "NotebookEdit" in matcher
                and any(
                    "LucidShark" in h.get("command", "")
                    for h in hook_group.get("hooks", [])
                )
            )
            if not is_lucidshark:
                filtered.append(hook_group)

        if filtered:
            hooks["PostToolUse"] = filtered
        else:
            hooks.pop("PostToolUse", None)

        if hooks:
            settings["hooks"] = hooks
        else:
            settings.pop("hooks", None)

    @staticmethod
    def _has_lucidshark_in_enabled_servers(enabled_servers: List[str]) -> bool:
        """Check if lucidshark is in the enabledMcpjsonServers list.

        Args:
            enabled_servers: List of enabled MCP server names.

        Returns:
            True if "lucidshark" is present.
        """
        return "lucidshark" in enabled_servers

    @staticmethod
    def _add_to_enabled_mcp_servers(settings: Dict[str, Any]) -> None:
        """Add lucidshark to enabledMcpjsonServers in settings in-place.

        Preserves all other entries in the list.

        Args:
            settings: The settings dict to modify.
        """
        enabled_servers = settings.get("enabledMcpjsonServers", [])
        if "lucidshark" not in enabled_servers:
            enabled_servers.append("lucidshark")
        settings["enabledMcpjsonServers"] = enabled_servers

    @staticmethod
    def _remove_from_enabled_mcp_servers(settings: Dict[str, Any]) -> None:
        """Remove lucidshark from enabledMcpjsonServers in settings in-place.

        Preserves all other entries in the list.

        Args:
            settings: The settings dict to modify.
        """
        enabled_servers = settings.get("enabledMcpjsonServers", [])
        if "lucidshark" in enabled_servers:
            enabled_servers.remove("lucidshark")
        if enabled_servers:
            settings["enabledMcpjsonServers"] = enabled_servers
        else:
            settings.pop("enabledMcpjsonServers", None)

    @staticmethod
    def _process_managed_section(
        content: str,
        start_marker: str,
        end_marker: str,
        replacement: Optional[str] = None,
    ) -> str:
        """Process a managed section delimited by markers.

        Args:
            content: The full file content.
            start_marker: Start of the managed section (prefix match).
            end_marker: End of the managed section (exact line match).
            replacement: If provided, replaces section with this content.
                         If None, section is removed.

        Returns:
            Content with the managed section processed.
        """
        lines = content.split("\n")
        result: List[str] = []
        in_section = False
        replaced = False
        for line in lines:
            if not in_section and start_marker in line:
                in_section = True
                if replacement is not None and not replaced:
                    result.append(replacement.rstrip())
                    replaced = True
            elif in_section and end_marker in line:
                in_section = False
            elif not in_section:
                result.append(line)
        return "\n".join(result)

    @staticmethod
    def _remove_managed_section(
        content: str, start_marker: str, end_marker: str
    ) -> str:
        """Remove a managed section delimited by markers from content."""
        return InitCommand._process_managed_section(content, start_marker, end_marker)

    @staticmethod
    def _replace_managed_section(
        content: str, start_marker: str, end_marker: str, new_section: str
    ) -> str:
        """Replace a managed section with new content."""
        return InitCommand._process_managed_section(
            content, start_marker, end_marker, new_section
        )

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
        """Print available CLI commands."""
        print("\n  Available commands:")
        print("    lucidshark scan --format ai     # Run quality checks")
        print("    lucidshark scan --fix           # Auto-fix linting issues")
        print("    lucidshark scan --all           # Full scan (all domains)")
        print("    lucidshark status               # Show configuration")
        print("    lucidshark validate             # Validate lucidshark.yml")
        print("    lucidshark help                 # Show documentation")
        print("\n  MCP server:")
        print("    lucidshark serve --mcp          # Run as MCP server")
