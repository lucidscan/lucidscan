# Kotlin

**Support tier: Full**

Kotlin has full tool coverage in LucidShark across all quality domains, with dedicated Kotlin tools for linting, formatting, and static analysis, plus shared Java tooling for testing and coverage.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.kt`, `.kts` |
| **Marker files** | `build.gradle.kts` (shared with Java) |

## Tools by Domain

| Domain | Tool | Auto-Fix | Notes |
|--------|------|----------|-------|
| **Linting** | ktlint | Yes | Kotlin linter with built-in formatter (managed, auto-downloaded) |
| **Type Checking** | detekt | -- | Static analysis for code smells, complexity, bugs (managed, auto-downloaded) |
| **Formatting** | ktlint | Yes | Rewrites files to match Kotlin coding conventions |
| **Security (SAST)** | OpenGrep | -- | Kotlin-specific vulnerability rules |
| **Security (SCA)** | Trivy | -- | Scans `build.gradle.kts`, `gradle.lockfile` |
| **Testing** | Maven/Gradle | -- | JUnit via Gradle test task or Maven Surefire |
| **Coverage** | JaCoCo | -- | XML reports, per-file tracking |
| **Duplication** | Duplo | -- | Scans `.kt`, `.kts` files |

## Linting

**Tool: [ktlint](https://pinterest.github.io/ktlint/)**

Anti-bikeshedding Kotlin linter with built-in formatter. Enforces the Kotlin coding conventions and Android Kotlin style guide.

- **Managed tool** -- auto-downloaded on first use, cached at `.lucidshark/bin/ktlint/{version}/`
- Built-in auto-fix support (`--format` flag)
- JSON output format for structured issue reporting
- Searches `src/main/kotlin`, `src/test/kotlin`, and standard Java source directories for `.kt`/`.kts` files
- Only requires Java (which any Kotlin project already has)

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: ktlint
```

## Type Checking

**Tool: [detekt](https://detekt.dev/)**

Static code analysis tool for Kotlin that finds code smells, complexity issues, and potential bugs.

- **Managed tool** -- auto-downloaded on first use, cached at `.lucidshark/bin/detekt/{version}/`
- Default rules cover complexity, coroutines, empty blocks, exceptions, naming, performance, potential bugs, and style
- Custom config detection: `detekt.yml`, `detekt.yaml`, `.detekt.yml`, `config/detekt/detekt.yml`, `config/detekt.yml`
- Checkstyle-format XML output for structured reporting
- Searches `src/main/kotlin`, `src/test/kotlin`, and standard Java source directories
- Only requires Java (which any Kotlin project already has)
- Categories: complexity, coroutines, empty-blocks, exceptions, naming, performance, potential-bugs, style

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: detekt
```

## Formatting

**Tool: [ktlint](https://pinterest.github.io/ktlint/) (format mode)**

ktlint doubles as a formatter -- its `--format` flag rewrites files to match the Kotlin coding conventions.

- Shares the same managed binary as the ktlint linter
- Always supports auto-fix (formatters fix by design)
- Checks formatting by running in lint-only mode and reporting files with style violations

```yaml
pipeline:
  formatting:
    enabled: true
    tools:
      - name: ktlint_format
```

## Testing

**Tool: Maven / Gradle (JUnit)**

Runs Kotlin tests via your build tool, the same way as Java.

- **Gradle:** Reads test results from `build/test-results`
- **Maven:** Reads Surefire reports from `target/surefire-reports`
- Multi-module project support
- JUnit XML parsing with test statistics

```yaml
pipeline:
  testing:
    enabled: true
    tools:
      - name: maven
```

## Coverage

**Tool: [JaCoCo](https://www.jacoco.org/)**

Code coverage for Kotlin projects, integrated with Maven and Gradle.

- Parses existing JaCoCo XML reports produced by the test runner
- Per-file line coverage tracking
- Multi-module project support
- Returns error if no JaCoCo report found (requires testing domain to be active)

```yaml
pipeline:
  coverage:
    enabled: true
    tools: [{ name: jacoco }]
    threshold: 80
```

## Security

Security tools (OpenGrep, Trivy, Checkov) are language-agnostic. See the domain-specific sections in the [main documentation](../main.md) for details.

Trivy SCA scans these Kotlin/JVM manifests: `build.gradle.kts`, `gradle.lockfile`, `pom.xml`.

## Duplication

Duplo scans `.kt` and `.kts` files for duplicate code blocks.

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
  languages: [kotlin]
pipeline:
  linting:
    enabled: true
    tools:
      - { name: ktlint }
  type_checking:
    enabled: true
    tools: [{ name: detekt }]
  formatting:
    enabled: true
    tools: [{ name: ktlint_format }]
  security:
    enabled: true
    tools:
      - { name: trivy, domains: [sca] }
      - { name: opengrep, domains: [sast] }
  testing:
    enabled: true
    tools: [{ name: maven }]
  coverage:
    enabled: true
    tools: [{ name: jacoco }]
    threshold: 80
  duplication:
    enabled: true
    threshold: 5.0
```

## See Also

- [Java](java.md) -- shares Maven/Gradle, JaCoCo tooling
- [Supported Languages Overview](README.md)
