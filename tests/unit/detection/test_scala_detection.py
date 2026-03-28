"""Tests for Scala language detection enhancements."""

from __future__ import annotations

from pathlib import Path

from lucidshark.detection.languages import (
    EXTENSION_MAP,
    MARKER_FILES,
    _detect_scala_version,
    _detect_version,
    detect_languages,
)


class TestScalaExtensionMap:
    """Tests for Scala file extension mapping."""

    def test_scala_extension(self) -> None:
        assert EXTENSION_MAP[".scala"] == "scala"

    def test_sc_extension(self) -> None:
        assert EXTENSION_MAP[".sc"] == "scala"


class TestScalaMarkerFiles:
    """Tests for Scala marker file detection."""

    def test_build_sbt_is_marker(self) -> None:
        assert "build.sbt" in MARKER_FILES["scala"]


class TestDetectScalaByExtension:
    """Tests for detecting Scala by file extension."""

    def test_detect_scala_by_extension(self, tmp_path: Path) -> None:
        (tmp_path / "App.scala").write_text("object App")
        (tmp_path / "Utils.scala").write_text("object Utils")

        languages = detect_languages(tmp_path)
        scala_lang = next((lang for lang in languages if lang.name == "scala"), None)
        assert scala_lang is not None
        assert scala_lang.file_count == 2

    def test_detect_scala_by_sc_extension(self, tmp_path: Path) -> None:
        (tmp_path / "script.sc").write_text("println('hello')")

        languages = detect_languages(tmp_path)
        scala_lang = next((lang for lang in languages if lang.name == "scala"), None)
        assert scala_lang is not None
        assert scala_lang.file_count == 1

    def test_detect_scala_by_marker(self, tmp_path: Path) -> None:
        (tmp_path / "build.sbt").write_text('scalaVersion := "3.3.1"')

        languages = detect_languages(tmp_path)
        scala_lang = next((lang for lang in languages if lang.name == "scala"), None)
        assert scala_lang is not None


class TestDetectScalaVersion:
    """Tests for _detect_scala_version function."""

    def test_from_build_sbt_scala3(self, tmp_path: Path) -> None:
        (tmp_path / "build.sbt").write_text('scalaVersion := "3.3.1"')
        version = _detect_scala_version(tmp_path)
        assert version == "3.3.1"

    def test_from_build_sbt_scala2(self, tmp_path: Path) -> None:
        (tmp_path / "build.sbt").write_text('scalaVersion := "2.13.12"')
        version = _detect_scala_version(tmp_path)
        assert version == "2.13.12"

    def test_from_build_sbt_this_build(self, tmp_path: Path) -> None:
        (tmp_path / "build.sbt").write_text('ThisBuild / scalaVersion := "3.4.0"')
        version = _detect_scala_version(tmp_path)
        assert version == "3.4.0"

    def test_from_build_sbt_single_quotes(self, tmp_path: Path) -> None:
        (tmp_path / "build.sbt").write_text("scalaVersion := '2.12.18'")
        version = _detect_scala_version(tmp_path)
        assert version == "2.12.18"

    def test_from_scala_version_file(self, tmp_path: Path) -> None:
        (tmp_path / ".scala-version").write_text("3.3.1")
        version = _detect_scala_version(tmp_path)
        assert version == "3.3.1"

    def test_no_version_found(self, tmp_path: Path) -> None:
        version = _detect_scala_version(tmp_path)
        assert version is None

    def test_version_detection_dispatch(self, tmp_path: Path) -> None:
        (tmp_path / "build.sbt").write_text('scalaVersion := "3.3.1"')
        version = _detect_version("scala", tmp_path)
        assert version == "3.3.1"

    def test_detect_languages_includes_version(self, tmp_path: Path) -> None:
        (tmp_path / "build.sbt").write_text('scalaVersion := "3.3.1"')
        (tmp_path / "App.scala").write_text("object App")

        languages = detect_languages(tmp_path)
        scala_lang = next((lang for lang in languages if lang.name == "scala"), None)
        assert scala_lang is not None
        assert scala_lang.version == "3.3.1"
