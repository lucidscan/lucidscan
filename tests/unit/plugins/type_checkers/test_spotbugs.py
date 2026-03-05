"""Unit tests for SpotBugs type checker plugin."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from lucidshark.core.models import Severity, ToolDomain
from lucidshark.plugins.type_checkers.spotbugs import SpotBugsChecker


class TestSpotBugsChecker:
    """Tests for SpotBugsChecker class."""

    def test_name(self) -> None:
        """Test plugin name."""
        checker = SpotBugsChecker()
        assert checker.name == "spotbugs"

    def test_languages(self) -> None:
        """Test supported languages."""
        checker = SpotBugsChecker()
        assert checker.languages == ["java"]

    def test_domain(self) -> None:
        """Test domain is TYPE_CHECKING."""
        checker = SpotBugsChecker()
        assert checker.domain == ToolDomain.TYPE_CHECKING

    def test_supports_strict_mode(self) -> None:
        """Test strict mode support."""
        checker = SpotBugsChecker()
        assert checker.supports_strict_mode is True


class TestSpotBugsJavaDetection:
    """Tests for Java detection logic."""

    @patch("shutil.which")
    def test_check_java_available(self, mock_which) -> None:
        """Test Java detection when available."""
        mock_which.return_value = "/usr/bin/java"
        checker = SpotBugsChecker()
        java_path = checker._check_java_available()
        assert java_path == Path("/usr/bin/java")

    @patch("shutil.which")
    def test_check_java_not_available(self, mock_which) -> None:
        """Test Java detection when not available."""
        mock_which.return_value = None
        checker = SpotBugsChecker()
        java_path = checker._check_java_available()
        assert java_path is None

    @patch("shutil.which")
    def test_ensure_binary_no_java_raises(self, mock_which) -> None:
        """Test ensure_binary raises when Java not available."""
        mock_which.return_value = None
        checker = SpotBugsChecker()

        with pytest.raises(FileNotFoundError) as exc:
            checker.ensure_binary()

        assert "Java is not installed" in str(exc.value)


class TestSpotBugsClassDirectoryFinding:
    """Tests for finding compiled class directories."""

    def test_find_maven_class_directories(self) -> None:
        """Test finding Maven target/classes directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            target_classes = project_root / "target" / "classes"
            target_classes.mkdir(parents=True)

            checker = SpotBugsChecker()
            class_dirs = checker._find_class_directories(project_root)

            assert target_classes in class_dirs

    def test_find_gradle_class_directories(self) -> None:
        """Test finding Gradle build/classes directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            build_classes = project_root / "build" / "classes" / "java" / "main"
            build_classes.mkdir(parents=True)

            checker = SpotBugsChecker()
            class_dirs = checker._find_class_directories(project_root)

            assert build_classes in class_dirs

    def test_find_multi_module_class_directories(self) -> None:
        """Test finding class directories in multi-module project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            module_classes = project_root / "module-a" / "target" / "classes"
            module_classes.mkdir(parents=True)

            checker = SpotBugsChecker()
            class_dirs = checker._find_class_directories(project_root)

            assert module_classes in class_dirs

    def test_no_class_directories(self) -> None:
        """Test empty list when no class directories found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            checker = SpotBugsChecker()
            class_dirs = checker._find_class_directories(project_root)

            assert class_dirs == []


class TestSpotBugsSourceDirectoryFinding:
    """Tests for finding source directories."""

    def test_find_standard_source_directory(self) -> None:
        """Test finding src/main/java directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_main_java = project_root / "src" / "main" / "java"
            src_main_java.mkdir(parents=True)

            checker = SpotBugsChecker()
            source_dirs = checker._find_source_directories(project_root)

            assert src_main_java in source_dirs


class TestSpotBugsXmlParsing:
    """Tests for SpotBugs XML output parsing."""

    def test_parse_xml_with_bugs(self) -> None:
        """Test parsing SpotBugs XML output with bugs."""
        checker = SpotBugsChecker()

        xml_output = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection version="4.8.6" timestamp="1704067200000">
    <BugInstance type="NP_NULL_ON_SOME_PATH" priority="1" rank="5" category="CORRECTNESS">
        <ShortMessage>Possible null pointer dereference</ShortMessage>
        <LongMessage>Possible null pointer dereference of user in method processUser</LongMessage>
        <SourceLine classname="com.example.UserService" start="42" end="42"
                    sourcepath="com/example/UserService.java"/>
    </BugInstance>
    <BugInstance type="DM_STRING_VOID_CTOR" priority="2" rank="15" category="PERFORMANCE">
        <ShortMessage>String constructor creates unnecessary object</ShortMessage>
        <LongMessage>Method creates unnecessary String object</LongMessage>
        <SourceLine classname="com.example.Utils" start="15" end="15"
                    sourcepath="com/example/Utils.java"/>
    </BugInstance>
</BugCollection>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src_main_java = project_root / "src" / "main" / "java"
            src_main_java.mkdir(parents=True)

            issues = checker._parse_output(xml_output, project_root, [src_main_java])

            assert len(issues) == 2

            # First issue (high priority, low rank = HIGH severity)
            issue1 = issues[0]
            assert issue1.rule_id == "NP_NULL_ON_SOME_PATH"
            assert issue1.severity == Severity.HIGH
            assert issue1.domain == ToolDomain.TYPE_CHECKING
            assert issue1.source_tool == "spotbugs"
            assert issue1.line_start == 42

            # Second issue (medium priority, high rank = MEDIUM severity)
            issue2 = issues[1]
            assert issue2.rule_id == "DM_STRING_VOID_CTOR"
            assert issue2.severity == Severity.MEDIUM

    def test_parse_xml_no_bugs(self) -> None:
        """Test parsing SpotBugs XML output with no bugs."""
        checker = SpotBugsChecker()

        xml_output = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection version="4.8.6" timestamp="1704067200000">
</BugCollection>
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            issues = checker._parse_output(xml_output, project_root, [])

            assert len(issues) == 0

    def test_parse_empty_output(self) -> None:
        """Test parsing empty output."""
        checker = SpotBugsChecker()
        issues = checker._parse_output("", Path("/tmp"), [])
        assert len(issues) == 0

    def test_parse_no_xml_in_output(self) -> None:
        """Test parsing output without XML."""
        checker = SpotBugsChecker()
        issues = checker._parse_output("Some text without XML", Path("/tmp"), [])
        assert len(issues) == 0


class TestSpotBugsSeverityMapping:
    """Tests for priority/rank to severity mapping."""

    def test_priority_1_high_severity(self) -> None:
        """Test priority 1 maps to HIGH severity."""
        checker = SpotBugsChecker()

        xml_output = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection>
    <BugInstance type="TEST" priority="1" rank="10" category="CORRECTNESS">
        <LongMessage>Test message</LongMessage>
    </BugInstance>
</BugCollection>
        """

        issues = checker._parse_output(xml_output, Path("/tmp"), [])
        assert issues[0].severity == Severity.HIGH

    def test_priority_2_medium_severity(self) -> None:
        """Test priority 2 maps to MEDIUM severity."""
        checker = SpotBugsChecker()

        xml_output = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection>
    <BugInstance type="TEST" priority="2" rank="15" category="PERFORMANCE">
        <LongMessage>Test message</LongMessage>
    </BugInstance>
</BugCollection>
        """

        issues = checker._parse_output(xml_output, Path("/tmp"), [])
        assert issues[0].severity == Severity.MEDIUM

    def test_priority_3_low_severity(self) -> None:
        """Test priority 3 maps to LOW severity."""
        checker = SpotBugsChecker()

        xml_output = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection>
    <BugInstance type="TEST" priority="3" rank="18" category="STYLE">
        <LongMessage>Test message</LongMessage>
    </BugInstance>
</BugCollection>
        """

        issues = checker._parse_output(xml_output, Path("/tmp"), [])
        assert issues[0].severity == Severity.LOW

    def test_low_rank_upgrades_severity(self) -> None:
        """Test low rank (scary) upgrades severity to HIGH."""
        checker = SpotBugsChecker()

        # Priority 3 (LOW) but rank 3 (very scary) should upgrade to HIGH
        xml_output = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection>
    <BugInstance type="TEST" priority="3" rank="3" category="SECURITY">
        <LongMessage>Test message</LongMessage>
    </BugInstance>
</BugCollection>
        """

        issues = checker._parse_output(xml_output, Path("/tmp"), [])
        assert issues[0].severity == Severity.HIGH


class TestSpotBugsIssueIdGeneration:
    """Tests for deterministic issue ID generation."""

    def test_same_input_same_id(self) -> None:
        """Test same input produces same ID."""
        checker = SpotBugsChecker()

        id1 = checker._generate_issue_id("NP_NULL", "file.java", 42, "message")
        id2 = checker._generate_issue_id("NP_NULL", "file.java", 42, "message")

        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Test different input produces different ID."""
        checker = SpotBugsChecker()

        id1 = checker._generate_issue_id("NP_NULL", "file.java", 42, "message")
        id2 = checker._generate_issue_id("NP_NULL", "other.java", 42, "message")

        assert id1 != id2

    def test_id_format(self) -> None:
        """Test ID format starts with spotbugs-."""
        checker = SpotBugsChecker()

        issue_id = checker._generate_issue_id("NP_NULL", "file.java", 42, "msg")

        assert issue_id.startswith("spotbugs-NP_NULL-")


class TestSpotBugsBinaryDetection:
    """Tests for SpotBugs binary/installation detection."""

    def test_find_spotbugs_dir_from_valid_jar(self) -> None:
        """Test finding SpotBugs dir from a valid jar path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            lib_dir = base_dir / "lib"
            lib_dir.mkdir()
            jar_path = lib_dir / "spotbugs.jar"
            jar_path.touch()

            checker = SpotBugsChecker()
            result = checker._find_spotbugs_dir_from_jar(jar_path)

            assert result == base_dir

    def test_find_spotbugs_dir_from_invalid_jar_name(self) -> None:
        """Test returns None for jar with wrong name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            lib_dir = base_dir / "lib"
            lib_dir.mkdir()
            jar_path = lib_dir / "other.jar"
            jar_path.touch()

            checker = SpotBugsChecker()
            result = checker._find_spotbugs_dir_from_jar(jar_path)

            assert result is None

    def test_find_spotbugs_dir_from_nonexistent_jar(self) -> None:
        """Test returns None for non-existent jar."""
        checker = SpotBugsChecker()
        result = checker._find_spotbugs_dir_from_jar(Path("/nonexistent/spotbugs.jar"))
        assert result is None

    def test_search_standard_layout(self) -> None:
        """Test searching in standard layout (lib/spotbugs.jar)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            lib_dir = base_dir / "lib"
            lib_dir.mkdir()
            (lib_dir / "spotbugs.jar").touch()

            checker = SpotBugsChecker()
            result = checker._search_for_spotbugs_jar(base_dir)

            assert result == base_dir

    def test_search_homebrew_libexec_layout(self) -> None:
        """Test searching in Homebrew layout (libexec/lib/spotbugs.jar)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            libexec_lib = base_dir / "libexec" / "lib"
            libexec_lib.mkdir(parents=True)
            (libexec_lib / "spotbugs.jar").touch()

            checker = SpotBugsChecker()
            result = checker._search_for_spotbugs_jar(base_dir)

            assert result == base_dir / "libexec"

    def test_search_from_bin_directory(self) -> None:
        """Test searching from bin directory finds sibling lib."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            bin_dir = base_dir / "bin"
            bin_dir.mkdir()
            lib_dir = base_dir / "lib"
            lib_dir.mkdir()
            (lib_dir / "spotbugs.jar").touch()

            checker = SpotBugsChecker()
            # Search from bin directory, should find ../lib/spotbugs.jar
            result = checker._search_for_spotbugs_jar(bin_dir)

            assert result == base_dir

    def test_search_homebrew_from_bin_directory(self) -> None:
        """Test searching from Homebrew bin finds libexec/lib."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate Homebrew: base/bin/spotbugs, base/libexec/lib/spotbugs.jar
            base_dir = Path(tmpdir)
            bin_dir = base_dir / "bin"
            bin_dir.mkdir()
            libexec_lib = base_dir / "libexec" / "lib"
            libexec_lib.mkdir(parents=True)
            (libexec_lib / "spotbugs.jar").touch()

            checker = SpotBugsChecker()
            result = checker._search_for_spotbugs_jar(bin_dir)

            assert result == base_dir / "libexec"

    def test_search_share_layout(self) -> None:
        """Test searching in Linux share layout (share/spotbugs/lib/)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            share_lib = base_dir / "share" / "spotbugs" / "lib"
            share_lib.mkdir(parents=True)
            (share_lib / "spotbugs.jar").touch()

            checker = SpotBugsChecker()
            result = checker._search_for_spotbugs_jar(base_dir)

            assert result == base_dir / "share" / "spotbugs"

    def test_search_returns_none_when_not_found(self) -> None:
        """Test returns None when spotbugs.jar not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            checker = SpotBugsChecker()
            result = checker._search_for_spotbugs_jar(base_dir)

            assert result is None

    @patch("shutil.which")
    def test_ensure_binary_via_spotbugs_home(self, mock_which) -> None:
        """Test ensure_binary finds SpotBugs via SPOTBUGS_HOME."""
        mock_which.side_effect = lambda cmd: "/usr/bin/java" if cmd == "java" else None

        with tempfile.TemporaryDirectory() as tmpdir:
            spotbugs_dir = Path(tmpdir)
            lib_dir = spotbugs_dir / "lib"
            lib_dir.mkdir()
            (lib_dir / "spotbugs.jar").touch()

            checker = SpotBugsChecker()
            with patch.dict("os.environ", {"SPOTBUGS_HOME": str(spotbugs_dir)}):
                result = checker.ensure_binary()

            assert result == spotbugs_dir

    @patch("shutil.which")
    def test_ensure_binary_via_path_standard_layout(self, mock_which) -> None:
        """Test ensure_binary finds SpotBugs via PATH (standard layout)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spotbugs_dir = Path(tmpdir)
            bin_dir = spotbugs_dir / "bin"
            bin_dir.mkdir()
            spotbugs_script = bin_dir / "spotbugs"
            spotbugs_script.touch()
            lib_dir = spotbugs_dir / "lib"
            lib_dir.mkdir()
            (lib_dir / "spotbugs.jar").touch()

            def which_side_effect(cmd: str):
                if cmd == "java":
                    return "/usr/bin/java"
                if cmd == "spotbugs":
                    return str(spotbugs_script)
                return None

            mock_which.side_effect = which_side_effect

            checker = SpotBugsChecker()
            with patch.dict("os.environ", {}, clear=False):
                # Remove SPOTBUGS_HOME if set
                import os
                env_backup = os.environ.pop("SPOTBUGS_HOME", None)
                try:
                    result = checker.ensure_binary()
                finally:
                    if env_backup:
                        os.environ["SPOTBUGS_HOME"] = env_backup

            assert result == spotbugs_dir

    @patch("shutil.which")
    def test_ensure_binary_via_path_homebrew_layout(self, mock_which) -> None:
        """Test ensure_binary finds SpotBugs via PATH (Homebrew layout)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spotbugs_dir = Path(tmpdir)
            bin_dir = spotbugs_dir / "bin"
            bin_dir.mkdir()
            spotbugs_script = bin_dir / "spotbugs"
            spotbugs_script.touch()
            # Homebrew layout: libexec/lib/spotbugs.jar
            libexec_lib = spotbugs_dir / "libexec" / "lib"
            libexec_lib.mkdir(parents=True)
            (libexec_lib / "spotbugs.jar").touch()

            def which_side_effect(cmd: str):
                if cmd == "java":
                    return "/usr/bin/java"
                if cmd == "spotbugs":
                    return str(spotbugs_script)
                return None

            mock_which.side_effect = which_side_effect

            checker = SpotBugsChecker()
            with patch.dict("os.environ", {}, clear=False):
                import os
                env_backup = os.environ.pop("SPOTBUGS_HOME", None)
                try:
                    result = checker.ensure_binary()
                finally:
                    if env_backup:
                        os.environ["SPOTBUGS_HOME"] = env_backup

            assert result == spotbugs_dir / "libexec"

    @patch("lucidshark.plugins.type_checkers.spotbugs.shutil.which")
    def test_ensure_binary_raises_when_not_found(self, mock_which) -> None:
        """Test ensure_binary raises FileNotFoundError when not found."""
        mock_which.side_effect = lambda cmd: "/usr/bin/java" if cmd == "java" else None

        checker = SpotBugsChecker()

        # Patch _search_for_spotbugs_jar to return None for all calls
        # This simulates an environment where SpotBugs is not installed anywhere
        with patch.object(checker, "_search_for_spotbugs_jar", return_value=None):
            with patch.dict("os.environ", {}, clear=False):
                import os
                env_backup = os.environ.pop("SPOTBUGS_HOME", None)
                try:
                    # Also patch Path.exists for the direct jar checks in common paths
                    original_exists = Path.exists

                    def mock_exists(self):
                        # Return False for spotbugs.jar paths
                        if "spotbugs.jar" in str(self):
                            return False
                        return original_exists(self)

                    with patch.object(Path, "exists", mock_exists):
                        with pytest.raises(FileNotFoundError) as exc:
                            checker.ensure_binary()
                        assert "SpotBugs is not installed" in str(exc.value)
                finally:
                    if env_backup:
                        os.environ["SPOTBUGS_HOME"] = env_backup
