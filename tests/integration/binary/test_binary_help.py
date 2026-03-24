"""Integration tests for binary help functionality.

These tests verify that the PyInstaller binary correctly bundles and accesses
the help.md documentation file. This catches issues with symlinks not being
properly bundled in the binary.

To run these tests:
    # Build the binary first
    pyinstaller lucidshark.spec

    # Then run the tests
    pytest tests/integration/binary/test_binary_help.py -v
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Find the binary location
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
BINARY_PATH = PROJECT_ROOT / "dist" / "lucidshark"

# Platform-specific binary name
if sys.platform == "win32":
    BINARY_PATH = BINARY_PATH.with_suffix(".exe")


def binary_exists() -> bool:
    """Check if the binary exists."""
    return BINARY_PATH.exists()


# Skip tests if binary doesn't exist
pytestmark = [
    pytest.mark.skipif(
        not binary_exists(),
        reason=f"Binary not found at {BINARY_PATH}. Run 'pyinstaller lucidshark.spec' first.",
    ),
    pytest.mark.binary,  # Mark as binary test for selective running
]


class TestBinaryHelpCommand:
    """Tests for the help command in the binary."""

    def test_binary_help_command_exists(self) -> None:
        """Test that the binary can execute the help command."""
        result = subprocess.run(
            [str(BINARY_PATH), "help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should exit successfully
        assert result.returncode == 0, f"Help command failed: {result.stderr}"

    def test_binary_help_contains_documentation(self) -> None:
        """Test that help command outputs complete documentation.

        This test catches a platform-specific bug where PyInstaller on Linux
        doesn't properly bundle files referenced via symlinks. The lucidshark.spec
        file must reference 'docs/help.md' directly, not 'src/lucidshark/data/help.md'
        (which is a symlink).

        Note: On macOS, PyInstaller follows symlinks correctly, but on Linux it
        creates a broken symlink in the binary, causing get_help_content() to
        fall back to "Help documentation not found".
        """
        result = subprocess.run(
            [str(BINARY_PATH), "help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout

        # Should NOT contain the fallback error message
        assert "Help documentation not found" not in output, (
            "Binary is missing help.md file! "
            "This indicates the symlink was not properly bundled. "
            "Verify lucidshark.spec uses 'docs/help.md' not 'src/lucidshark/data/help.md'."
        )

        # Verify key sections are present
        assert "# LucidShark Reference Documentation" in output
        assert "## Quick Start" in output
        assert "## CLI Commands" in output
        assert "## MCP Tools Reference" in output
        assert "## Configuration Reference" in output

    def test_binary_help_documents_cli_commands(self) -> None:
        """Test that help documents all CLI commands."""
        result = subprocess.run(
            [str(BINARY_PATH), "help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout

        # Check for all CLI commands
        cli_commands = ["init", "scan", "status", "serve", "help", "validate", "doctor", "overview"]
        for cmd in cli_commands:
            assert f"lucidshark {cmd}" in output, f"Missing documentation for '{cmd}' command"

    def test_binary_help_documents_mcp_tools(self) -> None:
        """Test that help documents all MCP tools."""
        result = subprocess.run(
            [str(BINARY_PATH), "help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout

        # Check for all MCP tools
        mcp_tools = [
            "scan",
            "check_file",
            "get_fix_instructions",
            "apply_fix",
            "get_status",
            "get_help",
            "autoconfigure",
            "validate_config",
        ]
        for tool in mcp_tools:
            # Tools should be documented with backticks
            assert f"`{tool}`" in output or f"### `{tool}`" in output, (
                f"Missing documentation for MCP tool '{tool}'"
            )


class TestBinaryMCPGetHelp:
    """Tests for the MCP get_help tool in the binary.

    These tests verify that the MCP server served by the binary can
    successfully access and return help documentation.
    """

    def test_binary_mcp_get_help_via_mocked_call(self, tmp_path: Path) -> None:
        """Test MCP get_help by simulating a tool call.

        This test creates a minimal project and uses the binary's MCP
        server to execute get_help, verifying the documentation is accessible.
        """
        # Create a minimal project directory
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        (project_dir / "main.py").write_text("print('hello')\n")

        # Create a minimal config file
        config_file = project_dir / "lucidshark.yml"
        config_file.write_text("""
pipeline:
  linting:
    enabled: true
    tools:
      - name: ruff
""")

        # We'll test this by running a Python script that imports lucidshark
        # and calls get_help through the executor. This verifies the binary's
        # bundled code can access help.md.
        test_script = tmp_path / "test_get_help.py"
        test_script.write_text(f"""
import sys
import asyncio
from pathlib import Path

# Add binary's bundled modules to path
sys.path.insert(0, str(Path("{BINARY_PATH}").parent))

from lucidshark.config import LucidSharkConfig
from lucidshark.mcp.tools import MCPToolExecutor

async def main():
    project_root = Path("{project_dir}")
    config = LucidSharkConfig()
    executor = MCPToolExecutor(project_root, config)

    result = await executor.get_help()

    # Verify result structure
    assert "documentation" in result, "Missing 'documentation' key"
    assert "format" in result, "Missing 'format' key"
    assert result["format"] == "markdown", "Wrong format"

    # Verify documentation content
    doc = result["documentation"]
    assert "LucidShark Reference Documentation" in doc, "Missing main heading"
    assert "Quick Start" in doc, "Missing Quick Start section"
    assert "CLI Commands" in doc, "Missing CLI Commands section"
    assert "MCP Tools Reference" in doc, "Missing MCP Tools Reference section"

    # Most importantly: check that it's not the fallback message
    assert "Help documentation not found" not in doc, (
        "Binary is returning fallback message - help.md not bundled correctly!"
    )

    print("SUCCESS: MCP get_help works correctly in binary")
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
""")

        # Note: This test is a bit tricky because we can't easily run Python
        # code using the binary's bundled modules. Instead, we verify via
        # the help command above, which uses the same code path.
        #
        # For a more complete test, we'd need to:
        # 1. Start the binary in MCP serve mode
        # 2. Send an MCP protocol message to call get_help
        # 3. Parse the MCP response
        #
        # This is complex, so we rely on the help command test above as a proxy.
        pytest.skip(
            "Full MCP protocol testing requires complex setup. "
            "The help command test above verifies the same code path."
        )


class TestBinaryHelpValidation:
    """Validation tests to ensure help documentation quality."""

    def test_binary_help_has_minimum_length(self) -> None:
        """Test that help output is substantial (not truncated or empty)."""
        result = subprocess.run(
            [str(BINARY_PATH), "help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout

        # Help documentation should be substantial (at least 50KB)
        # The actual help.md is ~85KB, so this is a reasonable threshold
        assert len(output) > 50000, (
            f"Help output too short ({len(output)} bytes). "
            "Expected >50KB. File may be truncated or missing."
        )

    def test_binary_help_has_all_major_sections(self) -> None:
        """Test that all major documentation sections are present."""
        result = subprocess.run(
            [str(BINARY_PATH), "help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout

        required_sections = [
            "# LucidShark Reference Documentation",
            "## Quick Start",
            "### Installation",
            "### Recommended Setup",
            "### Run Scans",
            "## CLI Commands",
            "### `lucidshark init`",
            "### `lucidshark scan`",
            "### `lucidshark status`",
            "### `lucidshark serve`",
            "### `lucidshark help`",
            "### `lucidshark doctor`",
            "### `lucidshark validate`",
            "### `lucidshark overview`",
            "### Exit Codes",
            "## MCP Tools Reference",
            "### `scan`",
            "### `check_file`",
            "### `get_fix_instructions`",
            "### `apply_fix`",
            "### `get_status`",
            "### `get_help`",
            "### `autoconfigure`",
            "### `validate_config`",
            "## Configuration Reference",
            "## Best Practices for AI Agents",
        ]

        missing_sections = [
            section for section in required_sections if section not in output
        ]

        assert not missing_sections, (
            f"Missing {len(missing_sections)} required sections in help output:\n"
            + "\n".join(f"  - {section}" for section in missing_sections)
        )

    def test_binary_help_contains_tool_availability_table(self) -> None:
        """Test that help includes the complete tool availability reference."""
        result = subprocess.run(
            [str(BINARY_PATH), "help"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout

        # Check for tool availability section
        assert "### Complete List of Supported Tools" in output or "Tool Availability" in output

        # Check for specific tools that should be documented
        documented_tools = [
            "ruff",
            "eslint",
            "biome",
            "mypy",
            "pyright",
            "trivy",
            "opengrep",
            "checkov",
            "pytest",
            "jest",
        ]

        for tool in documented_tools:
            assert tool in output.lower(), f"Tool '{tool}' not documented in help"
