# LucidScan

## 1. Problem Statement

Modern engineering teams build applications from multiple interconnected layers:

- **First-party application code**
- **Third-party open source dependencies**
- **Container images and base operating systems**
- **Infrastructure-as-code resources** (Terraform, Kubernetes, etc.)
- **AI-integrated components** such as MCP servers and tool-based automation

Security tooling across these layers is fragmented and inconsistent. Existing commercial platforms such as Snyk or SonarQube cover parts of the problem but introduce significant challenges:

- **Slow CI performance**: they are slow in CI pipelines, harming developer productivity.
- **Closed-source engines**: difficult to trust or validate their detection logic.
- **High cost**: often inaccessible to smaller companies.
- **Limited or complex self-hosting**: self-hosted options are limited or overly complex.
- **Noisy output**: they frequently overwhelm users with noisy or context-poor results when teams simply want actionable findings.

Meanwhile, excellent open-source scanners already exist across these domains - OSV-based SCA tools, Trivy for container scanning, Checkov for IaC, and OpenGrep for static analysis. But in practice, using them individually leads to new challenges:

- **Incompatible outputs**: each scanner produces different, incompatible output formats.
- **Poor correlation**: results cannot be easily correlated or deduplicated.
- **Inconsistent severity**: severity and prioritization rules vary wildly between tools.
- **Fragmented workflow**: there is no unified workflow or command-line interface that ties them together.
- **Multiple dashboards**: developers must jump between multiple dashboards and CLIs to understand overall risk.
- **No single pane of glass**: there is no single place where all findings across code, dependencies, containers, and IaC are viewed in a consistent way.

At the same time, the rise of AI-connected systems (e.g., MCP servers) introduces new security considerations such as over-privileged tool access, unsafe data flows, and insecure endpoint configurations. These needs are not addressed by existing scanners but will soon become critical for many teams.

There is a clear need for a fast, transparent, self-hostable, open-source security scanning **framework** that:

- **Orchestrates SCA, container scanning, IaC scanning, and static code analysis** through pluggable scanner adapters.
- **Unifies multiple proven open-source engines** behind a single CLI, consistent UX, and shared output schema.
- **Provides low-noise, actionable, developer-friendly results** suitable for local environments and CI/CD.
- **Avoids the opacity, complexity, and cost** of existing commercial platforms.
- **Enables extensibility** through a plugin architecture that allows third parties to add new scanners, enrichers, and reporters without changing the core framework.

This product aims to fill that gap by delivering an open, developer-first security scanning **framework** - the "LangChain for DevSecOps" - that orchestrates scanning across code, dependencies, containers, and infrastructure through a modular, pluggable architecture.

### 1.1 Vision: LangChain for DevSecOps

Just as LangChain revolutionized AI application development by providing a unified abstraction layer over multiple LLM providers, **lucidscan aims to be the LangChain for security scanning**. The core insight is the same:

| LangChain | lucidscan |
|-----------|-----------|
| Abstracts OpenAI, Anthropic, Ollama, etc. | Abstracts Trivy, OpenGrep, Snyk, CodeQL, etc. |
| Composable chains and agents | Composable scan pipelines and enrichers |
| Swap models without changing code | Swap scanners without changing config |
| Unified interface to any LLM | Unified interface to any security scanner |
| `langchain.llms.OpenAI()` | `lucidscan.scanners.TrivyScanner()` |

**Where the analogy diverges:** Unlike LLM orchestration, security scanning requires strict determinism, reproducibility, and auditability. lucidscan prioritizes predictability over dynamism - the same inputs always produce the same outputs, and every finding is traceable to its source scanner.

This architectural vision drives several key design decisions:

- **Scanners are plugins**: Each scanner (Trivy, OpenGrep, Checkov, etc.) is a self-contained plugin that implements a common interface. Users install only what they need.
- **Unified abstractions**: Common interfaces for SCA, SAST, container, and IaC scanning regardless of which tool performs the scan. Unified abstractions normalize core metadata while preserving scanner-specific details as structured extensions.
- **Composability**: Declarative pipelines chain scanners with enrichers and reporters. Execution order is deterministic with no dynamic runtime branching.
- **Extensible ecosystem**: The plugin architecture is designed to support third-party scanners as the ecosystem matures.
- **AI-augmented (not AI-driven)**: LLM-based enrichment adds explanations and context to findings. AI never makes pass/fail decisions, never mutates scanner results, and never suppresses findings. AI enriches; scanners decide.

This is not just a wrapper around existing tools - it's a **framework** that makes security scanning composable, extensible, and developer-friendly.

---

## 2. Goals

lucidscan is a **plugin-based security scanning framework** - the "LangChain for DevSecOps." Rather than building custom scanning engines, lucidscan provides:

- **Unified abstractions** over security scanning domains (SCA, SAST, IaC, containers).
- **Pluggable scanners** that can be swapped without changing configuration.
- **Composable pipelines** that chain scanners → enrichers → reporters.
- **A consistent CLI and output schema** regardless of which tools run underneath.

The framework ships with default plugins (Trivy, OpenGrep, Checkov) but is designed for extensibility - third parties can publish scanner plugins to PyPI.

### 2.1 Framework Architecture

The core of lucidscan is a **plugin-based framework** with three component types:

#### 2.1.1 Scanner Plugins

Scanner plugins wrap underlying security tools and expose them through a common interface:

```python
class ScannerPlugin(ABC):
    @property
    def name(self) -> str: ...
    @property
    def domains(self) -> List[ScanDomain]: ...
    def ensure_binary(self) -> Path: ...
    def scan(self, context: ScanContext) -> List[UnifiedIssue]: ...
```

Key properties:

- **Self-contained**: Each plugin manages its own binary (download, cache, invoke).
- **Swappable**: Replace the default SCA scanner (Trivy) with another (Snyk) without changing workflow.
- **Discoverable**: Plugins register via Python entry points for auto-discovery.

#### 2.1.2 Enricher Plugins

Enricher plugins enhance scan results with additional context:

```python
class EnricherPlugin(ABC):
    def enrich(self, issues: List[UnifiedIssue], context: ScanContext) -> List[UnifiedIssue]: ...
```

Examples: AI explanations, CVSS scoring, EPSS predictions, reachability analysis.

#### 2.1.3 Reporter Plugins

Reporter plugins format and output scan results:

```python
class ReporterPlugin(ABC):
    def report(self, result: ScanResult, output: IO) -> None: ...
```

Examples: JSON, SARIF, HTML, table, dashboard upload.

### 2.2 Scanning Domains

lucidscan defines four **abstract scanning domains**. Each domain can be served by one or more scanner plugins:

| Domain | Description | Default Plugin |
|--------|-------------|----------------|
| **SCA** | Dependency vulnerability scanning | `TrivyScanner` |
| **Container** | Container image scanning | `TrivyScanner` |
| **IaC** | Infrastructure-as-Code misconfigurations | `CheckovScanner` |
| **SAST** | Static application security testing | `OpenGrepScanner` |

Users select domains via CLI flags (`--sca`, `--iac`, `--sast`, `--container`, `--all`), and the framework routes to the appropriate plugin.

**Swappability example:**

```yaml
# .lucidscan.yml - use Snyk for SCA instead of Trivy
scanners:
  sca:
    plugin: snyk        # Requires: pip install lucidscan-snyk
  sast:
    plugin: opengrep    # Default
```

### 2.3 Built-in Scanner Plugins

lucidscan ships with three scanner plugins covering all four domains:

#### 2.3.1 TrivyScanner

- **Domains**: SCA, Container
- **Underlying tool**: [Trivy](https://github.com/aquasecurity/trivy)
- **Capabilities**:
  - Dependency vulnerability scanning (npm, pip, Go, Ruby, Cargo, etc.)
  - Container image scanning (OS packages + app dependencies)
  - Automatic vulnerability database updates
  - Fix version suggestions

#### 2.3.2 OpenGrepScanner

- **Domains**: SAST
- **Underlying tool**: [OpenGrep](https://github.com/opengrep/opengrep)
- **Capabilities**:
  - Pattern-based static analysis
  - Multi-language support (Python, JavaScript, Go, Java, etc.)
  - Community rulesets
  - Code snippet extraction

#### 2.3.3 CheckovScanner

- **Domains**: IaC
- **Underlying tool**: [Checkov](https://github.com/bridgecrewio/checkov)
- **Capabilities**:
  - Terraform, Kubernetes, CloudFormation, ARM scanning
  - Policy-as-code checks
  - Resource-level findings

### 2.4 Composable Pipelines

Scans execute as **pipelines** that compose plugins:

```
Scanners → Enrichers → Reporters
```

Example pipeline configuration:

```yaml
# .lucidscan.yml
pipeline:
  scanners:
    - trivy
    - opengrep
    - checkov
  enrichers:
    - ai-explainer
    - cvss-enricher
  reporters:
    - json
    - sarif
```

The framework orchestrates execution, handles parallelization, and merges results.

### 2.5 Unified Output Schema

All scanner plugins normalize their output to a **common issue schema**, ensuring consistent results regardless of which tool runs:

```json
{
  "id": "unique-issue-id",
  "domain": "sca | sast | iac | container",
  "source": "trivy | opengrep | checkov | ...",
  "severity": "critical | high | medium | low | info",
  "title": "Issue title",
  "description": "Detailed description",
  "location": {
    "file": "path/to/file",
    "line": 42,
    "resource": "aws_s3_bucket.example"
  },
  "remediation": "How to fix",
  "metadata": { }
}
```

This unified schema enables:

- Consistent filtering and sorting across scanners.
- Unified severity thresholds for CI/CD gates.
- Cross-scanner deduplication.
- Tool-agnostic reporting.

### 2.6 Enrichment Layer

Beyond raw scan results, lucidscan provides an **enrichment layer** that adds context:

| Enricher | Purpose | Status |
|----------|---------|--------|
| `AIExplainer` | LLM-powered plain-language explanations and fix guidance | ✓ Included |
| `CVSSEnricher` | Fetch/compute CVSS scores for vulnerabilities | ✓ Included |
| `EPSSEnricher` | Exploit Prediction Scoring System integration | Planned |
| `ReachabilityAnalyzer` | Determine if vulnerable code is actually reachable | Planned |

Enrichers run after scanners and augment each issue with additional fields.

### 2.7 Developer Experience

#### 2.7.1 CLI

A single CLI serves as the primary interface:

```bash
lucidscan --all                    # Run all domains
lucidscan --sca --sast             # Run specific domains
lucidscan --format json            # Output format
lucidscan --fail-on high           # CI gate
```

#### 2.7.2 Configuration

Project-level configuration via `.lucidscan.yml`:

```yaml
scanners:
  sca:
    enabled: true
  sast:
    enabled: true
    rulesets: ["security", "best-practices"]

severity_threshold: medium

ignore:
  - path: "vendor/**"
  - rule: "generic.secrets.*"
```

#### 2.7.3 CI/CD Integration

- GitHub Actions workflow
- GitLab CI template
- Exit codes for pass/fail gates
- SARIF output for GitHub Security tab

### 2.8 Extensibility

The plugin architecture enables future growth without core changes:

#### 2.8.1 First-Party Extensions (Planned)

| Plugin | Domain | Status |
|--------|--------|--------|
| `SnykScanner` | SCA, Container | Planned |
| `CodeQLScanner` | SAST | Planned |
| `GitleaksScanner` | Secrets | Planned |
| `SonarQubeImporter` | SAST (import) | Planned |

#### 2.8.2 Third-Party Plugins

Anyone can publish scanner plugins to PyPI:

```bash
pip install lucidscan-snyk
pip install lucidscan-codeql
pip install lucidscan-my-custom-scanner
```

Plugins are auto-discovered via Python entry points:

```toml
# Third-party plugin's pyproject.toml
[project.entry-points."lucidscan.scanners"]
snyk = "lucidscan_snyk:SnykScanner"
```

### 2.9 AI-Native Design

lucidscan is built for the AI era:

- **AI Explanations**: Every issue can be enriched with LLM-generated explanations.
- **AI-Assisted Fixes**: Future support for AI-generated patches.
- **MCP Integration**: Designed to work with AI coding assistants via MCP.

The `AIExplainer` enricher provides:

- Plain-language explanation of the vulnerability.
- Risk assessment in context.
- Concrete remediation steps.
- Code examples where applicable.

### 2.10 What lucidscan is NOT

To clarify the framework vision:

- **Not a scanner**: lucidscan orchestrates scanners, it doesn't implement scanning logic.
- **Not a vulnerability database**: It relies on underlying tools (Trivy, etc.) for vulnerability data.
- **Not a SaaS**: lucidscan is purely local/CLI. Dashboard features are future roadmap.
- **Not opinionated about tools**: Users can swap any scanner plugin without changing their workflow.

---

## 3. Non-Goals

The following items are explicitly out of scope. Documenting these reinforces the core principle: **lucidscan is a framework that orchestrates scanners, not a scanner itself.**

### 3.1 No Custom Scanning Engines

lucidscan does **not** implement:

- Custom dependency resolution or vulnerability matching (SCA).
- Custom container parsing or SBOM generation.
- Custom static analysis engines or security rules (SAST).
- Custom IaC rule engines or policy languages.

**This is by design.** lucidscan delegates all scanning to plugin scanners (Trivy, OpenGrep, Checkov, etc.) and focuses on orchestration, normalization, and composition. Building custom engines would duplicate existing tools and violate the framework principle.

### 3.2 No Vulnerability Database

lucidscan does **not** maintain:

- A proprietary vulnerability database.
- Manual curation or enrichment of vulnerability data.
- Custom CVE/advisory feeds.

Each scanner plugin is responsible for its own vulnerability data. lucidscan normalizes the output but does not own the data source.

### 3.3 No Dashboard, UI, or Hosted SaaS Platform

lucidscan is **CLI-only** with CI integrations. It does **not** include:

- Web dashboard.
- Project history or vulnerability trends.
- Reporting / governance views.
- Multi-user/team features.

The framework focuses on the core scanning pipeline. Dashboard features may be added in future releases.

### 3.4 No Organizational Policy Engine

lucidscan does **not** implement:

- Policy-as-code beyond scanner-native capabilities.
- License compliance policies.
- Org-wide rulesets for vulnerability acceptance.
- Enforcement on PRs beyond basic exit codes.

Policy enforcement is a future extension, not a core framework concern.

### 3.5 No Auto-Remediation or PR Generation

lucidscan does **not** include:

- Automatic pull request generation.
- Dependency updates.
- Code fix proposals.
- IaC or config file rewrites.

Basic **"fix version available"** hints (from scanner plugins) are surfaced but **not acted upon automatically**. Auto-remediation may be added as an enricher plugin in the future.

### 3.6 No AI-Driven Decisions

Consistent with the "AI-augmented, not AI-driven" principle, lucidscan does **not** include:

- AI-driven triage that changes which issues are surfaced or how they are ordered.
- AI-based cross-project prioritization.
- Autonomous AI agents that modify code, configs, or CI pipelines.

AI enriches findings with explanations and context. AI does not make decisions.

### 3.7 No AI/MCP Server Security Scanning

Although support for AI/MCP configuration scanning is planned for future releases, lucidscan does **not** currently include:

- Parsing MCP configurations.
- Detecting unsafe tool definitions.
- Analyzing AI-agent system boundaries.

This is a future scanner plugin domain, not a core framework feature.

### 3.8 No Enterprise-Grade Features

lucidscan does not currently include:

- RBAC.
- SSO/SAML/OIDC.
- Audit logs.
- Multi-project/org management.
- Compliance reporting.

These may be added once the core framework and plugin ecosystem are validated.

---

## 4. Target Users

lucidscan targets **developers, DevOps engineers, and security practitioners** who need a fast, transparent, open-source security scanning framework that covers code, dependencies, containers, and IaC with minimal setup. The framework is optimized for individuals and small-to-medium teams who want actionable results without the complexity, cost, or overhead of commercial platforms.

### 4.1 Primary Users

#### 4.1.1 Software Developers

Developers who want to:

- Run security scans locally during development.
- Quickly understand vulnerabilities without navigating multiple tools.
- Get clear, low-noise results.
- Avoid slow or heavy CI steps introduced by existing scanners.

**Motivation**: developers want tools that “just work” and don’t slow them down.

#### 4.1.2 DevOps / Platform Engineers

Engineers responsible for:

- Maintaining CI/CD pipelines.
- Managing container images.
- Validating IaC configurations.
- Ensuring security checks run consistently across environments.

**Motivation**: need a tool that is reliable, automation-friendly, and self-hostable.

#### 4.1.3 Security Engineers (AppSec / CloudSec)

Security professionals who:

- Need visibility across code, dependencies, containers, and IaC.
- Want to avoid vendor lock-in or closed-source tools.
- Prefer transparent, auditable scanners.
- Need unified data to build internal dashboards or policies.

**Motivation**: a single consistent source of truth across multiple domains.

### 4.2 Secondary Users

#### 4.2.1 Open Source Maintainers

Developers who maintain packages or infrastructure templates and want:

- Fast scanning before releases.
- SCA + IaC checks across their repos.
- Minimal setup and friction.

#### 4.2.2 Small Security-Focused Consultancies

Consultants who need to:

- Run consistent scanning across client projects.
- Avoid expensive commercial licenses.
- Store results locally for compliance or audit reporting.

### 4.3 Future Users

These users are relevant for product direction but are not the primary targets currently.

#### 4.3.1 Larger Enterprises

Enterprises needing:

- Dashboards.
- SSO/RBAC.
- Compliance reporting.
- Organizational policies.
- Integrations with internal systems.
- Multi-project visibility.

These features will be addressed in future versions.

#### 4.3.2 Teams Using AI/MCP or Advanced SAST

Teams that require:

- AI agent infrastructure scanning.
- SonarQube ingestion.
- AI-based triage or auto-remediation.
- More advanced SAST or custom rule management.

These represent future product expansion areas.

### 4.4 User Assumptions

We assume:

- Users are comfortable running CLI tools and using JSON outputs.
- Users have access to CI/CD and container environments.
- Users understand basic security concepts.
- Users are willing to configure minimal settings (e.g., `.lucidscan.yml`).
- Users accept that lucidscan is a CLI framework (no dashboard).

### 4.5 User Goals Summary

Across all personas, lucidscan helps users:

- Detect vulnerabilities in dependencies, containers, IaC, and code.
- Run everything from **one command and one workflow**.
- Minimize noise and inconsistent results.
- Avoid the overhead and opacity of commercial tools.
- Integrate seamlessly into modern development pipelines.

---

## 5. Core Product Requirements

lucidscan is a plugin-based security scanning framework that orchestrates scanner plugins behind a single CLI and produces consistent, actionable results. The requirements below define the expected behavior of the framework.

### 5.1 General Requirements

#### 5.1.1 Single Command-Line Interface

The product MUST provide one CLI executable that can run:

- SCA scans.
- Container scans.
- IaC scans.
- SAST scans.
- Any combination (e.g., `--all`).

The CLI should follow intuitive, **UNIX-style patterns**.

#### 5.1.2 Consistent Output

All scan results MUST be converted into a unified JSON schema, regardless of scanner source.

Key requirements:

- Normalized severity levels (e.g., `low` / `medium` / `high` / `critical`).
- Consistent field names.
- Consistent structure.
- Ability to emit both **machine-readable and human-friendly output**.
- No underlying scanner’s native format should be exposed to the user unless explicitly requested.

#### 5.1.3 Fast Execution

The framework MUST optimize for minimal scanning time by:

- Reusing scanner binaries when possible.
- Caching scanner downloads.
- Running appropriate scanners only when relevant files are present.

**Goal**: developer-friendly speed, especially in CI.

#### 5.1.4 Exit Codes for CI/CD

The CLI MUST support meaningful exit codes:

- `0` - no issues found.
- `1` - issues found with severity ≥ threshold.
- `2` - internal error.

The **exit code threshold MUST be configurable.**

#### 5.1.5 Local Development Support

The tool MUST work seamlessly in developer environments:

- Local CLI installation.
- Scanning partial directories.
- Ignoring/suppressing findings via config.
- Fast partial scans.

#### 5.1.6 Zero External Dependencies (Except Scanners)

The CLI MUST not require:

- A cloud backend.
- User accounts.
- Internet connectivity (after scanner DB is cached).

### 5.2 SCA Requirements (Default: Trivy Plugin)

#### 5.2.1 Supported Ecosystems

The default SCA plugin (Trivy) MUST support the ecosystems that Trivy supports out-of-the-box, including:

- Node.js (npm, yarn).
- Python (pip, pipenv, poetry).
- Go modules.
- Ruby (bundler).
- Rust (cargo).
- Java JAR-level vulnerability detection.
- Others as supported by Trivy.

#### 5.2.2 Vulnerability Detection

SCA MUST detect:

- Direct dependency vulnerabilities.
- Transitive dependency vulnerabilities.
- Fix versions.
- CVE/OSV/GHSA references.

#### 5.2.3 Output Normalization

SCA results MUST be normalized to common fields such as:

- Package name.
- Installed version.
- Fixed version.
- Severity.
- Dependency path.
- Vulnerability ID.
- Description and links.

### 5.3 Container Scanning Requirements (Default: Trivy Plugin)

#### 5.3.1 Supported Targets

The default container plugin (Trivy) MUST support scanning:

- Local Docker images.
- Remote registry images (Docker Hub, ECR, GCR, etc.).

#### 5.3.2 Vulnerability Detection

Container scanning MUST include:

- OS-level package vulnerabilities.
- Language-level vulnerabilities within container layers.

#### 5.3.3 Output Normalization

Container findings MUST map to unified schema fields like:

- Image reference.
- File/layer path.
- Installed package.
- Severity.
- CVE/OSV/GHSA ID.

### 5.4 IaC Scanning Requirements (Default: Checkov Plugin)

#### 5.4.1 Supported Formats

The default IaC plugin (Checkov) MUST support scanning:

- Terraform.
- Kubernetes manifests.
- CloudFormation.
- Helm templates (where possible).

#### 5.4.2 Detection

IaC scans MUST detect:

- Insecure config patterns.
- Missing encryption.
- Open network access.
- Privilege escalation risks.
- Misconfigured IAM policies.

#### 5.4.3 Output Normalization

IaC results MUST include:

- File and line reference.
- Rule ID.
- Severity.
- Resource name.
- Remediation summary.

### 5.5 SAST Requirements (Default: OpenGrep Plugin)

#### 5.5.1 Supported Languages

The default SAST plugin (OpenGrep) MUST support whatever languages OpenGrep supports in its OSS rulesets.

#### 5.5.2 Rule Selection

The OpenGrep plugin MUST:

- Run with a baseline community ruleset.
- Allow users to override rulesets via config.

#### 5.5.3 Output Normalization

SAST results MUST include:

- Rule ID.
- File and line position.
- Extracted code snippet context.
- Severity.
- Message / description.

### 5.6 Configuration Requirements

#### 5.6.1 Config File

The tool MUST support an optional config file `.lucidscan.yml` including:

- Enabled/disabled scanners.
- Ignore rules.
- Severity threshold.
- Custom OpenGrep ruleset path.
- CI behavior options.

#### 5.6.2 Inline Ignores

The framework MUST support inline ignore annotations (where supported by the underlying scanner), such as:

- OpenGrep inline comments.
- Checkov skip annotations.
- Custom ignore IDs.

### 5.7 Extensibility Requirements

#### 5.7.1 Pluggable Architecture

The system MUST be designed so new scanners can be added with:

- Minimal changes to the core CLI.
- Standard input/output handlers.
- Standardized JSON mapping logic.

#### 5.7.2 No Coupling to Trivy/Checkov/OpenGrep Internals

The integration MUST remain bounded by:

- Calling binaries.
- Using CLI flags.
- Parsing JSON.

This ensures future replacements or alternates (e.g., Grype, tfsec, SonarQube) can be plugged in easily.

### 5.8 Error Handling Requirements

- Meaningful error messages MUST be provided.
- CLI MUST distinguish between scanner failure and scan findings.
- Partial scans MUST still return structured output when possible.

### 5.9 Logging Requirements

The framework MUST support:

- Quiet mode.
- Verbose debug mode.
- Structured logging for CI troubleshooting.

### 5.10 Documentation Requirements

The framework MUST include:

- Installation instructions.
- CLI usage examples.
- Integration examples (GitHub, GitLab).
- Configuration examples.
- Explanation of unified schema.

---

## 6. System Architecture Overview

lucidscan uses a **plugin-based framework** architecture, inspired by the LangChain model. The CLI orchestrates security scanning through **scanner plugins**, where each plugin is responsible for managing its own underlying tool (binary download, caching, execution, output normalization).

There is **no remote scan server**: source code is never uploaded, and all analysis happens on the local filesystem (or inside a CI container). The CLI is installed via `pip install lucidscan` on developer machines. Scanner binaries are downloaded automatically by each plugin on first use.

### 6.1 High-Level Architecture

At a high level, `lucidscan` is a **framework** that orchestrates pluggable scanner and enricher components:

```text
┌─────────────────────────────────────────────────────────┐
│                   lucidscan Framework                   │
├─────────────────────────────────────────────────────────┤
│  CLI Layer                                              │
│  ├── Argument parsing                                   │
│  ├── Configuration loading                              │
│  └── Output formatting                                  │
├─────────────────────────────────────────────────────────┤
│  Pipeline Orchestrator                                  │
│  ├── Plugin discovery & loading                         │
│  ├── Scan context construction                          │
│  ├── Parallel/sequential execution                      │
│  └── Result aggregation                                 │
├─────────────────────────────────────────────────────────┤
│  Scanner Plugins (each manages its own binary)          │
│  ├── TrivyScanner     → downloads/runs trivy binary     │
│  ├── OpenGrepScanner   → downloads/runs opengrep binary   │
│  ├── CheckovScanner   → downloads/runs checkov binary   │
│  └── [Future: SnykScanner, CodeQLScanner, etc.]         │
├─────────────────────────────────────────────────────────┤
│  Enricher Plugins                                       │
│  ├── AIExplainer      → LLM-powered explanations        │
│  ├── CVSSEnricher     → CVSS score lookup               │
│  └── [Future: EPSSEnricher, ReachabilityAnalyzer]       │
├─────────────────────────────────────────────────────────┤
│  Normalization Layer                                    │
│  └── Raw scanner output → Unified Issue Schema          │
├─────────────────────────────────────────────────────────┤
│  Reporter Plugins                                       │
│  ├── JSONReporter                                       │
│  ├── TableReporter                                      │
│  ├── SARIFReporter                                      │
│  └── [Future: HTMLReporter, DashboardReporter]          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│           Local Binary Cache (~/.lucidscan/bin/)        │
├─────────────────────────────────────────────────────────┤
│  trivy/                                                 │
│  ├── 0.68.1/trivy          (version-specific binary)    │
│  └── current -> 0.68.1/    (symlink to active version)  │
│  opengrep/                                               │
│  ├── 1.12.1/opengrep                                     │
│  └── current -> 1.12.1/                                 │
│  checkov/                                               │
│  ├── 3.2.495/checkov                                    │
│  └── current -> 3.2.495/                                │
│  cache/                                                 │
│  └── trivy/db/             (vulnerability database)     │
└─────────────────────────────────────────────────────────┘
```

Key architectural principles:

- **Each scanner plugin is self-contained** - it knows how to download, cache, and invoke its tool.
- **Plugins are composable** - scanners, enrichers, and reporters can be combined in pipelines.
- **No central bundle** - each plugin manages its own binary independently.
- **Version isolation** - multiple versions of a tool can coexist.

### 6.2 CLI & Local Execution Model

The CLI binary (`lucidscan`) acts as the user entry point and is responsible for:

- Parsing command-line flags.
- Loading local and project configuration (e.g., `.lucidscan.yml` in the repo, and optional global settings under `~/.lucidscan/config`).
- Discovering the project root and effective scan set (respecting ignore rules).
- **Loading and initializing scanner plugins** based on configuration.
- Constructing an in-memory `ScanRequest` object (enabled scanners, paths, thresholds).
- Running the **pipeline orchestrator** with selected plugins.
- Rendering the resulting `ScanResult` in the requested output format (JSON, table, summary).
- Setting exit codes based on severity thresholds.

Example CLI usage:

```bash
lucidscan --all
lucidscan --sca --sast
lucidscan --format json
lucidscan --severity-threshold high
```

The CLI is **self-contained**: once scanner binaries have been downloaded by their respective plugins, `lucidscan` does not require any remote server for normal operation.

#### 6.2.1 Plugin Auto-Installation

When a scan requires a scanner plugin that hasn't been used before, the plugin automatically:

1. **Checks for existing binary** in `~/.lucidscan/bin/{tool}/{version}/`.
2. **Downloads if missing** from the tool's official release channel.
3. **Verifies integrity** using checksums where available.
4. **Caches for reuse** across subsequent scans.

This happens transparently on first use:

```bash
$ lucidscan --sca
Downloading trivy v0.68.1... done
Scanning with TrivyScanner...
```

### 6.3 Project Discovery & File Selection

This section describes how the CLI identifies what to scan on the local filesystem. All operations in this section are purely local; no code or metadata is uploaded.

#### 6.3.1 Project Root Identification

On each scan, the CLI MUST:

- **Identify the project root**
  - Start from the current working directory.
  - Optionally use heuristics (e.g., presence of `package.json`, `pyproject.toml`, `.git`, etc.) or an explicit `--project-root` flag.
- **Support monorepos and subdirectories**
  - Allow scanning either the entire repo or a subdirectory (e.g., `lucidscan --path services/api`).

The resolved project root and scan path are passed to the orchestrator and scanner adapters.

#### 6.3.2 Ignore Rules & Effective Scan Set

The CLI computes an **effective scan set** of files and directories by applying multiple layers of ignore rules:

- **Project-level ignore file**
  - Respect a project-specific ignore file (e.g., `.lucidscanignore`) for excluding paths and file patterns from scans.
- **VCS ignores**
  - Fall back to `.gitignore` rules when applicable to avoid scanning build artifacts and generated content.
- **CLI-level excludes**
  - Support additional excludes via flags (e.g., `--exclude node_modules/`, `--exclude dist/`, large binary directories).

Scanner adapters receive only the effective scan set, reducing noise and improving performance.

#### 6.3.3 Security Considerations (Local-Only)

Project discovery and file selection MUST adhere to the following security properties:

- **Local-only analysis**
  - Source code and configuration files are read from the local filesystem (or CI container filesystem) only.
  - No code upload, REST calls with source archives, or remote job submission occurs.
- **Read-only operation**
  - Scanners and the CLI treat the project directory as read-only; they MUST NOT modify code or configuration files.
- **Sensitive content handling**
  - Users can explicitly exclude paths that contain highly sensitive data via `.lucidscanignore` and CLI flags.

### 6.4 Pipeline Orchestrator

The orchestrator is the core control component running **inside the CLI process**. It manages the plugin lifecycle and scan execution pipeline.

#### 6.4.1 Plugin Discovery & Loading

The orchestrator discovers plugins through:

- **Built-in plugins**: `TrivyScanner`, `OpenGrepScanner`, `CheckovScanner` ship with lucidscan.
- **Installed plugins**: Third-party plugins installed via pip (e.g., `pip install lucidscan-snyk`).
- **Entry points**: Plugins register via Python entry points for auto-discovery.

```python
# Example entry point registration in pyproject.toml
[project.entry-points."lucidscan.scanners"]
snyk = "lucidscan_snyk:SnykScanner"
```

#### 6.4.2 Scanner Selection

Based on:

- CLI flags (e.g., `--sca`, `--sast`, `--all`).
- `.lucidscan.yml` configuration.
- Optional automatic project detection (e.g., only run OpenGrep if source files exist).

#### 6.4.3 Building Scan Context

The orchestrator builds a `ScanContext` that includes:

- Target directory / repository path on the local filesystem.
- Effective scan set after ignore rules.
- Config overrides (from CLI and config files).
- Selected scanner plugins and their configuration.
- Environment variables relevant to scanners (e.g., proxy settings).

Note: **Binary paths are managed by each plugin**, not by the orchestrator. Each plugin knows where its binary is cached and how to invoke it.

#### 6.4.4 Executing Scanner Plugins

The orchestrator calls each enabled plugin:

```python
for plugin in enabled_scanners:
    plugin.ensure_binary()  # Download if needed
    result = plugin.scan(context)
    results.append(result)
```

Execution characteristics:

- Scanners MAY be run **in parallel** when system resources allow.
- Each plugin manages its own binary and invocation.
- Plugins that require external services (e.g., Snyk API) handle authentication internally.

#### 6.4.5 Running Enricher Pipeline

After scanning, results pass through enricher plugins:

```python
for enricher in enabled_enrichers:
    results = enricher.enrich(results, context)
```

Enrichers can add AI explanations, CVSS scores, or other metadata.

#### 6.4.6 Collecting Results

The orchestrator collects per-scanner metadata:

- Normalized issues (already in unified schema).
- Scanner versions (from plugin's `get_version()` method).
- Execution time per scanner.
- Exit codes and any error messages.

This data is passed to the selected **Reporter Plugin** for output.

### 6.5 Scanner Plugins

Each scanner is implemented as a **plugin** that implements the `ScannerPlugin` interface. Plugins are self-contained and manage their own binary lifecycle.

#### 6.5.1 Plugin Interface

All scanner plugins implement:

```python
class ScannerPlugin(ABC):
    """Base class for all scanner plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin identifier (e.g., 'trivy', 'opengrep')."""
        
    @property
    @abstractmethod
    def domains(self) -> List[ScanDomain]:
        """Scan domains this plugin supports (SCA, SAST, IAC, CONTAINER)."""
    
    @abstractmethod
    def ensure_binary(self) -> Path:
        """Ensure the scanner binary is available, downloading if needed."""
        
    @abstractmethod
    def get_version(self) -> str:
        """Return the version of the underlying scanner."""
        
    @abstractmethod
    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        """Execute scan and return normalized issues."""
```

#### 6.5.2 `TrivyScanner` Plugin

Handles:

- SCA scans via `trivy fs`.
- Container scans via `trivy image`.

Binary management:

- Downloads from `https://github.com/aquasecurity/trivy/releases/`.
- Caches at `~/.lucidscan/bin/trivy/{version}/trivy`.
- Uses Trivy cache directory at `~/.lucidscan/cache/trivy/`.

```python
class TrivyScanner(ScannerPlugin):
    name = "trivy"
    domains = [ScanDomain.SCA, ScanDomain.CONTAINER]
    default_version = "0.68.1"
    
    def ensure_binary(self) -> Path:
        cache_dir = get_binary_cache() / "trivy" / self.version
        binary = cache_dir / "trivy"
        if not binary.exists():
            self._download_trivy(cache_dir)
        return binary
```

#### 6.5.3 `OpenGrepScanner` Plugin

Handles:

- SAST scanning across supported languages.

Binary management:

- Downloads standalone binary from `https://github.com/opengrep/opengrep/releases/`.
- Caches at `~/.lucidscan/bin/opengrep/{version}/opengrep`.

```python
class OpenGrepScanner(ScannerPlugin):
    name = "opengrep"
    domains = [ScanDomain.SAST]
    default_version = "1.12.1"
```

#### 6.5.4 `CheckovScanner` Plugin

Handles:

- IaC scans for Terraform, Kubernetes, CloudFormation, etc.

Binary management:

- Downloads standalone binary from `https://github.com/bridgecrewio/checkov/releases/`.
- Caches at `~/.lucidscan/bin/checkov/{version}/checkov`.

```python
class CheckovScanner(ScannerPlugin):
    name = "checkov"
    domains = [ScanDomain.IAC]
    default_version = "3.2.495"
```

#### 6.5.5 Binary Download Utility

All plugins share a common binary download utility:

```python
class BinaryManager:
    """Shared utility for downloading and caching scanner binaries."""
    
    def download(self, url: str, dest: Path, executable: bool = True) -> None:
        """Download a file, extract if archive, set permissions."""
        
    def get_platform(self) -> Tuple[str, str]:
        """Return (os, arch) tuple for current platform."""
```

This utility handles:

- Platform detection (darwin/linux/windows, amd64/arm64).
- Archive extraction (tar.gz, zip).
- Executable permissions.
- Checksum verification (where available).

### 6.6 Normalization Layer

Each scanner outputs different JSON schemas, so the normalization layer:

- Converts raw results into a **Unified Issue Schema**.
- Maps severity levels into consistent categories: `low | medium | high | critical`.
- Extracts common fields (rule ID, file, line, message, remediation).
- Preserves scanner-specific metadata under a generic `extra` field.

Example unified issue:

```json
{
  "scanner": "sca",
  "sourceTool": "trivy",
  "id": "CVE-2025-1234",
  "severity": "high",
  "title": "Vulnerability in express",
  "description": "Arbitrary code execution...",
  "location": {
    "file": "package.json",
    "package": "express",
    "version": "4.17.1"
  },
  "remediation": {
    "fixVersion": "4.18.0"
  }
}
```

Each adapter has a corresponding normalization function:

- `normalizeTrivySca()`
- `normalizeTrivyContainer()`
- `normalizeCheckov()`
- `normalizeOpenGrep()`

### 6.7 Aggregation Layer

The aggregation layer merges all normalized issues into a single output.

Responsibilities:

- Combine issues from all scanners.
- Remove duplicates or overlaps where applicable.
- Compute summary statistics:
  - Total issues.
  - Issues per severity.
  - Issues per scanner.
- Attach metadata:
  - Scanner versions.
  - Scan duration.
  - Trivy DB updated timestamp.
- Produce final `ScanResult` object.

Example:

```json
{
  "issues": [],
  "summary": {
    "total": 42,
    "bySeverity": { "critical": 2, "high": 10, "medium": 20, "low": 10 },
    "byScanner": { "sca": 25, "container": 5, "iac": 8, "sast": 4 }
  },
  "metadata": {
    "startedAt": "2025-01-01T10:00:00Z",
    "finishedAt": "2025-01-01T10:00:07Z",
    "durationMs": 7123,
    "scanners": [
      { "name": "trivy", "version": "0.68.1", "dbUpdatedAt": "2025-01-01T07:00:00Z" },
      { "name": "checkov", "version": "3.2.346" },
      { "name": "opengrep", "version": "1.12.1" }
    ]
  }
}
```

### 6.8 AI Enricher Plugin (AIExplainer)

The `AIExplainer` is an **optional enricher plugin** that runs after scanning and before reporting. It enriches unified issues with human-readable explanations and mitigation guidance.

Like all enricher plugins, it implements the `EnricherPlugin` interface:

```python
class AIExplainer(EnricherPlugin):
    name = "ai-explainer"

    def enrich(self, issues: List[UnifiedIssue], context: ScanContext) -> List[UnifiedIssue]:
        """Add AI-generated explanations to each issue."""
```

Responsibilities:

- Take the aggregated issues as input.
- For each issue, generate:
  - A plain-language explanation of the issue and its impact.
  - A short risk summary (why it matters in practice).
  - Concrete mitigation steps (configuration or code-level, where applicable).
- Attach these fields to each issue (e.g., `aiExplanation`, `aiRiskSummary`, `aiMitigationSteps`).

Constraints (consistent with "AI-augmented, not AI-driven" principle):

- The AI enricher is **advisory only** and MUST NOT:
  - Modify source code, configuration, or infrastructure.
  - Change issue severities, filtering, or ordering.
  - Suppress or re-rank issues (see **3.6 No AI-Driven Decisions**).
- The plugin MAY be disabled via configuration (e.g., CLI flag or `.lucidscan.yml`) for offline or air-gapped deployments.
- When disabled, the pipeline skips this enricher and passes issues directly to reporters.

The actual LLM backend (local model vs. remote service) is configured separately and is not coupled to scanner execution.

### 6.9 Reporter Plugins

Reporter plugins convert `ScanResult` (including any enriched fields) into user-facing output formats. Each reporter implements the `ReporterPlugin` interface:

```python
class ReporterPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Reporter identifier (e.g., 'json', 'table', 'sarif')."""

    @abstractmethod
    def report(self, result: ScanResult, output: IO) -> None:
        """Format and write the scan result."""
```

Built-in reporter plugins:

- **JSONReporter**: Full structured output, including AI explanations when present.
- **TableReporter**: Human-friendly table format for terminal output.
- **SARIFReporter**: SARIF format for IDE and CI integrations.
- **SummaryReporter**: High-level stats plus concise advisory text.

Reporter responsibilities:

- Format results according to their output specification.
- Write to stdout or specified file.
- Handle AI-enriched fields when present.

The CLI layer handles:

- Selecting the appropriate reporter based on `--format` flag.
- Applying severity threshold for exit codes.
- Routing output to stdout/stderr or files.

Exit code logic (handled by CLI, not reporters):

- `0` → no issues above threshold.
- `1` → issues found.
- `2` → internal error.

### 6.10 Tool Installation, Local Layout, and Caching

The framework standardizes how scanners are installed and used to maximize reproducibility.

#### 6.10.1 Developer Installation (pip)

On developer machines:

- Users install the CLI via:

  ```bash
  pip install lucidscan
  ```

- This installs only the Python CLI code. On first run of any scanner:
  - The scanner plugin detects OS and architecture (e.g., `linux/amd64`, `darwin/arm64`).
  - Downloads the scanner binary from its official upstream release.
  - Caches the binary under `~/.lucidscan/bin/{tool}/{version}/`.

#### 6.10.2 `~/.lucidscan` Directory Layout

The local binary cache is organized as follows:

- `~/.lucidscan/bin/`
  - `trivy/{version}/trivy` - Trivy binary for the platform.
  - `opengrep/{version}/opengrep` - OpenGrep binary for the platform.
  - `checkov/{version}/checkov` - Checkov binary for the platform.
  - Each tool directory has a `current` symlink pointing to the active version.
- `~/.lucidscan/cache/trivy/`
  - Trivy vulnerability database and related cache files.
- `~/.lucidscan/config/` (optional)
  - Global configuration overrides (e.g., default severity threshold, default scanners).
- `~/.lucidscan/logs/` (optional)
  - Diagnostic and debug logs.

Each scanner plugin manages its own binary version independently. Users can have multiple versions installed simultaneously.

#### 6.10.3 Vulnerability Data & Caching

Vulnerability database management is handled locally by Trivy:

- Trivy stores its DB under `~/.lucidscan/cache/trivy`.
- On first SCA/container scan, Trivy may need to download or update its DB.
- Subsequent scans reuse the cached DB, making runs significantly faster.

Reproducibility considerations:

- `versions.json` pins the compatible scanner versions for a given CLI release.
- The CLI and CI Docker image both reference `versions.json` to ensure consistent behavior across environments.

### 6.11 Docker Image for CI

Developer machines DO NOT need Docker to use `lucidscan`. However, for CI/CD environments, lucidscan provides an official Docker image to ensure fast, reproducible scans without downloading tools on every run.

Characteristics:

- Image name: `ghcr.io/voldeq/lucidscan:latest`.
- Contains:
  - The `lucidscan` CLI.
  - Pre-downloaded Trivy, OpenGrep, and Checkov binaries.
  - Pre-warmed Trivy vulnerability database.

Example CI snippet (generic YAML-style):

```yaml
image: ghcr.io/voldeq/lucidscan:latest

steps:
  - name: Run security scan
    script:
      - lucidscan --all --format json --severity-threshold high
```

Guidance:

- **Developer machines**: install with `pip install lucidscan` and let scanner plugins auto-download binaries.
- **CI environments**: use the official Docker image for zero download overhead and consistent scanner versions.

### 6.12 Extensibility Model and Future Server Mode

The plugin-based architecture treats each scanner as a self-contained plugin with:

- Binary management (download, cache, invoke).
- A normalization function (raw output → unified schema).
- Metadata describing capabilities (domains, versions).

Adding future scanners such as:

- Snyk (SCA, containers).
- CodeQL (SAST).
- Gitleaks (secrets).
- SonarQube (import existing results).

…requires only implementing a new `ScannerPlugin` class. No changes to orchestrator code needed.

Third-party plugins can be published to PyPI and auto-discovered via Python entry points.

lucidscan is **strictly local-only**. A future version may introduce an optional server/orchestrator mode (for centralized scanning, policy enforcement, or large multi-repo environments), but that is out of scope for this design and will not change the core plugin-based framework model described above.

## 7. Data Sources & Vulnerability Ingestion (Plugin-Based Architecture)

In the plugin-based architecture, all scanning, vulnerability ingestion, rule loading, and updates occur locally on the developer's machine. There is no remote server and no code ever leaves the local environment. Each scanner plugin manages its own binary, downloading and caching tools under `~/.lucidscan/bin/`.

The CLI's responsibility is to provide a predictable, reproducible, and self-contained scanning environment with zero external tooling requirements beyond the initial installation of the `lucidscan` Python package.

### 7.1 Overview of Ingestion Model

All vulnerability data comes from the open-source scanning engines that `lucidscan` orchestrates:

- **Trivy**: vulnerability databases for OS packages and SCA.
- **Checkov**: IaC rulepacks for Terraform, Kubernetes, CloudFormation.
- **OpenGrep**: SAST rulesets for source code analysis.

`lucidscan` does not maintain its own vulnerability database. Instead, it relies on the upstream scanners to download and maintain their own rulepacks or vulnerability feeds.

All ingestion processes happen inside the user’s local runtime:

`lucidscan → orchestrator → local tools → raw results → normalization → unified output`

There is no dependency on external APIs, server components, or cloud services.

### 7.2 Tool and Rule Source Breakdown

#### 7.2.1 Trivy (SCA + Container Vulnerabilities)

Trivy loads the following vulnerability feeds locally:

- **OSV (Open Source Vulnerabilities)**.
- **GHSA (GitHub Security Advisories)**.
- **NVD (National Vulnerability Database)**.
- **Linux distribution feeds** (Debian, Alpine, Ubuntu, etc.).
- **Language ecosystem advisories** (npm, PyPI, Go modules, etc.).

Trivy maintains its vulnerability DB under:

- `~/.lucidscan/cache/trivy/db`

`lucidscan` ensures Trivy uses this directory so the DB is downloaded once and reused across all scans.

#### 7.2.2 Checkov (IaC Misconfiguration Analysis)

Checkov uses:

- Built-in IaC policies included in the Checkov distribution.
- Terraform/Kubernetes/CloudFormation schema validation rules.
- No external vulnerability DB.

Checkov’s rules remain static unless the tool itself is updated. `lucidscan` keeps Checkov inside a packaged Python virtual environment to ensure deterministic behavior regardless of the system Python installation.

#### 7.2.3 OpenGrep (SAST Rulesets)

OpenGrep uses:

- Built-in core rules.
- Optionally downloaded community rulepacks.
- Local `.opengrep.yml` files if present.

OpenGrep maintains a small cache for downloaded rulepacks under:

- `~/.lucidscan/cache/opengrep`

Rule ingestion is lightweight and safe to run as part of a local scan.

### 7.3 Ingestion Lifecycle (Local Execution)

The ingestion process per scan follows these steps:

1. **User runs a scan**:

   ```bash
   lucidscan --all
   ```

2. **Each scanner plugin locates or downloads its binary** under:

   - `~/.lucidscan/bin/trivy/{version}/trivy`
   - `~/.lucidscan/bin/opengrep/{version}/opengrep`
   - `~/.lucidscan/bin/checkov/{version}/checkov`

3. **For each scanner**:

   - Trivy updates its local vulnerability DB (unless fresh or explicitly disabled).
   - Checkov loads its built-in rulepacks.
   - OpenGrep loads rulepacks or uses local cached copies.

4. **Each scanner produces raw JSON output.**

5. **`lucidscan` normalizes** the raw results into the unified issue schema.

6. **Final structured output is rendered** in human-readable and/or JSON format.

All work takes place on the local machine (or inside the CI container).

### 7.4 Vulnerability Database Management (Trivy)

Trivy downloads and updates its vulnerability database automatically.

`lucidscan` ensures:

- The DB is cached under `~/.lucidscan/cache/trivy/`.
- The DB is reused across all scans.
- The DB is not downloaded unnecessarily.

Users can optionally disable DB updates:

```bash
lucidscan --skip-db-update
```

The first Trivy run may take several seconds to download the DB; subsequent runs use the cached DB and are fast.

### 7.5 Reproducibility & Version Pinning

To ensure reproducibility:

- `lucidscan` tracks scanner versions in:
  - `~/.lucidscan/config/versions.json`

Each scan result includes metadata such as:

- `lucidscan` version.
- Trivy version and DB update timestamp.
- Checkov version.
- OpenGrep version.

Users can upgrade tools when `lucidscan` is upgraded via:

```bash
pip install --upgrade lucidscan
lucidscan --clear-cache  # Force re-download of scanner binaries
```

This allows consistent results across machines and CI.

### 7.6 Offline & Air-Gapped Support

Because ingestion is local:

- Offline scanning is fully supported once tools and DBs are installed.
- Trivy DB can be pre-fetched and transported manually.
- Checkov and OpenGrep require no network access after installation.
- Companies in air-gapped or regulated environments can use `lucidscan` without modification.
- Organizations that need strict offline readiness can optionally bundle a pre-warmed Trivy DB.

### 7.7 Security & Privacy Considerations

No code ever leaves the local machine.

Because scanning runs locally and ingestion occurs from local caches:

- No code is uploaded anywhere.
- No remote server sees user data.
- No external API calls occur during scanning.
- The only network activity is optional vulnerability DB updates from Trivy’s open-source feeds.

This satisfies:

- Privacy-sensitive users.
- Enterprises with strict policies.
- Offline environments.

### 7.8 Responsibilities Summary

#### 7.8.1 `lucidscan` (CLI) responsibilities

- Manage scanner plugins and their binaries.
- Ensure correct versioning and reproducibility.
- Trigger Trivy / Checkov / OpenGrep with local paths.
- Maintain local caches.
- Normalize results.
- Produce unified output.

#### 7.8.2 External scanner responsibilities

- Download and apply vulnerability feeds (Trivy).
- Provide rulepacks (Checkov, OpenGrep).
- Detect vulnerabilities and misconfigurations.
- Emit machine-readable JSON for `lucidscan`.


## 8. Dependency Resolution Strategy

This section defines how `lucidscan` identifies, resolves, and analyzes open-source dependencies across supported languages and package ecosystems. Consistent with the framework's plugin architecture, all dependency resolution is delegated to the **Trivy scanner plugin**. The framework orchestrates the scan but delegates dependency discovery, graph expansion, and vulnerability matching to Trivy.

The goal is to support multi-language repositories with minimal configuration, predictable performance, and consistent output across environments.

### 8.1 Overview

Dependency resolution determines:

- Which manifests exist in the project.
- What dependencies they declare.
- How transitive dependencies are affected.
- Which vulnerabilities apply to each dependency.

Consistent with the framework's non-goal of **not building custom scanning engines** (see section 3.1), lucidscan delegates all dependency resolution to the Trivy scanner plugin. The plugin uses Trivy's built-in SCA analyzers, which support a wide range of ecosystems.

The framework:

- Discovers relevant manifest files.
- Invokes the Trivy plugin with the correct context.
- Collects Trivy's resolved dependency graph and vulnerability matches.
- Normalizes results into the unified issue schema.

This ensures correctness and full alignment with a trusted, actively maintained vulnerability scanning engine.

### 8.2 Supported Dependency Ecosystems (via Trivy Plugin)

The Trivy plugin supports all ecosystems that Trivy supports. The framework inherits them automatically.

**Package Managers**

- **npm / yarn / pnpm**: `package.json`, `package-lock.json`, `yarn.lock`.
- **Python (pip/poetry)**: `requirements.txt`, `Pipfile.lock`, `poetry.lock`.
- **Ruby (bundler)**: `Gemfile.lock`.
- **Rust**: `Cargo.lock`.
- **Go**: `go.mod` (via module graph resolution).
- **Java**: `pom.xml`, `gradle.lockfile`.
- **PHP**: `composer.lock`.
- **.NET**: `packages.lock.json`.
- And others supported by the current Trivy release.

**Container Base Image Dependencies**

Container scanning also produces dependency insights, but those are handled in the container-scanning sections.

### 8.3 Project Scanning Flow

The dependency resolution flow is:

#### Step 1 - `lucidscan` detects supported manifests

On startup, the CLI recursively searches the project root for known manifest files.

Examples:

- `package.json`
- `yarn.lock`
- `go.mod`
- `Cargo.lock`
- `pom.xml`
- Terraform files (ignored for SCA)

Ignore logic is applied (e.g., skip `node_modules/`, `.lucidscanignore`, `.git/`).

#### Step 2 - The framework invokes the Trivy plugin

The Trivy plugin invokes Trivy in filesystem mode:

```bash
trivy fs --security-checks vuln --format json <project-root>
```

This triggers Trivy's built-in resolvers:

- Ecosystem-specific dependency extraction.
- Graph walking.
- Version normalization.
- (Future) License matching.
- Vulnerability matching via local Trivy DB.

#### Step 3 - Trivy produces a resolved dependency graph

Trivy outputs, for each ecosystem:

- Dependency name.
- Installed version.
- Dependency path/chains.
- Transitive relationships.
- Vulnerability list.
- Fixed version information.

#### Step 4 - The framework normalizes results

Results are mapped into the unified issue schema:

For each vulnerable dependency:

- `scanner`: `sca`.
- `sourceTool`: `trivy`.
- `ecosystem`: `npm` / `python` / `go` / `ruby` / etc.
- Dependency metadata.
- Vulnerability metadata (CVE, severity, fix versions).
- Code location (manifest file path).
- Dependency chain (optional field).

### 8.4 Multi-Language Repository Support

Modern repos may contain:

- Frontend (npm).
- Backend (Python or Go).
- Shared modules.
- Container images.
- IaC.

The Trivy plugin automatically detects each ecosystem independently.

The framework aggregates all dependency issues together into a single final `ScanResult`:

- No configuration required.
- Developers do not need to specify project type.

### 8.5 Handling Multiple Manifests

If multiple manifests of the same type exist (e.g., multiple microservices):

```text
services/
  api/package.json
  worker/package.json
```

The framework:

- Treats each manifest independently.
- Invokes the Trivy plugin once for the entire directory.
- Relies on Trivy to resolve all manifests recursively.
- Keeps issues grouped by manifest path in the normalized output.

This allows monorepos and polyrepos to work seamlessly.

### 8.6 Handling Large Dependency Graphs

Trivy supports:

- Caching.
- Parallel resolution.
- (Future) Incremental scanning.

The framework ensures speed by:

- Using local package manager lockfiles where available (fast path).
- Skipping directories via a unified ignore system.
- Enabling Trivy cache reuse under `~/.lucidscan/cache/trivy/db`.

On large JavaScript or Java projects, caching the Trivy DB locally significantly improves performance.

### 8.7 Limitations & Known Constraints

While the Trivy plugin is powerful, dependency resolution has some natural limitations inherited from Trivy:

1. **Incomplete lockfiles**
   - If a lockfile is missing, Trivy may fall back to best-effort graph generation, which may:
     - Produce partial results.
     - Miss some transitive dependencies.

2. **Non-standard dependency managers**
   - Custom or obscure ecosystems (e.g., Bazel, Buck) may not be supported.

3. **Runtime-only dependencies**
   - Dynamic imports or runtime-installed dependencies (e.g., `pip install` executed inside application code) cannot be accounted for.

4. **Vendor directories**
   - If `vendor/` directories exist, they may be skipped or duplicated unless explicitly excluded.

5. **Git submodules**
   - Trivy scans submodules as normal directories; `lucidscan` requires `.lucidscanignore` to customize behavior.

These limitations should be documented clearly for users.

### 8.8 Reproducibility

Dependency vulnerability results depend on:

- Exact dependency versions (from lockfiles).
- Trivy version.
- Trivy DB updated timestamp.

The framework includes all three in output metadata.

Developers can disable DB updates for audit-mode scans:

```bash
lucidscan --skip-db-update
```

This ensures deterministic scanning.

### 8.9 Future Enhancements

Future improvements may include:

- SBOM generation via the Trivy plugin (CycloneDX / SPDX).
- Enhanced dependency chain visualization.
- License policy enforcement.
- Deeper integration with AI enricher plugins for remediation context.
- More precise reachability analysis (combining SAST + SCA signals via enricher plugins).


## 9. Unified Issue Schema

`lucidscan` integrates multiple heterogeneous security scanners, each producing its own JSON representation, severity conventions, metadata fields, and terminology. To deliver a consistent developer experience and enable future features such as AI explanations, dashboards, and policy enforcement, `lucidscan` normalizes all findings into a **Unified Issue Schema (UIS)**.

The UIS is designed to:

- Represent all scanners uniformly.
- Preserve scanner-specific details.
- Simplify consumption by other tools.
- Support optional future extensions.
- Enable reproducible and machine-readable output.

This section defines the schema used internally and in output formats (e.g., `--format json`).

### 9.1 Design Goals

The schema must support:

- **Cross-scanner compatibility**
  - SAST (OpenGrep), SCA (Trivy), and IaC (Checkov) should be mappable.
- **Minimal but expressive field set**
  - It should be easy to understand and easy to extend.
- **Structured machine-readable data**
  - Required for automation, CI gates, AI remediation, and dashboards.
- **Preservation of original scanner data**
  - To ensure traceability and debugging.
- **Stable and versioned schema**
  - Backward compatibility lives under `schemaVersion`.

### 9.2 Top-Level Structure

Each scan returns a `ScanResult`:

```json
{
  "schemaVersion": "1.0",
  "issues": [ { "...Issue..." } ],
  "metadata": {
    "lucidscanVersion": "0.7.0",
    "trivyVersion": "0.68.1",
    "trivyDbUpdatedAt": "2025-01-10T12:00:00Z",
    "opengrepVersion": "1.12.1",
    "checkovVersion": "3.2.495",
    "scanStartedAt": "...",
    "scanFinishedAt": "...",
    "projectRoot": "/path/to/project"
  }
}
```

The core information resides in the `issues` array.

### 9.3 Issue Object Schema

Each issue conforms to the following structure:

```json
{
  "id": "unique-issue-id",
  "scanner": "sca|sast|iac",
  "sourceTool": "trivy|opengrep|checkov",
  "severity": "critical|high|medium|low|info",
  "title": "...",
  "description": "...",
  "filePath": "src/app/main.py",
  "lineStart": 17,
  "lineEnd": 17,
  "dependency": null,
  "iacResource": null,
  "codeSnippet": null,
  "recommendation": null,
  "scannerMetadata": { }
}
```

Fields vary by scanner type.

### 9.4 Field-by-Field Definition

#### 9.4.1 `id`

A deterministic issue ID, stable across runs when the underlying issue is unchanged.

Generated via hashing:

```text
sourceTool + filePath + lineStart + ruleId + (dependencyName if applicable)
```

#### 9.4.2 `scanner`

High-level category:

- `sca` → Trivy.
- `sast` → OpenGrep.
- `iac` → Checkov.

#### 9.4.3 `sourceTool`

The underlying tool:

- `trivy`
- `opengrep`
- `checkov`

#### 9.4.4 `severity`

Mapped into a unified severity model:

| Scanner | Native severity                  | Mapped        |
|---------|----------------------------------|---------------|
| Trivy   | `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` | same   |
| OpenGrep | `ERROR` / `WARNING` / `INFO`     | `high` / `medium` / `info` |
| Checkov | `HIGH` / `MEDIUM` / `LOW`        | same          |

#### 9.4.5 `title`

Short human-readable summary.

Examples:

- “Vulnerable dependency lodash@4.17.15”.
- “Hardcoded credentials in config file”.
- “Kubernetes Pod allows privilege escalation”.

#### 9.4.6 `description`

Structured explanation extracted from scanner output:

- Vulnerability description.
- Rule description.
- CWE details.
- Dependency vulnerability summary.

This field is **not AI-generated**. AI explanations appear separately.

#### 9.4.7 `filePath`, `lineStart`, `lineEnd`

Where applicable (OpenGrep, sometimes Checkov).

For Trivy/SCA, `filePath` points to the manifest, for example:

- `package.json`
- `requirements.txt`
- `pom.xml`

#### 9.4.8 `dependency` (SCA-only)

Example:

```json
"dependency": {
  "name": "lodash",
  "version": "4.17.15",
  "ecosystem": "npm",
  "manifestPath": "package.json",
  "dependencyChain": ["myapp", "lodash"]
}
```

#### 9.4.9 `iacResource` (IaC-only)

Example:

```json
"iacResource": {
  "resourceId": "aws_security_group.web",
  "resourceType": "security_group",
  "policyId": "CKV_AWS_123",
  "policyTitle": "Ensure security group does not allow ingress from 0.0.0.0/0"
}
```

#### 9.4.10 `codeSnippet` (SAST)

Extracted from local files for context:

```json
"codeSnippet": {
  "language": "python",
  "content": "password = \"12345\""
}
```

#### 9.4.11 `recommendation`

Initial trivial recommendations extracted from scanner output (non-AI), for example:

- “Upgrade lodash to 4.17.21”.
- “Disable privilege escalation in Pod spec”.

#### 9.4.12 `scannerMetadata`

Raw output preserved, but optionally truncated for size:

```json
"scannerMetadata": {
  "ruleId": "PY.SAST.HARDCODED.PASSWORD",
  "cwe": "CWE-259",
  "cvss": 7.5,
  "references": [ ],
  "rawFinding": { }
}
```

This preserves auditability.

### 9.5 Severity Model

Unified model:

- `critical`
- `high`
- `medium`
- `low`
- `info`

This is consistent across scanners and supports threshold-based CI policies, for example:

```bash
lucidscan --fail-on=high
```

### 9.6 Example Unified Issue (SAST)

```json
{
  "id": "opengrep:PY001:/src/app/handlers.py:42",
  "scanner": "sast",
  "sourceTool": "opengrep",
  "severity": "high",
  "title": "Hardcoded credentials detected",
  "description": "Hardcoded values used for authentication.",
  "filePath": "src/app/handlers.py",
  "lineStart": 42,
  "lineEnd": 42,
  "dependency": null,
  "iacResource": null,
  "codeSnippet": {
    "language": "python",
    "content": "api_key = \"secret123\""
  },
  "recommendation": "Move secrets to environment variables or a vault.",
  "scannerMetadata": {
    "ruleId": "python.hardcoded-credentials",
    "cwe": "CWE-798"
  }
}
```

### 9.7 Example Unified Issue (SCA)

```json
{
  "id": "trivy:lodash:4.17.15:critical",
  "scanner": "sca",
  "sourceTool": "trivy",
  "severity": "critical",
  "title": "Vulnerable dependency lodash@4.17.15",
  "description": "lodash versions <4.17.21 contain prototype pollution vulnerabilities.",
  "filePath": "package.json",
  "dependency": {
    "name": "lodash",
    "version": "4.17.15",
    "ecosystem": "npm",
    "manifestPath": "package.json",
    "dependencyChain": ["myapp", "lodash"]
  },
  "recommendation": "Upgrade to lodash>=4.17.21",
  "scannerMetadata": {
    "cve": "CVE-2021-23337",
    "cvss": 9.8,
    "references": [
      "https://nvd.nist.gov/vuln/detail/CVE-2021-23337"
    ]
  }
}
```

### 9.8 Example Unified Issue (IaC)

```json
{
  "id": "checkov:CKV_AWS_23:modules/security/main.tf",
  "scanner": "iac",
  "sourceTool": "checkov",
  "severity": "high",
  "title": "Security Group allows unrestricted ingress",
  "description": "Ensure no security group allows ingress from 0.0.0.0/0.",
  "filePath": "modules/security/main.tf",
  "iacResource": {
    "resourceId": "aws_security_group.web",
    "policyId": "CKV_AWS_23"
  },
  "recommendation": "Restrict ingress to known IP ranges.",
  "scannerMetadata": {}
}
```

### 9.9 Future Extensions to the Schema

Planned extensions:

- `aiExplanation`.
- `fixPatch` (automated patch generation).
- `riskScore` combining CVSS, EPSS, and reachability.
- Evidence nodes for dataflow (future SAST enhancements).

The schema is versioned specifically to allow for backward-compatible growth.


## 10. Packaging & Installation Strategy

`lucidscan` is distributed as a lightweight Python package. Scanner binaries are **not bundled** - instead, each scanner plugin downloads its own binary on first use. This plugin-managed approach provides:

- **Minimal package size** - the pip package is < 1 MB.
- **On-demand installation** - users only download scanners they actually use.
- **Version flexibility** - different projects can use different scanner versions.
- **Simplified builds** - no need to build platform-specific bundles.

The installation strategy is built around three pillars:

- Simple installation via pip.
- Plugin-managed binary downloads on first use.
- Fully self-contained Docker image for CI pipelines.

### 10.0 Build Artifacts Overview

The build process produces a single artifact type:

**Python Package (CLI)**: A lightweight pip-installable package containing the `lucidscan` framework, built-in scanner plugins, and binary management utilities. Published to PyPI.

Scanner binaries are downloaded from their **upstream release channels** (Trivy from GitHub releases, OpenGrep from GitHub releases, Checkov from GitHub releases) by each plugin when first invoked.

### 10.1 Distribution Channels

`lucidscan` is distributed through two official channels.

#### 10.1.1 PyPI (Python Package Index)

Developers install `lucidscan` via:

```bash
pip install lucidscan
```

The PyPI package contains:

- The `lucidscan` CLI entrypoint.
- Pipeline orchestrator and plugin loader.
- Built-in scanner plugins (Trivy, OpenGrep, Checkov).
- Built-in enricher plugins (AIExplainer).
- Binary download and caching utilities.
- Configuration loader.
- Unified schema definitions.

It does **not** contain scanner binaries, keeping the wheel small (target: < 1 MB).

#### 10.1.2 Docker Image (for CI use)

A pre-packaged image is hosted at:

```text
ghcr.io/voldeq/lucidscan:latest
```

This image contains:

- `lucidscan` CLI.
- Pre-downloaded Trivy, OpenGrep, and Checkov binaries.
- Pre-warmed Trivy vulnerability database.
- All dependencies pre-installed.

This ensures extremely fast CI execution with zero download overhead.

### 10.2 Plugin-Managed Binary Installation

Each scanner plugin manages its own binary. When a scan requires a scanner that hasn't been used before, the plugin automatically downloads it.

#### 10.2.1 On-Demand Download Flow

```bash
$ lucidscan --sca
[TrivyScanner] Binary not found, downloading trivy v0.68.1...
[TrivyScanner] Downloading from https://github.com/aquasecurity/trivy/releases/...
[TrivyScanner] Extracting to ~/.lucidscan/bin/trivy/0.68.1/
[TrivyScanner] Download complete (45 MB)
Scanning with TrivyScanner...
```

#### 10.2.2 Platform Detection

Each plugin detects the platform when downloading:

- Operating system: `darwin`, `linux`, `windows`
- Architecture: `amd64`, `arm64`

Plugins use this to construct the correct download URL for upstream releases.

#### 10.2.3 Binary Sources

Each scanner plugin downloads from its **official upstream source**:

| Scanner | Source URL |
|---------|------------|
| Trivy | `https://github.com/aquasecurity/trivy/releases/download/v{version}/trivy_{version}_{os}_{arch}.tar.gz` |
| OpenGrep | `https://github.com/opengrep/opengrep/releases/download/v{version}/opengrep-{version}-{platform}.zip` |
| Checkov | `https://github.com/bridgecrewio/checkov/releases/download/{version}/checkov_{platform}.zip` |

This means lucidscan **does not host any binaries** - it simply orchestrates downloads from official sources.

#### 10.2.4 Verification

After download, plugins verify:

- Binary exists and is executable.
- Binary runs successfully (`{tool} --version`).
- Version matches expected version.

### 10.3 Local Directory Structure

Scanner binaries are cached under `~/.lucidscan/bin/`:

```text
~/.lucidscan/
  bin/
    trivy/
      0.68.1/
        trivy              # Trivy binary
      current -> 0.68.1/   # Symlink to active version
    opengrep/
      1.12.1/
        opengrep            # OpenGrep binary
      current -> 1.12.1/
    checkov/
      3.2.495/
        checkov            # Checkov binary
      current -> 3.2.495/
  cache/
    trivy/
      db/                  # Trivy vulnerability database
  config/
    config.yml             # User configuration overrides
```

Key properties:

- **Version isolation**: Multiple versions can coexist.
- **Per-tool directories**: Each scanner has its own directory.
- **Current symlink**: Points to the default version for each tool.

### 10.4 Version Pinning & Configuration

#### 10.4.1 Default Versions

Each scanner plugin has a **default version** hardcoded in the plugin:

```python
class TrivyScanner(ScannerPlugin):
    default_version = "0.68.1"
```

This default version is updated with each `lucidscan` release.

#### 10.4.2 User Override via Configuration

Users can override scanner versions in `.lucidscan.yml`:

```yaml
scanners:
  trivy:
    version: "0.70.0"     # Use specific version
  opengrep:
    version: "1.150.0"
  checkov:
    version: "latest"     # Always use latest (downloads fresh)
```

Or globally in `~/.lucidscan/config/config.yml`.

#### 10.4.3 Version Command

Users can check installed scanner versions:

```bash
$ lucidscan --version
lucidscan 0.7.0

Scanner versions:
  trivy:   0.68.1 (default)
  opengrep: 1.12.1 (default)
  checkov: 3.2.495 (default)
```

#### 10.4.4 Update Flow

Users update lucidscan itself via pip:

```bash
pip install --upgrade lucidscan
```

Scanner binaries are updated by clearing the cache:

```bash
lucidscan --clear-cache          # Remove all cached binaries
lucidscan --clear-cache trivy    # Remove only trivy
```

On next run, plugins will download fresh binaries with the new default versions.

### 10.5 System PATH Fallback

Plugins check for binaries in this order:

1. **Cached binary**: `~/.lucidscan/bin/{tool}/current/{tool}`
2. **System PATH**: `which {tool}`

This allows users who have scanners pre-installed to use them:

```yaml
# .lucidscan.yml
scanners:
  trivy:
    use_system: true    # Use system-installed trivy instead of downloading
```

### 10.6 Offline / Air-Gapped Support

For environments without internet access, organizations can:

1. **Pre-download binaries** on a connected machine.
2. **Copy to target machines** under `~/.lucidscan/bin/`.
3. **Configure mirror URLs** for internal artifact servers:

```yaml
# ~/.lucidscan/config/config.yml
binary_mirrors:
  trivy: "https://internal-artifacts.mycorp/trivy/{version}/trivy_{platform}.tar.gz"
  opengrep: "https://internal-artifacts.mycorp/opengrep/{version}/opengrep_{platform}.zip"
```

### 10.7 Cross-Platform Support

Scanner plugins support the following platform matrix:

| OS             | Arch    | Notes                              |
|----------------|---------|-----------------------------------|
| Linux          | amd64   | Primary target, used in most CI   |
| Linux          | arm64   | AWS Graviton, Raspberry Pi        |
| macOS          | arm64   | Apple Silicon (M1, M2, M3+)       |
| macOS          | amd64   | Intel Macs (legacy)               |
| Windows        | amd64   | Windows 10+                       |

Each scanner plugin is responsible for detecting the platform and downloading the correct binary. Platform detection is handled by a shared utility:

```python
def get_platform() -> Tuple[str, str]:
    """Return (os, arch) tuple for current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    os_map = {"darwin": "darwin", "linux": "linux", "windows": "windows"}
    arch_map = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}
    
    return os_map[system], arch_map[machine]
```

### 10.8 Build Process & GitHub Actions

The build process is simplified since scanner binaries are downloaded on-demand by plugins.

#### 10.8.1 Python Package Build

The only build artifact is the Python package:

```bash
python -m build
twine upload dist/*
```

The PyPI package contains only the `lucidscan` Python code (< 1 MB) and does not include scanner binaries.

#### 10.8.2 Release Process

On tagged releases (e.g., `v0.7.0`):

1. GitHub Actions runs tests on all supported platforms.
2. The Python package is built and published to PyPI.
3. Docker images are built (with pre-downloaded scanners) and pushed to GHCR.
4. Release notes document the default scanner versions.

Release artifacts:

```text
lucidscan v0.7.0 Release
├── PyPI: lucidscan==0.7.0
├── Docker: ghcr.io/voldeq/lucidscan:0.7.0
└── Release Notes (with default scanner versions)
```

#### 10.8.3 Testing Across Platforms

CI tests run on multiple platforms to ensure scanner plugins correctly download and execute binaries:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python: ["3.10", "3.11", "3.12"]

steps:
  - name: Install lucidscan
    run: pip install -e .
    
  - name: Run integration tests
    run: pytest tests/integration --run-scanners
```

### 10.9 Docker Image for CI (Recommended)

CI environments should use the official Docker image:

```yaml
image: ghcr.io/<org>/lucidscan:latest

script:
  - lucidscan --all --format json
```

Benefits:

- Zero installation time.
- Tools already bundled.
- Trivy DB pre-warmed for instant SCA scans.
- Reproducible across CI providers.
- No dependency on `pip` or Python version in CI.
- Identical behavior between CI and local dev.

Image contents:

```text
/usr/local/lucidscan/
  bin/
    trivy                # Trivy binary
  venv/                  # Python 3.11 virtual environment
    bin/
      python
      opengrep            # pip-installed
      checkov            # pip-installed
  cache/
    trivy/db/            # Pre-warmed vulnerability database
  config/
    versions.json
```

Environment variable:

```bash
export LUCIDSCAN_HOME=/usr/local/lucidscan
```

The Docker image includes pre-downloaded Trivy, OpenGrep, and Checkov binaries plus a pre-warmed Trivy vulnerability database for instant scanning.

### 10.10 Optional Portable Mode

Users can configure a custom binary cache location, bypassing the default `~/.lucidscan/`.

This is useful for:

- CI debugging.
- Ephemeral environments.
- Security-sensitive environments.
- Shared binary caches across teams.

Custom cache location is configured via:

```bash
export LUCIDSCAN_HOME=/path/to/custom/cache
lucidscan --all
```

Or in configuration:

```yaml
# .lucidscan.yml
cache_dir: /path/to/custom/cache
```

### 10.11 Why This Strategy Works

This packaging strategy satisfies all design constraints:

| Requirement                | Achieved by                              |
|---------------------------|-------------------------------------------|
| Zero-setup for developers | `pip install` + auto-download on first use |
| Fast local runs           | Cached binaries + local scanning           |
| Fast CI runs              | Official Docker image                      |
| Reproducible scans        | Version pinning in plugin defaults         |
| Cross-platform            | Per-scanner platform detection             |
| No dependency conflicts   | Tools run from isolated directories        |
| Easy updates              | `pip` upgrade + cache clear                |
| Offline-capable           | Local cache + configurable mirrors         |

This is the simplest and most reliable developer experience possible for a security scanning tool.


## 11. CLI UX & Command Structure

The `lucidscan` CLI is the primary interface through which developers run security scans on their source code, dependencies, Infrastructure-as-Code, and container configurations. It is designed to be:

- **Simple**: one main command (`lucidscan --all`).
- **Fast**: local scanning with cached tools.
- **Uniform**: same commands work in local dev and CI.
- **Predictable**: clear, stable output and exit codes.
- **Scriptable**: machine-readable output for CI.

The CLI is installed via `pip` and runs instantly (scanner binaries are downloaded on first use).

This section defines commands, flags, defaults, and usage patterns.

### 11.1 CLI Principles

- **One-command experience**
  - The default workflow is intentionally minimal:

    ```bash
    lucidscan --all
    ```

- **All scanners optional and configurable**
  - Developers can run specific scanners:
    - SCA only.
    - SAST only.
    - IaC only.

- **Deterministic output**
  - Output formats are stable and versioned.

- **No surprise network calls**
  - Only Trivy DB updates occur unless explicitly disabled.

- **CI-ready**
  - Machine-readable JSON, clean exit codes, optional quiet mode.

- **User-friendly local dev**
  - Colorful terminal output, concise summaries, optional detailed views.

### 11.2 Command Overview

`lucidscan` exposes a single main command with flags:

```bash
lucidscan [OPTIONS]
```

Everything is flag-driven to keep the CLI small and memorable.

**Primary commands & flags**

| Command / Flag               | Description                                              |
|-----------------------------|----------------------------------------------------------|
| `--all`                     | Run all scanners (default behavior).                     |
| `--sca`                     | Run Trivy dependency analysis.                           |
| `--sast`                    | Run OpenGrep static analysis.                             |
| `--iac`                     | Run Checkov IaC scanning.                                |
| `--path <dir>`              | Scan a specific directory (default: current directory).  |
| `--format table|json|sarif` | Select output format.                                    |
| `--fail-on <severity>`      | Exit with non-zero code if issues ≥ severity.           |
| `--skip-db-update`          | Skip Trivy DB update for speed / reproducibility.        |
| `--ignore-file <file>`      | Additional ignore file.                                  |
| `--config <file>`           | Load `.lucidscan.yml` from a custom path.                  |
| `--debug`                   | Verbose logs for troubleshooting.                        |
| `--version`                 | Show tool + scanner versions.                            |
| `--clear-cache [tool]`      | Clear cached scanner binaries.                           |

**Internal maintenance commands** (hidden by default in help):

| Command                 | Purpose                                                     |
|-------------------------|-------------------------------------------------------------|
| `lucidscan doctor`      | Diagnose installation, missing tools, download issues.      |
| `lucidscan cache clean` | Delete cache (Trivy DB, scanner binaries).                  |
| `lucidscan cache path`  | Print cache installation path.                              |
### 11.3 Default Behavior

Running:

```bash
lucidscan
```

is equivalent to:

```bash
lucidscan --all --format table
```

Default includes:

- SCA (Trivy).
- SAST (OpenGrep).
- IaC (Checkov).

Unless overridden in `.lucidscan.yml`.

The scan directory defaults to the current working directory.

### 11.4 Exit Codes

Exit codes are essential for CI/CD.

| Exit code | Meaning                                                            |
|-----------|--------------------------------------------------------------------|
| `0`       | Scan completed with no issues at or above fail threshold.         |
| `1`       | Issues found at or above the severity threshold set by `--fail-on`. |
| `2`       | Scanner failure (OpenGrep/Trivy/Checkov error).                    |
| `3`       | Invalid CLI usage or configuration.                               |
| `4`       | Scanner binary download failure or missing tool.                  |

CI uses:

```bash
lucidscan --fail-on high
```

to block merging changes that introduce serious vulnerabilities.

### 11.5 Output Formats

#### 11.5.1 `table` (default)

Human-friendly summary:

```text
Scanner  Severity  File/Resource                Description
-------- --------  ---------------------------  -------------------------------
SCA      HIGH      package.json > lodash        Prototype pollution vulnerability
SAST     HIGH      src/utils/auth.py:42         Hardcoded credentials detected
IaC      MEDIUM    aws_security_group.web       0.0.0.0/0 ingress rule
```

#### 11.5.2 `json`

Machine-readable output using the Unified Issue Schema:

```bash
lucidscan --format json > results.json
```

Ideal for CI or integration in tools.

#### 11.5.3 `sarif`

Supports GitHub Advanced Security / Azure DevOps integrations:

```bash
lucidscan --format sarif > results.sarif
```

SARIF output maps fields from UIS to SARIF concepts.

### 11.6 Specifying Scanners

Examples:

- Only dependency scan:

  ```bash
  lucidscan --sca
  ```

- Only SAST scan:

  ```bash
  lucidscan --sast
  ```

- SAST + IaC:

  ```bash
  lucidscan --sast --iac
  ```

If neither `--sca`, `--sast`, nor `--iac` is provided, `--all` is assumed.

### 11.7 Specifying Scan Paths

Default is the current directory.

To scan a subfolder:

```bash
lucidscan --path services/api
```

To scan multiple directories:

```bash
lucidscan --path frontend --path backend
```

Paths are aggregated internally and passed to each scanner.

### 11.8 Configuration Resolution

The CLI loads configuration in this order:

1. CLI flags (highest precedence).
2. `.lucidscan.yml` in project root.
3. Global config in `~/.lucidscan/config/user-config.yml`.
4. Built-in defaults (lowest precedence).

Example `.lucidscan.yml`:

```yaml
sca: true
sast: true
iac: false
failOn: medium
ignore:
  - "tests/"
  - "**/*.md"
opengrep:
  ruleset: "p/ci"
```

### 11.9 Ignore System

`lucidscan` uses combined ignore rules from:

- `.lucidscanignore`.
- `.gitignore` (optional, configurable).
- `.lucidscan.yml` `ignore` section.
- CLI flags (`--ignore-file`).

Ignored paths are excluded consistently for all scanners.

### 11.10 Logging & Verbosity

**Normal mode**

- Concise output.
- No raw scanner logs.

**Debug mode**

```bash
lucidscan --debug
```

Shows:

- Full scanner command invocation.
- Tool paths.
- Version information.
- Environment variables used.
- Raw scanner logs.

Used for troubleshooting or reporting issues.

### 11.11 Examples

- **Typical local run**

  ```bash
  lucidscan --all
  ```

- **CI run blocking failures above medium**

  ```bash
  lucidscan --format json --fail-on medium
  ```

- **Skip Trivy DB update for speed**

  ```bash
  lucidscan --sca --skip-db-update
  ```

- **Generate SARIF for GitHub PR annotations**

  ```bash
  lucidscan --all --format sarif > results.sarif
  ```

### 11.12 CLI Help System

```bash
lucidscan --help
```

Displays:

- Intro.
- Usage.
- Main flags.
- Examples.

```bash
lucidscan --help-all
```

Displays:

- Maintenance commands.
- Expert options.
- Environment variables.

This keeps the default help output simple but powerful.

### 11.13 Design for Future Extensions

The CLI is intentionally flat but extensible.

Future subcommands may include:

```bash
lucidscan sbom
lucidscan ai-explain
lucidscan serve   # future self-hosted server mode
```

The framework keeps the experience tight and minimalist.


## 12. Configuration System (`.lucidscan.yml`)

`lucidscan` provides a flexible configuration system that allows developers and teams to customize scanning behavior at the project level and globally across machines. The configuration mechanism is inspired by tools like OpenGrep, ESLint, and Prettier-designed to be simple, predictable, and overrideable by CLI flags.

Configuration can:

- Enable / disable scanners.
- Control severity thresholds.
- Specify ignore rules.
- Configure OpenGrep rulepacks.
- Specify CI behavior.
- Toggle AI explanations.
- Define advanced scanner options.

The CLI loads configuration from three layers, with CLI flags overriding everything.

### 12.1 Configuration Loading Order (Precedence)

Configuration precedence:

1. **CLI flags** (highest priority).
2. **Project-local config**:
   - `<project-root>/.lucidscan.yml`
3. **User-global config**:
   - `~/.lucidscan/config/user-config.yml`
4. **Built-in defaults** (lowest priority).

This ensures:

- Teams can enforce repo settings.
- Users can set personal preferences.
- CLI flags always win (e.g., CI overrides).

### 12.2 Configuration File Format

The configuration file is YAML and supports the following top-level keys:

```yaml
sca: true
sast: true
iac: true

failOn: medium

ignore:
  - "tests/"
  - "*.md"

opengrep:
  ruleset: "p/default"
  additionalRules:
    - "rules/custom-security.yml"

trivy:
  skipDbUpdate: false
  ignoreUnfixed: true

checkov:
  softFail: false
  framework:
    - terraform
    - kubernetes

ai:
  explanations: false

output:
  format: table
```

Every field is optional. `lucidscan` provides sensible defaults.

### 12.3 Core Keys

#### 12.3.1 `sca`, `sast`, `iac`

Boolean values enabling or disabling specific scanners.

Example:

```yaml
sca: true
sast: false
iac: true
```

If none are defined, `--all` is assumed.

#### 12.3.2 `failOn`

Controls exit code severity threshold.

Valid values:

- `critical`
- `high`
- `medium`
- `low`
- `info`
- `none` (always exit 0)

Example:

```yaml
failOn: high
```

Used heavily in CI.

#### 12.3.3 `ignore`

List of file or directory patterns to exclude.

Supports:

- Globs (e.g., `*.md`).
- Directories (e.g., `tests/`).
- Recursive wildcards (e.g., `**/generated/*`).
- Negation rules (e.g., `!src/keep-this.js`).

Example:

```yaml
ignore:
  - "dist/"
  - "**/*.lock"
  - "*.md"
```

These patterns are merged with `.lucidscanignore` (if present).

### 12.4 OpenGrep Configuration

OpenGrep-specific config is nested under `opengrep`.

#### 12.4.1 `ruleset`

One of:

- OpenGrep built-in packs (e.g., `p/security-audit`, `p/r2c`).
- Multiple rulepacks possible.

Example:

```yaml
opengrep:
  ruleset:
    - "p/security-audit"
    - "p/secrets"
```

#### 12.4.2 `additionalRules`

Allows teams to specify project-level rules:

```yaml
opengrep:
  additionalRules:
    - "opengrep/custom/*.yml"
```

#### 12.4.3 `timeout`

Override OpenGrep scan timeout:

```yaml
opengrep:
  timeout: 120
```

### 12.5 Trivy Configuration (SCA)

Trivy-specific settings fall under `trivy`.

#### 12.5.1 `skipDbUpdate`

For speed or reproducibility:

```yaml
trivy:
  skipDbUpdate: true
```

#### 12.5.2 `ignoreUnfixed`

Ignore vulnerabilities without fixes:

```yaml
trivy:
  ignoreUnfixed: true
```

#### 12.5.3 `severity`

Filter severity levels:

```yaml
trivy:
  severity:
    - HIGH
    - CRITICAL
```

### 12.6 Checkov Configuration (IaC)

Checkov options live under `checkov`.

#### 12.6.1 `softFail`

Warn instead of failing the pipeline:

```yaml
checkov:
  softFail: true
```

#### 12.6.2 `framework`

Restrict scanning to specific frameworks:

```yaml
checkov:
  framework:
    - terraform
    - kubernetes
```

#### 12.6.3 `skipChecks`

Ignore specific checks:

```yaml
checkov:
  skipChecks:
    - CKV_AWS_23
    - CKV_GCP_19
```

### 12.7 AI Configuration

The AIExplainer enricher plugin is optional and disabled by default. The configuration schema supports a toggle:

```yaml
ai:
  explanations: true
```

Future versions may support:

- Local caching.
- Remote or LLM API inference.
- Severity-aware explanation.

### 12.8 Output Configuration

Control presentation:

```yaml
output:
  format: json     # json | table | sarif
  colors: true
```

Defaults:

- Local: `table`.
- CI: `json`.

### 12.9 Environment Variables

`lucidscan` respects environment variables for scripting, CI, and automation:

| Variable                | Purpose                                   |
|-------------------------|-------------------------------------------|
| `lucidscan_CONFIG`       | Path to config file.                      |
| `lucidscan_HOME`         | Override default `~/.lucidscan` directory.  |
| `lucidscan_DEBUG`        | Enable debug logs.                        |
| `lucidscan_NO_COLOR`     | Disable colored output.                   |
| `lucidscan_SKIP_DB_UPDATE` | Global override for Trivy DB updates.  |

Example:

```bash
lucidscan_SKIP_DB_UPDATE=1 lucidscan --sca
```

### 12.10 Merging Rules

Configuration merging works as follows:

1. Start with built-in defaults.
2. Overlay global config (`~/.lucidscan/config/user-config.yml`).
3. Overlay project config (`.lucidscan.yml`).
4. Override with CLI flags.

This makes the system predictable and transparent.

### 12.11 Configuration Validation

Invalid configuration entries:

- Generate a clear error.
- List the invalid keys.
- Show examples of correct syntax.

Example:

```text
Invalid key 'scann' in .lucidscan.yml
Did you mean 'sca'?
```

This prevents silent misconfiguration.

### 12.12 Minimal Configuration Example

```yaml
sca: true
sast: true
iac: false
failOn: medium

ignore:
  - "tests/"
```

### 12.13 Full Configuration Example

```yaml
sca: true
sast: true
iac: true

failOn: high

ignore:
  - "dist/"
  - "**/*.md"

opengrep:
  ruleset:
    - "p/security-audit"
    - "p/secrets"
  additionalRules:
    - "rules/custom/*.yml"

trivy:
  skipDbUpdate: false
  ignoreUnfixed: true

checkov:
  softFail: false
  framework:
    - terraform
    - kubernetes
  skipChecks:
    - CKV_AWS_23

ai:
  explanations: true

output:
  format: table
  colors: true
```

## 13. CI/CD Integration

`lucidscan` integrates seamlessly with all major CI/CD systems by providing a fully self-contained Docker image that includes:

- `lucidscan` CLI.
- Trivy, OpenGrep, Checkov (already installed).
- A pre-warmed Trivy DB (optional, configurable).
- Identical directory structure to local installations.

This ensures CI scans are fast, reproducible, and require zero setup: no `pip` installation, no downloading tools inside pipelines, no Python conflicts, and no waiting for scanner downloads.

Local development uses `pip install` with on-demand scanner downloads, whereas CI uses the official container image for maximum speed.

### 13.1 Docker Image Overview

The official CI image is published at:

```text
ghcr.io/<org>/lucidscan:latest
```

It contains:

```text
/usr/local/lucidscan/
  bin/
    trivy                # Trivy binary
  venv/                  # Python 3.11 virtual environment
    bin/
      python
      opengrep            # pip-installed
      checkov            # pip-installed
  cache/
    trivy/db/            # Pre-warmed vulnerability database
  config/
    versions.json
```

Environment variable:

```bash
export LUCIDSCAN_HOME=/usr/local/lucidscan
```

This mirrors `~/.lucidscan` on developer machines.

Benefits:

- Instant SCA scans due to pre-warmed DB.
- Consistent behavior between local and CI.
- No Python or `pip` installation required in CI.
- Minimal pipeline runtime.
- Small and predictable CI footprint.

### 13.2 CI Exit Behavior

CI decisions are controlled by:

```bash
lucidscan --fail-on <severity>
```

Severity levels:

- `critical`
- `high`
- `medium`
- `low`
- `info`
- `none` (never fail)

Exit code behavior:

| Exit Code | Explanation                             |
|-----------|-----------------------------------------|
| `0`       | No issues at or above threshold.       |
| `1`       | Issues found at or above threshold.    |
| `2`       | Scanner execution failed.              |
| `3`       | Invalid usage or configuration.        |
| `4`       | Scanner binary problem (not expected in CI). |

Typical usage:

```bash
lucidscan --all --fail-on high --format json
```

### 13.3 CI Output Formats

**Machine-readable JSON**

Recommended for:

- Artifact storage.
- Report ingestion.
- Dashboards.
- Programmatic parsing.

```bash
lucidscan --format json
```

**SARIF**

For GitHub Advanced Security and other SARIF-compatible systems:

```bash
lucidscan --format sarif > results.sarif
```

CI workflows can annotate pull requests automatically.

### 13.4 GitHub Actions Integration

**Simple integration**

```yaml
name: Security Scan

on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/<org>/lucidscan:latest
    steps:
      - uses: actions/checkout@v4

      - name: Run lucidscan
        run: lucidscan --all --format json --fail-on high
```

**SARIF integration (PR annotations)**

```yaml
- name: Run lucidscan
  run: lucidscan --all --format sarif > results.sarif

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: results.sarif
```

### 13.5 GitLab CI Integration

```yaml
security_scan:
  image: ghcr.io/<org>/lucidscan:latest
  script:
    - lucidscan --all --format json --fail-on high
  artifacts:
    paths:
      - lucidscan-results.json
    reports:
      dotenv: lucidscan-results.json
```

GitLab can also treat the JSON output as a custom vulnerability report.

### 13.6 Bitbucket Pipelines Integration

```yaml
pipelines:
  default:
    - step:
        name: Security Scan
        image: ghcr.io/<org>/lucidscan:latest
        script:
          - lucidscan --all --format json --fail-on high
```

### 13.7 Jenkins / Generic CI Integration

Docker agent example:

```groovy
pipeline {
  agent {
    docker {
      image 'ghcr.io/<org>/lucidscan:latest'
    }
  }
  stages {
    stage('Scan') {
      steps {
        sh 'lucidscan --all --format json --fail-on high'
        archiveArtifacts artifacts: 'results.json', allowEmptyArchive: true
      }
    }
  }
}
```

### 13.8 Caching Considerations

Because all scanners and DBs are pre-downloaded in the Docker image:

- CI pipelines rarely need caching.
- No tool installation is repeated.
- Trivy DB updates occur only at image build time.

If a user wants CI caches anyway:

```yaml
cache:
  key: trivy-db
  paths:
    - /usr/local/lucidscan/cache/trivy/db
```

This is optional.

### 13.9 Monorepo Support

`lucidscan` supports multi-directory scanning:

```yaml
script:
  - lucidscan --path services/api --path services/web --all
```

Or patterns:

```bash
lucidscan --path "services/*" --all
```

You can include multiple job steps or run `lucidscan` in matrix mode in GitHub Actions.

### 13.10 Pull Request Workflow

Recommended PR workflow:

1. Developer pushes feature branch.
2. `lucidscan` runs in CI.
3. If issues ≥ threshold → pipeline fails.
4. SARIF uploaded → GitHub annotates code lines with findings.
5. Developer fixes vulnerabilities.
6. Pipeline passes → PR ready to merge.

This creates a smooth developer security workflow with minimal noise.

### 13.11 Failing the Build on Specific Severity Levels

Examples:

- **Fail on any high/critical issues**

  ```bash
  lucidscan --fail-on high
  ```

- **Fail on medium or above**

  ```bash
  lucidscan --fail-on medium
  ```

- **Don’t fail on anything**

  ```bash
  lucidscan --fail-on none
  ```

This allows security gates to be configured per repo.

### 13.12 CI Time Expectations

- Warm CI image: **1–5 seconds** to run a full scan.
- Without warm DB: **10–20 seconds** for initial run.
- No `pip` installation needed.
- No downloading of tools.
- Extremely predictable and fast.

### 13.13 Recommended CI Patterns

- **Pattern 1 – “Fail early”**
  - Run `lucidscan` as the first job before expensive tests.

- **Pattern 2 – “Security gate before merge”**
  - Only block merging if severity ≥ `high`.

- **Pattern 3 – “Nightly deep scans”**
  - Run `lucidscan --all` on `main` nightly with no thresholds.

- **Pattern 4 – “Allow-listed repos”**
  - Disable scanners selectively via `.lucidscan.yml`.

### 13.14 Future CI Enhancements

Planned for future releases:

- Uploading results to a hosted dashboard.
- Incremental scanning (only changed files).
- Agent-based multi-scan orchestration.
- SAST reachability correlation (SAST + SCA).
- GitHub App for automatic PR comments.


## 14. Logging, Error Handling & Telemetry

`lucidscan` is designed to be a developer-first security tool that behaves predictably, communicates clearly, and provides actionable diagnostics. All logging, errors, and telemetry behaviors are explicitly defined to avoid surprise network calls, noisy output, or unpredictable failure modes.

Guiding principles:

- Fail loudly, but fail clearly.
- Debug logs for developers, silent mode for CI.
- Never phone home without user consent.
- Prefer graceful fallbacks instead of hard crashes.
- Clean exit codes suitable for CI pipelines.

This section defines how `lucidscan` logs, reports errors, and optionally emits anonymous telemetry.

### 14.1 Logging Philosophy

- **Minimal output by default**
  - `lucidscan` only prints essential progress indicators and final results.
- **Developer-friendly formatting**
  - Local runs include color, indentation, and concise text.
- **CI-friendly formatting**
  - When using `--format json` or `--format sarif`, logging is suppressed unless `--debug` is provided.
- **Debug mode provides full insight**
  - Raw scanner process output.
  - Internal decisions (ignore patterns, config path).
  - Scanner binary paths.
  - Timings.

No logs are ever sent to external services (unless telemetry is explicitly enabled by the user).

### 14.2 Logging Levels

`lucidscan` defines three logging modes:

#### Normal Mode (default)

- Minimal console text.
- Colored summary table (unless disabled).
- No raw scanner output.
- Error messages visible.
- Ideal for local development.

#### Quiet / CI Mode

Automatically activated when:

- Output format is `json` or `sarif`, or
- Environment is a non-interactive terminal, or
- `lucidscan_CI=1`.

Behavior:

- No progress logs.
- No colored output.
- Only validated JSON/SARIF printed.
- Errors printed to `stderr` in a predictable format.

#### Debug Mode

Enabled via:

```bash
lucidscan --debug
```

or:

```bash
export lucidscan_DEBUG=1
```

Debug mode includes:

- Full scanner command invocation.
- Tool versions and paths.
- Timing for each scanner.
- Config file resolution.
- Ignore rule evaluation.
- Download status for scanner binaries.
- System information (OS, architecture).

Used for troubleshooting or filing bug reports.

### 14.3 Error Handling Model

`lucidscan` handles three main types of errors:

- **User errors**.
- **Scanner errors**.
- **System/tooling errors**.

Each category has clear messages and structured reporting.

#### 14.3.1 User Errors

Triggered by:

- Invalid flags.
- Invalid configuration keys.
- Nonexistent paths.
- Missing permissions.

Example:

```text
Error: Unknown option '--alll'. Did you mean '--all'?
Exit code: 3
```

`lucidscan` suggests corrections if possible.

#### 14.3.2 Scanner Errors

Triggered when a scanner (Trivy, OpenGrep, Checkov) fails unexpectedly:

- Non-zero exit code from underlying process.
- Missing or corrupted binary.
- Version mismatch.

Examples:

```text
Scanner error (opengrep): process exited with code 2
Checkov failed: invalid Terraform syntax in modules/security/main.tf
```

`lucidscan` includes relevant `stderr` from scanners in debug mode only.

Exit code: `2`.

#### 14.3.3 Scanner Binary Failures

Issues with scanner binary management:

- Download failure (network, server unavailable).
- Corrupted archive extraction.
- Missing expected binary after extraction.
- Wrong architecture binary.
- Checksum mismatch (if enabled).

Example:

```text
lucidscan: Failed to download trivy v0.68.1
Error: Connection timeout
Try: lucidscan --clear-cache trivy
```

Exit code: `4`.

#### 14.3.4 Trivy DB Update Errors

Trivy DB update failures do **not** cause scan failure unless `--require-db-update` is set.

Normal behavior:

- Warn user.
- Continue using cached DB.

Example:

```text
Warning: Unable to update Trivy DB. Using cached DB instead.
```

#### 14.3.5 Graceful Handling of Partial Failures

If one scanner fails but others succeed, `lucidscan`:

- Reports failure in the summary.
- Includes partial results.
- Outputs metadata showing failed scanners.

Example:

```text
Warning: OpenGrep failed, but SCA and IaC scans completed.
```

Whether this fails CI depends on the user’s `--fail-on` threshold.

### 14.4 Error Messages Format

All errors follow a consistent structure:

```text
Error: <short message>

Details:
- <specific reason>
- <path or rule>
- <suggested remediation>

Run with --debug for more details.
```

This avoids cryptic scanner-native errors.

### 14.5 Telemetry (Optional & Disabled by Default)

`lucidscan` values privacy. No telemetry is collected by default.

If enabled manually by the user, telemetry:

- Is 100% anonymous.
- Contains no file paths, code, or dependency names.
- Includes only:
  - `lucidscan` version.
  - Scanner versions.
  - Which scanners were enabled.
  - Runtime duration.
  - Error type (if any).

Enable:

```bash
lucidscan --enable-telemetry
```

Disable:

```bash
lucidscan --disable-telemetry
```

or:

```bash
export lucidscan_TELEMETRY_DISABLED=1
```

All telemetry fields are documented in transparent detail.

### 14.6 Logging Locations

- All logs go to `stdout` or `stderr` by default.
- Optionally, users may configure:

  ```text
  ~/.lucidscan/config/logging.yml
  ```

  to persist logs or write them to a file for debugging.

No logs are ever written silently.

### 14.7 Crash Safety & Recovery

`lucidscan` includes several guardrails to avoid leaving the system in a bad state:

- Temporary directories cleaned on failure.
- Trivy DB corruption autocorrected by forcing re-download.
- Scanner binaries re-downloaded if corruption detected.
- Cache cleared automatically if version mismatch detected.

In worst-case scenarios, `lucidscan` suggests:

```bash
lucidscan --clear-cache
```

or deleting the `~/.lucidscan` directory.

### 14.8 Summary of Guarantees

`lucidscan` guarantees that:

- Scans never silently fail.
- Errors never produce malformed output.
- CI always receives a non-zero exit code on failure.
- Local errors are easy to diagnose.
- Scanner-specific issues are isolated from overall logic.
- Telemetry is off unless explicitly enabled.

This provides a high level of trust and predictability in development and CI workflows.


## 15. AI Enricher Plugin (AIExplainer)

The `AIExplainer` is an **optional enricher plugin** that enhances scan findings by generating clear, actionable, context-aware guidance for developers. It transforms raw scanner results into high-quality narrative explanations that help developers understand what the issue means, why it matters, and how to fix it.

Consistent with the "AI-augmented, not AI-driven" principle (section 1.1), the AIExplainer enriches findings but never alters scanner decisions. The core security scanning remains fully functional without AI, ensuring lucidscan is 100% open source, privacy-preserving, and fully local by default.

### 15.1 Goals

The AIExplainer plugin aims to:

- Provide human-readable descriptions of problems.
- Offer actionable remediation steps with examples.
- Reduce developer time spent interpreting findings.
- Improve onboarding for junior engineers.
- Make security findings more accessible and actionable for all developers.

Like all enricher plugins, AIExplainer operates on the Unified Issue Schema (Section 9).

### 15.2 Non-Goals

Consistent with section 3.6 (No AI-Driven Decisions), the AIExplainer does **not**:

- Alter scanner outputs or severity levels.
- Change issue ordering or filtering.
- Automatically apply fixes.
- Upload any code without explicit permission.
- Operate silently in the background.

The plugin is always explicitly enabled and triggered.

### 15.3 Invocation Methods

AI explanations can be invoked in three ways:

#### 15.3.1 Command-line flag

```bash
lucidscan --all --ai
```

or:

```bash
lucidscan --format json --ai
```

#### 15.3.2 Per-issue explanation

```bash
lucidscan explain <issue-id>
```

#### 15.3.3 Post-processing on result files

```bash
lucidscan explain --input results.json --output explained.json
```

This enables offline re-analysis.

### 15.4 Output Format

Each issue gains an additional field:

```json
"aiExplanation": {
  "short": "This hardcoded credential can be extracted by attackers...",
  "long": "Hardcoded credentials are dangerous because...",
  "fixExample": "For example, you can move the secret to an environment variable...",
  "riskScore": 0.82
}
```

If AI is disabled or not configured, this field is `null` or omitted.

### 15.5 Security & Privacy Model

Fundamental rule:

> No source code or sensitive data is ever sent to an AI provider unless the user explicitly configures API keys and approves usage.

By default:

- AI is disabled.
- No network calls happen.
- No external API is invoked.

When enabled, users select a provider:

- Anthropic.
- OpenAI.
- Local LLM (e.g., Ollama).
- Self-hosted inference server.

Control is via config:

```yaml
ai:
  explanations: true
  provider: "openai"
  apiKey: "env:OPENAI_API_KEY"
  model: "gpt-4.1"
```

### 15.6 Context Passed to the LLM

The AIExplainer plugin prepares a minimal, privacy-conscious prompt containing:

Always included:

- Issue title.
- Issue description.
- Severity.
- Scanner name (SAST, SCA, IaC).
- Dependency name/version (for SCA).
- IaC resource IDs (for Checkov).

Code snippet is **only** included if the user enables snippet sending.

Snippets require explicit opt-in:

```yaml
ai:
  sendCodeSnippets: true
```

Default: `false`. This protects sensitive codebases.

### 15.7 Prompt Design

Example prompt template:

```text
You are a security expert. Given the following vulnerability data from a security scanner,
generate a clear explanation and actionable remediation steps.

Issue:
- Title: {{title}}
- Severity: {{severity}}
- Description: {{description}}
- File: {{filePath}}:{{lineStart}}
- Code Snippet (optional): {{snippet}}

Write:
1. A short summary
2. Why this issue matters
3. The exact steps to fix it
4. A concrete fix example
5. Additional context for developers
```

Prompt templates are versioned and can be updated independently of scanner logic.

### 15.8 Caching & Performance

AI explanations may be slow (1–5 seconds per issue). The plugin provides:

1. **Per-issue caching**

   Cached at:

   ```text
   ~/.lucidscan/cache/ai/<issue-id>.json
   ```

   AI is only re-run when:

   - Issue content changes.
   - Scanner version changes.
   - User clears cache.

2. **Batch requests**

   For JSON output, the plugin can send multiple issues in a single API call (if the provider supports it).

### 15.9 CI Behavior

- CI **never** runs AI explanations by default.

To enable:

```bash
lucidscan --all --ai --format json
```

Use cases:

- Security audits.
- Developer training.
- Nightly reports.

Not recommended for blocking builds.
AI explanations **never** affect exit codes.

### 15.10 Risks & Mitigations

| Risk                             | Mitigation                                      |
|----------------------------------|-------------------------------------------------|
| Users afraid of sending code     | Code not sent unless opted-in explicitly.       |
| High LLM cost                    | Caching + batch mode.                           |
| Low-quality responses            | Curated prompts + feedback loop.                |
| LLM hallucinations               | Present clear disclaimer; avoid auto-fixes.     |
| Vendor lock-in                   | Pluggable provider architecture.                |

### 15.11 Plugin Architecture

The AIExplainer plugin implements the `EnricherPlugin` interface and consists of:

```python
class AIExplainer(EnricherPlugin):
    name = "ai-explainer"

    def enrich(self, issues: List[UnifiedIssue], context: ScanContext) -> List[UnifiedIssue]:
        """Add AI-generated explanations to each issue."""
```

Internal components:

- **Issue Normalizer**
  - Converts unified issues into AI prompt-ready inputs.
- **Provider Adapter** (pluggable)
  - `openai` (HTTP).
  - `anthropic`.
  - Local LLM (Ollama subprocess).
  - Self-hosted inference server.
- **Prompt Composer**
  - Templates per issue type (SAST, SCA, IaC).
- **Response Parser**
  - Converts LLM output into structured fields.
- **Cache Manager**
  - Stores explanations keyed by issue ID + scanner version.

All components run locally inside the CLI process. The plugin receives issues from the pipeline orchestrator and returns enriched issues to the next stage (reporter plugins).

### 15.12 Example Final Output (Human Format)

```text
Issue: Hardcoded credentials detected
Severity: High
Location: src/auth/login.py:27

AI Explanation:
  Hardcoded credentials pose a severe security risk because anyone with access
  to the source code can extract them. Attackers may use them to impersonate
  users or escalate privileges.

  Fix:
    - Move the credential to an environment variable.
    - Use a configuration manager or secrets vault.
    - Rotate the exposed secret.

  Example:
    Replace:
      password = "12345"
    With:
      password = os.environ["APP_PASSWORD"]
```

### 15.13 Example Final Output (JSON)

```json
{
  "id": "opengrep:PY001:/src/auth/login.py:27",
  "scanner": "sast",
  "severity": "high",
  "title": "Hardcoded credentials",
  "aiExplanation": {
    "short": "Hardcoded credentials allow attackers to extract passwords directly from the code.",
    "long": "Embedding credentials in source code exposes them to anyone who has access to the repository...",
    "fixExample": "Use environment variables or a secrets manager...",
    "riskScore": 0.89
  }
}
```

## 16. Future Extensions (Roadmap)

lucidscan is intentionally designed with a **plugin-based framework architecture** (the "LangChain for DevSecOps" model) that can evolve well beyond the initial CLI release. The following roadmap outlines future capabilities that build on the foundation of the plugin framework, unified issue schema, and AI-powered enrichment.

The plugin architecture is **core to the framework** - what follows are extensions that leverage this architecture.

### 16.1 Short-Term Enhancements (1–3 Months After Launch)

#### 16.1.1 Incremental Scanning

Improve performance by scanning only changed files rather than the entire directory.

**Approach:**

- Detect git diff changes.
- Skip unchanged OpenGrep targets.
- Skip unmodified IaC files.
- Allow an `--incremental` flag.

This yields a huge speed win for monorepos.

#### 16.1.2 SBOM Generation

Using Trivy or Syft:

```bash
lucidscan sbom --format cyclonedx
```

Useful for compliance (SLSA, ISO 27001, SOC2).

#### 16.1.3 Enhanced Fix Suggestions (Non-AI)

Improve static remediation recommendations extracted from scanners.

**Examples:**

- Automatic “Upgrade to X version” SCA fixes.
- IaC policy examples.
- SAST inline secure coding patterns.

#### 16.1.4 Policy-as-Code Plugin (Minimal Version)

A lightweight rule definition system for:

- Allowed severity levels.
- Forbidden dependencies.
- Required IaC checks.

Managed through `.lucidscan-policy.yml`.

### 16.2 Medium-Term Features (3–9 Months)
#### 16.2.1 IDE Integrations (VS Code, JetBrains)

Provide:

- Inline SAST findings.
- Hover explanations.
- Quick-fix suggestions.
- Rule suppression features.
- Integration with local `lucidscan` CLI and cached scanners.

Mechanism:

- IDE plugin calls `lucidscan` locally.
- No server required.
- Performance optimized via incremental scanning.

This creates a developer workflow similar to SonarLint or Snyk Code, but fully local.

#### 16.2.2 Dashboard / Web UI (Optional)

A local or server-hosted dashboard to:

- Import JSON scan results.
- Compare runs over time.
- Visualize dependency vulnerabilities.
- Perform team-level reporting.

Modes:

- Local UI (Electron or minimal web server).
- Self-hosted mode: multi-user dashboard.

This provides team visibility while keeping everything self-hosted and open source.

#### 16.2.3 SARIF Rule Mapping Improvements

Better integration with:

- GitHub Advanced Security.
- Azure DevOps.
- SonarQube (via SARIF import).

This increases compatibility with enterprise pipelines.

#### 16.2.4 Third-Party Scanner Plugins

The core plugin architecture enables a rich ecosystem of third-party scanner plugins:

**Community Plugins (Published to PyPI):**

```bash
pip install lucidscan-snyk      # Snyk integration
pip install lucidscan-codeql    # GitHub CodeQL
pip install lucidscan-gitleaks  # Secret detection
pip install lucidscan-bandit    # Python security linter
```

**Custom Corporate Plugins:**

Organizations can create internal scanner plugins:

```python
# my_corp_scanner/plugin.py
from lucidscan.scanners import ScannerPlugin

class CorpSecurityScanner(ScannerPlugin):
    name = "corp-security"
    domains = [ScanDomain.SAST]
    
    def scan(self, context: ScanContext) -> List[UnifiedIssue]:
        # Run internal security checks
        ...
```

**Lightweight Script Adapters:**

For simple integrations, users can wrap shell scripts:

```yaml
# .lucidscan.yml
custom_scanners:
  - name: license-check
    command: ./scripts/check-licenses.sh
    output_format: json
```

#### 16.2.5 Secrets Scanning

Add optional integration with:

- Trivy secrets scanner.
- Gitleaks.
- OpenGrep secrets rules.

Future CLI flag:

```bash
lucidscan --secrets
```

#### 16.2.6 Auto-Fix Mode (Non-AI or AI-Assisted)

Two versions:

- **Non-AI**: apply known dependency upgrades automatically.
- **AI-assisted**: propose git diffs for SAST or IaC fixes.

Delivered via:

```bash
lucidscan fix <issue-id>
lucidscan fix --all
```

AI-assisted auto-fix significantly improves developer productivity.

### 16.3 Long-Term Extensions (9–24 Months)

#### 16.3.1 Self-Hosted Server Mode

A self-hosted server component that supports:

- Team dashboards.
- Policy enforcement.
- Historical scan tracking.
- Multi-repo aggregation.
- Compliance reporting.
- Integration with GitHub/GitLab apps.

Architecture:

- CLI sends results, not code.
- Core scanning remains local to maintain privacy.
- Only metadata is aggregated.
- Fully self-hosted and open source.

#### 16.3.2 Enterprise Self-Hosted Features

Additional self-hosted capabilities for larger teams:

- Centralized configuration.
- Centralized AI inference.
- Aggregated metrics.
- Rule synchronization.
- Caching and artifacts store.

Thick CLI remains available; server mode becomes optional.

#### 16.3.3 Agent-Based Scanning (Distributed)

Ideal for monorepos:

- Break projects into submodules.
- Scan concurrently across agents.
- Aggregate results.

#### 16.3.4 Reachability Analysis (Advanced SAST + SCA Correlation)

Correlate OpenGrep findings with dependency vulnerabilities to reduce noise.

Example:

> “This vulnerable dependency is only reachable through code path X.”

This dramatically reduces false positives and improves the signal-to-noise ratio for developers.

#### 16.3.5 ML-Based Issue Ranking

Use local ML models to compute:

- Exploit likelihood.
- Contextual severity.
- Prioritization scores.

Expose via a `riskScore` field in the Unified Issue Schema.

#### 16.3.6 Organization-Wide Knowledge Graph

For self-hosted server mode, aggregate organization-wide:

- Dependencies.
- IaC resources.
- Code patterns.
- Known vulnerabilities.

Enable organization-wide analysis and advisories.

### 16.4 Vision Summary

`lucidscan` begins as:

- A fast.
- Local.
- Privacy-first.
- Open source.
- Developer-friendly CLI scanner.

The roadmap positions `lucidscan` to evolve into:

- A full security platform.
- With optional AI augmentation.
- Optional self-hosted server mode for teams.
- Wide integration with development ecosystems.

All while remaining fully open source and local-first.