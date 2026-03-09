# Kotlin

**Support tier: Partial**

Kotlin is supported through shared Java tooling for testing and coverage, plus security scanning and duplication detection.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.kt`, `.kts` |
| **Marker files** | `build.gradle.kts` (shared with Java) |

## Tools by Domain

| Domain | Tool | Notes |
|--------|------|-------|
| **Security (SAST)** | OpenGrep | Kotlin-specific vulnerability rules |
| **Security (SCA)** | Trivy | Scans `build.gradle.kts`, `gradle.lockfile` |
| **Testing** | Maven/Gradle | JUnit via Gradle test task or Maven Surefire |
| **Coverage** | JaCoCo | XML reports, per-file tracking |

## Testing

**Tool: Maven / Gradle (JUnit)**

Runs Kotlin tests via your build tool, the same way as Java.

- **Gradle:** Reads test results from `build/test-results`
- **Maven:** Reads Surefire reports from `target/surefire-reports`
- Multi-module project support

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

## Not Yet Supported

The following domains do not yet have Kotlin-specific tools:

- **Linting** -- no dedicated Kotlin linter (e.g., ktlint, detekt) integrated yet
- **Type Checking** -- Kotlin's compiler handles type safety; no separate tool integrated
- **Duplication** -- Duplo does not currently support Kotlin files

## Example Configuration

```yaml
version: 1
project:
  languages: [kotlin]
pipeline:
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
```

## See Also

- [Java](java.md) -- shares Maven/Gradle, JaCoCo tooling
- [Supported Languages Overview](README.md)
