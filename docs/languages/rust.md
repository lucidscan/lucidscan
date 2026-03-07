# Rust

**Support tier: Full**

Rust projects are fully supported with linting, type checking, testing, coverage, security scanning, and duplication detection.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.rs` |
| **Marker files** | `Cargo.toml` |
| **Version detection** | `edition` from `Cargo.toml` |

## Tools by Domain

| Domain | Tool | Notes |
|--------|------|-------|
| **Linting** | Clippy | Official Rust linter; detects common mistakes and style issues |
| **Type Checking** | cargo check | Rust compiler diagnostics; catches type errors and lifetime issues |
| **Testing** | cargo test | Built-in Rust test runner |
| **Coverage** | Tarpaulin | Code coverage via `cargo-tarpaulin` |
| **Security (SAST)** | OpenGrep | Rust-specific vulnerability rules |
| **Security (SCA)** | Trivy | Scans `Cargo.lock` |
| **Duplication** | Duplo | Scans `.rs` files |

## Linting

Clippy is the official Rust linter, providing hundreds of lints organized by category:

- **correctness** -- code that is outright wrong or useless (severity: HIGH)
- **suspicious** -- code that is most likely wrong or useless (severity: HIGH)
- **complexity** -- code that does something simple but in a complex way (severity: MEDIUM)
- **perf** -- code that can be written to run faster (severity: MEDIUM)
- **style** -- code that should be written in a more idiomatic way (severity: LOW)
- **pedantic** -- lints which are rather strict or have occasional false positives (severity: LOW)

Clippy supports auto-fix via `cargo clippy --fix`.

```yaml
pipeline:
  linting:
    enabled: true
```

## Type Checking

`cargo check` runs the Rust compiler's type checking without producing binaries. It catches:

- Type mismatches
- Lifetime errors
- Borrow checker violations
- Unused imports and variables (compiler warnings)

Clippy lints are filtered out of type checking results to avoid domain overlap.

```yaml
pipeline:
  type_checking:
    enabled: true
```

## Testing

`cargo test` runs all unit tests (in `#[cfg(test)]` modules), integration tests (in `tests/`), and doc tests.

```yaml
pipeline:
  testing:
    enabled: true
```

## Coverage

[cargo-tarpaulin](https://github.com/xd009642/tarpaulin) measures code coverage for Rust projects. It instruments the binary and runs the test suite.

- Automatically fails if tests have failures or errors (prevents stale coverage data)

```yaml
pipeline:
  coverage:
    enabled: true
    tools: [{ name: tarpaulin }]
    threshold: 80
```

**Note:** `cargo-tarpaulin` must be installed separately: `cargo install cargo-tarpaulin`

## Security

Security tools (OpenGrep, Trivy, Checkov) are language-agnostic. See the domain-specific sections in the [main documentation](../main.md) for details.

Trivy SCA scans Rust manifests: `Cargo.lock`.

## Duplication

Duplo scans `.rs` files for duplicate code blocks.

```yaml
pipeline:
  duplication:
    enabled: true
    threshold: 5.0
```

## Example Configuration

```yaml
version: 1
project:
  languages: [rust]
pipeline:
  linting:
    enabled: true
  type_checking:
    enabled: true
  testing:
    enabled: true
  coverage:
    enabled: true
    tools: [{ name: tarpaulin }]
    threshold: 80
  security:
    enabled: true
    tools:
      - { name: trivy, domains: [sca] }
      - { name: opengrep, domains: [sast] }
  duplication:
    enabled: true
    threshold: 5.0
```

## See Also

- [Supported Languages Overview](README.md)
