# LucidScan Roadmap

> **Vision**: The trust layer for AI-assisted development

LucidScan unifies code quality tools (linting, type checking, security, testing, coverage) into a single pipeline that auto-configures for any project and integrates with AI coding tools like Claude Code and Cursor.

---

## Roadmap Overview

```
         v0.1.x                v0.2 ✅              v0.3 ✅              v0.4 ✅              v0.5 ✅             v1.0
           │                    │                   │                   │                   │                   │
    ───────●────────────────────●───────────────────●───────────────────●───────────────────●───────────────────●───────
           │                    │                   │                   │                   │                   │
        Complete            Complete            Complete            Complete            Complete          Production
                                                                                                               Ready
    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
    │ Security     │    │ ✅ init cmd  │    │ ✅ ESLint    │    │ ✅ pytest    │    │ ✅ MCP server│    │ Docs         │
    │ scanning     │    │ ✅ Detection │    │ ✅ Biome     │    │ ✅ Jest      │    │ ✅ Watcher   │    │ Performance  │
    │ (Trivy,      │    │ ✅ CI gen    │    │ ✅ mypy      │    │ ✅ coverage  │    │ ✅ AI instruct│    │ Stability    │
    │ OpenGrep,    │    │ ✅ Ruff      │    │ ✅ pyright   │    │ ✅ istanbul  │    │ ✅ format    │    │              │
    │ Checkov)     │    │ ✅ Plugins   │    │ ✅ tsc       │    │ ✅ threshold │    │              │    │              │
    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

---

## Current State (v0.5.0)

LucidScan is now a complete code quality platform with AI integration:

| Component | Status |
|-----------|--------|
| CLI framework (subcommands) | ✅ Complete |
| Plugin system (unified `plugins/` package) | ✅ Complete |
| Pipeline orchestrator | ✅ Complete |
| Configuration system | ✅ Complete |
| Security scanners | ✅ Trivy, OpenGrep, Checkov |
| Reporters | ✅ JSON, Table, SARIF, Summary |
| AI enricher | ✅ OpenAI, Anthropic, Ollama |
| `lucidscan init` command | ✅ Complete |
| Codebase detection | ✅ Complete |
| CI config generation | ✅ GitHub, GitLab, Bitbucket |
| Project-local tool storage | ✅ `.lucidscan/` folder |
| **Linter plugins** | ✅ Ruff, ESLint, Biome, Checkstyle |
| **Type checker plugins** | ✅ mypy, pyright, TypeScript |
| **Test runner plugins** | ✅ pytest, Jest |
| **Coverage plugins** | ✅ coverage.py, Istanbul |
| **MCP server** | ✅ Claude Code, Cursor integration |
| **File watcher** | ✅ Real-time incremental checking |
| **Language support** | ✅ Python, JavaScript, TypeScript, Java |

**What works today:**
```bash
lucidscan init                       # Interactive project setup
lucidscan scan --sca --sast --iac    # Security scanning
lucidscan scan --lint                # Linting (Ruff, ESLint, Biome, Checkstyle)
lucidscan scan --lint --fix          # Auto-fix linting issues
lucidscan scan --type-check          # Type checking (mypy, pyright, tsc)
lucidscan scan --test                # Run tests (pytest, Jest)
lucidscan scan --coverage            # Coverage analysis
lucidscan scan --all                 # Run everything
lucidscan scan --format sarif        # SARIF output for GitHub
lucidscan scan --ai                  # AI-powered explanations
lucidscan status                     # Show plugin status
lucidscan serve --mcp                # MCP server for AI tools
lucidscan serve --watch              # File watcher mode
```

---

## v0.2 — Foundation ✅ COMPLETE

**Theme**: Smart initialization and expanded architecture

### Key Deliverables

| Feature | Status | Description |
|---------|--------|-------------|
| **`lucidscan init`** | ✅ | Interactive project setup that detects your stack and generates config |
| **Codebase detection** | ✅ | Auto-detect languages, frameworks, existing tools, CI systems |
| **CI config generation** | ✅ | Generate GitHub Actions, GitLab CI, Bitbucket Pipelines configs |
| **Plugin restructure** | ✅ | Unified `plugins/` package with scanners, linters, reporters, enrichers |
| **CLI subcommands** | ✅ | `lucidscan init`, `lucidscan scan`, `lucidscan status` |
| **Project-local tools** | ✅ | Tools downloaded to `.lucidscan/` in project root |
| **Ruff linter** | ✅ | First linter plugin with auto-fix support |

### User Experience

```bash
$ lucidscan init

Analyzing project...

Detected:
  Languages:    Python 3.11
  Frameworks:   FastAPI
  Tools:        pytest, ruff (pyproject.toml)
  CI:           GitHub Actions

? Linter         [Ruff] ✓
? Type checker   [mypy]
? Security       [Trivy + OpenGrep]
? CI platform    [GitHub Actions] ✓

Generated:
  ✓ .lucidscan.yml
  ✓ .github/workflows/lucidscan.yml
```

### Success Criteria

- [x] `lucidscan init` works for Python and JavaScript projects
- [x] CI config generation for GitHub, GitLab, Bitbucket
- [x] Existing security scanning continues to work
- [x] Plugin architecture unified under `plugins/` package
- [x] Ruff linter with `--lint` and `--fix` flags

---

## v0.3 — Code Quality ✅ COMPLETE

**Theme**: Expanded linting and type checking

### Key Deliverables

| Feature | Status | Description |
|---------|--------|-------------|
| **Ruff linter** | ✅ | Python linting with auto-fix |
| **ESLint plugin** | ✅ | JavaScript/TypeScript linting |
| **Biome plugin** | ✅ | Fast JS/TS linting alternative |
| **Checkstyle plugin** | ✅ | Java linting |
| **mypy plugin** | ✅ | Python type checking |
| **pyright plugin** | ✅ | Alternative Python type checker |
| **TypeScript plugin** | ✅ | TypeScript type checking via tsc |
| **`--type-check` flag** | ✅ | CLI flag for type checking |
| **Java support** | ✅ | Language detection and Checkstyle linting |
| **Unified output** | ✅ | All issues in same UnifiedIssue format |

### User Experience

```bash
$ lucidscan scan --type-check --lint

Linting ━━━━━━━━━━━━━━━━━━━━ 100%
Type Checking ━━━━━━━━━━━━━━ 100%

┌─────────────────────────────────────────────────────────┐
│ Summary                                                 │
├─────────────────────────────────────────────────────────┤
│ Linting:       3 errors, 12 warnings (8 fixable)        │
│ Type Checking: 1 error                                  │
└─────────────────────────────────────────────────────────┘

$ lucidscan scan --lint --fix

Fixed 8 linting issues in 4 files.
```

### Success Criteria

- [x] Ruff and ESLint plugins working
- [x] Biome and Checkstyle plugins working
- [x] mypy, pyright, and TypeScript plugins working
- [x] `--fix` mode applies auto-fixes
- [x] Unified issue format across all tools
- [x] Java language detection and linting

---

## v0.4 — Full Pipeline ✅ COMPLETE

**Theme**: Testing and coverage

### Key Deliverables

| Feature | Status | Description |
|---------|--------|-------------|
| **pytest plugin** | ✅ | Python test runner with failure reporting |
| **Jest plugin** | ✅ | JavaScript/TypeScript test runner |
| **coverage.py plugin** | ✅ | Python coverage measurement |
| **Istanbul plugin** | ✅ | JavaScript/TypeScript coverage |
| **Coverage thresholds** | ✅ | `--coverage-threshold` flag |
| **Complete pipeline** | ✅ | All domains in one command |

### User Experience

```bash
$ lucidscan scan --test --coverage

Testing ━━━━━━━━━━━━━━━━━━━━ 100%
Coverage ━━━━━━━━━━━━━━━━━━━ 100%

┌─────────────────────────────────────────────────────────┐
│ Summary                                                 │
├─────────────────────────────────────────────────────────┤
│ Testing:       42 passed, 0 failed                      │
│ Coverage:      87% (threshold: 80%) ✓                   │
└─────────────────────────────────────────────────────────┘
```

### Success Criteria

- [x] pytest and Jest plugins working
- [x] Coverage threshold enforcement
- [x] Complete pipeline execution
- [x] Python and JavaScript projects fully supported

---

## v0.5 — AI Integration ✅ COMPLETE

**Theme**: MCP server and AI feedback loop

### Key Deliverables

| Feature | Status | Description |
|---------|--------|-------------|
| **MCP server** | ✅ | `lucidscan serve --mcp` for Claude Code and Cursor |
| **File watcher** | ✅ | `lucidscan serve --watch` for real-time checking |
| **AI instruction format** | ✅ | Structured fix instructions with priority, action, fix_steps |
| **MCP tools** | ✅ | scan, check_file, get_fix_instructions, apply_fix, get_status |

### User Experience

**Claude Code / Cursor integration:**

```json
{
  "mcpServers": {
    "lucidscan": {
      "command": "lucidscan",
      "args": ["serve", "--mcp"]
    }
  }
}
```

**AI receives structured instructions:**

```json
{
  "total_issues": 2,
  "blocking": true,
  "instructions": [
    {
      "priority": 1,
      "action": "FIX_SECURITY_HARDCODED_SECRET",
      "summary": "Hardcoded password in auth.py:23",
      "file": "src/auth.py",
      "line": 23,
      "problem": "Hardcoded password detected",
      "fix_steps": [
        "Import os module at the top of the file",
        "Replace the hardcoded password with os.environ.get('DB_PASSWORD')",
        "Add DB_PASSWORD to your .env file"
      ],
      "suggested_fix": "password = os.environ.get('DB_PASSWORD')"
    }
  ]
}
```

**File watcher mode:**

```bash
$ lucidscan serve --watch --debounce 500

Watching /path/to/project for changes...
[2025-01-08 12:34:56] File changed: src/main.py
[2025-01-08 12:34:57] 2 issues found
```

### Success Criteria

- [x] MCP server works with Claude Code
- [x] MCP server works with Cursor
- [x] File watcher mode functional
- [x] AI agents can receive and act on fix instructions

---

## v1.0 — Production Ready

**Theme**: Polish and stability

### Key Deliverables

| Feature | Description |
|---------|-------------|
| **Documentation** | Comprehensive user and developer guides |
| **Performance** | Incremental checking, caching, parallel execution |
| **Error handling** | Graceful degradation, clear error messages |
| **Distribution** | Updated PyPI package, Docker image, Homebrew |

### Success Criteria

- [ ] Complete documentation
- [ ] Performance optimized for large codebases
- [ ] Stable API (no breaking changes in 1.x)
- [ ] Production use by early adopters

---

## Future Considerations

Beyond v1.0, potential directions include:

| Direction | Description |
|-----------|-------------|
| **More languages** | Go, Rust, C# support |
| **VS Code extension** | Native IDE integration |
| **Team features** | Shared configurations, policy enforcement |
| **Custom rules** | User-defined linting and security rules |
| **Dashboard** | Optional web UI for visibility |

These are not committed — they depend on user feedback and adoption.

---

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2025-01 | v0.1.x | Security scanning foundation complete |
| 2025-01 | v0.2.0 | Foundation complete: init command, codebase detection, CI generation, plugin restructure, Ruff linter |
| 2025-01 | v0.3.0 | Code Quality complete: type checkers (mypy, pyright, tsc), linters (ESLint, Biome, Checkstyle), Java support |
| 2025-01 | v0.4.0 | Full Pipeline complete: test runners (pytest, Jest), coverage plugins (coverage.py, Istanbul), thresholds |
| 2025-01 | v0.5.0 | AI Integration complete: MCP server, file watcher, structured AI instructions |
| — | v1.0 | Production Ready (planned) |

---

## Contributing

See the [full specification](main.md) for detailed technical requirements.

To contribute:
1. Pick an item from the current milestone
2. Open an issue to discuss approach
3. Submit a PR

We welcome contributions for:
- New tool plugins
- Documentation improvements
- Bug fixes and testing
