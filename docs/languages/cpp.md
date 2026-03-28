# C++

**Support tier: Full**

C++ projects are fully supported with linting, type checking, testing, coverage, formatting, security scanning, and duplication detection.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.h`, `.hh`, `.hxx` |
| **Marker files** | `CMakeLists.txt` |

## Tools by Domain

| Domain | Tool | Notes |
|--------|------|-------|
| **Linting** | clang-tidy | Clang-based C++ linter with 300+ checks (bugprone, modernize, performance, etc.) |
| **Formatting** | clang-format | Clang-based code formatter; supports multiple styles (LLVM, Google, Chromium, etc.) |
| **Type Checking** | cppcheck | Static analysis for bugs, undefined behavior, and dangerous constructs |
| **Testing** | CTest | CMake test driver; supports Google Test, Catch2, and any CMake-registered test |
| **Coverage** | lcov | Parses lcov `.info` files from gcov/lcov coverage instrumentation |
| **Security (SAST)** | OpenGrep | Language-agnostic vulnerability rules (also covers C++) |
| **Security (SCA)** | Trivy | Scans package manifests for known vulnerabilities |
| **Duplication** | Duplo | Scans `.cpp`, `.cc`, `.cxx`, `.hpp` files |

## Linting

**Tool: [clang-tidy](https://clang.llvm.org/extra/clang-tidy/)**

clang-tidy is a clang-based C++ linter tool that provides diagnostics and fixes for typical programming errors, style violations, interface misuse, and bugs detectable via static analysis.

- Supports auto-fix via `clang-tidy --fix`
- Uses `compile_commands.json` from the CMake build directory when available
- 300+ checks organized in categories: bugprone, cert, clang-analyzer, concurrency, cppcoreguidelines, misc, modernize, performance, portability, readability

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: clang_tidy
```

**Severity mapping:** Severity is determined by the check category:

- **High** -- correctness/security categories: bugprone, cert, concurrency, clang-analyzer, clang-diagnostic
- **Medium** -- potential bugs/performance: cppcoreguidelines, misc, modernize, performance, portability, hicpp
- **Low** -- style/readability categories: readability, google, llvm, abseil

**Installation:**

- macOS: `brew install llvm`
- Ubuntu/Debian: `apt install clang-tidy`

## Formatting

**Tool: [clang-format](https://clang.llvm.org/docs/ClangFormat.html)**

clang-format is the canonical C++ code formatter from the LLVM project. It supports multiple coding styles and is highly configurable via `.clang-format` files.

- Supports auto-fix (`clang-format -i` writes formatted files in-place)
- Check-only mode via `clang-format --dry-run --Werror`
- Configurable via `.clang-format` or `_clang-format` files
- Built-in styles: LLVM, Google, Chromium, Mozilla, WebKit, Microsoft, GNU

```yaml
pipeline:
  formatting:
    enabled: true
    tools:
      - name: clang_format
```

## Type Checking

**Tool: [cppcheck](https://cppcheck.sourceforge.io/)**

cppcheck is a static analysis tool for C/C++ code. Unlike the compiler, it focuses on detecting bugs, undefined behavior, and dangerous coding constructs that the compiler does not warn about.

- XML output via `--xml --xml-version=2` for structured parsing
- Uses `compile_commands.json` when available for accurate analysis
- Detects: null pointer dereferences, uninitialized variables, buffer overflows, memory leaks, dead code, etc.
- Supports inline suppressions via `// cppcheck-suppress`
- CWE-mapped findings where applicable

**Severity mapping:** Cppcheck severity maps directly to LucidShark severity:

- **High** -- `error` severity (null pointer, uninitialized var, buffer overflow)
- **Medium** -- `warning`, `performance`, `portability` severity
- **Low** -- `style`, `information` severity

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: cppcheck
```

## Testing

**Tool: [CTest](https://cmake.org/cmake/help/latest/manual/ctest.1.html)**

CTest is the test driver from CMake. It runs any tests registered via `add_test()` in CMakeLists.txt, including Google Test, Catch2, Boost.Test, and plain executables.

- Parses CTest text output and XML results (`-T Test`)
- Supports test frameworks: Google Test, Catch2, Boost.Test, doctest, or any CMake-registered executable
- Requires a configured CMake build directory (run `cmake -B build` first)

```yaml
pipeline:
  testing:
    enabled: true
    tools:
      - name: ctest
```

> **Note:** CTest requires a configured CMake build directory. Run `cmake -B build` to create one before running tests.

## Coverage

**Tool: [lcov](https://github.com/linux-test-project/lcov)**

lcov parses gcov/lcov `.info` files for line-level code coverage data. Coverage data is produced by compiling with `--coverage` flags and running lcov after test execution.

- Parses existing `.info` files (never runs tests)
- Looks for `coverage.info` or `lcov.info` in the project root and build directory
- Per-file coverage with missing line tracking

> **Note:** To generate coverage data, compile with `--coverage` (or `-fprofile-arcs -ftest-coverage`) and run `lcov --capture --directory build --output-file coverage.info` after tests.

```yaml
pipeline:
  coverage:
    enabled: true
    tools:
      - name: lcov
    threshold: 80
```

## Security

### SAST: OpenGrep (language-agnostic)

OpenGrep provides C++ SAST coverage with auto-detected rule sets for common vulnerability patterns.

### SCA: Trivy

Trivy SCA scans package manifests for known vulnerabilities in dependencies.

See the domain-specific sections in the [main documentation](../main.md) for details on OpenGrep and Trivy.

## Duplication

Duplo scans `.cpp`, `.cc`, `.cxx`, `.hpp` files for duplicate code blocks.

```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 5.0
```

## Timeouts

| Tool | Timeout | Rationale |
|------|---------|-----------|
| clang-tidy | 300s | Runs many checks; large projects with headers need headroom |
| cppcheck | 300s | Full static analysis; large codebases can be slow |
| CTest | 600s | Test suites can include integration tests |
| clang-format | 120s | Pure formatting; fastest of the tools |

## Prerequisites

- **CMake 3.14+** recommended (for CTest `--test-dir` support)
- **clang-tidy**: `brew install llvm` (macOS), `apt install clang-tidy` (Ubuntu/Debian)
- **cppcheck**: `brew install cppcheck` (macOS), `apt install cppcheck` (Ubuntu/Debian)
- **CTest**: Ships with CMake (`brew install cmake` or `apt install cmake`)
- **lcov**: `brew install lcov` (macOS), `apt install lcov` (Ubuntu/Debian)
- **clang-format**: `brew install clang-format` (macOS), `apt install clang-format` (Ubuntu/Debian)
- **OpenGrep** and **Trivy**: Auto-downloaded by LucidShark

## Example Configuration

```yaml
version: 1
project:
  languages: [c++]
pipeline:
  linting:
    enabled: true
    tools:
      - name: clang_tidy
  formatting:
    enabled: true
    tools:
      - name: clang_format
  type_checking:
    enabled: true
    tools:
      - name: cppcheck
  testing:
    enabled: true
    tools:
      - name: ctest
  coverage:
    enabled: true
    tools:
      - name: lcov
    threshold: 80
  security:
    enabled: true
    tools:
      - { name: opengrep, domains: [sast] }
      - { name: trivy, domains: [sca] }
  duplication:
    enabled: true
    threshold: 5.0
```

## See Also

- [C](c.md) -- related language with similar tooling
- [Supported Languages Overview](README.md)
