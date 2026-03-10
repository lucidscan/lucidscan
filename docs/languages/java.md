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
| **Linting** | Checkstyle | No | Style checking with Google or custom checks (managed, auto-downloaded) |
| **Linting** | PMD | No | Bug detection, design issues, complexity (managed, auto-downloaded) |
| **Formatting** | google-java-format | Yes | Google's opinionated Java formatter |
| **Type Checking** | SpotBugs | -- | Static analysis for bugs, requires compiled classes (managed, auto-downloaded) |
| **Security (SAST)** | OpenGrep | -- | Java-specific vulnerability rules |
| **Security (SCA)** | Trivy | -- | Scans `pom.xml`, `build.gradle`, `gradle.lockfile` |
| **Testing** | Maven/Gradle | -- | JUnit via Surefire (Maven) or Gradle test task |
| **Coverage** | JaCoCo | -- | XML reports, per-file tracking |
| **Duplication** | Duplo | -- | Scans `.java` files |

## Linting

Java has two complementary linters. **Checkstyle** enforces coding style and conventions, while **PMD** detects bugs, design issues, and complexity problems. Using both together provides comprehensive coverage.

### Checkstyle

**Tool: [Checkstyle](https://checkstyle.org/)**

Java style checker distributed as a JAR file. Requires Java runtime.

- **Managed tool** — auto-downloaded on first use, cached at `.lucidshark/bin/checkstyle/{version}/`
- Default configuration: bundled Google Java Style (`checkstyle-google.xml`) with relaxed Javadoc rules
- Custom config detection: `checkstyle.xml`, `.checkstyle.xml`, `config/checkstyle/checkstyle.xml`
- Does not support auto-fix
- Only requires Java (which any Java project already has)

### PMD

**Tool: [PMD](https://pmd.github.io/)**

Source code analyzer that finds common programming flaws — unused variables, empty catch blocks, unnecessary object creation, God classes, and more.

- **Managed tool** — auto-downloaded on first use, cached at `.lucidshark/bin/pmd/{version}/`
- Default ruleset: `rulesets/java/quickstart.xml` (118 rules)
- Custom config detection: `pmd-ruleset.xml`, `pmd.xml`, `ruleset.xml`, `.pmd/rulesets.xml`, `config/pmd/pmd.xml`, `config/pmd/ruleset.xml`
- Does not support auto-fix
- Only requires Java (which any Java project already has)
- PMD priority mapping: 1→Critical, 2→High, 3→Medium, 4→Low, 5→Info

```yaml
pipeline:
  linting:
    enabled: true
    tools:
      - name: checkstyle   # Style checking
      - name: pmd          # Bug detection and design analysis
```

## Formatting

**Tool: [google-java-format](https://github.com/google/google-java-format)**

Google's opinionated Java source code formatter.

- Supports auto-fix via `google-java-format --replace`
- Check-only mode via `google-java-format --dry-run --set-exit-if-changed`
- Requires `google-java-format` binary installed

```yaml
pipeline:
  formatting:
    enabled: true
    tools:
      - name: google_java_format
```

## Type Checking

**Tool: [SpotBugs](https://spotbugs.github.io/)**

Static analysis tool that finds bugs in Java code by analyzing bytecode.

- **Managed tool** — auto-downloaded on first use, cached at `.lucidshark/bin/spotbugs/{version}/`
- Requires compiled `.class` files (runs after build)
- Looks for classes in `target/classes` (Maven) or `build/classes` (Gradle)
- Bug categories: BAD_PRACTICE, CORRECTNESS, MT_CORRECTNESS, PERFORMANCE, SECURITY, STYLE, MALICIOUS_CODE
- Rank-based severity adjustment
- Only requires Java runtime (which any Java project already has)

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

- Parses existing JaCoCo XML reports produced by the test runner
- XML report parsing with per-file line coverage
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
    tools:
      - { name: checkstyle }
      - { name: pmd }
  formatting:
    enabled: true
    tools:
      - { name: google_java_format }
  type_checking:
    enabled: true
    tools: [{ name: spotbugs }]
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

- [Kotlin](kotlin.md) -- shares Maven/Gradle, JaCoCo tooling
- [Supported Languages Overview](README.md)
