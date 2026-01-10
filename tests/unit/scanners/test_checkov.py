"""Tests for CheckovScanner plugin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


from lucidscan.plugins.scanners.checkov import CheckovScanner, DEFAULT_VERSION, _glob_to_regex
from lucidscan.plugins.scanners.base import ScannerPlugin
from lucidscan.core.models import ScanDomain, Severity


class TestCheckovScannerInterface:
    """Tests for CheckovScanner implementing ScannerPlugin interface."""

    def test_inherits_from_scanner_plugin(self) -> None:
        """Test that CheckovScanner is a ScannerPlugin."""
        assert issubclass(CheckovScanner, ScannerPlugin)

    def test_name_property(self) -> None:
        """Test that name is 'checkov'."""
        scanner = CheckovScanner()
        assert scanner.name == "checkov"

    def test_domains_property(self) -> None:
        """Test that Checkov supports IAC domain."""
        scanner = CheckovScanner()
        assert ScanDomain.IAC in scanner.domains
        assert len(scanner.domains) == 1

    def test_get_version_default(self) -> None:
        """Test that default version matches DEFAULT_VERSION."""
        scanner = CheckovScanner()
        assert scanner.get_version() == DEFAULT_VERSION

    def test_get_version_custom(self) -> None:
        """Test that custom version can be specified."""
        scanner = CheckovScanner(version="3.0.0")
        assert scanner.get_version() == "3.0.0"


class TestCheckovScannerBinaryManagement:
    """Tests for Checkov binary/venv management."""

    def test_ensure_binary_returns_path(self, tmp_path: Path) -> None:
        """Test that ensure_binary returns a Path."""
        scanner = CheckovScanner()

        # Mock paths to use tmp_path
        with patch.object(scanner, "_paths") as mock_paths:
            venv_dir = tmp_path / "bin" / "checkov" / DEFAULT_VERSION / "venv"
            venv_dir.mkdir(parents=True)
            binary_dir = venv_dir / "bin"
            binary_dir.mkdir(parents=True)
            binary_path = binary_dir / "checkov"
            binary_path.write_text("#!/bin/bash\necho checkov")

            mock_paths.plugin_bin_dir.return_value = tmp_path / "bin" / "checkov" / DEFAULT_VERSION

            result = scanner.ensure_binary()
            assert isinstance(result, Path)
            assert result == binary_path

    def test_ensure_binary_uses_cached_binary(self, tmp_path: Path) -> None:
        """Test that existing binary is reused without installation."""
        scanner = CheckovScanner()

        with patch.object(scanner, "_paths") as mock_paths:
            with patch.object(scanner, "_install_checkov") as mock_install:
                venv_dir = tmp_path / "bin" / "checkov" / DEFAULT_VERSION / "venv"
                venv_dir.mkdir(parents=True)
                binary_dir = venv_dir / "bin"
                binary_dir.mkdir(parents=True)
                binary_path = binary_dir / "checkov"
                binary_path.write_text("#!/bin/bash\necho checkov")

                mock_paths.plugin_bin_dir.return_value = tmp_path / "bin" / "checkov" / DEFAULT_VERSION

                scanner.ensure_binary()

                # Should not install if binary exists
                mock_install.assert_not_called()


class TestCheckovScannerBinaryPath:
    """Tests for Checkov binary path construction."""

    def test_binary_path_unix(self, tmp_path: Path) -> None:
        """Test binary path on Unix systems."""
        scanner = CheckovScanner()

        with patch("sys.platform", "linux"):
            venv_dir = tmp_path / "venv"
            path = scanner._get_binary_path(venv_dir)
            assert path == venv_dir / "bin" / "checkov"

    def test_binary_path_darwin(self, tmp_path: Path) -> None:
        """Test binary path on macOS."""
        scanner = CheckovScanner()

        with patch("sys.platform", "darwin"):
            venv_dir = tmp_path / "venv"
            path = scanner._get_binary_path(venv_dir)
            assert path == venv_dir / "bin" / "checkov"

    def test_binary_path_windows(self, tmp_path: Path) -> None:
        """Test binary path on Windows."""
        scanner = CheckovScanner()

        with patch("sys.platform", "win32"):
            venv_dir = tmp_path / "venv"
            path = scanner._get_binary_path(venv_dir)
            assert path == venv_dir / "Scripts" / "checkov.exe"


class TestCheckovScannerIssueIdGeneration:
    """Tests for issue ID generation."""

    def test_issue_id_is_deterministic(self) -> None:
        """Test that the same inputs produce the same ID."""
        scanner = CheckovScanner()

        id1 = scanner._generate_issue_id("CKV_AWS_1", "main.tf", "aws_s3_bucket.test", 10)
        id2 = scanner._generate_issue_id("CKV_AWS_1", "main.tf", "aws_s3_bucket.test", 10)

        assert id1 == id2

    def test_issue_id_differs_for_different_inputs(self) -> None:
        """Test that different inputs produce different IDs."""
        scanner = CheckovScanner()

        id1 = scanner._generate_issue_id("CKV_AWS_1", "main.tf", "aws_s3_bucket.test", 10)
        id2 = scanner._generate_issue_id("CKV_AWS_2", "main.tf", "aws_s3_bucket.test", 10)
        id3 = scanner._generate_issue_id("CKV_AWS_1", "other.tf", "aws_s3_bucket.test", 10)
        id4 = scanner._generate_issue_id("CKV_AWS_1", "main.tf", "aws_s3_bucket.other", 10)

        assert id1 != id2
        assert id1 != id3
        assert id1 != id4

    def test_issue_id_has_correct_prefix(self) -> None:
        """Test that issue ID starts with 'checkov-'."""
        scanner = CheckovScanner()

        issue_id = scanner._generate_issue_id("CKV_AWS_1", "main.tf", "aws_s3_bucket.test", 10)

        assert issue_id.startswith("checkov-")

    def test_issue_id_handles_none_line(self) -> None:
        """Test that issue ID handles None line number."""
        scanner = CheckovScanner()

        # Should not raise
        issue_id = scanner._generate_issue_id("CKV_AWS_1", "main.tf", "aws_s3_bucket.test", None)

        assert issue_id.startswith("checkov-")


class TestCheckovScannerJsonParsing:
    """Tests for Checkov JSON output parsing."""

    def test_parse_empty_results(self) -> None:
        """Test parsing JSON with no failed checks."""
        scanner = CheckovScanner()

        json_output = '''{"check_type": "terraform", "results": {"passed_checks": [], "failed_checks": [], "skipped_checks": []}}'''
        issues = scanner._parse_checkov_json(json_output, Path("/project"))

        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test handling of invalid JSON."""
        scanner = CheckovScanner()

        invalid_json = "not valid json {"
        issues = scanner._parse_checkov_json(invalid_json, Path("/project"))

        assert issues == []

    def test_parse_basic_failed_check(self) -> None:
        """Test parsing a basic Checkov failed check."""
        scanner = CheckovScanner()

        json_output = '''{
            "check_type": "terraform",
            "results": {
                "passed_checks": [],
                "failed_checks": [
                    {
                        "check_id": "CKV_AWS_18",
                        "check": "Ensure the S3 bucket has access logging enabled",
                        "file_path": "/main.tf",
                        "file_line_range": [1, 10],
                        "resource": "aws_s3_bucket.example",
                        "guideline": "https://docs.bridgecrew.io/docs/s3_13-enable-logging",
                        "severity": "HIGH"
                    }
                ],
                "skipped_checks": []
            }
        }'''

        issues = scanner._parse_checkov_json(json_output, Path("/project"))

        assert len(issues) == 1
        issue = issues[0]
        assert issue.scanner == ScanDomain.IAC
        assert issue.source_tool == "checkov"
        assert "CKV_AWS_18" in issue.title
        assert issue.severity == Severity.HIGH
        assert issue.line_start == 1
        assert issue.line_end == 10
        assert issue.iac_resource == "aws_s3_bucket.example"

    def test_parse_check_with_medium_severity(self) -> None:
        """Test parsing a check with medium severity."""
        scanner = CheckovScanner()

        json_output = '''{
            "check_type": "kubernetes",
            "results": {
                "passed_checks": [],
                "failed_checks": [
                    {
                        "check_id": "CKV_K8S_1",
                        "check": "Ensure that CPU limits are set",
                        "file_path": "/deployment.yaml",
                        "file_line_range": [15, 20],
                        "resource": "Deployment.default.nginx",
                        "severity": "MEDIUM"
                    }
                ],
                "skipped_checks": []
            }
        }'''

        issues = scanner._parse_checkov_json(json_output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_parse_check_without_severity_defaults_to_medium(self) -> None:
        """Test that checks without severity default to MEDIUM."""
        scanner = CheckovScanner()

        json_output = '''{
            "check_type": "terraform",
            "results": {
                "passed_checks": [],
                "failed_checks": [
                    {
                        "check_id": "CKV_AWS_1",
                        "check": "Some check without severity",
                        "file_path": "/main.tf",
                        "file_line_range": [1, 5],
                        "resource": "aws_resource.test"
                    }
                ],
                "skipped_checks": []
            }
        }'''

        issues = scanner._parse_checkov_json(json_output, Path("/project"))

        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_parse_multiple_failed_checks(self) -> None:
        """Test parsing multiple failed checks."""
        scanner = CheckovScanner()

        json_output = '''{
            "check_type": "terraform",
            "results": {
                "passed_checks": [],
                "failed_checks": [
                    {
                        "check_id": "CKV_AWS_1",
                        "check": "Check 1",
                        "file_path": "/main.tf",
                        "file_line_range": [1, 5],
                        "resource": "aws_resource.one"
                    },
                    {
                        "check_id": "CKV_AWS_2",
                        "check": "Check 2",
                        "file_path": "/main.tf",
                        "file_line_range": [10, 15],
                        "resource": "aws_resource.two"
                    }
                ],
                "skipped_checks": []
            }
        }'''

        issues = scanner._parse_checkov_json(json_output, Path("/project"))

        assert len(issues) == 2

    def test_parse_list_of_framework_results(self) -> None:
        """Test parsing a list of results from multiple frameworks."""
        scanner = CheckovScanner()

        json_output = '''[
            {
                "check_type": "terraform",
                "results": {
                    "passed_checks": [],
                    "failed_checks": [
                        {
                            "check_id": "CKV_AWS_1",
                            "check": "Terraform check",
                            "file_path": "/main.tf",
                            "file_line_range": [1, 5],
                            "resource": "aws_resource.one"
                        }
                    ],
                    "skipped_checks": []
                }
            },
            {
                "check_type": "kubernetes",
                "results": {
                    "passed_checks": [],
                    "failed_checks": [
                        {
                            "check_id": "CKV_K8S_1",
                            "check": "Kubernetes check",
                            "file_path": "/deployment.yaml",
                            "file_line_range": [10, 20],
                            "resource": "Deployment.nginx"
                        }
                    ],
                    "skipped_checks": []
                }
            }
        ]'''

        issues = scanner._parse_checkov_json(json_output, Path("/project"))

        assert len(issues) == 2
        # Check that both frameworks are represented
        check_types = {issue.scanner_metadata.get("check_type") for issue in issues}
        assert "terraform" in check_types
        assert "kubernetes" in check_types


class TestCheckovScannerCheckConversion:
    """Tests for converting Checkov checks to UnifiedIssue."""

    def test_check_to_unified_issue_basic(self) -> None:
        """Test basic check conversion."""
        scanner = CheckovScanner()

        check = {
            "check_id": "CKV_AWS_18",
            "check": "Ensure S3 bucket has access logging enabled",
            "file_path": "/main.tf",
            "file_line_range": [1, 10],
            "resource": "aws_s3_bucket.example",
            "guideline": "https://docs.bridgecrew.io/docs/s3_13",
            "severity": "HIGH",
        }

        issue = scanner._check_to_unified_issue(check, "terraform", Path("/project"))

        assert issue is not None
        assert issue.scanner == ScanDomain.IAC
        assert issue.source_tool == "checkov"
        assert issue.severity == Severity.HIGH
        assert "CKV_AWS_18" in issue.title
        assert issue.iac_resource == "aws_s3_bucket.example"
        assert issue.line_start == 1
        assert issue.line_end == 10
        assert "https://docs.bridgecrew.io" in issue.recommendation

    def test_check_to_unified_issue_preserves_metadata(self) -> None:
        """Test that scanner metadata is preserved."""
        scanner = CheckovScanner()

        check = {
            "check_id": "CKV_AWS_18",
            "check": "Test check",
            "file_path": "/main.tf",
            "file_line_range": [1, 10],
            "resource": "aws_s3_bucket.example",
            "resource_address": "module.s3.aws_s3_bucket.example",
            "bc_check_id": "BC_AWS_S3_13",
            "severity": "HIGH",
        }

        issue = scanner._check_to_unified_issue(check, "terraform", Path("/project"))

        assert issue is not None
        assert issue.scanner_metadata["check_id"] == "CKV_AWS_18"
        assert issue.scanner_metadata["check_type"] == "terraform"
        assert issue.scanner_metadata["resource"] == "aws_s3_bucket.example"
        assert issue.scanner_metadata["resource_address"] == "module.s3.aws_s3_bucket.example"
        assert issue.scanner_metadata["bc_check_id"] == "BC_AWS_S3_13"

    def test_check_to_unified_issue_handles_missing_fields(self) -> None:
        """Test handling of checks with minimal fields."""
        scanner = CheckovScanner()

        check = {
            "check_id": "CKV_AWS_1",
            "check": "Minimal check",
            "file_path": "",
            "file_line_range": [],
            "resource": "",
        }

        issue = scanner._check_to_unified_issue(check, "terraform", Path("/project"))

        assert issue is not None
        assert issue.line_start is None
        assert issue.iac_resource is None

    def test_check_to_unified_issue_strips_leading_slash(self) -> None:
        """Test that leading slash is stripped from file path."""
        scanner = CheckovScanner()

        check = {
            "check_id": "CKV_AWS_1",
            "check": "Test check",
            "file_path": "/main.tf",  # Leading slash
            "file_line_range": [1, 5],
            "resource": "aws_resource.test",
        }

        issue = scanner._check_to_unified_issue(check, "terraform", Path("/project"))

        assert issue is not None
        assert issue.file_path == Path("/project/main.tf")


class TestGlobToRegex:
    """Tests for glob-to-regex conversion used for Checkov --skip-path."""

    def test_double_star_converts_to_dotstar(self) -> None:
        """Test that ** converts to .* for recursive matching."""
        assert _glob_to_regex(".venv/**") == r"\.venv/.*"
        assert _glob_to_regex("tests/**") == "tests/.*"
        assert _glob_to_regex("**/*.tf") == r".*/[^/]*\.tf"

    def test_single_star_converts_to_non_slash_match(self) -> None:
        """Test that * converts to [^/]* to match non-slash characters."""
        assert _glob_to_regex("*.tf") == r"[^/]*\.tf"
        assert _glob_to_regex("test_*.py") == r"test_[^/]*\.py"

    def test_dot_is_escaped(self) -> None:
        """Test that dots are escaped for regex."""
        assert _glob_to_regex(".venv") == r"\.venv"
        assert _glob_to_regex("file.txt") == r"file\.txt"

    def test_question_mark_converts_to_single_char(self) -> None:
        """Test that ? converts to [^/] for single character matching."""
        assert _glob_to_regex("file?.txt") == r"file[^/]\.txt"

    def test_regex_special_chars_escaped(self) -> None:
        """Test that regex special characters are properly escaped."""
        assert _glob_to_regex("test[1].txt") == r"test\[1\]\.txt"
        assert _glob_to_regex("foo(bar)") == r"foo\(bar\)"
        assert _glob_to_regex("a+b") == r"a\+b"
        assert _glob_to_regex("a^b$c") == r"a\^b\$c"

    def test_combined_patterns(self) -> None:
        """Test realistic combined patterns."""
        # Pattern from the original issue
        assert _glob_to_regex(".venv/**") == r"\.venv/.*"
        assert _glob_to_regex("tests/**") == "tests/.*"
        # More complex patterns
        assert _glob_to_regex("src/**/*.py") == r"src/.*/[^/]*\.py"
        assert _glob_to_regex("node_modules/**") == "node_modules/.*"

    def test_plain_paths_unchanged(self) -> None:
        """Test that plain paths without glob chars stay mostly unchanged."""
        assert _glob_to_regex("src/main") == "src/main"
        assert _glob_to_regex("README") == "README"
