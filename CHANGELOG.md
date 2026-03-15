# Changelog

All notable changes to LucidShark are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.4] - 2026-03-15

### Added
- **gosec** Go-specific SAST scanner plugin — inspects Go AST for 30+ security rule categories (SQL injection, command injection, weak crypto, hardcoded credentials, file permissions, SSRF, etc.)
  - Managed binary: auto-downloaded from GitHub releases on first use (version 2.21.4), cached at `.lucidshark/bin/gosec/{version}/`
  - CWE-mapped findings with confidence ratings (HIGH/MEDIUM/LOW)
  - Supports `// nosec` annotations for suppressing known false positives
  - Runs alongside OpenGrep for defense-in-depth (both produce SAST findings with tool-prefixed issue IDs)
  - Requires Go toolchain; auto-skips for non-Go projects
- **Mocha test runner plugin** for JavaScript/TypeScript — Mocha-native JSON reporter parsing with automatic NYC coverage wrapping
  - Stack trace location extraction for precise error reporting
  - Automatic config file detection (`.mocharc.json`, `.mocharc.js`, etc.)
  - 71 unit tests ensuring robust implementation
- Enhanced E2E test suites with comprehensive testing philosophy and quality standards
  - Critical testing philosophy section emphasizing bug finding over validation
  - Non-negotiable testing rules with detailed completion checklists (~40-60 verification questions per language)
  - Language-specific warnings for previously failed tests
  - Test completion certificates with pass/fail verdicts

### Changed
- Updated tagline from "Unified code quality pipeline" to "Unified code quality and security scanner" across all codebase locations
  - README.md, pyproject.toml, CLI help text, Claude skill descriptions, and documentation
  - Better reflects LucidShark's comprehensive capabilities across both code quality and security domains
- Bumped GitHub Actions dependencies: upload-artifact from v4 to v7, download-artifact from v4 to v8

### Fixed
- Linux binary builds now use manylinux_2_28 containers to lower glibc dependency from ~2.39 to 2.28 for broader compatibility
- Release workflow fixed to use actions/setup-python with --enable-shared required by PyInstaller
- Enabled domains by default when pipeline config section is None
- Track tools_executed in ScanContext for accurate scanners_used metadata
- Fixed test_apply_fix_exception to mock subprocess.run instead of removed _run_linting method
- Coverage data file path resolution improved
- Ruff format summary lines now skipped in output parsing
- All new plugins (gosec, Mocha, PMD, Checkstyle, SpotBugs) included in lucidshark.spec for binary distribution

## [0.6.0] - 2026-03-14

### Added
- **Full Go language support** — Go is now a fully supported language with dedicated tools across all quality domains
  - **golangci-lint** linter plugin — meta-linter with 100+ linters (staticcheck, gosimple, govet, errcheck, etc.)
  - **go vet** type checking plugin — compiler diagnostics + vet analyzers with `-json` output
  - **go test** test runner plugin — built-in Go test runner with `-json` output parsing
  - **go cover** coverage plugin — coverprofile format parsing
  - **gofmt** formatting plugin — canonical Go formatter
  - Go previously had: language detection, security scanning (Trivy/OpenGrep), duplication detection (Duplo)
  - Requires Go 1.16+ for `go vet -json` output; golangci-lint installed separately

## [0.5.57] - 2026-03-11

### Added
- **Strict mode** (enabled by default) — all configured tools must run successfully for a scan to pass
  - `settings.strict_mode: true` (default) — tool skips (not installed, missing prerequisites, execution failed) create HIGH severity issues
  - Per-tool `mandatory: true/false` option for fine-grained control when strict mode is disabled
  - Skipped tools now tracked with `ToolSkipInfo` and `SkipReason` (tool_not_installed, no_applicable_files, missing_prerequisite, execution_failed)
- **Testing failures now block scans** — when tests fail, a HIGH severity issue is created with pass/fail/skip/error counts
- **Skipped tools section** in reporter output — summary and AI reporters now show which tools were skipped and why, with suggestions for fixing
- **Domain status for all configured domains** — scan reports now show status for ALL configured domains, not just the ones that were executed
  - Domains that weren't executed show "Skipped" status (e.g., when running `--linting` only, other configured domains show as skipped)
  - New `enabled_domains` and `executed_domains` fields in `ScanMetadata` for tracking configuration vs execution
  - `get_all_configured_domains()` method added to `LucidSharkConfig` to list all domains configured in pipeline and scanners

### Changed
- **Breaking:** Coverage with 0/0 lines measured now fails instead of passing — previously returned 100% (vacuous pass), now returns 0% and fails any threshold
  - Added `has_data` property to `CoverageResult` for semantic clarity
  - `CoverageResult.passed` returns `False` when no coverage data is measured

### Fixed
- Missing bundled data files in PyInstaller binary distribution (pmd-ruleset.xml, checkstyle-google.xml, spotbugs-exclude.xml)

## [0.5.54] - 2026-03-10

### Added
- **SpotBugs type checker plugin** is now a managed tool — auto-downloaded from GitHub releases on first use, cached at `.lucidshark/bin/spotbugs/{version}/`
  - Managed binary: auto-downloaded on first use (version 4.9.8), no manual installation required
  - Requires Java runtime (any Java project already has one)
  - Analyzes compiled Java bytecode for bugs like null pointer dereferences, resource leaks, and concurrency issues
  - Bug categories: BAD_PRACTICE, CORRECTNESS, MT_CORRECTNESS, PERFORMANCE, SECURITY, STYLE, MALICIOUS_CODE
- **Checkstyle linter plugin** is now a managed tool — auto-downloaded from GitHub releases on first use, cached at `.lucidshark/bin/checkstyle/{version}/`
  - Default configuration: bundled Google Java Style (`checkstyle-google.xml`) with relaxed Javadoc rules
  - Custom config detection: `checkstyle.xml`, `.checkstyle.xml`, `config/checkstyle/checkstyle.xml`
  - Only requires Java runtime (any Java project already has one)
- **PMD linter plugin** for Java static analysis — complements Checkstyle with bug detection, design issues, performance, and complexity checks (296 rules across 8 categories)
  - Managed binary: auto-downloaded on first use from GitHub releases, cached at `.lucidshark/bin/pmd/{version}/`
  - Default ruleset: `rulesets/java/quickstart.xml` (118 rules); auto-detects custom configs (`pmd-ruleset.xml`, `pmd.xml`, `config/pmd/pmd.xml`, etc.)
  - JSON output parsing with PMD priority-to-severity mapping (1=Critical, 2=High, 3=Medium, 4=Low, 5=Info)
  - Uses `--file-list` for precise file targeting (respects gitignore patterns)
  - Requires Java runtime (any Java project already has one)
- PMD tool detection for existing project configurations
- `paths` option for `ignore_issues` — scope ignored issues to specific file paths with glob patterns

### Fixed
- Missing hiddenimports for PyInstaller binary distribution (PMD, Checkstyle, SpotBugs plugins)
- Cross-platform binary detection and replacement for stale binaries
- Flaky Checkstyle test on Linux CI

## [0.5.50] - 2026-03-08

### Added
- Vitest test runner plugin for JavaScript/TypeScript projects
- Vitest coverage plugin with Istanbul-compatible JSON report parsing (supports both `coverage-summary.json` and `coverage-final.json`)

### Changed
- **Breaking:** Removed `with_coverage` parameter from `run_tests()` — test runners that support coverage (pytest, jest, vitest, maven) now always include coverage instrumentation
- **Breaking:** Coverage plugins no longer run tests — removed `run_tests` parameter from `measure_coverage()`
- Coverage plugins return a `no_coverage_data` error issue when no existing coverage files are found, directing users to enable the testing domain
- Clean separation of concerns: testing domain produces coverage files, coverage domain only reads them

## [0.5.48] - 2025-03-07

### Added
- Incremental scanning improvements with better documentation
- `threshold_scope` configuration for linting, type checking, coverage, and duplication domains
- Support for applying thresholds to changed files only, full project, or both

### Fixed
- Threshold scope validation and loading in configuration
- Configuration examples across documentation
- Separated ignored issues from active issues in AI formatter output
- SpotBugs detection for all installation methods

## [0.5.46] - 2025-03-05

### Added
- `ignore_issues` configuration to acknowledge known issues without failing scans
- Strict tool validation before scans to catch misconfiguration early
- Pre-command support for coverage and other domains

### Fixed
- Missing plugins in PyInstaller spec for standalone binaries
- Ignored issues now clearly shown in all reporter outputs
- `init --force` preserves non-LucidShark hooks in VS Code settings.json

### Changed
- Init command now uses directive-first approach with MCP tools and PostToolUse hooks
- Duplo baseline tracking is now opt-in (default: false)
- Bumped Trivy to v0.69.2

## [0.5.41] - 2025-02-28

### Added
- MCP is now a required dependency (previously optional)
- AI-optimized output format (`--format ai`) for better Claude Code integration

### Changed
- Deduplicated AIReporter by delegating to InstructionFormatter
- Extracted shared AI formatting constants to reduce code duplication

## [0.5.40] - 2025-02-26

### Added
- `pre_command` support for all pipeline domains
- `command` and `post_command` unified across all domains
- Coverage domain now requires testing domain to be enabled

### Fixed
- Cargo test availability check improved
- Documentation synced with code behavior
- Always install to project root (removed global install option)

### Changed
- Bumped Duplo to v0.1.6

## [0.5.38] - 2025-02-24

### Added
- `test_command` and `post_test_command` options for custom test execution

### Fixed
- Global exclusion patterns now applied in Duplo git mode
- Duplication exclude patterns respected in git mode

### Changed
- Reduced code duplication in domain_runner and git modules

## [0.5.35] - 2025-02-22

### Added
- Git mode for Duplo with baseline tracking and caching
- Comprehensive common exclusions in autoconfigure output

### Fixed
- `help.md` bundled as package data so MCP `get_help` works in binaries
- CLAUDE.md now written to `.claude/CLAUDE.md` instead of project root
- Autoconfigure duplication defaults changed to 5% threshold, 7 min lines

## [0.5.31] - 2025-02-20

### Fixed
- GitHub URLs updated from lucidshark-code to toniantunovi

## [0.5.30] - 2025-02-18

### Added
- Full Rust language support (Clippy, cargo check, cargo test, Tarpaulin)
- Per-language reference documentation for all 15 supported languages
- Per-domain exclude patterns for all pipeline domains

### Removed
- Cursor IDE support (now exclusively focused on Claude Code)
- Presets system and CLI autoconfigure command (simplified configuration)

## [0.5.29] - 2025-02-15

### Added
- Devcontainer configuration for GitHub Codespaces
- SARIF reporter for GitHub Advanced Security integration
- Checkov scanner for Infrastructure-as-Code security scanning
- OpenGrep scanner for SAST (SemGrep-compatible rules)

### Fixed
- CI pipeline failures across Linux, macOS, and Windows
- Pyright type checking errors
- Security scan findings resolved

## [0.5.0] - 2025-02-01

### Added
- Plugin-based architecture with on-demand binary downloads
- Trivy scanner with SCA and container scanning
- Reporter plugin system (JSON, Table, AI, SARIF, Summary)
- Plugin discovery system

### Changed
- Major refactor to plugin-based architecture
- Switched to real PyPI for publishing

## [0.1.0] - 2025-01-15

### Added
- Initial release
- Core scanning pipeline with linting and type checking
- Python support (Ruff, mypy, Pyright)
- JavaScript/TypeScript support (ESLint, Biome, TypeScript)
- CLI with scan, init, validate, status, and doctor commands
- YAML configuration system
- CI/CD integration support

[0.6.4]: https://github.com/toniantunovi/lucidshark/compare/v0.6.0...v0.6.4
[0.5.57]: https://github.com/toniantunovi/lucidshark/compare/v0.5.54...v0.5.57
[0.5.54]: https://github.com/toniantunovi/lucidshark/compare/v0.5.50...v0.5.54
[0.5.50]: https://github.com/toniantunovi/lucidshark/compare/v0.5.48...v0.5.50
[0.5.48]: https://github.com/toniantunovi/lucidshark/compare/v0.5.46...v0.5.48
[0.5.46]: https://github.com/toniantunovi/lucidshark/compare/v0.5.41...v0.5.46
[0.5.41]: https://github.com/toniantunovi/lucidshark/compare/v0.5.40...v0.5.41
[0.5.40]: https://github.com/toniantunovi/lucidshark/compare/v0.5.38...v0.5.40
[0.5.38]: https://github.com/toniantunovi/lucidshark/compare/v0.5.35...v0.5.38
[0.5.35]: https://github.com/toniantunovi/lucidshark/compare/v0.5.31...v0.5.35
[0.5.31]: https://github.com/toniantunovi/lucidshark/compare/v0.5.30...v0.5.31
[0.5.30]: https://github.com/toniantunovi/lucidshark/compare/v0.5.29...v0.5.30
[0.5.29]: https://github.com/toniantunovi/lucidshark/compare/v0.5.0...v0.5.29
[0.5.0]: https://github.com/toniantunovi/lucidshark/compare/v0.1.0...v0.5.0
[0.1.0]: https://github.com/toniantunovi/lucidshark/releases/tag/v0.1.0
