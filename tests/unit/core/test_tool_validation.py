"""Unit tests for tool validation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from lucidshark.config.models import (
    DomainPipelineConfig,
    LucidSharkConfig,
    PipelineConfig,
    ToolConfig,
)
from lucidshark.core.tool_validation import (
    AUTO_DOWNLOADABLE_TOOLS,
    INSTALL_INSTRUCTIONS,
    ToolValidationError,
    ToolValidationResult,
    format_validation_errors,
    validate_configured_tools,
)


class TestAutoDownloadableTools:
    """Tests for auto-downloadable tool constants."""

    def test_auto_downloadable_tools_includes_security_tools(self):
        """Security scanners should be auto-downloadable."""
        assert "trivy" in AUTO_DOWNLOADABLE_TOOLS
        assert "opengrep" in AUTO_DOWNLOADABLE_TOOLS
        assert "checkov" in AUTO_DOWNLOADABLE_TOOLS

    def test_auto_downloadable_tools_includes_duplo(self):
        """Duplo should be auto-downloadable."""
        assert "duplo" in AUTO_DOWNLOADABLE_TOOLS

    def test_manually_installed_tools_have_instructions(self):
        """All manually installed tools should have install instructions."""
        manual_tools = [
            "ruff", "eslint", "biome", "mypy", "pyright",
            "pytest", "jest", "coverage_py", "istanbul",
        ]
        for tool in manual_tools:
            assert tool in INSTALL_INSTRUCTIONS, f"Missing install instruction for {tool}"


class TestToolValidationResult:
    """Tests for ToolValidationResult dataclass."""

    def test_success_result(self):
        """Successful validation should have no errors."""
        result = ToolValidationResult(success=True, errors=[])
        assert result.success is True
        assert len(result.errors) == 0

    def test_failure_result(self):
        """Failed validation should have errors."""
        error = ToolValidationError(
            tool_name="ruff",
            domain="linting",
            reason="Not found",
            install_instruction="pip install ruff",
        )
        result = ToolValidationResult(success=False, errors=[error])
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].tool_name == "ruff"


class TestValidateConfiguredTools:
    """Tests for validate_configured_tools function."""

    def test_passes_when_no_tools_configured(self):
        """Validation passes when no tools are configured."""
        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(enabled=True, tools=[]),
            )
        )
        result = validate_configured_tools(config, Path("/tmp"))
        assert result.success is True
        assert len(result.errors) == 0

    def test_passes_when_domain_disabled(self):
        """Validation skips disabled domains."""
        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=False,
                    tools=[ToolConfig(name="ruff")],
                ),
            )
        )
        result = validate_configured_tools(config, Path("/tmp"))
        assert result.success is True
        assert len(result.errors) == 0

    def test_skips_auto_downloadable_tools(self):
        """Auto-downloadable tools are not validated."""
        # duplo is auto-downloadable, so it should be skipped
        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                duplication=MagicMock(
                    enabled=True,
                    tools=[ToolConfig(name="duplo")],
                ),
            )
        )
        result = validate_configured_tools(config, Path("/tmp"))
        assert result.success is True
        assert len(result.errors) == 0

    @patch("lucidshark.core.tool_validation.get_plugin")
    def test_validates_configured_linters(self, mock_get_plugin):
        """Configured linters should be validated."""
        mock_plugin = MagicMock()
        mock_plugin.ensure_binary.side_effect = FileNotFoundError("ruff not found")
        mock_get_plugin.return_value = mock_plugin

        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="ruff")],
                ),
            )
        )
        result = validate_configured_tools(
            config, Path("/tmp"), enabled_domains=["linting"]
        )
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].tool_name == "ruff"
        assert result.errors[0].domain == "linting"

    @patch("lucidshark.core.tool_validation.get_plugin")
    def test_validates_configured_type_checkers(self, mock_get_plugin):
        """Configured type checkers should be validated."""
        mock_plugin = MagicMock()
        mock_plugin.ensure_binary.side_effect = FileNotFoundError("mypy not found")
        mock_get_plugin.return_value = mock_plugin

        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                type_checking=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="mypy")],
                ),
            )
        )
        result = validate_configured_tools(
            config, Path("/tmp"), enabled_domains=["type_checking"]
        )
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].tool_name == "mypy"
        assert result.errors[0].domain == "type_checking"

    @patch("lucidshark.core.tool_validation.get_plugin")
    def test_returns_install_instructions(self, mock_get_plugin):
        """Validation errors should include install instructions."""
        mock_plugin = MagicMock()
        mock_plugin.ensure_binary.side_effect = FileNotFoundError("ruff not found")
        mock_get_plugin.return_value = mock_plugin

        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="ruff")],
                ),
            )
        )
        result = validate_configured_tools(
            config, Path("/tmp"), enabled_domains=["linting"]
        )
        assert result.errors[0].install_instruction == "pip install ruff"

    @patch("lucidshark.core.tool_validation.get_plugin")
    def test_validates_multiple_tools(self, mock_get_plugin):
        """All missing tools should be reported, not just the first."""
        mock_plugin = MagicMock()
        mock_plugin.ensure_binary.side_effect = FileNotFoundError("tool not found")
        mock_get_plugin.return_value = mock_plugin

        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="ruff")],
                ),
                type_checking=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="mypy")],
                ),
            )
        )
        result = validate_configured_tools(
            config, Path("/tmp"), enabled_domains=["linting", "type_checking"]
        )
        assert result.success is False
        assert len(result.errors) == 2
        tool_names = {e.tool_name for e in result.errors}
        assert tool_names == {"ruff", "mypy"}

    @patch("lucidshark.core.tool_validation.get_plugin")
    def test_passes_when_all_tools_available(self, mock_get_plugin):
        """Validation passes when all tools are available."""
        mock_plugin = MagicMock()
        mock_plugin.ensure_binary.return_value = Path("/usr/bin/ruff")
        mock_get_plugin.return_value = mock_plugin

        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="ruff")],
                ),
            )
        )
        result = validate_configured_tools(
            config, Path("/tmp"), enabled_domains=["linting"]
        )
        assert result.success is True
        assert len(result.errors) == 0

    def test_skips_validation_for_unconfigured_domains(self):
        """Domains not in enabled_domains are not validated."""
        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="ruff")],
                ),
            )
        )
        # Only validate type_checking, not linting
        result = validate_configured_tools(
            config, Path("/tmp"), enabled_domains=["type_checking"]
        )
        assert result.success is True
        assert len(result.errors) == 0

    @patch("lucidshark.core.tool_validation.get_plugin")
    def test_handles_plugin_not_found(self, mock_get_plugin):
        """Validation fails gracefully when plugin is not found."""
        mock_get_plugin.return_value = None

        config = LucidSharkConfig(
            pipeline=PipelineConfig(
                linting=DomainPipelineConfig(
                    enabled=True,
                    tools=[ToolConfig(name="unknown_linter")],
                ),
            )
        )
        result = validate_configured_tools(
            config, Path("/tmp"), enabled_domains=["linting"]
        )
        assert result.success is False
        assert len(result.errors) == 1
        assert "not found" in result.errors[0].reason.lower()


class TestFormatValidationErrors:
    """Tests for format_validation_errors function."""

    def test_formats_single_error(self):
        """Single error is formatted correctly."""
        errors = [
            ToolValidationError(
                tool_name="ruff",
                domain="linting",
                reason="Not installed",
                install_instruction="pip install ruff",
            )
        ]
        output = format_validation_errors(errors)
        assert "Missing required tools" in output
        assert "[linting] ruff" in output
        assert "pip install ruff" in output

    def test_formats_multiple_errors(self):
        """Multiple errors are all included."""
        errors = [
            ToolValidationError(
                tool_name="ruff",
                domain="linting",
                reason="Not installed",
                install_instruction="pip install ruff",
            ),
            ToolValidationError(
                tool_name="mypy",
                domain="type_checking",
                reason="Not installed",
                install_instruction="pip install mypy",
            ),
        ]
        output = format_validation_errors(errors)
        assert "[linting] ruff" in output
        assert "[type_checking] mypy" in output
        assert "pip install ruff" in output
        assert "pip install mypy" in output

    def test_includes_auto_download_note(self):
        """Output includes note about auto-downloadable tools."""
        errors = [
            ToolValidationError(
                tool_name="ruff",
                domain="linting",
                reason="Not installed",
                install_instruction="pip install ruff",
            )
        ]
        output = format_validation_errors(errors)
        assert "trivy" in output.lower() or "automatically" in output.lower()

    def test_handles_missing_install_instruction(self):
        """Errors without install instructions are handled."""
        errors = [
            ToolValidationError(
                tool_name="custom_tool",
                domain="linting",
                reason="Not installed",
                install_instruction=None,
            )
        ]
        output = format_validation_errors(errors)
        assert "[linting] custom_tool" in output
        # Should not crash, just skip the install line
