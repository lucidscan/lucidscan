# Supported Languages

LucidShark supports 15 programming languages with varying levels of tool coverage. Languages with full support have dedicated tools across most quality domains. All detected languages benefit from security scanning and many from duplication detection.

## Support Tiers

| Tier | Languages | Description |
|------|-----------|-------------|
| **Full** | [Python](python.md), [TypeScript](typescript.md), [JavaScript](javascript.md), [Java](java.md), [Kotlin](kotlin.md), [Rust](rust.md), [Go](go.md), [C#](csharp.md), [C](c.md), [C++](cpp.md), [Scala](scala.md), [Swift](swift.md), [Ruby](ruby.md) | Dedicated tools across linting, formatting, type checking, testing, coverage, security, and duplication |
| **Minimal** | [PHP](php.md) | Security scanning only |

## Tools by Domain

| Domain | Tools | Languages |
|--------|-------|-----------|
| **Linting** | [Ruff](python.md#linting), [ESLint](typescript.md#linting), [Biome](javascript.md#linting), [Clippy](rust.md#linting), [Checkstyle](java.md#linting), [PMD](java.md#pmd), [ktlint](kotlin.md#linting), [golangci-lint](go.md#linting), [dotnet format](csharp.md#linting), [clang-tidy](c.md#linting), [Scalafix](scala.md#linting), [SwiftLint](swift.md#linting), [RuboCop](ruby.md#linting) | Python, JS/TS, Rust, Java, Kotlin, Go, C#, C/C++, Scala, Swift, Ruby |
| **Formatting** | [Ruff Format](python.md#formatting), [Prettier](javascript.md#formatting), [ktlint](kotlin.md#formatting), [rustfmt](rust.md#formatting), [gofmt](go.md#formatting), [dotnet format](csharp.md#formatting), [clang-format](c.md#formatting), [Scalafmt](scala.md#formatting), [SwiftFormat](swift.md#formatting), [RuboCop Format](ruby.md#formatting) | Python, JS/TS, Kotlin, Rust, Go, C#, C/C++, Scala, Swift, Ruby |
| **Type Checking** | [mypy](python.md#type-checking), [Pyright](python.md#type-checking), [tsc](typescript.md#type-checking), [SpotBugs](java.md#type-checking), [detekt](kotlin.md#type-checking), [cargo check](rust.md#type-checking), [go vet](go.md#type-checking), [dotnet build](csharp.md#type-checking), [cppcheck](c.md#type-checking), [scalac](scala.md#type-checking), [Swift compiler](swift.md#type-checking), [Sorbet](ruby.md#type-checking) | Python, TypeScript, Java, Kotlin, Rust, Go, C#, C/C++, Scala, Swift, Ruby |
| **Security (SAST)** | OpenGrep, [gosec](go.md#security) (Go) | All languages (gosec is Go-specific) |
| **Security (SCA)** | Trivy | All languages with package manifests |
| **Security (IaC)** | Checkov | Language-agnostic (Terraform, K8s, CloudFormation, etc.) |
| **Security (Container)** | Trivy | Language-agnostic (Dockerfile, container images) |
| **Testing** | [pytest](python.md#testing), [Jest](javascript.md#testing), [Vitest](javascript.md#testing), [Mocha](javascript.md#testing), [Karma](javascript.md#testing), [Playwright](javascript.md#testing), [Maven/Gradle](java.md#testing), [cargo test](rust.md#testing), [go test](go.md#testing), [dotnet test](csharp.md#testing), [CTest](c.md#testing), [sbt test](scala.md#testing), [swift test](swift.md#testing), [RSpec](ruby.md#testing) | Python, JS/TS, Java, Kotlin, Rust, Go, C#, C/C++, Scala, Swift, Ruby |
| **Coverage** | [coverage.py](python.md#coverage), [Istanbul](javascript.md#coverage), [Vitest](javascript.md#coverage), [JaCoCo](java.md#coverage), [Tarpaulin](rust.md#coverage), [go cover](go.md#coverage), [dotnet coverage](csharp.md#coverage), [gcov/lcov](c.md#coverage), [Scoverage](scala.md#coverage), [llvm-cov](swift.md#coverage), [SimpleCov](ruby.md#coverage) | Python, JS/TS, Java, Kotlin, Rust, Go, C#, C/C++, Scala, Swift, Ruby |
| **Duplication** | Duplo | Python, JS/TS, Java, Kotlin, Go, Rust, Scala, Swift, C, C++, C#, Ruby, Erlang, VB, HTML, CSS |

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
