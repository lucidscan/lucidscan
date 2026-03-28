# C

**Support tier: Full**

C projects are fully supported with linting, formatting, type checking (static analysis), testing, coverage, security scanning, and duplication detection.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.c`, `.h` |
| **Marker files** | `CMakeLists.txt`, `Makefile`, `configure`, `configure.ac`, `meson.build` |

## Tools by Domain

| Domain | Tool | Notes |
|--------|------|-------|
| **Linting** | clang-tidy | LLVM-based linter with bugprone, cert, security, and readability checks |
| **Formatting** | clang-format | LLVM-based formatter with configurable style presets |
| **Type Checking** | cppcheck | C/C++ static analyzer with error, warning, style, and performance checks |
| **Testing** | CTest | CMake's test runner; parses XML or text output |
| **Coverage** | gcov/lcov | GCC coverage toolchain; parses lcov info files |
| **Security (SAST)** | OpenGrep | Language-agnostic vulnerability rules (also covers C) |
| **Duplication** | Duplo | Scans `.c` and `.h` files |

## Linting

**Tool: [clang-tidy](https://clang.llvm.org/extra/clang-tidy/)**

clang-tidy is an LLVM-based linter and static analysis tool for C (and C++) code. It provides a framework of pluggable checks for diagnosing common programming errors, style violations, and misuse of interfaces.

- Supports auto-fix via `clang-tidy --fix`
- Configurable via `.clang-tidy` file in the project root
- Check categories: bugprone, cert, security, misc, readability, modernize, performance

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: clang_tidy
```

**Severity mapping:** Severity is determined by the check category that reported the issue:

- **High** -- correctness/security checks: bugprone, cert, security
- **Medium** -- code quality checks: misc, performance, modernize
- **Low** -- style/convention checks: readability

**Installation:** Install via LLVM/Clang packages (e.g., `apt install clang-tidy` or `brew install llvm`)

## Formatting

**Tool: [clang-format](https://clang.llvm.org/docs/ClangFormat.html)**

clang-format is an LLVM-based code formatter for C (and C++) code. It supports multiple style presets (LLVM, Google, Chromium, Mozilla, WebKit) and full customization.

- Supports auto-fix via `clang-format -i` (in-place formatting)
- Check-only mode via `clang-format --dry-run --Werror` (returns non-zero if formatting differs)
- Configurable via `.clang-format` file in the project root

```yaml
pipeline:
  formatting:
    enabled: true
    tools:
      - name: clang_format
```

## Type Checking

**Tool: [cppcheck](https://cppcheck.sourceforge.io/)**

cppcheck is a static analysis tool for C and C++ code. It detects bugs, undefined behavior, and dangerous coding patterns that compilers do not catch.

- Runs with `--enable=all --language=c` for comprehensive analysis
- Supports strict mode via `--inconclusive` for additional heuristic checks
- No compilation required -- works directly on source code

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: cppcheck
```

**Severity mapping:** cppcheck severity maps directly to LucidShark severity:

- **High** -- `error` severity findings (null pointer dereference, buffer overflow, memory leak)
- **Medium** -- `warning` and `performance` severity findings (redundant conditions, unnecessary copies)
- **Low** -- `style` severity findings (unused variables, variable scope reduction)

## Testing

**Tool: [CTest](https://cmake.org/cmake/help/latest/manual/ctest.1.html)**

CTest is CMake's built-in test runner. It discovers and executes tests defined via `add_test()` in CMakeLists.txt.

- Requires a CMake build directory containing `CMakeCache.txt`
- Parses XML output (`Testing/TAG/Test.xml`) or falls back to text output
- Uses `--output-on-failure` to capture stdout/stderr from failed tests

```yaml
pipeline:
  testing:
    enabled: true
    tools:
      - name: ctest
```

## Coverage

**Tool: [gcov/lcov](https://gcc.gnu.org/onlinedocs/gcc/Gcov.html)**

gcov is GCC's coverage analysis tool, used together with lcov for generating human-readable and machine-parseable coverage reports. LucidShark parses lcov info files (`coverage.info`).

- Requires compiling with the `--coverage` flag (adds `-fprofile-arcs -ftest-coverage`)
- Requires running tests to generate `.gcda` data files
- Parses existing `coverage.info` produced by `lcov --capture`
- Returns error if no coverage data found (requires testing domain to be active)

> **Note:** When both the `testing` and `coverage` domains are active, LucidShark will look for `coverage.info` in the build directory after tests complete. Ensure your CMake build is configured with `--coverage` and that lcov runs as a post-test step to generate the info file.

```yaml
pipeline:
  coverage:
    enabled: true
    tools:
      - name: gcov
    threshold: 80
```

## Security

### SAST: OpenGrep (language-agnostic)

OpenGrep includes SAST rules for C code, covering common vulnerability patterns such as buffer overflows, format string issues, integer overflows, and use-after-free.

See the domain-specific sections in the [main documentation](../main.md) for details on OpenGrep, Trivy, and Checkov.

```yaml
pipeline:
  security:
    enabled: true
    tools:
      - { name: opengrep, domains: [sast] }
```

## Duplication

Duplo scans `.c` and `.h` files for duplicate code blocks.

```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 5.0
```

## Timeouts

| Tool | Timeout | Rationale |
|------|---------|-----------|
| clang-tidy | 300s | Runs many checks per translation unit; large projects need headroom |
| clang-format | 120s | Pure formatting; fastest of the tools |
| cppcheck | 300s | Deep static analysis; large codebases need headroom |
| CTest | 600s | Test suites can be inherently slow (integration tests, etc.) |
| gcov/lcov | 120s | Parses coverage data files; typically fast |

## Prerequisites

- **clang-tidy**: Install via LLVM/Clang packages (`apt install clang-tidy`, `brew install llvm`)
- **clang-format**: Install via LLVM/Clang packages (`apt install clang-format`, `brew install llvm`)
- **cppcheck**: `apt install cppcheck` or `brew install cppcheck`
- **CTest**: Ships with CMake (`apt install cmake`, `brew install cmake`); requires a CMake build directory with `CMakeCache.txt`
- **gcov**: Ships with GCC (no separate installation); lcov is optional (`apt install lcov`, `brew install lcov`)

## Example Configuration

```yaml
version: 1
project:
  languages: [c]
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
      - name: gcov
    threshold: 80
  security:
    enabled: true
    tools:
      - { name: opengrep, domains: [sast] }
  duplication:
    enabled: true
    threshold: 5.0
```

## See Also

- [C++](cpp.md) -- related language with similar support
- [Supported Languages Overview](README.md)
