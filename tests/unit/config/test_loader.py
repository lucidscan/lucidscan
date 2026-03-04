"""Tests for lucidshark.config.loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from lucidshark.config.loader import (
    ConfigError,
    _parse_coverage_pipeline_config,
    _parse_domain_pipeline_config,
    dict_to_config,
    expand_env_vars,
    find_project_config,
    load_config,
    load_yaml_file,
    merge_configs,
)
from lucidshark.config.models import LucidSharkConfig


class TestExpandEnvVars:
    """Tests for expand_env_vars function."""

    def test_expands_simple_env_var(self) -> None:
        with patch.dict(os.environ, {"MY_VAR": "test_value"}):
            result = expand_env_vars("${MY_VAR}")
            assert result == "test_value"

    def test_expands_env_var_with_default(self) -> None:
        # Remove the var if it exists
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("UNSET_VAR", None)
            result = expand_env_vars("${UNSET_VAR:-default}")
            assert result == "default"

    def test_uses_value_when_set_ignoring_default(self) -> None:
        with patch.dict(os.environ, {"SET_VAR": "actual"}):
            result = expand_env_vars("${SET_VAR:-default}")
            assert result == "actual"

    def test_returns_empty_for_unset_without_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("UNSET_VAR", None)
            result = expand_env_vars("${UNSET_VAR}")
            assert result == ""

    def test_expands_in_dict_values(self) -> None:
        with patch.dict(os.environ, {"TOKEN": "secret"}):
            data = {"api_token": "${TOKEN}"}
            result = expand_env_vars(data)
            assert result == {"api_token": "secret"}

    def test_expands_in_list_items(self) -> None:
        with patch.dict(os.environ, {"PATH1": "/a", "PATH2": "/b"}):
            data = ["${PATH1}", "${PATH2}"]
            result = expand_env_vars(data)
            assert result == ["/a", "/b"]

    def test_expands_in_nested_structures(self) -> None:
        with patch.dict(os.environ, {"TOKEN": "secret", "URL": "http://example.com"}):
            data = {
                "api": {
                    "token": "${TOKEN}",
                    "url": "${URL}",
                },
                "paths": ["${TOKEN}"],
            }
            result = expand_env_vars(data)
            assert result["api"]["token"] == "secret"
            assert result["api"]["url"] == "http://example.com"
            assert result["paths"] == ["secret"]

    def test_preserves_non_string_values(self) -> None:
        data = {"number": 42, "boolean": True, "none": None}
        result = expand_env_vars(data)
        assert result == data


class TestMergeConfigs:
    """Tests for merge_configs function."""

    def test_overlay_replaces_scalars(self) -> None:
        base = {"a": 1, "b": 2}
        overlay = {"b": 3}
        result = merge_configs(base, overlay)
        assert result == {"a": 1, "b": 3}

    def test_overlay_adds_new_keys(self) -> None:
        base = {"a": 1}
        overlay = {"b": 2}
        result = merge_configs(base, overlay)
        assert result == {"a": 1, "b": 2}

    def test_overlay_replaces_lists(self) -> None:
        base = {"items": [1, 2]}
        overlay = {"items": [3, 4, 5]}
        result = merge_configs(base, overlay)
        assert result == {"items": [3, 4, 5]}

    def test_deep_merges_dicts(self) -> None:
        base = {"scanners": {"sca": {"enabled": True, "timeout": 60}}}
        overlay = {"scanners": {"sca": {"timeout": 120}}}
        result = merge_configs(base, overlay)
        assert result == {"scanners": {"sca": {"enabled": True, "timeout": 120}}}

    def test_empty_overlay_returns_base(self) -> None:
        base = {"a": 1}
        result = merge_configs(base, {})
        assert result == {"a": 1}

    def test_empty_base_returns_overlay(self) -> None:
        overlay = {"a": 1}
        result = merge_configs({}, overlay)
        assert result == {"a": 1}


class TestDictToConfig:
    """Tests for dict_to_config function."""

    def test_empty_dict_returns_default_config(self) -> None:
        config = dict_to_config({})
        assert config.fail_on is None
        assert config.ignore == []
        assert config.output.format == "json"
        assert config.scanners == {}

    def test_parses_fail_on(self) -> None:
        config = dict_to_config({"fail_on": "high"})
        assert config.fail_on == "high"

    def test_parses_ignore_patterns(self) -> None:
        config = dict_to_config({"ignore": ["tests/**", "*.md"]})
        assert config.ignore == ["tests/**", "*.md"]

    def test_parses_output_format(self) -> None:
        config = dict_to_config({"output": {"format": "table"}})
        assert config.output.format == "table"

    def test_parses_scanner_config(self) -> None:
        data = {
            "scanners": {
                "sca": {
                    "enabled": True,
                    "plugin": "snyk",
                    "api_token": "secret",
                }
            }
        }
        config = dict_to_config(data)
        assert "sca" in config.scanners
        assert config.scanners["sca"].enabled is True
        assert config.scanners["sca"].plugin == "snyk"
        assert config.scanners["sca"].options == {"api_token": "secret"}

    def test_parses_enrichers(self) -> None:
        data = {"enrichers": {"ai": {"enabled": False}}}
        config = dict_to_config(data)
        assert config.enrichers == {"ai": {"enabled": False}}

    def test_top_level_exclude_maps_to_ignore(self) -> None:
        """Top-level 'exclude' key should be stored in the 'ignore' field."""
        config = dict_to_config({"exclude": ["vendor/**", "*.pb.go"]})
        assert config.ignore == ["vendor/**", "*.pb.go"]

    def test_top_level_exclude_takes_precedence_over_ignore(self) -> None:
        """When both 'exclude' and 'ignore' are present, 'exclude' wins."""
        config = dict_to_config({
            "ignore": ["old_pattern/**"],
            "exclude": ["new_pattern/**"],
        })
        assert config.ignore == ["new_pattern/**"]

    def test_top_level_ignore_still_works_without_exclude(self) -> None:
        """Backward compat: 'ignore' still works when 'exclude' is absent."""
        config = dict_to_config({"ignore": ["tests/**"]})
        assert config.ignore == ["tests/**"]

    def test_parses_domain_pipeline_exclude(self) -> None:
        """Domain pipeline configs should parse the 'exclude' field."""
        data = {
            "pipeline": {
                "linting": {
                    "tools": ["ruff"],
                    "exclude": ["generated/**"],
                },
            },
        }
        config = dict_to_config(data)
        assert config.pipeline.linting is not None
        assert config.pipeline.linting.exclude == ["generated/**"]

    def test_parses_type_checking_exclude(self) -> None:
        """Type checking domain should parse 'exclude'."""
        data = {
            "pipeline": {
                "type_checking": {
                    "tools": ["mypy"],
                    "exclude": ["stubs/**"],
                },
            },
        }
        config = dict_to_config(data)
        assert config.pipeline.type_checking is not None
        assert config.pipeline.type_checking.exclude == ["stubs/**"]

    def test_parses_testing_exclude(self) -> None:
        """Testing domain should parse 'exclude'."""
        data = {
            "pipeline": {
                "testing": {
                    "tools": ["pytest"],
                    "exclude": ["integration/**"],
                },
            },
        }
        config = dict_to_config(data)
        assert config.pipeline.testing is not None
        assert config.pipeline.testing.exclude == ["integration/**"]

    def test_parses_security_exclude(self) -> None:
        """Security domain should parse 'exclude'."""
        data = {
            "pipeline": {
                "security": {
                    "tools": [{"name": "trivy", "domains": ["sca"]}],
                    "exclude": ["test_data/**"],
                },
            },
        }
        config = dict_to_config(data)
        assert config.pipeline.security is not None
        assert config.pipeline.security.exclude == ["test_data/**"]

    def test_parses_coverage_exclude(self) -> None:
        """Coverage domain should parse 'exclude'."""
        data = {
            "pipeline": {
                "coverage": {
                    "enabled": True,
                    "tools": ["coverage_py"],
                    "exclude": ["tests/**", "conftest.py"],
                },
            },
        }
        config = dict_to_config(data)
        assert config.pipeline.coverage is not None
        assert config.pipeline.coverage.exclude == ["tests/**", "conftest.py"]

    def test_domain_exclude_defaults_to_empty_list(self) -> None:
        """Domain exclude should default to empty list when not specified."""
        data = {
            "pipeline": {
                "linting": {
                    "tools": ["ruff"],
                },
            },
        }
        config = dict_to_config(data)
        assert config.pipeline.linting is not None
        assert config.pipeline.linting.exclude == []


class TestFindProjectConfig:
    """Tests for find_project_config function."""

    def test_finds_lucidshark_yml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidshark.yml"
        config_file.write_text("fail_on: high")
        result = find_project_config(tmp_path)
        assert result == config_file

    def test_finds_lucidshark_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidshark.yaml"
        config_file.write_text("fail_on: high")
        result = find_project_config(tmp_path)
        assert result == config_file

    def test_returns_none_when_no_config(self, tmp_path: Path) -> None:
        result = find_project_config(tmp_path)
        assert result is None

    def test_prefers_yml_over_yaml(self, tmp_path: Path) -> None:
        yml_file = tmp_path / ".lucidshark.yml"
        yaml_file = tmp_path / ".lucidshark.yaml"
        yml_file.write_text("fail_on: high")
        yaml_file.write_text("fail_on: low")
        result = find_project_config(tmp_path)
        assert result == yml_file


class TestLoadYamlFile:
    """Tests for load_yaml_file function."""

    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("fail_on: high\nignore:\n  - tests/**")
        result = load_yaml_file(config_file)
        assert result == {"fail_on": "high", "ignore": ["tests/**"]}

    def test_returns_empty_dict_for_empty_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("")
        result = load_yaml_file(config_file)
        assert result == {}

    def test_raises_for_invalid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("invalid: yaml: content:")
        with pytest.raises(Exception):  # yaml.YAMLError
            load_yaml_file(config_file)

    def test_raises_for_non_dict_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("- item1\n- item2")
        with pytest.raises(ConfigError):
            load_yaml_file(config_file)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_returns_default_config_when_no_files(self, tmp_path: Path) -> None:
        config = load_config(tmp_path)
        assert isinstance(config, LucidSharkConfig)
        assert config.fail_on is None

    def test_loads_project_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidshark.yml"
        config_file.write_text("fail_on: high")
        config = load_config(tmp_path)
        assert config.fail_on == "high"

    def test_cli_overrides_take_precedence(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidshark.yml"
        config_file.write_text("fail_on: low")
        config = load_config(
            tmp_path,
            cli_overrides={"fail_on": "critical"},
        )
        assert config.fail_on == "critical"

    def test_custom_config_path(self, tmp_path: Path) -> None:
        custom_config = tmp_path / "custom.yml"
        custom_config.write_text("fail_on: medium")
        config = load_config(tmp_path, cli_config_path=custom_config)
        assert config.fail_on == "medium"

    def test_raises_for_missing_custom_config(self, tmp_path: Path) -> None:
        missing_config = tmp_path / "missing.yml"
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path, cli_config_path=missing_config)
        assert "not found" in str(exc_info.value)

    def test_tracks_config_sources(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidshark.yml"
        config_file.write_text("fail_on: high")
        config = load_config(tmp_path, cli_overrides={"ignore": ["*.md"]})
        assert any("project" in s for s in config._config_sources)
        assert "cli" in config._config_sources

    def test_env_vars_expanded_in_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidshark.yml"
        config_file.write_text(
            "scanners:\n"
            "  sca:\n"
            "    api_token: ${TEST_TOKEN}\n"
        )
        with patch.dict(os.environ, {"TEST_TOKEN": "secret123"}):
            config = load_config(tmp_path)
        assert config.scanners["sca"].options["api_token"] == "secret123"


class TestLoadConfigMerging:
    """Tests for config merging behavior."""

    def test_scanner_options_merged(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".lucidshark.yml"
        config_file.write_text(
            "scanners:\n"
            "  sca:\n"
            "    enabled: true\n"
            "    ignore_unfixed: true\n"
        )
        config = load_config(
            tmp_path,
            cli_overrides={
                "scanners": {
                    "sca": {"severity": ["HIGH", "CRITICAL"]},
                }
            },
        )
        # Both file config and CLI override should be present
        sca_config = config.scanners["sca"]
        assert sca_config.enabled is True
        assert sca_config.options.get("ignore_unfixed") is True
        assert sca_config.options.get("severity") == ["HIGH", "CRITICAL"]


class TestParseDomainPipelineConfigExclude:
    """Tests for _parse_domain_pipeline_config handling of exclude."""

    def test_parses_exclude_field(self) -> None:
        """Test that exclude is parsed from domain config dict."""
        data = {
            "enabled": True,
            "tools": [{"name": "ruff"}],
            "exclude": ["scripts/**", "generated/**"],
        }
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.exclude == ["scripts/**", "generated/**"]

    def test_exclude_defaults_to_empty(self) -> None:
        """Test that exclude defaults to empty when not in dict."""
        data = {
            "enabled": True,
            "tools": [{"name": "ruff"}],
        }
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.exclude == []

    def test_returns_none_for_none_input(self) -> None:
        """Test that None input returns None."""
        assert _parse_domain_pipeline_config(None) is None

    def test_exclude_with_empty_list(self) -> None:
        """Test that explicit empty list is preserved."""
        data: Dict[str, Any] = {"tools": [], "exclude": []}
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.exclude == []

    def test_exclude_preserves_pattern_order(self) -> None:
        """Test that pattern order is preserved."""
        data = {
            "tools": [{"name": "ruff"}],
            "exclude": ["z/**", "a/**", "m/**"],
        }
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.exclude == ["z/**", "a/**", "m/**"]


class TestParseDomainPipelineConfigCommand:
    """Tests for _parse_domain_pipeline_config handling of command and post_command."""

    def test_parses_command(self) -> None:
        """Test that command is parsed from domain config dict."""
        data = {
            "enabled": True,
            "tools": [{"name": "pytest"}],
            "command": "make test",
        }
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.command == "make test"

    def test_parses_post_command(self) -> None:
        """Test that post_command is parsed from domain config dict."""
        data = {
            "enabled": True,
            "tools": [{"name": "pytest"}],
            "post_command": "make clean",
        }
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.post_command == "make clean"

    def test_parses_both_commands(self) -> None:
        """Test that both command and post_command are parsed."""
        data = {
            "enabled": True,
            "tools": [{"name": "pytest"}],
            "command": "npm test",
            "post_command": "npm run cleanup",
        }
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.command == "npm test"
        assert result.post_command == "npm run cleanup"

    def test_commands_default_to_none(self) -> None:
        """Test that command and post_command default to None."""
        data = {
            "enabled": True,
            "tools": [{"name": "pytest"}],
        }
        result = _parse_domain_pipeline_config(data)
        assert result is not None
        assert result.command is None
        assert result.post_command is None

    def test_dict_to_config_parses_commands(self) -> None:
        """Test that dict_to_config correctly parses command and post_command."""
        data = {
            "pipeline": {
                "testing": {
                    "enabled": True,
                    "tools": [{"name": "pytest"}],
                    "command": "python -m pytest -x",
                    "post_command": "rm -rf .pytest_cache",
                },
            },
        }
        config = dict_to_config(data)
        assert config.pipeline.testing is not None
        assert config.pipeline.testing.command == "python -m pytest -x"
        assert config.pipeline.testing.post_command == "rm -rf .pytest_cache"


class TestDictToConfigIgnoreIssues:
    """Tests for dict_to_config handling of ignore_issues."""

    def test_parses_simple_string_entries(self) -> None:
        data = {"ignore_issues": ["E501", "CVE-2021-1234"]}
        config = dict_to_config(data)
        assert len(config.ignore_issues) == 2
        assert config.ignore_issues[0].rule_id == "E501"
        assert config.ignore_issues[0].reason is None
        assert config.ignore_issues[1].rule_id == "CVE-2021-1234"

    def test_parses_structured_entries(self) -> None:
        data = {
            "ignore_issues": [
                {
                    "rule_id": "CVE-2021-1234",
                    "reason": "Accepted risk",
                    "expires": "2026-12-31",
                }
            ]
        }
        config = dict_to_config(data)
        assert len(config.ignore_issues) == 1
        entry = config.ignore_issues[0]
        assert entry.rule_id == "CVE-2021-1234"
        assert entry.reason == "Accepted risk"
        assert entry.expires == "2026-12-31"

    def test_parses_mixed_entries(self) -> None:
        data = {
            "ignore_issues": [
                "E501",
                {"rule_id": "CVE-2021-1234", "reason": "accepted"},
            ]
        }
        config = dict_to_config(data)
        assert len(config.ignore_issues) == 2
        assert config.ignore_issues[0].rule_id == "E501"
        assert config.ignore_issues[1].rule_id == "CVE-2021-1234"
        assert config.ignore_issues[1].reason == "accepted"

    def test_empty_ignore_issues(self) -> None:
        data: dict = {"ignore_issues": []}
        config = dict_to_config(data)
        assert config.ignore_issues == []

    def test_no_ignore_issues_key(self) -> None:
        config = dict_to_config({})
        assert config.ignore_issues == []

    def test_structured_entry_without_optional_fields(self) -> None:
        data = {"ignore_issues": [{"rule_id": "E501"}]}
        config = dict_to_config(data)
        assert len(config.ignore_issues) == 1
        assert config.ignore_issues[0].rule_id == "E501"
        assert config.ignore_issues[0].reason is None
        assert config.ignore_issues[0].expires is None

    def test_pyyaml_date_object_normalised_to_string(self) -> None:
        """PyYAML parses bare dates as datetime.date objects; loader should normalise."""
        from datetime import date

        data = {
            "ignore_issues": [
                {"rule_id": "CVE-2021-1234", "expires": date(2026, 6, 1)}
            ]
        }
        config = dict_to_config(data)
        assert config.ignore_issues[0].expires == "2026-06-01"
        assert isinstance(config.ignore_issues[0].expires, str)


class TestParseCoveragePipelineConfigExclude:
    """Tests for _parse_coverage_pipeline_config handling of exclude."""

    def test_parses_exclude_field(self) -> None:
        """Test that exclude is parsed from coverage config dict."""
        data = {
            "enabled": True,
            "tools": [{"name": "coverage_py"}],
            "threshold": 80,
            "exclude": ["tests/**"],
        }
        result = _parse_coverage_pipeline_config(data)
        assert result is not None
        assert result.exclude == ["tests/**"]

    def test_exclude_defaults_to_empty(self) -> None:
        """Test that exclude defaults to empty when not in dict."""
        data = {
            "enabled": True,
            "tools": [{"name": "coverage_py"}],
        }
        result = _parse_coverage_pipeline_config(data)
        assert result is not None
        assert result.exclude == []

    def test_returns_none_for_none_input(self) -> None:
        """Test that None input returns None."""
        assert _parse_coverage_pipeline_config(None) is None

    def test_exclude_coexists_with_threshold_and_extra_args(self) -> None:
        """Test that exclude does not interfere with other coverage fields."""
        data = {
            "enabled": True,
            "tools": [{"name": "coverage_py"}],
            "threshold": 90,
            "extra_args": ["-DskipITs"],
            "exclude": ["vendor/**"],
        }
        result = _parse_coverage_pipeline_config(data)
        assert result is not None
        assert result.threshold == 90
        assert result.extra_args == ["-DskipITs"]
        assert result.exclude == ["vendor/**"]
