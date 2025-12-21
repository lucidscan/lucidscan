"""Tests for lucidscan.config.ignore module."""

from __future__ import annotations

from pathlib import Path

import pytest

from lucidscan.config.ignore import (
    IgnorePatterns,
    find_lucidscanignore,
    load_ignore_patterns,
)


class TestIgnorePatterns:
    """Tests for IgnorePatterns class."""

    def test_simple_pattern_match(self) -> None:
        """Test basic glob pattern matching."""
        patterns = IgnorePatterns(["*.log", "temp/"])
        root = Path("/project")

        assert patterns.matches(Path("/project/debug.log"), root)
        assert patterns.matches(Path("/project/app.log"), root)
        assert not patterns.matches(Path("/project/src/main.py"), root)

    def test_double_star_glob(self) -> None:
        """Test ** recursive glob patterns."""
        patterns = IgnorePatterns(["**/test_*.py"])
        root = Path("/project")

        assert patterns.matches(Path("/project/test_foo.py"), root)
        assert patterns.matches(Path("/project/tests/test_bar.py"), root)
        assert patterns.matches(Path("/project/deep/nested/test_baz.py"), root)
        assert not patterns.matches(Path("/project/main.py"), root)

    def test_negation_pattern(self) -> None:
        """Test ! negation patterns to re-include files."""
        patterns = IgnorePatterns(["*.log", "!important.log"])
        root = Path("/project")

        assert patterns.matches(Path("/project/debug.log"), root)
        assert not patterns.matches(Path("/project/important.log"), root)

    def test_comments_ignored(self) -> None:
        """Test that # comments are ignored."""
        patterns = IgnorePatterns(
            [
                "# This is a comment",
                "*.log",
                "  # Indented comment",
            ]
        )
        root = Path("/project")

        assert patterns.matches(Path("/project/app.log"), root)
        exclude = patterns.get_exclude_patterns()
        assert "*.log" in exclude
        assert "# This is a comment" not in exclude
        assert "  # Indented comment" not in exclude

    def test_empty_lines_ignored(self) -> None:
        """Test that empty lines are ignored."""
        patterns = IgnorePatterns(["", "*.log", "  ", "temp/"])
        exclude = patterns.get_exclude_patterns()
        assert "" not in exclude
        assert "  " not in exclude
        assert len(exclude) == 2

    def test_directory_patterns(self) -> None:
        """Test patterns matching directories."""
        patterns = IgnorePatterns(["node_modules/", "vendor/**"])
        root = Path("/project")

        assert patterns.matches(Path("/project/node_modules/package.json"), root)
        assert patterns.matches(Path("/project/vendor/lib/file.js"), root)

    def test_relative_path_calculation(self) -> None:
        """Test that paths are correctly made relative to root."""
        patterns = IgnorePatterns(["src/*.tmp"])
        root = Path("/project")

        # Absolute path within root
        assert patterns.matches(Path("/project/src/file.tmp"), root)
        # Relative path
        assert patterns.matches(Path("src/test.tmp"), root)

    def test_get_exclude_patterns_returns_clean_list(self) -> None:
        """Test that get_exclude_patterns returns patterns without comments."""
        patterns = IgnorePatterns(
            [
                "# Comment",
                "*.log",
                "",
                "  ",
                "tests/**",
                "!tests/important.py",
            ]
        )
        exclude = patterns.get_exclude_patterns()

        assert exclude == ["*.log", "tests/**", "!tests/important.py"]

    def test_no_patterns_matches_nothing(self) -> None:
        """Test that empty patterns match nothing."""
        patterns = IgnorePatterns([])
        root = Path("/project")

        assert not patterns.matches(Path("/project/any/file.py"), root)
        assert patterns.get_exclude_patterns() == []


class TestIgnorePatternsFromFile:
    """Tests for IgnorePatterns.from_file class method."""

    def test_loads_from_file(self, tmp_path: Path) -> None:
        """Test loading patterns from a file."""
        ignore_file = tmp_path / ".lucidscanignore"
        ignore_file.write_text("*.log\ntemp/\n# Comment\n")

        patterns = IgnorePatterns.from_file(ignore_file)
        assert patterns is not None
        assert patterns.matches(Path(tmp_path / "debug.log"), tmp_path)

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Test that missing file returns None."""
        missing = tmp_path / "nonexistent"
        result = IgnorePatterns.from_file(missing)
        assert result is None

    def test_handles_empty_file(self, tmp_path: Path) -> None:
        """Test loading an empty file."""
        ignore_file = tmp_path / ".lucidscanignore"
        ignore_file.write_text("")

        patterns = IgnorePatterns.from_file(ignore_file)
        assert patterns is not None
        assert patterns.get_exclude_patterns() == []


class TestIgnorePatternsMerge:
    """Tests for IgnorePatterns.merge class method."""

    def test_merges_multiple_patterns(self) -> None:
        """Test merging multiple IgnorePatterns instances."""
        p1 = IgnorePatterns(["*.log"], source="file")
        p2 = IgnorePatterns(["tests/**"], source="config")

        merged = IgnorePatterns.merge(p1, p2)
        exclude = merged.get_exclude_patterns()

        assert "*.log" in exclude
        assert "tests/**" in exclude

    def test_handles_none_values(self) -> None:
        """Test that None values are skipped during merge."""
        p1 = IgnorePatterns(["*.log"], source="file")

        merged = IgnorePatterns.merge(None, p1, None)
        exclude = merged.get_exclude_patterns()

        assert exclude == ["*.log"]

    def test_empty_merge(self) -> None:
        """Test merging with no patterns."""
        merged = IgnorePatterns.merge(None, None)
        assert merged.get_exclude_patterns() == []


class TestFindLucidscanignore:
    """Tests for find_lucidscanignore function."""

    def test_finds_lucidscanignore(self, tmp_path: Path) -> None:
        """Test finding .lucidscanignore in project root."""
        ignore_file = tmp_path / ".lucidscanignore"
        ignore_file.write_text("*.log\n")

        result = find_lucidscanignore(tmp_path)
        assert result == ignore_file

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Test that missing file returns None."""
        result = find_lucidscanignore(tmp_path)
        assert result is None


class TestLoadIgnorePatterns:
    """Tests for load_ignore_patterns function."""

    def test_loads_from_file(self, tmp_path: Path) -> None:
        """Test loading patterns from .lucidscanignore file."""
        ignore_file = tmp_path / ".lucidscanignore"
        ignore_file.write_text("*.log\ntemp/\n")

        patterns = load_ignore_patterns(tmp_path, [])
        exclude = patterns.get_exclude_patterns()

        assert "*.log" in exclude
        assert "temp/" in exclude

    def test_loads_from_config(self, tmp_path: Path) -> None:
        """Test loading patterns from config list."""
        patterns = load_ignore_patterns(tmp_path, ["tests/**", "*.md"])
        exclude = patterns.get_exclude_patterns()

        assert "tests/**" in exclude
        assert "*.md" in exclude

    def test_merges_file_and_config(self, tmp_path: Path) -> None:
        """Test merging patterns from both file and config."""
        ignore_file = tmp_path / ".lucidscanignore"
        ignore_file.write_text("*.log\n")

        patterns = load_ignore_patterns(tmp_path, ["tests/**"])
        exclude = patterns.get_exclude_patterns()

        assert "*.log" in exclude
        assert "tests/**" in exclude

    def test_empty_sources(self, tmp_path: Path) -> None:
        """Test with no file and empty config."""
        patterns = load_ignore_patterns(tmp_path, [])
        assert patterns.get_exclude_patterns() == []

    def test_config_patterns_after_file(self, tmp_path: Path) -> None:
        """Test that config patterns come after file patterns in merge."""
        ignore_file = tmp_path / ".lucidscanignore"
        ignore_file.write_text("*.log\n")

        patterns = load_ignore_patterns(tmp_path, ["vendor/"])
        exclude = patterns.get_exclude_patterns()

        # Both patterns present
        assert "*.log" in exclude
        assert "vendor/" in exclude
