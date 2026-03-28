# Supported Languages

LucidShark supports 15 programming languages with varying levels of tool coverage. Languages with full support have dedicated tools across most quality domains. All detected languages benefit from security scanning and many from duplication detection.

## Support Tiers

| Tier | Languages | Description |
|------|-----------|-------------|
| **Full** | [Python](python.md), [TypeScript](typescript.md), [JavaScript](javascript.md), [Java](java.md), [Rust](rust.md), [Go](go.md), [C++](cpp.md), [Scala](scala.md), [Swift](swift.md) | Dedicated tools across linting, formatting, type checking, testing, coverage, security, and duplication |
| **Partial** | [Kotlin](kotlin.md) | Testing, coverage, and security via shared Java tooling |
| **Basic** | [Ruby](ruby.md), [C](c.md), [C#](csharp.md) | Security scanning and duplication detection |
| **Minimal** | [PHP](php.md) | Security scanning only |

## Tools by Domain

| Domain | Tools | Languages |
|--------|-------|-----------|
| **Linting** | [Ruff](python.md#linting), [ESLint](typescript.md#linting), [Biome](javascript.md#linting), [Clippy](rust.md#linting), [Checkstyle](java.md#linting), [PMD](java.md#pmd), [golangci-lint](go.md#linting), [clang-tidy](cpp.md#linting), [Scalafix](scala.md#linting), [SwiftLint](swift.md#linting) | Python, JS/TS, Rust, Java, Go, C++, Scala, Swift |
| **Formatting** | [Ruff Format](python.md#formatting), [Prettier](javascript.md#formatting), [rustfmt](rust.md#formatting), [gofmt](go.md#formatting), [clang-format](cpp.md#formatting), [Scalafmt](scala.md#formatting), [SwiftFormat](swift.md#formatting) | Python, JS/TS, Rust, Go, C++, Scala, Swift |
| **Type Checking** | [mypy](python.md#type-checking), [Pyright](python.md#type-checking), [tsc](typescript.md#type-checking), [SpotBugs](java.md#type-checking), [cargo check](rust.md#type-checking), [go vet](go.md#type-checking), [cppcheck](cpp.md#type-checking), [scalac](scala.md#type-checking), [Swift compiler](swift.md#type-checking) | Python, TypeScript, Java, Rust, Go, C++, Scala, Swift |
| **Security (SAST)** | OpenGrep, [gosec](go.md#security) (Go) | All languages (gosec is Go-specific) |
| **Security (SCA)** | Trivy | All languages with package manifests |
| **Security (IaC)** | Checkov | Language-agnostic (Terraform, K8s, CloudFormation, etc.) |
| **Security (Container)** | Trivy | Language-agnostic (Dockerfile, container images) |
| **Testing** | [pytest](python.md#testing), [Jest](javascript.md#testing), [Vitest](javascript.md#testing), [Mocha](javascript.md#testing), [Karma](javascript.md#testing), [Playwright](javascript.md#testing), [Maven/Gradle](java.md#testing), [cargo test](rust.md#testing), [go test](go.md#testing), [CTest](cpp.md#testing), [sbt test](scala.md#testing), [swift test](swift.md#testing) | Python, JS/TS, Java, Kotlin, Rust, Go, C++, Scala, Swift |
| **Coverage** | [coverage.py](python.md#coverage), [Istanbul](javascript.md#coverage), [Vitest](javascript.md#coverage), [JaCoCo](java.md#coverage), [Tarpaulin](rust.md#coverage), [go cover](go.md#coverage), [lcov](cpp.md#coverage), [Scoverage](scala.md#coverage), [llvm-cov](swift.md#coverage) | Python, JS/TS, Java, Kotlin, Rust, Go, C++, Scala, Swift |
| **Duplication** | Duplo | Python, JS/TS, Java, Go, Rust, Scala, Swift, C, C++, C#, Ruby, Erlang, VB, HTML, CSS |

## Language Detection

LucidShark auto-detects languages in your project by scanning for file extensions and marker files (e.g., `pyproject.toml`, `package.json`, `go.mod`). See each language page for detection details.

## Configuration

Detected languages are listed in `lucidshark.yml` under the `project` section:

```yaml
version: 1
project:
  languages: [python, typescript]
```

You can override auto-detection by specifying languages explicitly.

## See Also

- [Full Specification](../main.md)
- [CLI Reference](../help.md)
