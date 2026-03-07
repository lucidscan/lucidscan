# Changelog

All notable changes to LucidShark are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
