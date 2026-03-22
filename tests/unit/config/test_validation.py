"""Tests for lucidshark.config.validation."""

from __future__ import annotations

from pathlib import Path

from lucidshark.config.validation import (
    ConfigValidationWarning,
    ConfigValidationIssue,
    ValidationSeverity,
    validate_config,
    validate_config_file,
    _suggest_key,
)


class TestSuggestKey:
    """Tests for _suggest_key function."""

    def test_suggests_close_match(self) -> None:
        result = _suggest_key("sac", {"sca", "sast", "iac"})
        assert result == "sca"

    def test_suggests_typo_fix(self) -> None:
        result = _suggest_key("faol_on", {"fail_on", "ignore", "output"})
        assert result == "fail_on"

    def test_returns_none_for_no_match(self) -> None:
        result = _suggest_key("xyz", {"fail_on", "ignore", "output"})
        assert result is None

    def test_handles_empty_valid_keys(self) -> None:
        result = _suggest_key("test", set())
        assert result is None


def _non_version_warnings(
    warnings: list[ConfigValidationWarning],
) -> list[ConfigValidationWarning]:
    """Filter out the 'missing version' info warning for tests that don't care about it."""
    return [w for w in warnings if "version" not in w.message.lower()]


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_valid_config_returns_no_warnings(self) -> None:
        data = {
            "version": 1,
            "fail_on": "high",
            "exclude": ["tests/**"],
            "output": {"format": "json"},
            "scanners": {
                "sca": {"enabled": True},
            },
        }
        warnings = validate_config(data, source="test.yml")
        # Filter out INFO-level warnings
        errors = [w for w in warnings if "Unknown" in w.message]
        assert len(errors) == 0

    def test_warns_on_unknown_top_level_key(self) -> None:
        data = {"version": 1, "unknown_key": "value"}
        warnings = validate_config(data, source="test.yml")
        unknown_warnings = [w for w in warnings if "unknown_key" in w.message]
        assert len(unknown_warnings) == 1
        assert unknown_warnings[0].key == "unknown_key"

    def test_suggests_typo_fix_for_top_level(self) -> None:
        data = {"version": 1, "fail_ob": "high"}  # typo: should be fail_on
        warnings = validate_config(data, source="test.yml")
        typo_warnings = [w for w in warnings if w.suggestion == "fail_on"]
        assert len(typo_warnings) == 1

    def test_warns_on_invalid_fail_on_severity(self) -> None:
        data = {"version": 1, "fail_on": "super_high"}  # invalid severity
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "Invalid severity" in warnings[0].message

    def test_warns_on_invalid_fail_on_type(self) -> None:
        data = {"version": 1, "fail_on": 123}  # should be string
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a string" in warnings[0].message

    def test_warns_on_invalid_exclude_type(self) -> None:
        data = {"version": 1, "exclude": "should-be-list"}  # should be list
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a list" in warnings[0].message

    def test_warns_on_invalid_output_type(self) -> None:
        data = {"version": 1, "output": "json"}  # should be dict
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message

    def test_warns_on_unknown_output_key(self) -> None:
        data = {"version": 1, "output": {"unknown": "value"}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "output.unknown" in warnings[0].message

    def test_warns_on_invalid_scanners_type(self) -> None:
        data = {"version": 1, "scanners": ["sca"]}  # should be dict
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message

    def test_warns_on_unknown_domain(self) -> None:
        data = {"version": 1, "scanners": {"unknowndomain": {"enabled": True}}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "Unknown scanner domain" in warnings[0].message

    def test_suggests_domain_typo_fix(self) -> None:
        data = {
            "version": 1,
            "scanners": {"sac": {"enabled": True}},
        }  # typo: should be sca
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert warnings[0].suggestion == "sca"

    def test_warns_on_invalid_enabled_type(self) -> None:
        data = {"version": 1, "scanners": {"sca": {"enabled": "yes"}}}  # should be bool
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a boolean" in warnings[0].message

    def test_warns_on_invalid_plugin_type(self) -> None:
        data = {"version": 1, "scanners": {"sca": {"plugin": 123}}}  # should be string
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a string" in warnings[0].message

    def test_allows_plugin_specific_options(self) -> None:
        # Plugin-specific options should not trigger warnings
        data = {
            "version": 1,
            "scanners": {
                "sca": {
                    "enabled": True,
                    "plugin": "trivy",
                    "ignore_unfixed": True,  # plugin-specific
                    "severity": ["HIGH"],  # plugin-specific
                    "custom_option": "value",  # plugin-specific
                },
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_returns_warning_for_non_dict_data(self) -> None:
        warnings = validate_config("not a dict", source="test.yml")  # type: ignore[arg-type]
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message


class TestConfigValidationWarning:
    """Tests for ConfigValidationWarning dataclass."""

    def test_basic_warning(self) -> None:
        warning = ConfigValidationWarning(
            message="Test message",
            source="test.yml",
        )
        assert warning.message == "Test message"
        assert warning.source == "test.yml"
        assert warning.key is None
        assert warning.suggestion is None

    def test_warning_with_key_and_suggestion(self) -> None:
        warning = ConfigValidationWarning(
            message="Unknown key",
            source="test.yml",
            key="fail_ob",
            suggestion="fail_on",
        )
        assert warning.key == "fail_ob"
        assert warning.suggestion == "fail_on"


class TestValidateConfigFile:
    """Tests for validate_config_file function."""

    def test_valid_config_returns_valid(self, tmp_path: Path) -> None:
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("version: 1\nfail_on: high\nexclude:\n  - tests/**\n")

        is_valid, issues = validate_config_file(config_file)

        assert is_valid is True
        assert len(issues) == 0

    def test_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "nonexistent.yml"

        is_valid, issues = validate_config_file(config_file)

        assert is_valid is False
        assert len(issues) == 1
        assert issues[0].severity == ValidationSeverity.ERROR
        assert "not found" in issues[0].message

    def test_yaml_syntax_error_returns_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("invalid: yaml: content:\n  - bad")

        is_valid, issues = validate_config_file(config_file)

        assert is_valid is False
        assert len(issues) == 1
        assert issues[0].severity == ValidationSeverity.ERROR
        assert "YAML" in issues[0].message

    def test_empty_file_returns_warning(self, tmp_path: Path) -> None:
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("")

        is_valid, issues = validate_config_file(config_file)

        # Empty file is valid but has a warning
        assert is_valid is True
        assert len(issues) == 1
        assert issues[0].severity == ValidationSeverity.WARNING
        assert "empty" in issues[0].message

    def test_unknown_key_returns_warning(self, tmp_path: Path) -> None:
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("version: 1\nunknown_key: value\n")

        is_valid, issues = validate_config_file(config_file)

        # Unknown keys are warnings, not errors
        assert is_valid is True
        unknown_issues = [i for i in issues if "unknown_key" in i.message]
        assert len(unknown_issues) == 1
        assert unknown_issues[0].severity == ValidationSeverity.WARNING

    def test_type_error_returns_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("version: 1\nfail_on: 123\n")  # Should be string

        is_valid, issues = validate_config_file(config_file)

        assert is_valid is False
        assert len(issues) == 1
        assert issues[0].severity == ValidationSeverity.ERROR
        assert "must be a" in issues[0].message

    def test_invalid_severity_returns_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("version: 1\nfail_on: super_high\n")  # Invalid severity

        is_valid, issues = validate_config_file(config_file)

        assert is_valid is False
        error_issues = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert len(error_issues) == 1
        assert "Invalid severity" in error_issues[0].message

    def test_typo_suggestion_included(self, tmp_path: Path) -> None:
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("version: 1\nfail_ob: high\n")  # Typo: should be fail_on

        is_valid, issues = validate_config_file(config_file)

        assert is_valid is True  # Unknown key is just a warning
        typo_issues = [i for i in issues if i.suggestion == "fail_on"]
        assert len(typo_issues) == 1


class TestValidationSeverity:
    """Tests for ValidationSeverity enum."""

    def test_error_value(self) -> None:
        assert ValidationSeverity.ERROR.value == "error"

    def test_warning_value(self) -> None:
        assert ValidationSeverity.WARNING.value == "warning"


class TestConfigValidationIssue:
    """Tests for ConfigValidationIssue dataclass."""

    def test_basic_issue(self) -> None:
        issue = ConfigValidationIssue(
            message="Test message",
            source="test.yml",
            severity=ValidationSeverity.ERROR,
        )
        assert issue.message == "Test message"
        assert issue.source == "test.yml"
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.key is None
        assert issue.suggestion is None

    def test_issue_with_all_fields(self) -> None:
        issue = ConfigValidationIssue(
            message="Unknown key",
            source="test.yml",
            severity=ValidationSeverity.WARNING,
            key="fail_ob",
            suggestion="fail_on",
        )
        assert issue.key == "fail_ob"
        assert issue.suggestion == "fail_on"
        assert issue.severity == ValidationSeverity.WARNING

    def test_to_dict_basic(self) -> None:
        """Test to_dict method without suggestion."""
        issue = ConfigValidationIssue(
            message="Test message",
            source="test.yml",
            severity=ValidationSeverity.ERROR,
            key="test_key",
        )
        result = issue.to_dict()
        assert result["message"] == "Test message"
        assert result["key"] == "test_key"
        assert "suggestion" not in result

    def test_to_dict_with_suggestion(self) -> None:
        """Test to_dict method with suggestion."""
        issue = ConfigValidationIssue(
            message="Unknown key",
            source="test.yml",
            severity=ValidationSeverity.WARNING,
            key="fail_ob",
            suggestion="fail_on",
        )
        result = issue.to_dict()
        assert result["message"] == "Unknown key"
        assert result["key"] == "fail_ob"
        assert result["suggestion"] == "fail_on"


class TestValidateConfigFailOnDict:
    """Tests for fail_on dict format validation."""

    def test_valid_fail_on_dict(self) -> None:
        """Test valid fail_on dict format."""
        data = {
            "version": 1,
            "fail_on": {
                "linting": "error",
                "security": "high",
                "testing": "any",
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_warns_on_unknown_fail_on_domain(self) -> None:
        """Test warning for unknown domain in fail_on."""
        data = {"version": 1, "fail_on": {"unknown_domain": "error"}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "Unknown domain" in warnings[0].message

    def test_warns_on_invalid_fail_on_value(self) -> None:
        """Test warning for invalid value in fail_on."""
        data = {"version": 1, "fail_on": {"linting": "invalid_value"}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "Invalid value" in warnings[0].message

    def test_warns_on_non_string_fail_on_value(self) -> None:
        """Test warning for non-string fail_on value."""
        data = {"version": 1, "fail_on": {"linting": 123}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a string" in warnings[0].message


class TestValidateConfigPipeline:
    """Tests for pipeline section validation."""

    def test_warns_on_invalid_pipeline_type(self) -> None:
        """Test warning for non-dict pipeline."""
        data = {"version": 1, "pipeline": "invalid"}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message

    def test_warns_on_unknown_pipeline_key(self) -> None:
        """Test warning for unknown pipeline key."""
        data = {"version": 1, "pipeline": {"unknown_key": "value"}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "pipeline.unknown_key" in warnings[0].message

    def test_warns_on_invalid_enrichers_type(self) -> None:
        """Test warning for non-list enrichers."""
        data = {"version": 1, "pipeline": {"enrichers": "not-a-list"}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a list" in warnings[0].message

    def test_warns_on_invalid_max_workers_type(self) -> None:
        """Test warning for non-int max_workers."""
        data = {"version": 1, "pipeline": {"max_workers": "four"}}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be an integer" in warnings[0].message

    def test_warns_on_missing_tools_when_enabled(self) -> None:
        """Test warning for missing tools when domain is enabled."""
        data = {"version": 1, "pipeline": {"linting": {"enabled": True}}}
        warnings = validate_config(data, source="test.yml")
        assert any("tools" in w.message and "required" in w.message for w in warnings)

    def test_warns_on_invalid_tools_type(self) -> None:
        """Test warning for non-list tools."""
        data = {"version": 1, "pipeline": {"linting": {"tools": "ruff"}}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a list" in w.message for w in warnings)

    def test_warns_on_invalid_coverage_threshold_type(self) -> None:
        """Test warning for non-numeric coverage threshold."""
        data = {
            "version": 1,
            "pipeline": {"coverage": {"tools": ["coverage_py"], "threshold": "80%"}},
        }
        warnings = validate_config(data, source="test.yml")
        assert any("threshold" in w.message and "number" in w.message for w in warnings)

    def test_domain_exclude_accepted_for_linting(self) -> None:
        """Test that exclude key is accepted in pipeline.linting."""
        data = {
            "version": 1,
            "pipeline": {
                "linting": {"tools": [{"name": "ruff"}], "exclude": ["gen/**"]}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any(
            "pipeline.linting.exclude" in (w.key or "") and "Unknown" in w.message
            for w in warnings
        )

    def test_domain_exclude_accepted_for_type_checking(self) -> None:
        """Test that exclude key is accepted in pipeline.type_checking."""
        data = {
            "version": 1,
            "pipeline": {
                "type_checking": {"tools": [{"name": "mypy"}], "exclude": ["stubs/**"]}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any(
            "pipeline.type_checking.exclude" in (w.key or "") and "Unknown" in w.message
            for w in warnings
        )

    def test_warns_on_invalid_domain_exclude_type(self) -> None:
        """Test warning for non-list exclude in domain config."""
        data = {
            "version": 1,
            "pipeline": {
                "linting": {"tools": [{"name": "ruff"}], "exclude": "not-a-list"}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "pipeline.linting.exclude" in (w.key or "")
            and "must be a list" in w.message
            for w in warnings
        )


class TestValidateConfigCommand:
    """Tests for pipeline command and post_command validation."""

    def test_command_accepted_in_testing(self) -> None:
        """Test that command is accepted in pipeline.testing."""
        data = {
            "version": 1,
            "pipeline": {
                "testing": {"tools": [{"name": "pytest"}], "command": "make test"}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any(
            "command" in (w.key or "") and "Unknown" in w.message for w in warnings
        )

    def test_post_command_accepted_in_testing(self) -> None:
        """Test that post_command is accepted in pipeline.testing."""
        data = {
            "version": 1,
            "pipeline": {
                "testing": {"tools": [{"name": "pytest"}], "post_command": "make clean"}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any(
            "post_command" in (w.key or "") and "Unknown" in w.message for w in warnings
        )

    def test_both_commands_accepted(self) -> None:
        """Test that both command and post_command are accepted together."""
        data = {
            "version": 1,
            "pipeline": {
                "testing": {
                    "tools": [{"name": "pytest"}],
                    "command": "npm test",
                    "post_command": "npm run cleanup",
                }
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown" in w.message for w in warnings)

    def test_warns_on_non_string_command(self) -> None:
        """Test warning for non-string command."""
        data = {
            "version": 1,
            "pipeline": {"testing": {"tools": [{"name": "pytest"}], "command": 123}},
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "pipeline.testing.command" in (w.key or "")
            and "must be a string" in w.message
            for w in warnings
        )

    def test_warns_on_non_string_post_command(self) -> None:
        """Test warning for non-string post_command."""
        data = {
            "version": 1,
            "pipeline": {
                "testing": {
                    "tools": [{"name": "pytest"}],
                    "post_command": ["cmd1", "cmd2"],
                }
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "pipeline.testing.post_command" in (w.key or "")
            and "must be a string" in w.message
            for w in warnings
        )

    def test_command_valid_in_all_domains(self) -> None:
        """Test that command is accepted in all pipeline domains."""
        for domain in ["linting", "type_checking", "testing", "coverage"]:
            data = {
                "version": 1,
                "pipeline": {
                    domain: {"tools": [{"name": "some_tool"}], "command": "make check"}
                },
            }
            warnings = validate_config(data, source="test.yml")
            assert not any(
                "Unknown" in w.message and "command" in w.message for w in warnings
            )


class TestValidateConfigAI:
    """Tests for AI section validation."""

    def test_warns_on_invalid_ai_type(self) -> None:
        """Test warning for non-dict ai section."""
        data = {"version": 1, "ai": "enabled"}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "must be a mapping" in warnings[0].message

    def test_warns_on_unknown_ai_key(self) -> None:
        """Test warning for unknown ai key."""
        data = {"version": 1, "ai": {"unknown_key": "value"}}
        warnings = validate_config(data, source="test.yml")
        assert any("ai.unknown_key" in w.message for w in warnings)

    def test_warns_on_invalid_ai_enabled_type(self) -> None:
        """Test warning for non-bool ai.enabled."""
        data = {"version": 1, "ai": {"enabled": "yes"}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a boolean" in w.message for w in warnings)

    def test_warns_on_invalid_ai_provider(self) -> None:
        """Test warning for unknown AI provider."""
        data = {"version": 1, "ai": {"provider": "unknown_provider"}}
        warnings = validate_config(data, source="test.yml")
        assert any("Unknown AI provider" in w.message for w in warnings)

    def test_warns_on_invalid_ai_provider_type(self) -> None:
        """Test warning for non-string AI provider."""
        data = {"version": 1, "ai": {"provider": 123}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a string" in w.message for w in warnings)

    def test_warns_on_invalid_temperature_type(self) -> None:
        """Test warning for non-numeric temperature."""
        data = {"version": 1, "ai": {"temperature": "hot"}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a number" in w.message for w in warnings)

    def test_warns_on_invalid_max_tokens_type(self) -> None:
        """Test warning for non-int max_tokens."""
        data = {"version": 1, "ai": {"max_tokens": "1000"}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be an integer" in w.message for w in warnings)

    def test_warns_on_invalid_send_code_snippets_type(self) -> None:
        """Test warning for non-bool send_code_snippets."""
        data = {"version": 1, "ai": {"send_code_snippets": "yes"}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a boolean" in w.message for w in warnings)

    def test_warns_on_invalid_cache_enabled_type(self) -> None:
        """Test warning for non-bool cache_enabled."""
        data = {"version": 1, "ai": {"cache_enabled": "true"}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a boolean" in w.message for w in warnings)


class TestValidateConfigSecurity:
    """Tests for pipeline.security validation."""

    def test_warns_on_invalid_security_tools_type(self) -> None:
        """Test warning for non-list security tools."""
        data = {"version": 1, "pipeline": {"security": {"tools": "trivy"}}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a list" in w.message for w in warnings)

    def test_warns_on_missing_tool_name(self) -> None:
        """Test warning for security tool missing name."""
        data = {
            "version": 1,
            "pipeline": {"security": {"tools": [{"domains": ["sca"]}]}},
        }
        warnings = validate_config(data, source="test.yml")
        assert any("must have a 'name'" in w.message for w in warnings)

    def test_warns_on_unknown_security_key(self) -> None:
        """Test warning for unknown pipeline.security key."""
        data = {"version": 1, "pipeline": {"security": {"unknown_key": "value"}}}
        warnings = validate_config(data, source="test.yml")
        assert any("pipeline.security.unknown_key" in w.message for w in warnings)

    def test_security_exclude_is_valid_key(self) -> None:
        """Test that 'exclude' is accepted in pipeline.security section."""
        data = {
            "version": 1,
            "pipeline": {
                "security": {
                    "enabled": True,
                    "tools": [{"name": "trivy", "domains": ["sca"]}],
                    "exclude": ["tests/**"],
                }
            },
        }
        warnings = validate_config(data, source="test.yml")
        unknown_warnings = [
            w
            for w in warnings
            if "pipeline.security.exclude" in (w.key or "") and "Unknown" in w.message
        ]
        assert not unknown_warnings

    def test_warns_on_invalid_security_exclude_type(self) -> None:
        """Test warning for non-list security exclude."""
        data = {
            "version": 1,
            "pipeline": {
                "security": {
                    "tools": [{"name": "trivy", "domains": ["sca"]}],
                    "exclude": "not-a-list",
                }
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "pipeline.security.exclude" in (w.key or "")
            and "must be a list" in w.message
            for w in warnings
        )


class TestCoverageRequiresTesting:
    """Tests for coverage-requires-testing validation."""

    def test_warns_when_coverage_enabled_testing_disabled(self) -> None:
        """Coverage enabled with testing disabled should produce an error."""
        data = {
            "pipeline": {
                "coverage": {"enabled": True, "tools": [{"name": "coverage_py"}]},
                "testing": {"enabled": False, "tools": [{"name": "pytest"}]},
            }
        }
        warnings = validate_config(data, source="test.yml")
        assert any("Coverage requires testing" in w.message for w in warnings)

    def test_warns_when_coverage_enabled_testing_missing(self) -> None:
        """Coverage enabled with testing not configured should produce an error."""
        data = {
            "pipeline": {
                "coverage": {"enabled": True, "tools": [{"name": "coverage_py"}]},
                # testing not configured at all
            }
        }
        warnings = validate_config(data, source="test.yml")
        # Testing not configured (None) means not enabled
        assert any("Coverage requires testing" in w.message for w in warnings)

    def test_no_warning_when_both_enabled(self) -> None:
        """No warning when both coverage and testing are enabled."""
        data = {
            "pipeline": {
                "coverage": {"enabled": True, "tools": [{"name": "coverage_py"}]},
                "testing": {"enabled": True, "tools": [{"name": "pytest"}]},
            }
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("Coverage requires testing" in w.message for w in warnings)

    def test_no_warning_when_coverage_disabled(self) -> None:
        """No warning when coverage is disabled."""
        data = {
            "pipeline": {
                "coverage": {"enabled": False, "tools": [{"name": "coverage_py"}]},
                "testing": {"enabled": False, "tools": [{"name": "pytest"}]},
            }
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("Coverage requires testing" in w.message for w in warnings)

    def test_coverage_testing_error_is_error_not_warning(self, tmp_path: Path) -> None:
        """Coverage-requires-testing should be classified as ERROR severity."""
        config_file = tmp_path / "lucidshark.yml"
        config_file.write_text("""
pipeline:
  coverage:
    enabled: true
    tools:
      - name: coverage_py
  testing:
    enabled: false
    tools:
      - name: pytest
""")
        is_valid, issues = validate_config_file(config_file)
        # Should be invalid because coverage requires testing
        assert is_valid is False
        error_issues = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert any("Coverage requires testing" in i.message for i in error_issues)


class TestValidateConfigDuplication:
    """Tests for pipeline.duplication validation."""

    def test_warns_on_unknown_duplication_key(self) -> None:
        """Test warning for unknown duplication key."""
        data = {"version": 1, "pipeline": {"duplication": {"unknown_key": "value"}}}
        warnings = validate_config(data, source="test.yml")
        assert any("pipeline.duplication.unknown_key" in w.message for w in warnings)

    def test_warns_on_invalid_duplication_threshold_type(self) -> None:
        """Test warning for non-numeric duplication threshold."""
        data = {"version": 1, "pipeline": {"duplication": {"threshold": "10%"}}}
        warnings = validate_config(data, source="test.yml")
        assert any("threshold" in w.message and "number" in w.message for w in warnings)

    def test_warns_on_invalid_exclude_type(self) -> None:
        """Test warning for non-list exclude."""
        data = {"version": 1, "pipeline": {"duplication": {"exclude": "*.test.py"}}}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a list" in w.message for w in warnings)


class TestValidateConfigIgnoreIssues:
    """Tests for ignore_issues validation."""

    def test_ignore_issues_is_valid_top_level_key(self) -> None:
        """ignore_issues should not trigger unknown key warning."""
        data = {"version": 1, "ignore_issues": ["E501"]}
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown" in w.message for w in warnings)

    def test_ignore_issues_must_be_list(self) -> None:
        data = {"version": 1, "ignore_issues": "E501"}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a list" in w.message for w in warnings)

    def test_valid_string_entries(self) -> None:
        data = {"version": 1, "ignore_issues": ["E501", "CVE-2021-1234"]}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_warns_on_empty_string_entry(self) -> None:
        data = {"version": 1, "ignore_issues": [""]}
        warnings = validate_config(data, source="test.yml")
        assert any("empty string" in w.message for w in warnings)

    def test_valid_structured_entry(self) -> None:
        data = {
            "version": 1,
            "ignore_issues": [
                {"rule_id": "E501", "reason": "accepted", "expires": "2026-12-31"}
            ],
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_warns_on_missing_rule_id(self) -> None:
        data = {"version": 1, "ignore_issues": [{"reason": "some reason"}]}
        warnings = validate_config(data, source="test.yml")
        assert any("rule_id" in w.message for w in warnings)

    def test_warns_on_non_string_rule_id(self) -> None:
        data = {"version": 1, "ignore_issues": [{"rule_id": 123}]}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a string" in w.message for w in warnings)

    def test_warns_on_non_string_reason(self) -> None:
        data = {"version": 1, "ignore_issues": [{"rule_id": "E501", "reason": 123}]}
        warnings = validate_config(data, source="test.yml")
        assert any(
            "reason" in w.message and "must be a string" in w.message for w in warnings
        )

    def test_warns_on_non_string_expires(self) -> None:
        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "expires": 20261231}],
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "expires" in w.message and "must be a string" in w.message for w in warnings
        )

    def test_warns_on_invalid_expires_format(self) -> None:
        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "expires": "12/31/2026"}],
        }
        warnings = validate_config(data, source="test.yml")
        assert any("YYYY-MM-DD" in w.message for w in warnings)

    def test_warns_on_unknown_keys_in_structured_entry(self) -> None:
        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "unknown_key": "value"}],
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "Unknown key" in w.message and "unknown_key" in w.message for w in warnings
        )

    def test_warns_on_invalid_entry_type(self) -> None:
        data = {"version": 1, "ignore_issues": [123]}
        warnings = validate_config(data, source="test.yml")
        assert any("must be a string or mapping" in w.message for w in warnings)

    def test_mixed_valid_entries(self) -> None:
        data = {
            "version": 1,
            "ignore_issues": [
                "E501",
                {"rule_id": "CVE-2021-1234", "reason": "accepted"},
            ],
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_pyyaml_date_object_is_accepted(self) -> None:
        """PyYAML parses bare dates as datetime.date; validation should accept them."""
        from datetime import date

        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "expires": date(2026, 12, 31)}],
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_paths_valid_list(self) -> None:
        """Valid paths list should not produce warnings."""
        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "paths": ["tests/**", "scripts/*"]}],
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_paths_must_be_list(self) -> None:
        """paths field must be a list."""
        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "paths": "tests/**"}],
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "paths" in w.message and "must be a list" in w.message for w in warnings
        )

    def test_paths_patterns_must_be_strings(self) -> None:
        """Each pattern in paths must be a string."""
        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "paths": [123, "tests/**"]}],
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "paths[0]" in w.message and "must be a string" in w.message
            for w in warnings
        )

    def test_paths_warns_on_empty_pattern(self) -> None:
        """Empty string pattern should produce warning."""
        data = {"version": 1, "ignore_issues": [{"rule_id": "E501", "paths": [""]}]}
        warnings = validate_config(data, source="test.yml")
        assert any(
            "paths[0]" in w.message and "empty string" in w.message for w in warnings
        )

    def test_paths_with_all_fields(self) -> None:
        """Entry with all fields including paths should validate."""
        data = {
            "version": 1,
            "ignore_issues": [
                {
                    "rule_id": "S101",
                    "reason": "Tests use assert",
                    "expires": "2026-12-31",
                    "paths": ["tests/**"],
                }
            ],
        }
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_paths_is_valid_key(self) -> None:
        """paths should not trigger unknown key warning."""
        data = {
            "version": 1,
            "ignore_issues": [{"rule_id": "E501", "paths": ["tests/**"]}],
        }
        warnings = validate_config(data, source="test.yml")
        assert not any(
            "Unknown key" in w.message and "paths" in w.message for w in warnings
        )


class TestValidateConfigExclude:
    """Tests for the exclude pattern system validation."""

    def test_top_level_exclude_is_valid_key(self) -> None:
        """Top-level 'exclude' should not trigger unknown key warning."""
        data = {"version": 1, "exclude": ["tests/**"]}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0

    def test_top_level_exclude_must_be_list(self) -> None:
        """Top-level 'exclude' must be a list."""
        data = {"version": 1, "exclude": "tests/**"}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 1
        assert "'exclude' must be a list" in warnings[0].message
        assert warnings[0].key == "exclude"

    def test_domain_exclude_is_valid_for_linting(self) -> None:
        """pipeline.linting.exclude should not trigger unknown key warning."""
        data = {
            "version": 1,
            "pipeline": {"linting": {"tools": ["ruff"], "exclude": ["generated/**"]}},
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("unknown" in w.message.lower() for w in warnings)

    def test_domain_exclude_is_valid_for_type_checking(self) -> None:
        """pipeline.type_checking.exclude should not trigger unknown key warning."""
        data = {
            "version": 1,
            "pipeline": {"type_checking": {"tools": ["mypy"], "exclude": ["stubs/**"]}},
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("unknown" in w.message.lower() for w in warnings)

    def test_domain_exclude_is_valid_for_testing(self) -> None:
        """pipeline.testing.exclude should not trigger unknown key warning."""
        data = {
            "version": 1,
            "pipeline": {
                "testing": {"tools": ["pytest"], "exclude": ["slow_tests/**"]}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("unknown" in w.message.lower() for w in warnings)

    def test_domain_exclude_is_valid_for_coverage(self) -> None:
        """pipeline.coverage.exclude should not trigger unknown key warning."""
        data = {
            "version": 1,
            "pipeline": {
                "coverage": {"tools": ["coverage_py"], "exclude": ["tests/**"]}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("unknown" in w.message.lower() for w in warnings)

    def test_domain_exclude_is_valid_for_security(self) -> None:
        """pipeline.security.exclude should not trigger unknown key warning."""
        data = {
            "version": 1,
            "pipeline": {
                "security": {
                    "tools": [{"name": "trivy", "domains": ["sca"]}],
                    "exclude": ["fixtures/**"],
                }
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("unknown" in w.message.lower() for w in warnings)

    def test_domain_exclude_must_be_list_for_linting(self) -> None:
        """pipeline.linting.exclude must be a list."""
        data = {
            "version": 1,
            "pipeline": {"linting": {"tools": ["ruff"], "exclude": "not-a-list"}},
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "pipeline.linting.exclude" in (w.key or "")
            and "must be a list" in w.message
            for w in warnings
        )

    def test_domain_exclude_must_be_list_for_coverage(self) -> None:
        """pipeline.coverage.exclude must be a list."""
        data = {
            "version": 1,
            "pipeline": {"coverage": {"tools": ["coverage_py"], "exclude": 123}},
        }
        warnings = validate_config(data, source="test.yml")
        assert any(
            "pipeline.coverage.exclude" in (w.key or "")
            and "must be a list" in w.message
            for w in warnings
        )

    def test_domain_exclude_must_be_list_for_security(self) -> None:
        """pipeline.security.exclude must be a list."""
        data = {"version": 1, "pipeline": {"security": {"exclude": "not-a-list"}}}
        warnings = validate_config(data, source="test.yml")
        assert any(
            "pipeline.security.exclude" in (w.key or "")
            and "must be a list" in w.message
            for w in warnings
        )

    def test_exclude_is_valid_top_level_key(self) -> None:
        """'exclude' should be accepted as a top-level key."""
        data = {"version": 1, "exclude": ["b/**"]}
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown" in w.message for w in warnings)


class TestValidateConfigVersion:
    """Tests for version value constraint validation."""

    def test_valid_version_1(self) -> None:
        """Version 1 should be accepted without warnings."""
        data = {"version": 1}
        warnings = validate_config(data, source="test.yml")
        assert len(warnings) == 0


class TestValidateConfigLanguages:
    """Tests for project.languages  -  validation was removed, languages are pass-through."""

    def test_valid_languages_no_warnings(self) -> None:
        """Languages under project are not validated; no language-specific warnings."""
        data = {"version": 1, "project": {"languages": ["python", "javascript", "go"]}}
        warnings = validate_config(data, source="test.yml")
        assert not any("language" in w.message.lower() for w in warnings)


class TestValidateConfigToolNames:
    """Tests for pipeline tool names  -  tool name validation was removed.

    validate_config no longer checks whether tool names are known.
    Tools are passed through without name validation.
    """

    def test_any_linting_tool_accepted(self) -> None:
        """Any linting tool name should be accepted without 'Unknown tool' warnings."""
        data = {"version": 1, "pipeline": {"linting": {"tools": [{"name": "ruff"}]}}}
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown tool" in w.message for w in warnings)

    def test_any_type_checking_tool_accepted(self) -> None:
        """Any type checking tool name should be accepted without 'Unknown tool' warnings."""
        data = {
            "version": 1,
            "pipeline": {"type_checking": {"tools": [{"name": "mypy"}]}},
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown tool" in w.message for w in warnings)

    def test_any_testing_tool_accepted(self) -> None:
        """Any testing tool name should be accepted without 'Unknown tool' warnings."""
        data = {"version": 1, "pipeline": {"testing": {"tools": [{"name": "pytest"}]}}}
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown tool" in w.message for w in warnings)

    def test_any_coverage_tool_accepted(self) -> None:
        """Any coverage tool name should be accepted without 'Unknown tool' warnings."""
        data = {
            "version": 1,
            "pipeline": {"coverage": {"tools": [{"name": "coverage_py"}]}},
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown tool" in w.message for w in warnings)

    def test_any_security_tool_accepted(self) -> None:
        """Any security tool name should be accepted without 'Unknown tool' warnings."""
        data = {
            "version": 1,
            "pipeline": {
                "security": {"tools": [{"name": "trivy", "domains": ["sca"]}]}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown tool" in w.message for w in warnings)

    def test_unknown_tool_names_not_validated(self) -> None:
        """Unknown tool names should not produce warnings (validation removed)."""
        data = {
            "version": 1,
            "pipeline": {"linting": {"tools": [{"name": "nonexistent_tool"}]}},
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("Unknown tool" in w.message for w in warnings)


class TestValidateConfigThresholdRange:
    """Tests for threshold values  -  range validation (0-100) was removed.

    validate_config checks that thresholds are numeric but no longer
    enforces 0-100 range constraints.
    """

    def test_valid_coverage_threshold(self) -> None:
        """Coverage threshold of 80 should be accepted."""
        data = {
            "version": 1,
            "pipeline": {
                "coverage": {"tools": [{"name": "coverage_py"}], "threshold": 80}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("must be between" in w.message for w in warnings)

    def test_coverage_threshold_zero(self) -> None:
        """Coverage threshold of 0 should be accepted."""
        data = {
            "version": 1,
            "pipeline": {
                "coverage": {"tools": [{"name": "coverage_py"}], "threshold": 0}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("must be between" in w.message for w in warnings)

    def test_coverage_threshold_100(self) -> None:
        """Coverage threshold of 100 should be accepted."""
        data = {
            "version": 1,
            "pipeline": {
                "coverage": {"tools": [{"name": "coverage_py"}], "threshold": 100}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("must be between" in w.message for w in warnings)

    def test_coverage_threshold_out_of_range_no_warning(self) -> None:
        """Out-of-range coverage thresholds no longer produce range warnings."""
        data = {
            "version": 1,
            "pipeline": {
                "coverage": {"tools": [{"name": "coverage_py"}], "threshold": 200}
            },
        }
        warnings = validate_config(data, source="test.yml")
        assert not any("must be between" in w.message for w in warnings)

    def test_duplication_threshold_valid(self) -> None:
        """Duplication threshold of 10 should be accepted."""
        data = {"version": 1, "pipeline": {"duplication": {"threshold": 10}}}
        warnings = validate_config(data, source="test.yml")
        assert not any("must be between" in w.message for w in warnings)

    def test_duplication_threshold_out_of_range_no_warning(self) -> None:
        """Out-of-range duplication thresholds no longer produce range warnings."""
        data = {"version": 1, "pipeline": {"duplication": {"threshold": 200}}}
        warnings = validate_config(data, source="test.yml")
        assert not any("must be between" in w.message for w in warnings)


class TestValidateConfigAliasKeys:
    """Tests that former alias keys are now treated as unknown top-level keys.

    Keys like 'languages', 'domains', 'exclude_patterns', 'settings', and
    'overview' are no longer in VALID_TOP_LEVEL_KEYS and trigger unknown
    key warnings.
    """

    def test_top_level_languages_triggers_warning(self) -> None:
        """Top-level 'languages' should trigger unknown key warning."""
        data = {"version": 1, "languages": ["python", "typescript"]}
        warnings = validate_config(data, source="test.yml")
        unknown_warnings = [w for w in warnings if "Unknown top-level key" in w.message]
        assert any("languages" in w.message for w in unknown_warnings)

    def test_top_level_domains_triggers_warning(self) -> None:
        """Top-level 'domains' should trigger unknown key warning."""
        data = {
            "version": 1,
            "domains": {
                "linting": {"enabled": True, "tools": ["ruff"]},
            },
        }
        warnings = validate_config(data, source="test.yml")
        unknown_warnings = [w for w in warnings if "Unknown top-level key" in w.message]
        assert any("domains" in w.message for w in unknown_warnings)

    def test_top_level_exclude_patterns_triggers_warning(self) -> None:
        """Top-level 'exclude_patterns' should trigger unknown key warning."""
        data = {"version": 1, "exclude_patterns": ["tests/**", "build/**"]}
        warnings = validate_config(data, source="test.yml")
        unknown_warnings = [w for w in warnings if "Unknown top-level key" in w.message]
        assert any("exclude_patterns" in w.message for w in unknown_warnings)

    def test_top_level_settings_is_valid(self) -> None:
        """Top-level 'settings' should be accepted as a valid key."""
        data = {"version": 1, "settings": {"strict_mode": True}}
        warnings = validate_config(data, source="test.yml")
        unknown_warnings = [w for w in warnings if "Unknown top-level key" in w.message]
        assert not any("settings" in w.message for w in unknown_warnings)

    def test_top_level_overview_is_valid(self) -> None:
        """Top-level 'overview' should be accepted as a valid key."""
        data = {"version": 1, "overview": {"enabled": True}}
        warnings = validate_config(data, source="test.yml")
        unknown_warnings = [w for w in warnings if "Unknown top-level key" in w.message]
        assert not any("overview" in w.message for w in unknown_warnings)
