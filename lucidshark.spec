# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for LucidShark.

This creates a single-file executable that bundles all dependencies.
Usage: pyinstaller lucidshark.spec
"""

import sys
from pathlib import Path

exe_name = 'lucidshark'

# Path to the source package
src_path = Path('src')

a = Analysis(
    ['src/lucidshark/cli/__init__.py'],
    pathex=[str(src_path)],
    binaries=[],
    datas=[
        ('docs/help.md', 'lucidshark/data'),  # Use actual file instead of symlink for cross-platform compatibility
        ('src/lucidshark/data/pmd-ruleset.xml', 'lucidshark/data'),
        ('src/lucidshark/data/checkstyle-google.xml', 'lucidshark/data'),
        ('src/lucidshark/data/spotbugs-exclude.xml', 'lucidshark/data'),
    ],
    hiddenimports=[
        # Core modules
        'lucidshark',
        'lucidshark.cli',
        'lucidshark.cli.runner',
        'lucidshark.cli.arguments',
        'lucidshark.cli.commands',
        'lucidshark.core',
        'lucidshark.config',
        'lucidshark.bootstrap',
        'lucidshark.detection',
        'lucidshark.generation',
        'lucidshark.mcp',
        'lucidshark.pipeline',
        'lucidshark.plugins.go_utils',
        # Plugin entry points - linters
        'lucidshark.plugins.linters.ruff',
        'lucidshark.plugins.linters.eslint',
        'lucidshark.plugins.linters.biome',
        'lucidshark.plugins.linters.checkstyle',
        'lucidshark.plugins.linters.clippy',
        'lucidshark.plugins.linters.pmd',
        'lucidshark.plugins.linters.golangci_lint',
        'lucidshark.plugins.linters.ktlint',
        'lucidshark.plugins.linters.dotnet_format',
        'lucidshark.plugins.linters.clang_tidy',
        'lucidshark.plugins.linters.scalafix',
        'lucidshark.plugins.linters.swiftlint',
        'lucidshark.plugins.linters.rubocop',
        # Plugin entry points - scanners
        'lucidshark.plugins.scanners.trivy',
        'lucidshark.plugins.scanners.opengrep',
        'lucidshark.plugins.scanners.checkov',
        'lucidshark.plugins.scanners.gosec',
        # Plugin entry points - reporters
        'lucidshark.plugins.reporters.ai_reporter',
        'lucidshark.plugins.reporters.json_reporter',
        'lucidshark.plugins.reporters.sarif_reporter',
        'lucidshark.plugins.reporters.summary_reporter',
        'lucidshark.plugins.reporters.table_reporter',
        # Plugin entry points - type checkers
        'lucidshark.plugins.type_checkers.mypy',
        'lucidshark.plugins.type_checkers.pyright',
        'lucidshark.plugins.type_checkers.typescript',
        'lucidshark.plugins.type_checkers.spotbugs',
        'lucidshark.plugins.type_checkers.cargo_check',
        'lucidshark.plugins.type_checkers.go_vet',
        'lucidshark.plugins.type_checkers.detekt',
        'lucidshark.plugins.type_checkers.dotnet_build',
        'lucidshark.plugins.type_checkers.cppcheck',
        'lucidshark.plugins.type_checkers.scala_compile',
        'lucidshark.plugins.type_checkers.swift_compiler',
        'lucidshark.plugins.type_checkers.sorbet',
        # Plugin entry points - test runners
        'lucidshark.plugins.test_runners.pytest',
        'lucidshark.plugins.test_runners.jest',
        'lucidshark.plugins.test_runners.karma',
        'lucidshark.plugins.test_runners.playwright',
        'lucidshark.plugins.test_runners.maven',
        'lucidshark.plugins.test_runners.cargo',
        'lucidshark.plugins.test_runners.vitest',
        'lucidshark.plugins.test_runners.go_test',
        'lucidshark.plugins.test_runners.mocha',
        'lucidshark.plugins.test_runners.dotnet_test',
        'lucidshark.plugins.test_runners.ctest',
        'lucidshark.plugins.test_runners.sbt',
        'lucidshark.plugins.test_runners.swift_test',
        'lucidshark.plugins.test_runners.rspec',
        # Plugin entry points - coverage
        'lucidshark.plugins.coverage.coverage_py',
        'lucidshark.plugins.coverage.istanbul',
        'lucidshark.plugins.coverage.jacoco',
        'lucidshark.plugins.coverage.tarpaulin',
        'lucidshark.plugins.coverage.vitest',
        'lucidshark.plugins.coverage.go_cover',
        'lucidshark.plugins.coverage.dotnet_coverage',
        'lucidshark.plugins.coverage.gcov',
        'lucidshark.plugins.coverage.lcov',
        'lucidshark.plugins.coverage.scoverage',
        'lucidshark.plugins.coverage.swift_coverage',
        'lucidshark.plugins.coverage.simplecov',
        # Plugin entry points - duplication
        'lucidshark.plugins.duplication.duplo',
        # Plugin entry points - formatters
        'lucidshark.plugins.formatters.ruff_format',
        'lucidshark.plugins.formatters.prettier',
        'lucidshark.plugins.formatters.rustfmt',
        'lucidshark.plugins.formatters.gofmt',
        'lucidshark.plugins.formatters.ktlint_format',
        'lucidshark.plugins.formatters.dotnet_format',
        'lucidshark.plugins.formatters.clang_format',
        'lucidshark.plugins.formatters.scalafmt',
        'lucidshark.plugins.formatters.swiftformat',
        'lucidshark.plugins.formatters.rubocop_format',
        # Dependencies that may need explicit import
        'yaml',
        'pathspec',
        'questionary',
        'jinja2',
        'watchdog',
        'defusedxml',
        'tomli',
        'mcp',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test modules
        'pytest',
        'pytest_asyncio',
        '_pytest',
        # Exclude dev tools
        'mypy',
        'pyright',
        # Exclude unused stdlib modules to reduce size
        'tkinter',
        'unittest',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
