"""Unit tests for cppcheck type checker plugin."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


from lucidshark.core.models import ScanContext, Severity, ToolDomain
from lucidshark.plugins.type_checkers.cppcheck import CppcheckChecker


SAMPLE_XML_OUTPUT = """\
<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <cppcheck version="2.12.0"/>
    <errors>
        <error id="nullPointer" severity="error" msg="Null pointer dereference" verbose="Null pointer dereference: ptr" cwe="476">
            <location file="/tmp/test/main.cpp" line="42" column="5"/>
        </error>
        <error id="uninitvar" severity="error" msg="Uninitialized variable: x" verbose="Uninitialized variable: x">
            <location file="/tmp/test/utils.cpp" line="10" column="3"/>
        </error>
        <error id="unusedFunction" severity="style" msg="The function 'foo' is never used." verbose="The function 'foo' is never used.">
            <location file="/tmp/test/utils.cpp" line="20" column="1"/>
        </error>
        <error id="unreadVariable" severity="style" msg="Variable 'y' is assigned a value that is never used." verbose="Variable 'y' is assigned a value that is never used.">
            <location file="/tmp/test/main.cpp" line="50" column="5"/>
        </error>
    </errors>
</results>
"""


class TestCppcheckProperties:
    """Basic property tests for CppcheckChecker."""

    def test_name(self) -> None:
        checker = CppcheckChecker()
        assert checker.name == "cppcheck"

    def test_languages(self) -> None:
        checker = CppcheckChecker()
        assert checker.languages == ["c++"]

    def test_domain(self) -> None:
        checker = CppcheckChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        checker = CppcheckChecker()
        assert checker.supports_strict_mode is True


class TestParseXmlOutput:
    """Tests for _parse_xml_output."""

    def test_parse_valid_xml(self) -> None:
        checker = CppcheckChecker()
        issues = checker._parse_xml_output(SAMPLE_XML_OUTPUT, Path("/tmp/test"))
        assert len(issues) == 4
        # Check first issue
        assert issues[0].rule_id == "nullPointer"
        assert issues[0].severity == Severity.HIGH
        assert issues[0].line_start == 42

    def test_parse_empty_output(self) -> None:
        checker = CppcheckChecker()
        issues = checker._parse_xml_output("", Path("/tmp"))
        assert issues == []

    def test_parse_non_xml_output(self) -> None:
        checker = CppcheckChecker()
        issues = checker._parse_xml_output("not xml output", Path("/tmp"))
        assert issues == []

    def test_severity_mapping_error(self) -> None:
        checker = CppcheckChecker()
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <errors>
        <error id="test" severity="error" msg="test error" verbose="test error">
            <location file="/tmp/test.cpp" line="1" column="1"/>
        </error>
    </errors>
</results>
"""
        issues = checker._parse_xml_output(xml, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.HIGH

    def test_severity_mapping_warning(self) -> None:
        checker = CppcheckChecker()
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <errors>
        <error id="test" severity="warning" msg="test warning" verbose="test warning">
            <location file="/tmp/test.cpp" line="1" column="1"/>
        </error>
    </errors>
</results>
"""
        issues = checker._parse_xml_output(xml, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_severity_mapping_style(self) -> None:
        checker = CppcheckChecker()
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <errors>
        <error id="test" severity="style" msg="test style" verbose="test style">
            <location file="/tmp/test.cpp" line="1" column="1"/>
        </error>
    </errors>
</results>
"""
        issues = checker._parse_xml_output(xml, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.LOW

    def test_severity_mapping_performance(self) -> None:
        checker = CppcheckChecker()
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <errors>
        <error id="test" severity="performance" msg="test perf" verbose="test perf">
            <location file="/tmp/test.cpp" line="1" column="1"/>
        </error>
    </errors>
</results>
"""
        issues = checker._parse_xml_output(xml, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].severity == Severity.MEDIUM

    def test_deduplication(self) -> None:
        checker = CppcheckChecker()
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <errors>
        <error id="test" severity="error" msg="same msg" verbose="same msg">
            <location file="/tmp/test.cpp" line="1" column="1"/>
        </error>
        <error id="test" severity="error" msg="same msg" verbose="same msg">
            <location file="/tmp/test.cpp" line="1" column="1"/>
        </error>
    </errors>
</results>
"""
        issues = checker._parse_xml_output(xml, Path("/tmp"))
        assert len(issues) == 1

    def test_skips_errors_without_location(self) -> None:
        checker = CppcheckChecker()
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
    <errors>
        <error id="toomanyconfigs" severity="information" msg="Too many configs" verbose="Too many configs"/>
    </errors>
</results>
"""
        issues = checker._parse_xml_output(xml, Path("/tmp"))
        assert len(issues) == 0

    def test_cwe_in_metadata(self) -> None:
        checker = CppcheckChecker()
        issues = checker._parse_xml_output(SAMPLE_XML_OUTPUT, Path("/tmp/test"))
        # First error has cwe="476"
        assert issues[0].metadata.get("cwe") == "476"


class TestParseTextOutput:
    """Tests for _parse_text_output."""

    def test_parse_text_format(self) -> None:
        checker = CppcheckChecker()
        output = "[/tmp/main.cpp:42]: (error) Null pointer dereference\n"
        issues = checker._parse_text_output(output, Path("/tmp"))
        assert len(issues) == 1
        assert issues[0].line_start == 42
        assert issues[0].severity == Severity.HIGH

    def test_parse_empty_text(self) -> None:
        checker = CppcheckChecker()
        issues = checker._parse_text_output("", Path("/tmp"))
        assert issues == []

    def test_parse_multiple_text_issues(self) -> None:
        checker = CppcheckChecker()
        output = (
            "[/tmp/main.cpp:10]: (error) Memory leak\n"
            "[/tmp/main.cpp:20]: (warning) Suspicious cast\n"
            "[/tmp/main.cpp:30]: (style) Unused variable\n"
        )
        issues = checker._parse_text_output(output, Path("/tmp"))
        assert len(issues) == 3


class TestCheck:
    """Tests for check method."""

    @patch.object(CppcheckChecker, "ensure_binary")
    def test_check_binary_not_found(self, mock_binary) -> None:
        mock_binary.side_effect = FileNotFoundError("cppcheck not found")
        checker = CppcheckChecker()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        issues = checker.check(context)
        assert issues == []

    @patch("lucidshark.plugins.type_checkers.cppcheck.run_with_streaming")
    @patch.object(CppcheckChecker, "ensure_binary")
    def test_check_timeout(self, mock_binary, mock_run) -> None:
        mock_binary.return_value = Path("/usr/bin/cppcheck")
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="cppcheck", timeout=300)
        checker = CppcheckChecker()
        context = ScanContext(
            project_root=Path("/tmp"),
            paths=[Path("/tmp")],
            enabled_domains=[],
        )
        issues = checker.check(context)
        assert issues == []

    @patch("lucidshark.plugins.type_checkers.cppcheck.run_with_streaming")
    @patch.object(CppcheckChecker, "ensure_binary")
    def test_check_parses_xml(self, mock_binary, mock_run) -> None:
        mock_binary.return_value = Path("/usr/bin/cppcheck")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr=SAMPLE_XML_OUTPUT,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "main.cpp").write_text("int main() {}")
            checker = CppcheckChecker()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            issues = checker.check(context)
            assert len(issues) == 4

    def test_get_targets_with_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            checker = CppcheckChecker()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[tmpdir_path],
                enabled_domains=[],
            )
            targets = checker._get_targets(context)
            assert str(tmpdir_path) in targets

    def test_get_targets_with_cpp_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cpp_file = tmpdir_path / "test.cpp"
            cpp_file.write_text("int main() {}")
            checker = CppcheckChecker()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[cpp_file],
                enabled_domains=[],
            )
            targets = checker._get_targets(context)
            assert str(cpp_file) in targets

    def test_get_targets_filters_non_cpp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            py_file = tmpdir_path / "test.py"
            py_file.write_text("x = 1")
            checker = CppcheckChecker()
            context = ScanContext(
                project_root=tmpdir_path,
                paths=[py_file],
                enabled_domains=[],
            )
            targets = checker._get_targets(context)
            assert targets == []
