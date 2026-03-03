# Java

**Support tier: Full**

Java has full tool coverage in LucidShark across all six quality domains, with support for both Maven and Gradle build systems.

## Detection

| Method | Indicators |
|--------|-----------|
| **File extensions** | `.java` |
| **Marker files** | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| **Version detection** | `maven.compiler.source` / `java.version` from `pom.xml`, `sourceCompatibility` from `build.gradle` |

## Tools by Domain

| Domain | Tool | Auto-Fix | Notes |
|--------|------|----------|-------|
| **Linting** | Checkstyle | No | Google or custom checks |
| **Type Checking** | SpotBugs | -- | Static analysis for bugs, requires compiled classes |
| **Security (SAST)** | OpenGrep | -- | Java-specific vulnerability rules |
| **Security (SCA)** | Trivy | -- | Scans `pom.xml`, `build.gradle`, `gradle.lockfile` |
| **Testing** | Maven/Gradle | -- | JUnit via Surefire (Maven) or Gradle test task |
| **Coverage** | JaCoCo | -- | XML reports, per-file tracking |
| **Duplication** | Duplo | -- | Scans `.java` files |

## Linting

**Tool: [Checkstyle](https://checkstyle.org/)**

Java style checker distributed as a JAR file. Requires Java runtime.

- Default configuration: Google Java Style (`google_checks.xml`)
- Custom config detection: `checkstyle.xml`, `.checkstyle.xml`, `config/checkstyle/checkstyle.xml`
- Does not support auto-fix

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: checkstyle
```

## Type Checking

**Tool: [SpotBugs](https://spotbugs.github.io/)**

Static analysis tool that finds bugs in Java code by analyzing bytecode.

- Requires compiled `.class` files (runs after build)
- Looks for classes in `target/classes` (Maven) or `build/classes` (Gradle)
- Bug categories: BAD_PRACTICE, CORRECTNESS, MT_CORRECTNESS, PERFORMANCE, SECURITY, STYLE, MALICIOUS_CODE
- Rank-based severity adjustment

```yaml
pipeline:
  type_checking:
    enabled: true
    tools:
      - name: spotbugs
```

## Testing

**Tool: Maven / Gradle (JUnit)**

Runs JUnit tests via your build tool.

- **Maven:** Reads Surefire reports from `target/surefire-reports`
- **Gradle:** Reads test results from `build/test-results`
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

Java Code Coverage library integrated with Maven and Gradle.

- **Maven:** Runs `test` then `jacoco:report`
- **Gradle:** Runs `clean test jacocoTestReport`
- Existing report detection (skips re-running tests if report exists)
- XML report parsing with per-file line coverage
- Multi-module project support
- Automatically fails if tests have failures or errors (prevents stale coverage data)

```yaml
pipeline:
  coverage:
    enabled: true
    threshold: 80
```

## Security

Security tools (OpenGrep, Trivy, Checkov) are language-agnostic. See the domain-specific sections in the [main documentation](../main.md) for details.

Trivy SCA scans these Java manifests: `pom.xml`, `build.gradle`, `gradle.lockfile`.

## Duplication

Duplo scans `.java` files for duplicate code blocks.

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
  languages: [java]
pipeline:
  linting:
    enabled: true
    tools: [{ name: checkstyle }]
  type_checking:
    enabled: true
    tools: [{ name: spotbugs }]
  security:
    enabled: true
    tools: [{ name: trivy }, { name: opengrep }]
  testing:
    enabled: true
    tools: [{ name: maven }]
  coverage:
    enabled: true
    threshold: 80
  duplication:
    enabled: true
    threshold: 5.0
```

## See Also

- [Kotlin](kotlin.md) -- shares Maven/Gradle, JaCoCo tooling
- [Supported Languages Overview](README.md)
