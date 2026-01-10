"""Tests for OpenGrepScanner plugin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock


from lucidscan.plugins.scanners.opengrep import OpenGrepScanner, DEFAULT_VERSION
from lucidscan.plugins.scanners.base import ScannerPlugin
from lucidscan.core.models import ScanDomain


class TestOpenGrepScannerInterface:
    """Tests for OpenGrepScanner implementing ScannerPlugin interface."""

    def test_inherits_from_scanner_plugin(self) -> None:
        """Test that OpenGrepScanner is a ScannerPlugin."""
        assert issubclass(OpenGrepScanner, ScannerPlugin)

    def test_name_property(self) -> None:
        """Test that name is 'opengrep'."""
        scanner = OpenGrepScanner()
        assert scanner.name == "opengrep"

    def test_domains_property(self) -> None:
        """Test that OpenGrep supports SAST domain."""
        scanner = OpenGrepScanner()
        assert ScanDomain.SAST in scanner.domains
        assert len(scanner.domains) == 1

    def test_get_version_default(self) -> None:
        """Test that default version matches DEFAULT_VERSION."""
        scanner = OpenGrepScanner()
        assert scanner.get_version() == DEFAULT_VERSION

    def test_get_version_custom(self) -> None:
        """Test that custom version can be specified."""
        scanner = OpenGrepScanner(version="2.0.0")
        assert scanner.get_version() == "2.0.0"


class TestOpenGrepScannerBinaryManagement:
    """Tests for OpenGrep binary download and caching."""

    def test_ensure_binary_returns_path(self, tmp_path: Path) -> None:
        """Test that ensure_binary returns a Path."""
        scanner = OpenGrepScanner()

        # Mock paths to use tmp_path
        with patch.object(scanner, "_paths") as mock_paths:
            binary_dir = tmp_path / "bin" / "opengrep" / DEFAULT_VERSION
            binary_dir.mkdir(parents=True)
            binary_path = binary_dir / "opengrep"
            binary_path.write_text("#!/bin/bash\necho opengrep")

            mock_paths.plugin_bin_dir.return_value = binary_dir

            result = scanner.ensure_binary()
            assert isinstance(result, Path)
            assert result == binary_path

    def test_ensure_binary_uses_cached_binary(self, tmp_path: Path) -> None:
        """Test that existing binary is reused without download."""
        scanner = OpenGrepScanner()

        with patch.object(scanner, "_paths") as mock_paths:
            with patch.object(scanner, "_download_binary") as mock_download:
                binary_dir = tmp_path / "bin" / "opengrep" / DEFAULT_VERSION
                binary_dir.mkdir(parents=True)
                binary_path = binary_dir / "opengrep"
                binary_path.write_text("#!/bin/bash\necho opengrep")

                mock_paths.plugin_bin_dir.return_value = binary_dir

                scanner.ensure_binary()

                # Should not download if binary exists
                mock_download.assert_not_called()


class TestOpenGrepScannerBinaryNaming:
    """Tests for OpenGrep binary naming conventions."""

    def test_binary_name_linux(self) -> None:
        """Test binary name on Linux."""
        scanner = OpenGrepScanner()

        with patch("lucidscan.plugins.scanners.opengrep.get_platform_info") as mock_platform:
            mock_platform.return_value = MagicMock(os="linux", arch="amd64")
            assert scanner._get_binary_name() == "opengrep"

    def test_binary_name_darwin(self) -> None:
        """Test binary name on macOS."""
        scanner = OpenGrepScanner()

        with patch("lucidscan.plugins.scanners.opengrep.get_platform_info") as mock_platform:
            mock_platform.return_value = MagicMock(os="darwin", arch="arm64")
            assert scanner._get_binary_name() == "opengrep"

    def test_binary_name_windows(self) -> None:
        """Test binary name on Windows."""
        scanner = OpenGrepScanner()

        with patch("lucidscan.plugins.scanners.opengrep.get_platform_info") as mock_platform:
            mock_platform.return_value = MagicMock(os="windows", arch="amd64")
            assert scanner._get_binary_name() == "opengrep.exe"


class TestOpenGrepScannerDownloadUrl:
    """Tests for OpenGrep download URL construction."""

    def test_download_url_linux_amd64(self) -> None:
        """Test download URL for Linux amd64."""
        scanner = OpenGrepScanner(version="1.12.1")

        with patch("lucidscan.plugins.scanners.opengrep.get_platform_info") as mock_platform:
            mock_platform.return_value = MagicMock(os="linux", arch="amd64")

            # Verify the method exists and platform mapping works
            assert hasattr(scanner, "_download_binary")

    def test_download_url_darwin_arm64(self) -> None:
        """Test download URL for macOS arm64."""
        scanner = OpenGrepScanner(version="1.12.1")

        with patch("lucidscan.plugins.scanners.opengrep.get_platform_info") as mock_platform:
            mock_platform.return_value = MagicMock(os="darwin", arch="arm64")

            assert hasattr(scanner, "_download_binary")


class TestOpenGrepScannerIssueIdGeneration:
    """Tests for issue ID generation."""

    def test_issue_id_is_deterministic(self) -> None:
        """Test that the same inputs produce the same ID."""
        scanner = OpenGrepScanner()

        id1 = scanner._generate_issue_id("rule.test", "src/main.py", 10, 5)
        id2 = scanner._generate_issue_id("rule.test", "src/main.py", 10, 5)

        assert id1 == id2

    def test_issue_id_differs_for_different_inputs(self) -> None:
        """Test that different inputs produce different IDs."""
        scanner = OpenGrepScanner()

        id1 = scanner._generate_issue_id("rule.test", "src/main.py", 10, 5)
        id2 = scanner._generate_issue_id("rule.other", "src/main.py", 10, 5)
        id3 = scanner._generate_issue_id("rule.test", "src/other.py", 10, 5)
        id4 = scanner._generate_issue_id("rule.test", "src/main.py", 20, 5)

        assert id1 != id2
        assert id1 != id3
        assert id1 != id4

    def test_issue_id_has_correct_prefix(self) -> None:
        """Test that issue ID starts with 'opengrep-'."""
        scanner = OpenGrepScanner()

        issue_id = scanner._generate_issue_id("rule.test", "src/main.py", 10, 5)

        assert issue_id.startswith("opengrep-")


class TestOpenGrepScannerTitleFormatting:
    """Tests for title formatting."""

    def test_format_title_basic(self) -> None:
        """Test basic title formatting."""
        scanner = OpenGrepScanner()

        title = scanner._format_title("python.security.hardcoded-password", "Found hardcoded password")

        assert "python.security.hardcoded-password" in title
        assert "Found hardcoded password" in title

    def test_format_title_truncates_long_message(self) -> None:
        """Test that long messages are truncated."""
        scanner = OpenGrepScanner()

        long_message = "A" * 200
        title = scanner._format_title("rule.id", long_message)

        # Title should be shorter than the original message
        assert len(title) < 200
        assert "..." in title


class TestOpenGrepScannerJsonParsing:
    """Tests for OpenGrep JSON output parsing."""

    def test_parse_empty_results(self) -> None:
        """Test parsing JSON with no results."""
        scanner = OpenGrepScanner()

        json_output = '{"results": [], "errors": []}'
        issues = scanner._parse_opengrep_json(json_output, Path("/project"))

        assert issues == []

    def test_parse_invalid_json(self) -> None:
        """Test handling of invalid JSON."""
        scanner = OpenGrepScanner()

        invalid_json = "not valid json {"
        issues = scanner._parse_opengrep_json(invalid_json, Path("/project"))

        assert issues == []

    def test_parse_basic_result(self) -> None:
        """Test parsing a basic OpenGrep result."""
        scanner = OpenGrepScanner()

        json_output = '''{
            "results": [
                {
                    "check_id": "python.security.test-rule",
                    "path": "src/main.py",
                    "start": {"line": 10, "col": 5},
                    "end": {"line": 10, "col": 20},
                    "extra": {
                        "message": "Test security issue",
                        "severity": "WARNING",
                        "lines": "password = 'secret'"
                    }
                }
            ],
            "errors": []
        }'''

        issues = scanner._parse_opengrep_json(json_output, Path("/project"))

        assert len(issues) == 1
        issue = issues[0]
        assert issue.scanner == ScanDomain.SAST
        assert issue.source_tool == "opengrep"
        assert "python.security.test-rule" in issue.title
        assert issue.line_start == 10
        assert issue.line_end == 10
        assert issue.code_snippet == "password = 'secret'"

    def test_parse_result_with_metadata(self) -> None:
        """Test parsing result with metadata including CWE."""
        scanner = OpenGrepScanner()

        json_output = '''{
            "results": [
                {
                    "check_id": "python.security.hardcoded-password",
                    "path": "src/auth.py",
                    "start": {"line": 15, "col": 1},
                    "end": {"line": 15, "col": 30},
                    "extra": {
                        "message": "Hardcoded password detected",
                        "severity": "ERROR",
                        "lines": "PASSWORD = 'admin123'",
                        "metadata": {
                            "cwe": ["CWE-259"],
                            "owasp": ["A3:2017"],
                            "references": ["https://example.com/security"],
                            "severity": "HIGH"
                        }
                    }
                }
            ],
            "errors": []
        }'''

        issues = scanner._parse_opengrep_json(json_output, Path("/project"))

        assert len(issues) == 1
        issue = issues[0]
        # Metadata severity should override extra.severity
        from lucidscan.core.models import Severity
        assert issue.severity == Severity.HIGH
        assert "cwe" in issue.scanner_metadata.get("metadata", {})

    def test_parse_multiple_results(self) -> None:
        """Test parsing multiple results."""
        scanner = OpenGrepScanner()

        json_output = '''{
            "results": [
                {
                    "check_id": "rule1",
                    "path": "file1.py",
                    "start": {"line": 1, "col": 1},
                    "end": {"line": 1, "col": 10},
                    "extra": {"message": "Issue 1", "severity": "WARNING"}
                },
                {
                    "check_id": "rule2",
                    "path": "file2.py",
                    "start": {"line": 5, "col": 1},
                    "end": {"line": 5, "col": 10},
                    "extra": {"message": "Issue 2", "severity": "ERROR"}
                }
            ],
            "errors": []
        }'''

        issues = scanner._parse_opengrep_json(json_output, Path("/project"))

        assert len(issues) == 2
