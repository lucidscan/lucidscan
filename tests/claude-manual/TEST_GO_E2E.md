# LucidShark Go Support — End-to-End Test Instructions

**Purpose:** You are performing a comprehensive end-to-end test of LucidShark's Go support. You will test both the CLI and MCP interfaces across all domains, using real open-source Go projects checked out from GitHub. You will test installation, run `lucidshark init`, `autoconfigure`, and exercise every scan domain and MCP tool relevant to Go. At the end, write a detailed test report.

**IMPORTANT:** Execute every step below. Do not skip steps or summarize without actually running the commands. Capture actual output, exit codes, and timings. If a step fails, document the failure in detail and continue with the next step.

---

## 🚨🚨🚨 CRITICAL INSTALLATION REQUIREMENT 🚨🚨🚨

**YOU MUST TEST THE LOCAL DEVELOPMENT VERSION, NOT THE PUBLISHED VERSION!**

**WHY THIS MATTERS:**
- The published version on PyPI (e.g., 0.6.4) does NOT include your latest bug fixes
- Testing the wrong version means you're "going in circles" - testing old bugs you already fixed
- The local development version (check `pyproject.toml`) is the only one that matters

**WHAT YOU MUST DO:**

**Use the universal setup script in Phase 2.3:**
```bash
/Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual/setup-test-installation.sh <project-path>
```

**This script is the SOURCE OF TRUTH for all E2E tests and automatically:**
1. ✅ Builds the PyInstaller binary from local source (same as release process)
2. ✅ Creates venv in project root and installs lucidshark from local source (editable mode)
3. ✅ Copies binary to project root
4. ✅ Verifies ALL versions match the local development version
5. ✅ Fails immediately if any version mismatch is detected

**DO NOT manually install lucidshark - use the script!** It ensures deterministic, reproducible installations.

**If you see version 0.6.4 but local is 0.6.5, you're testing the WRONG version - the script will catch this and stop.**

---

## 🚨 CRITICAL TESTING PHILOSOPHY 🚨

**YOU ARE A QUALITY ASSURANCE ENGINEER, NOT A CHEERLEADER.**

Your job is to **FIND BUGS**, not to confirm that things work.

### Non-Negotiable Testing Rules

1. **EXECUTE EVERY SINGLE STEP** — No exceptions, no shortcuts, no "I already know this works"
2. **TRY TO BREAK THINGS** — Find edge cases, bugs, crashes, incorrect outputs
3. **BE DEEPLY SKEPTICAL** — Question every result, assume bugs exist until proven otherwise
4. **DOCUMENT EVERYTHING IN EXTREME DETAIL** — Raw output, exit codes, exact error messages, file diffs
5. **IF SOMETHING SEEMS OFF, INVESTIGATE RUTHLESSLY** — "Seems to work" is not acceptable
6. **COMPARE ACTUAL VS EXPECTED** — Don't just run commands, verify the results are correct
7. **NO PARTIAL CREDIT** — A test either passes completely or it fails

### What "Execute Every Step" Means

- **COUNT issues**: "found 12 linting issues" NOT "found some issues"
- **QUOTE errors verbatim**: Include the actual error text in your report
- **RECORD exit codes**: Every `lucidshark scan` command must have its exit code documented
- **MEASURE timings**: Use `time` command or record start/end timestamps
- **VERIFY with actual data**: Read files, diff outputs, check specific line numbers
- **No vague language**: Replace "seems to work", "probably correct", "looks good" with actual measurements

### Success vs Failure

**❌ FAILURE:**
- "The scan completed successfully" (no data provided)
- "Found some issues" (no count, no specifics)
- "⏳ Test incomplete due to time constraints" (unacceptable excuse)
- "Skipping this test because..." (no, run the test)
- "Seems to work fine" (prove it with data)

**✅ SUCCESS:**
- "golangci-lint found exactly 15 issues: 8 from golint, 4 from govet, 3 from errcheck. Exit code: 1. Runtime: 3.2s"
- "go test ran 47 tests, 45 passed, 2 failed (TestHandler and TestDB). Exit code: 1. See full output below: [paste output]"
- "Compared MCP scan() output vs CLI scan output: IDENTICAL (0 discrepancies)"
- "BUG FOUND: apply_fix() changed 5 files but only 3 had issues. Files X and Y were incorrectly modified."

### Your Mission

At the end of this test, the user should be able to:
- **Trust that LucidShark works correctly for Go** (if your verdict is ✅ PASS)
- **Know exactly what's broken** (if your verdict is ❌ FAIL)
- **Reproduce any bug you found** (with exact steps and data)

**If you wouldn't trust this software in production based on your testing, say so.**

---

**Go Tools Under Test:**

| Domain | Tool | Binary |
|--------|------|--------|
| Linting | golangci-lint | `golangci-lint` |
| Type Checking | go vet | `go vet` |
| Formatting | gofmt | `gofmt` |
| Testing | go test | `go test` |
| Coverage | go cover | `go test -coverprofile` |
| SAST (Go-specific) | gosec | `gosec` |
| SAST (cross-language) | OpenGrep | `opengrep` |
| SCA | Trivy | `trivy` |
| Duplication | Duplo | `duplo` |

---

## Phase 0: Environment Setup

### 0.1 Record Environment Info

```bash
uname -a
go version
golangci-lint --version 2>/dev/null || echo "golangci-lint not installed"
gosec -version 2>/dev/null || echo "gosec not installed"
gofmt -e /dev/null 2>&1 && echo "gofmt available" || echo "gofmt not available"
git --version
echo "Disk space:" && df -h .
echo "Working directory:" && pwd
echo "GOPATH:" && go env GOPATH
echo "GOROOT:" && go env GOROOT
```

Record all output in the test report under "Environment".

### 0.2 Create Clean Test Workspace

```bash
export TEST_WORKSPACE="/tmp/lucidshark-go-e2e-$(date +%s)"
mkdir -p "$TEST_WORKSPACE"
cd "$TEST_WORKSPACE"
echo "Test workspace created at: $TEST_WORKSPACE"
```

**📁 IMPORTANT: Workspace Isolation**

All subsequent work happens inside `$TEST_WORKSPACE`. Do NOT use any pre-existing LucidShark installation.

**Everything runs in the `/tmp` folder:**
- All real-world projects are cloned to: `$TEST_WORKSPACE/<project-name>/`
- The artificial test project is created at: `$TEST_WORKSPACE/test-project/`
- Installation tests happen in: `$TEST_WORKSPACE/install-*/`
- **Nothing touches your actual workspace or home directory**
- The entire test environment is isolated and can be safely deleted after testing

---

## Phase 1: Install Go Tools

Ensure all Go tools are available:

```bash
# golangci-lint (required for linting domain)
go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
golangci-lint --version

# gofmt ships with Go — verify
which gofmt
gofmt --help 2>&1 | head -5

# go vet ships with Go — verify
go vet --help 2>&1 | head -5
```

**Verify:**
- [ ] `golangci-lint` installed and on PATH (or at `~/go/bin/golangci-lint`)
- [ ] `gofmt` available (ships with Go)
- [ ] `go vet` available (ships with Go)


---

## Phase 2: Test Project Setup

### 2.1 Clone Test Projects from GitHub

Clone these real-world Go projects. Each serves a different test purpose:

```bash
cd "$TEST_WORKSPACE"

# Project 1: Gin — popular HTTP web framework, clean code, good tests
git clone --depth 1 https://github.com/gin-gonic/gin.git

# Project 2: Cobra — CLI framework, well-structured, widely used
git clone --depth 1 https://github.com/spf13/cobra.git

# Project 3: GoFiber — Express-inspired web framework, active development
git clone --depth 1 https://github.com/gofiber/fiber.git

# Project 4: Hugo — large Go codebase, complex project structure
git clone --depth 1 https://github.com/gohugoio/hugo.git
```

**Verify all projects cloned successfully:**
```bash
ls -la "$TEST_WORKSPACE"
echo ""
echo "Expected directories:"
echo "  - gin/"
echo "  - cobra/"
echo "  - fiber/"
echo "  - hugo/"
```

**Verify:**
- [ ] All four project directories exist in `$TEST_WORKSPACE`
- [ ] Each directory contains a git repository (`.git/` folder)
- [ ] Each directory is inside `/tmp/lucidshark-go-e2e-*/`

**Why these projects:**
- **Gin**: Standard HTTP framework, moderate size, well-tested — baseline for linting/type-checking
- **Cobra**: CLI library, different code patterns (code generation, templates)
- **GoFiber**: Modern Go patterns, extensive test suite, good coverage target
- **Hugo**: Very large Go codebase, tests timeout/performance handling

### 2.2 Create Custom Vulnerable Test Project

This project has intentional issues across ALL domains for comprehensive testing:

```bash
mkdir -p "$TEST_WORKSPACE/test-project/cmd/myapp"
mkdir -p "$TEST_WORKSPACE/test-project/internal/handlers"
mkdir -p "$TEST_WORKSPACE/test-project/internal/models"
mkdir -p "$TEST_WORKSPACE/test-project/internal/utils"
cd "$TEST_WORKSPACE/test-project"
git init
```

**Create `go.mod`:**
```go
module github.com/test/test-project

go 1.21

require (
	github.com/gin-gonic/gin v1.7.0
	github.com/mattn/go-sqlite3 v1.14.6
	golang.org/x/crypto v0.0.0-20210322153248-0c34fe9e7dc2
	gopkg.in/yaml.v2 v2.2.2
)
```

**Create `go.sum`:** (empty — will be populated by `go mod tidy`)
```bash
touch go.sum
```

**Create `cmd/myapp/main.go`** (linting + formatting + vet issues):
```go
package main

import (
	"fmt"
	"os"
	"sync"
	"unsafe"
)

func main() {
	fmt.Println("Hello World")
	processData("test")
}

// Unused function (linting issue)
func unusedFunction() string {
	return "never called"
}

// Bad formatting: inconsistent spacing, wrong indentation
func processData(  data string  ) string {
    x := 123
    _ = x
    result := fmt.Sprintf( "%s processed",data  )
    return result
}

// go vet issue: Printf format mismatch
func printUser(name string, age int) {
	fmt.Printf("Name: %d, Age: %s\n", name, age) // wrong format verbs
}

// go vet issue: copying a lock
func copyLock() {
	var mu sync.Mutex
	mu2 := mu // copies lock value
	_ = mu2
}

// go vet issue: unreachable code
func unreachable() int {
	return 42
	fmt.Println("this is unreachable") // unreachable
	return 0
}

// go vet issue: unsafe pointer conversion
func unsafePointer() {
	var x int = 42
	p := unsafe.Pointer(&x)
	_ = p
}

// Unused variable (linting issue)
var globalUnused = "unused"

// Shadowed error (linting issue)
func shadowedErr() error {
	err := fmt.Errorf("first error")
	if true {
		err := fmt.Errorf("shadowed error")
		_ = err
	}
	return err
}

// Missing error check (errcheck linting issue)
func missingErrCheck() {
	f, _ := os.Open("nonexistent.txt")
	f.Close() // error not checked
}
```

**Create `internal/handlers/handler.go`** (SAST issues):
```go
package handlers

import (
	"crypto/md5"
	"database/sql"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
)

// SQL Injection — string concatenation in query
func GetUser(db *sql.DB, username string) (*sql.Row, error) {
	query := "SELECT * FROM users WHERE name = '" + username + "'"
	row := db.QueryRow(query)
	return row, nil
}

// Command Injection — user input in exec.Command
func RunCommand(w http.ResponseWriter, r *http.Request) {
	cmd := r.URL.Query().Get("cmd")
	out, err := exec.Command("sh", "-c", cmd).Output()
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	w.Write(out)
}

// Weak Crypto — MD5 for passwords
func HashPassword(password string) string {
	hash := md5.Sum([]byte(password))
	return fmt.Sprintf("%x", hash)
}

// Hardcoded Secret
const APIKey = "sk-1234567890abcdef1234567890abcdef"
const DatabasePassword = "super_secret_password_123"

// Path Traversal — unsanitized user input in filepath
func ServeFile(w http.ResponseWriter, r *http.Request) {
	filename := r.URL.Query().Get("file")
	path := filepath.Join("/var/data", filename)
	http.ServeFile(w, r, path)
}

// Unvalidated redirect
func Redirect(w http.ResponseWriter, r *http.Request) {
	target := r.URL.Query().Get("url")
	http.Redirect(w, r, target, http.StatusFound)
}

// SSRF potential
func FetchURL(w http.ResponseWriter, r *http.Request) {
	url := r.URL.Query().Get("url")
	resp, err := http.Get(url)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	defer resp.Body.Close()
	w.WriteHeader(resp.StatusCode)
}

// Insecure file permissions
func WriteConfig(data []byte) error {
	return os.WriteFile("/tmp/config.txt", data, 0777)
}
```

**Create `internal/models/user.go`** (type issues + linting):
```go
package models

import "fmt"

// User represents a user in the system.
type User struct {
	Name  string
	Email string
	Age   int
}

// Validate has a type consistency issue
func (u *User) Validate() (bool, string) {
	if u.Name == "" {
		return false, "name required"
	}
	if u.Age < 0 {
		return false, "invalid age"
	}
	return true, ""
}

// String returns string representation
func (u *User) String() string {
	return fmt.Sprintf("User{Name: %s, Email: %s, Age: %d}", u.Name, u.Email, u.Age)
}

// Dead code - exported but never used outside package
func HelperNeverCalled() {
	x := 1
	y := 2
	_ = x + y
}
```

**Create `internal/utils/duplicate1.go`** (duplication detection):
```go
package utils

import "math"

// CalculateStatistics computes stats on a slice of float64.
func CalculateStatistics(numbers []float64) map[string]float64 {
	if len(numbers) == 0 {
		return map[string]float64{
			"mean": 0, "total": 0, "count": 0, "min": 0, "max": 0,
		}
	}
	total := 0.0
	for _, n := range numbers {
		total += n
	}
	count := float64(len(numbers))
	mean := total / count
	minimum := numbers[0]
	maximum := numbers[0]
	for _, n := range numbers {
		if n < minimum {
			minimum = n
		}
		if n > maximum {
			maximum = n
		}
	}
	variance := 0.0
	for _, n := range numbers {
		variance += math.Pow(n-mean, 2)
	}
	variance /= count
	stdDev := math.Sqrt(variance)
	return map[string]float64{
		"mean": mean, "total": total, "count": count,
		"min": minimum, "max": maximum,
		"variance": variance, "std_dev": stdDev,
	}
}
```

**Create `internal/utils/duplicate2.go`** (near-duplicate of duplicate1.go):
```go
package utils

import "math"

// ComputeStatistics computes stats on a slice of float64.
func ComputeStatistics(values []float64) map[string]float64 {
	if len(values) == 0 {
		return map[string]float64{
			"mean": 0, "total": 0, "count": 0, "min": 0, "max": 0,
		}
	}
	total := 0.0
	for _, v := range values {
		total += v
	}
	count := float64(len(values))
	mean := total / count
	minimum := values[0]
	maximum := values[0]
	for _, v := range values {
		if v < minimum {
			minimum = v
		}
		if v > maximum {
			maximum = v
		}
	}
	variance := 0.0
	for _, v := range values {
		variance += math.Pow(v-mean, 2)
	}
	variance /= count
	stdDev := math.Sqrt(variance)
	return map[string]float64{
		"mean": mean, "total": total, "count": count,
		"min": minimum, "max": maximum,
		"variance": variance, "std_dev": stdDev,
	}
}
```

**Create `cmd/myapp/main_test.go`:**
```go
package main

import (
	"testing"
)

func TestProcessData(t *testing.T) {
	result := processData("hello")
	expected := "hello processed"
	if result != expected {
		t.Errorf("processData(\"hello\") = %q, want %q", result, expected)
	}
}

func TestShadowedErr(t *testing.T) {
	err := shadowedErr()
	if err == nil {
		t.Error("expected non-nil error")
	}
	if err.Error() != "first error" {
		t.Errorf("expected 'first error', got %q", err.Error())
	}
}

func TestUnreachable(t *testing.T) {
	result := unreachable()
	if result != 42 {
		t.Errorf("unreachable() = %d, want 42", result)
	}
}

// This test will fail intentionally
func TestFailingTest(t *testing.T) {
	result := processData("fail")
	if result != "FAIL PROCESSED" {
		t.Errorf("processData(\"fail\") = %q, want %q", result, "FAIL PROCESSED")
	}
}

func TestPassing1(t *testing.T) {
	if 1+1 != 2 {
		t.Error("math is broken")
	}
}

func TestPassing2(t *testing.T) {
	s := "hello"
	if len(s) != 5 {
		t.Errorf("len(%q) = %d, want 5", s, len(s))
	}
}
```

**Create `internal/models/user_test.go`:**
```go
package models

import "testing"

func TestUserValidate(t *testing.T) {
	tests := []struct {
		name     string
		user     User
		valid    bool
		message  string
	}{
		{"valid user", User{Name: "Alice", Email: "alice@example.com", Age: 30}, true, ""},
		{"empty name", User{Name: "", Email: "test@test.com", Age: 25}, false, "name required"},
		{"negative age", User{Name: "Bob", Email: "bob@test.com", Age: -1}, false, "invalid age"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			valid, msg := tt.user.Validate()
			if valid != tt.valid {
				t.Errorf("Validate() valid = %v, want %v", valid, tt.valid)
			}
			if msg != tt.message {
				t.Errorf("Validate() message = %q, want %q", msg, tt.message)
			}
		})
	}
}

func TestUserString(t *testing.T) {
	u := User{Name: "Alice", Email: "alice@test.com", Age: 30}
	s := u.String()
	if s == "" {
		t.Error("String() returned empty string")
	}
}
```

Commit everything:
```bash
cd "$TEST_WORKSPACE/test-project"
git add -A && git commit -m "Initial commit with intentional issues"
```

**Note:** The `go.mod` requires modules that may not resolve. Run `go mod tidy` — if it fails, simplify `go.mod` to only use stdlib:

```bash
cd "$TEST_WORKSPACE/test-project"
go mod tidy 2>&1 || echo "go mod tidy failed — may need to simplify deps"
```

If `go mod tidy` fails, replace `go.mod` with:
```go
module github.com/test/test-project

go 1.21
```
And remove external imports from handler.go (keep only stdlib). Then re-commit.

---

### 2.3 Install LucidShark in Test Project Using Setup Script

**🚨 CRITICAL: Use the Universal Setup Script**

All E2E tests (Go, Python, Java, JavaScript, etc.) MUST use the universal setup script located at:
`/Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual/setup-test-installation.sh`

This script is the **SOURCE OF TRUTH** for E2E test installations. It ensures deterministic, reproducible installations across all language tests.

#### 2.3.1 Run the Setup Script

```bash
cd /Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual
./setup-test-installation.sh "$TEST_WORKSPACE/test-project"
```

**What the script does:**
1. Builds PyInstaller binary from local source (cached in /tmp for speed)
2. Copies binary to `$TEST_WORKSPACE/test-project/lucidshark`
3. Creates venv at `$TEST_WORKSPACE/test-project/.venv`
4. Installs lucidshark from local source in editable mode
5. Verifies ALL versions match the local development version

**Expected output:**
```
[INFO] LucidShark E2E Test Installation Setup
[INFO] ========================================
[INFO] Local development version: 0.6.5
[SUCCESS] Binary verified: version 0.6.5
[SUCCESS] Binary copied to .../test-project/lucidshark (version 0.6.5)
[SUCCESS] Pip installation verified: version 0.6.5
[SUCCESS] ✅ All versions match! Installation successful.
```

**Verify:**
- [ ] Script completes without errors
- [ ] All three versions (local, binary, pip) match
- [ ] Binary exists at `$TEST_WORKSPACE/test-project/lucidshark`
- [ ] Venv exists at `$TEST_WORKSPACE/test-project/.venv`

**If the script fails:** DO NOT PROCEED. Debug and fix the installation issue first.

#### 2.3.2 Activate the Venv for Testing

**For all remaining tests in Phase 3-9, use the PIP installation (keep .venv activated):**

```bash
cd "$TEST_WORKSPACE/test-project"
source .venv/bin/activate
```

**Reason:** Pip editable install ensures any code changes during testing are immediately reflected without reinstalling.

---

## Phase 3: Init & Configuration Testing

### 3.1 Test `lucidshark init` on Test Project

```bash
cd "$TEST_WORKSPACE/test-project"
```

#### 3.1.1 Init Dry Run
```bash
lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files WOULD be created without creating them
- [ ] Lists: `.mcp.json`, `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/skills/lucidshark/SKILL.md`
- [ ] No files actually created (check with `ls -la .mcp.json .claude/ 2>/dev/null`)

#### 3.1.2 Init (Full)
```bash
lucidshark init
```

**Verify:**
- [ ] `.mcp.json` created with correct MCP server config
- [ ] `.claude/CLAUDE.md` created with lucidshark instructions (check for `<!-- lucidshark:start -->` markers)
- [ ] `.claude/settings.json` created with PostToolUse hooks
- [ ] `.claude/skills/lucidshark/SKILL.md` created
- [ ] Read each file and verify contents are sensible

```bash
cat .mcp.json
cat .claude/CLAUDE.md
cat .claude/settings.json
cat .claude/skills/lucidshark/SKILL.md
```

#### 3.1.3 Init Re-run (Should Detect Existing)
```bash
lucidshark init
```

**Verify:**
- [ ] Detects existing configuration
- [ ] Suggests `--force` to overwrite
- [ ] Does NOT overwrite existing files

#### 3.1.4 Init Force
```bash
lucidshark init --force
```

**Verify:**
- [ ] Overwrites all files successfully
- [ ] Files are identical or updated versions

#### 3.1.5 Init Remove
```bash
lucidshark init --remove
```

**Verify:**
- [ ] All LucidShark artifacts removed
- [ ] `.mcp.json` is `{}` (empty object) or removed
- [ ] `.claude/CLAUDE.md` has lucidshark section removed
- [ ] `.claude/settings.json` has lucidshark hooks removed
- [ ] `.claude/skills/lucidshark/` removed

Re-run init for remaining tests:
```bash
lucidshark init
```

### 3.2: End-to-End Autoconfiguration Testing

**CRITICAL:** Test complete autoconfiguration workflow from detection to validation to execution. Do NOT use pre-written configs.

---

### 3.2.1 Autoconfigure Real-World Project: Gin (Go web framework)

**Objective:** Test autoconfiguration on popular Go web framework.

#### Step 1: Call Autoconfigure MCP Tool
```bash
cd "$TEST_WORKSPACE/gin"
```
```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Mentions detecting Go from go.mod
- [ ] Mentions golangci-lint for linting
- [ ] Mentions go vet for type checking
- [ ] Mentions go test for testing
- [ ] Includes example configs for Go projects
- [ ] Mentions vendor/ exclusion

#### Step 2: Detect Project Tools

```bash
# Check for Go module
ls -la go.mod go.sum 2>/dev/null
cat go.mod | head -10

# Check for test files
find . -name '*_test.go' 2>/dev/null | head -10

# Check for golangci-lint config
ls -la .golangci.yml .golangci.yaml 2>/dev/null

# Check if golangci-lint is installed
which golangci-lint
golangci-lint --version 2>/dev/null || echo "Not installed"
```

**Record findings:**
- [ ] Go module detected: _____________ (yes/no)
- [ ] Test files found: _____________ (count)
- [ ] golangci-lint installed: _____________ (yes/no)
- [ ] golangci-lint config exists: _____________ (yes/no)

#### Step 3: Install Missing Tools

```bash
# Install golangci-lint if not present
which golangci-lint || go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest

# Verify installation
which golangci-lint
golangci-lint --version
```

**Verify:** [ ] golangci-lint installed and in PATH

#### Step 4: Generate lucidshark.yml Based on Detection

**IMPORTANT:** Go has limited built-in LucidShark plugin support. Use 'command' field for integration.

```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: gin
  languages: [go]

pipeline:
  linting:
    enabled: true
    command: "golangci-lint run ./..."

  type_checking:
    enabled: true
    command: "go vet ./..."

  testing:
    enabled: true
    command: "go test -v ./..."

  coverage:
    enabled: true
    command: "go test -coverprofile=coverage.out ./... && go tool cover -func=coverage.out"
    threshold: 70

  duplication:
    enabled: true
    tools: [duplo]
    threshold: 5.0
    min_lines: 7

  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: gosec
        domains: [sast]

fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/vendor/**"
EOF
```

#### Step 5: Validate Configuration

```bash
lucidshark validate
echo "Validation exit code: $?"
```

**Verify:**
- [ ] Exit code 0 (valid)
- [ ] No validation errors
- [ ] Custom commands accepted

#### Step 6: Test Generated Config

**Test linting:**
```bash
lucidshark scan --linting --format ai 2>&1 | head -30
```

**Verify:**
- [ ] golangci-lint executes via custom command
- [ ] Linting issues reported (or passes)

**Test type checking:**
```bash
lucidshark scan --type-checking --format ai 2>&1 | head -30
```

**Verify:**
- [ ] go vet executes via custom command

**Test testing:**
```bash
lucidshark scan --testing --format ai 2>&1 | head -30
```

**Verify:**
- [ ] go test executes
- [ ] Test results reported

**Test exclusions:**
```bash
lucidshark scan --duplication --all-files --format ai 2>&1 | grep -c 'vendor/'
echo "vendor/ files scanned (should be 0): $?"
```

**Verify:**
- [ ] vendor/ NOT scanned

---

### 3.2.2 Autoconfigure Real-World Project: Cobra (CLI library)

**Objective:** Test on popular Go CLI framework.

```bash
cd "$TEST_WORKSPACE/cobra"

# Detect project
cat go.mod | head -5
find . -name '*_test.go' | wc -l
```

**Generate config:**
```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: cobra
  languages: [go]

pipeline:
  linting:
    enabled: true
    command: "golangci-lint run ./..."

  type_checking:
    enabled: true
    command: "go vet ./..."

  testing:
    enabled: true
    command: "go test -v ./..."

  coverage:
    enabled: true
    command: "go test -coverprofile=coverage.out ./... && go tool cover -func=coverage.out"
    threshold: 80

  duplication:
    enabled: true
    tools: [duplo]
    threshold: 5.0
    min_lines: 7

  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: gosec
        domains: [sast]

fail_on:
  linting: error
  type_checking: error
  testing: any
  coverage: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/vendor/**"
EOF
```

**Validate and test:**
```bash
lucidshark validate
lucidshark scan --linting --type-checking --format ai 2>&1 | head -40
```

**Verify:**
- [ ] Config valid
- [ ] Custom commands work

---

### 3.2.3 Autoconfigure Real-World Project: Fiber (Web framework)

```bash
cd "$TEST_WORKSPACE/fiber"

# Detect
cat go.mod | head -5
ls -la .golangci.yml 2>/dev/null
```

**Generate config and test:**
```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: fiber
  languages: [go]

pipeline:
  linting:
    enabled: true
    command: "golangci-lint run ./..."

  testing:
    enabled: true
    command: "go test -v ./..."

  duplication:
    enabled: true
    tools: [duplo]
    threshold: 5.0
    min_lines: 7

  security:
    enabled: true
    tools:
      - name: trivy
        domains: [sca]
      - name: gosec
        domains: [sast]

fail_on:
  linting: error
  testing: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/vendor/**"
EOF
```

```bash
lucidshark validate
lucidshark scan --testing --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Config valid
- [ ] Tests run successfully

---

### 3.2.4 Summary Table: Autoconfiguration Results

| Project | Has go.mod? | Has tests? | golangci-lint config? | Config Valid? | Scans Work? | Notes |
|---------|-------------|------------|----------------------|---------------|-------------|-------|
| gin | | | | | | |
| cobra | | | | | | |
| fiber | | | | | | |

**Autoconfiguration Test Verdict:**
- [ ] **PASS:** All Go projects detected correctly
- [ ] **PASS:** Custom commands work for linting/testing/type checking
- [ ] **PASS:** Configs validated successfully
- [ ] **PASS:** Scans executed successfully
- [ ] **PASS:** Exclusions prevented scanning vendor/
- [ ] **FAIL:** <describe failure> _____________

---

### 3.3 Test Autoconfigure MCP Tool Directly

```
mcp__lucidshark__autoconfigure()
```

**Verify returns:**
- [ ] Go detection guidance (go.mod)
- [ ] golangci-lint installation steps
- [ ] Custom command examples for Go
- [ ] Example lucidshark.yml for Go
- [ ] vendor/ exclusion guidance

---

### 3.4 Validate Configuration via MCP

```bash
cd "$TEST_WORKSPACE/gin"
```

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Reports config as valid
- [ ] Accepts custom commands

**Test invalid config:**
```bash
cp lucidshark.yml lucidshark.yml.backup
echo "bad: : yaml" > lucidshark.yml
```

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Returns validation error

```bash
mv lucidshark.yml.backup lucidshark.yml
```

---

### 3.5 Test lucidshark init on Real Projects

```bash
cd "$TEST_WORKSPACE/gin"
lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files would be created
- [ ] No conflict with go.mod

```bash
lucidshark init
```

**Verify:**
- [ ] Creates .mcp.json, .claude/ files
- [ ] go.mod intact

---

## Phase 4: CLI Scan Testing

Use the test-project for all CLI tests unless otherwise noted.

```bash
cd "$TEST_WORKSPACE/test-project"
```

### 4.1 Linting (golangci-lint)

#### 4.1.1 CLI — Linting Only (No Config)
Remove or rename `lucidshark.yml` temporarily:
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] golangci-lint auto-detected for Go project (has `go.mod`)
- [ ] Finds unused function `unusedFunction` in `main.go`
- [ ] Finds unused global variable `globalUnused` in `main.go`
- [ ] Finds shadowed variable `err` in `shadowedErr()`
- [ ] Finds missing error check in `missingErrCheck()` (errcheck linter)
- [ ] Finds `ineffassign` or similar for unused assignments
- [ ] Each issue has: file_path, line, column, rule_id, message, severity
- [ ] Exit code is non-zero (issues found)

#### 4.1.2 CLI — Linting with Config
```bash
lucidshark scan --linting --all-files --format json
```

**Verify:**
- [ ] Same issues detected as without config
- [ ] Exclude patterns applied (no `vendor/**` files scanned)

#### 4.1.3 CLI — Linting Auto-Fix
```bash
cp -r cmd cmd.backup
cp -r internal internal.backup
lucidshark scan --linting --all-files --fix --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] golangci-lint `--fix` applied
- [ ] Some auto-fixable issues resolved (e.g., formatting-related lint issues)
- [ ] Re-scan shows fewer issues
- [ ] Files actually modified on disk

Restore: `rm -rf cmd internal && mv cmd.backup cmd && mv internal.backup internal`

#### 4.1.4 CLI — Linting Specific File
```bash
lucidshark scan --linting --files internal/handlers/handler.go --format json
```

**Verify:**
- [ ] Only scans `handler.go`
- [ ] Does NOT report issues from `main.go`

#### 4.1.5 CLI — Linting on Gin (Clean Project)
```bash
cd "$TEST_WORKSPACE/gin"
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Zero or very few linting issues on well-maintained project
- [ ] golangci-lint auto-detected
- [ ] Scan completes without timeout (Gin is moderate size)

#### 4.1.6 CLI — Linting on Cobra
```bash
cd "$TEST_WORKSPACE/cobra"
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify and record issue count.**

### 4.2 Type Checking (go vet)

#### 4.2.1 CLI — Type Checking Only (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] go vet auto-detected for Go project
- [ ] Finds Printf format mismatch in `printUser()` (wrong format verbs: `%d` for string, `%s` for int)
- [ ] Finds lock copy issue in `copyLock()` (copies sync.Mutex)
- [ ] Finds unreachable code in `unreachable()`
- [ ] Each issue has severity mapped (expect HIGH for printf, copylocks, unreachable)

#### 4.2.2 CLI — Type Checking with Config
```bash
lucidshark scan --type-checking --all-files --format json
```

**Verify:**
- [ ] go_vet runs and produces same results
- [ ] JSON output properly parsed (go vet -json format with brace-balanced extraction)

#### 4.2.3 CLI — Type Checking on Gin (Well-Vetted Project)
```bash
cd "$TEST_WORKSPACE/gin"
lucidshark scan --type-checking --all-files --format json 2>&1 | head -100
cd "$TEST_WORKSPACE/test-project"
```

**Record results.** Gin is well-maintained, so expect few/zero vet errors.

#### 4.2.4 CLI — Type Checking on Cobra
```bash
cd "$TEST_WORKSPACE/cobra"
lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Record results.**

### 4.3 Formatting (gofmt)

#### 4.3.1 CLI — Formatting Flag (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --formatting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] Does the `--formatting` flag work without config?
- [ ] If it fails, record the exact error message
- [ ] gofmt detects unformatted files (especially `main.go` with bad spacing)

#### 4.3.2 CLI — Formatting with Config
```bash
lucidshark scan --formatting --all-files --format json
```

**Verify:**
- [ ] gofmt lists unformatted files via `gofmt -l`
- [ ] `main.go` flagged as unformatted (bad spacing in `processData`)
- [ ] Each formatting issue has file_path

#### 4.3.3 CLI — Formatting Auto-Fix
```bash
cp -r cmd cmd.backup
cp -r internal internal.backup
lucidshark scan --formatting --all-files --fix --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] `gofmt -w` applied to unformatted files
- [ ] `main.go` reformatted on disk (check diff with backup)
- [ ] Re-scan shows zero formatting issues

Restore: `rm -rf cmd internal && mv cmd.backup cmd && mv internal.backup internal`

#### 4.3.4 CLI — Formatting on Gin (Already Formatted)
```bash
cd "$TEST_WORKSPACE/gin"
lucidshark scan --formatting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Zero formatting issues (Gin uses gofmt)
- [ ] Scan completes quickly

### 4.4 Testing (go test)

#### 4.4.1 CLI — Testing Domain
```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] `go test -json -count=1 ./...` executed
- [ ] Reports test results (pass/fail/skip counts)
- [ ] `TestFailingTest` should FAIL (returns "fail processed" not "FAIL PROCESSED")
- [ ] `TestProcessData`, `TestShadowedErr`, `TestUnreachable`, `TestPassing1`, `TestPassing2` should PASS
- [ ] `TestUserValidate` and `TestUserString` should PASS
- [ ] Failed tests generate issues with file_path and line number

#### 4.4.2 CLI — Testing + Coverage Together
```bash
# Clean slate — remove any pre-existing coverage data
rm -f coverage.out
lucidshark scan --testing --coverage --all-files --format json
echo "Exit code: $?"
# Prove the testing step produced coverage data
ls -la coverage.out
echo "coverage.out exists: $?"
head -5 coverage.out
```

**Verify:**
- [ ] Tests run with `-coverprofile=coverage.out` flag added
- [ ] `coverage.out` file exists on disk after scan (verified with `ls`)
- [ ] `coverage.out` starts with `mode:` line (valid Go coverprofile format)
- [ ] Coverage percentage calculated and non-zero
- [ ] Coverage percentage in scan output is derived from the `coverage.out` file
- [ ] Coverage threshold comparison works (below 80% → issue)
- [ ] Per-file coverage stats available

#### 4.4.3 CLI — Testing on Gin
```bash
cd "$TEST_WORKSPACE/gin"
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Gin's test suite runs (may take a while)
- [ ] Results correctly parsed from JSON output
- [ ] Record pass/fail/skip counts and duration

### 4.5 Coverage (go cover)

#### 4.5.1 CLI — Coverage Without Testing (Should Error or Show No Data)
```bash
# Clean slate — ensure no leftover coverage data from previous runs
rm -f coverage.out
lucidshark scan --coverage --all-files --format json
echo "Exit code: $?"
ls coverage.out 2>/dev/null
echo "coverage.out exists after coverage-only scan: $?"
```

**Verify:**
- [ ] No `coverage.out` file produced (testing didn't run)
- [ ] Reports error or "no coverage data" (coverage requires `coverage.out` from testing)
- [ ] Exit code is non-zero
- [ ] Does not crash

#### 4.5.2 CLI — Coverage Threshold
Run with different thresholds:
```bash
# Low threshold (should pass)
lucidshark scan --testing --coverage --all-files --coverage-threshold 10 --format json
echo "Exit code: $?"

# High threshold (should fail)
lucidshark scan --testing --coverage --all-files --coverage-threshold 90 --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] With 10% threshold: no coverage issue
- [ ] With 90% threshold: coverage issue reported with gap percentage
- [ ] Coverage data parsed from Go coverprofile format correctly
- [ ] Module path stripped from file paths (e.g., `github.com/test/test-project/cmd/myapp/main.go` → `cmd/myapp/main.go`)

#### 4.5.3 CLI — Coverage on GoFiber
```bash
cd "$TEST_WORKSPACE/fiber"
lucidshark scan --testing --coverage --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] GoFiber tests run and coverage collected
- [ ] Per-file coverage stats generated

### 4.6 Duplication (Duplo)

#### 4.6.1 CLI — Duplication Domain
```bash
lucidshark scan --duplication --all-files --format json
```

**Verify:**
- [ ] Duplo detects duplicates between `duplicate1.go` and `duplicate2.go`
- [ ] Reports duplication percentage
- [ ] Reports file locations of duplicate blocks
- [ ] Respects `min_lines: 4` config
- [ ] Go files properly detected as language "go" by duplo

---

**🚨 CRITICAL: Go Has TWO SAST Tools — You Must Test BOTH**

**LucidShark supports TWO SAST scanners for Go:**
1. **gosec** (Go-specific, finds Go security issues like G201, G204, G401)
2. **OpenGrep** (cross-language, finds SQL injection, XSS, command injection)

**YOU MUST TEST BOTH AND COMPARE THEIR RESULTS.**

Do NOT test only one and skip the other. The value of LucidShark's Go support is that it runs BOTH tools and combines their findings. If you test only gosec, you're missing half the picture.

**Required comparison:**
- Run `lucidshark scan --sast` (should run BOTH gosec and OpenGrep for Go files)
- Document how many issues gosec finds
- Document how many issues OpenGrep finds
- Identify overlapping issues (same vulnerability found by both tools)
- Identify gosec-only issues (Go-specific checks)
- Identify OpenGrep-only issues (cross-language patterns)

**This comparison is NOT optional. It's a core feature of Go SAST in LucidShark.**

---

### 4.7 SAST — gosec (Go-Specific)

#### 4.7.1 CLI — SAST Domain (gosec should run automatically for Go projects)
```bash
lucidshark scan --sast --all-files --format json
```

**Verify gosec findings — record which of these are detected:**
- [ ] SQL injection in `handler.go` — G201/G202 (string concatenation in SQL query)
- [ ] Command injection in `handler.go` — G204 (`exec.Command("sh", "-c", cmd)`)
- [ ] Weak crypto in `handler.go` — G401 (`md5.Sum()` for password hashing)
- [ ] Hardcoded secrets in `handler.go` — G101 (`APIKey`, `DatabasePassword`)
- [ ] Path traversal in `handler.go` — G304 (unsanitized user input in filepath)
- [ ] SSRF in `handler.go` — G107 (`http.Get(url)` with user input)
- [ ] Insecure file permissions in `handler.go` — G306 (`0777`)
- [ ] Net/http serve without timeouts — G114 (if applicable)
- [ ] Each gosec issue has:
  - [ ] `source_tool` = "gosec"
  - [ ] Issue ID starts with `gosec-`
  - [ ] CWE reference in metadata (e.g., `metadata.cwe.id`)
  - [ ] Confidence rating in metadata (`HIGH`, `MEDIUM`, or `LOW`)
  - [ ] Severity mapped correctly (`HIGH`, `MEDIUM`, or `LOW`)

#### 4.7.2 CLI — Verify gosec vs OpenGrep Both Run
```bash
lucidshark scan --sast --all-files --format json > /tmp/sast-scan.json
python3 -c "
import json
with open('/tmp/sast-scan.json') as f:
    data = json.load(f)
issues = data.get('issues', [])
gosec_issues = [i for i in issues if i.get('source_tool') == 'gosec']
opengrep_issues = [i for i in issues if i.get('source_tool') == 'opengrep']
print(f'Gosec issues: {len(gosec_issues)}')
print(f'OpenGrep issues: {len(opengrep_issues)}')
print(f'Total SAST issues: {len(issues)}')
for i in gosec_issues[:5]:
    print(f'  gosec: {i.get(\"rule_id\")} - {i.get(\"title\", \"\")[:60]}')
for i in opengrep_issues[:5]:
    print(f'  opengrep: {i.get(\"rule_id\")} - {i.get(\"title\", \"\")[:60]}')
"
```

**Verify:**
- [ ] Both gosec AND OpenGrep produce results (defense in depth)
- [ ] Gosec issues have `gosec-` prefixed IDs
- [ ] OpenGrep issues have `opengrep-` prefixed IDs
- [ ] Gosec finds Go-specific issues (G-prefixed rule IDs)
- [ ] Some overlap expected (both detect SQL injection, command injection, etc.)

#### 4.7.3 CLI — gosec CWE Mapping
```bash
lucidshark scan --sast --all-files --format json > /tmp/sast-cwe.json
python3 -c "
import json
with open('/tmp/sast-cwe.json') as f:
    data = json.load(f)
gosec_issues = [i for i in data.get('issues', []) if i.get('source_tool') == 'gosec']
for i in gosec_issues:
    meta = i.get('metadata', {})
    cwe = meta.get('cwe', {})
    print(f'{i.get(\"rule_id\")}: CWE-{cwe.get(\"id\", \"none\")} conf={meta.get(\"confidence\", \"?\")} sev={i.get(\"severity\")}')
"
```

**Verify:**
- [ ] Most gosec issues have CWE IDs (e.g., CWE-89 for SQL injection, CWE-78 for command injection)
- [ ] CWE URLs point to valid mitre.org definitions
- [ ] Confidence levels are present (HIGH, MEDIUM, LOW)

### 4.7b SAST — OpenGrep (Cross-Language)

#### 4.7b.1 CLI — OpenGrep Also Runs
OpenGrep should also produce findings for the Go project:

```bash
lucidshark scan --sast --all-files --format json > /tmp/sast-all.json
python3 -c "
import json
with open('/tmp/sast-all.json') as f:
    data = json.load(f)
opengrep_issues = [i for i in data.get('issues', []) if i.get('source_tool') == 'opengrep']
print(f'OpenGrep SAST issues: {len(opengrep_issues)}')
"
```

**Verify:**
- [ ] OpenGrep finds at least some issues
- [ ] OWASP references present where applicable

---

**🚨 CRITICAL: SCA (Trivy) Test — Do NOT Skip This**

**This test was FAILED in a previous Python E2E run because the tester gave up after encountering a perceived "timeout" instead of actually running the command properly.**

**Reality: SCA scans typically complete in 5-15 seconds, even for projects with many dependencies.**

**What you must do:**
1. Run `lucidshark scan --sca --all-files --format json` and WAIT for it to complete
2. Record the EXACT runtime (use `time` command if needed)
3. Record the EXACT number of CVEs found with severity breakdown
4. If it takes longer than 30 seconds, investigate why (slow network, Trivy DB download, large project)
5. If it fails, record the EXACT error message and debug it

**Expected behavior:**
- First run may download Trivy vulnerability database (~100MB) — this is normal, wait for it
- Subsequent runs use cached database and are faster
- Should find CVEs in the intentionally vulnerable dependencies in go.mod

**DO NOT:**
- ❌ Give up after one error without investigating
- ❌ Report "timeout" without recording actual runtime
- ❌ Skip this test because "it's taking too long"
- ❌ Accept vague results like "found some CVEs"

**DO:**
- ✅ Record exact CVE count and severity breakdown
- ✅ Measure actual runtime with timestamps
- ✅ Verify CVE metadata (ID, severity, affected package, fixed version)
- ✅ Test on BOTH test-project AND real-world project (Gin or Cobra)

---

### 4.8 SCA (Trivy)

#### 4.8.1 CLI — SCA Domain
```bash
lucidshark scan --sca --all-files --format json
```

**Verify:**
- [ ] Trivy scans `go.mod` / `go.sum`
- [ ] Finds known CVEs in old dependency versions:
  - `golang.org/x/crypto v0.0.0-20210322153248-0c34fe9e7dc2` (multiple CVEs)
  - `gopkg.in/yaml.v2 v2.2.2` (CVE-2019-11254, CVE-2022-28948)
  - `github.com/gin-gonic/gin v1.7.0` (potential CVEs)
  - `github.com/mattn/go-sqlite3 v1.14.6` (potential CVEs)
- [ ] Each CVE has: CVE ID, severity, affected package, fixed version
- [ ] If Trivy DB download fails, document the error handling behavior

#### 4.8.2 SCA on Gin
```bash
cd "$TEST_WORKSPACE/gin"
lucidshark scan --sca --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

**Record results.**

### 4.9 Full Scan (`--all`)

#### 4.9.1 CLI — `--all` with Config
```bash
lucidshark scan --all --all-files --format json > /tmp/full-scan-go-with-config.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/full-scan-go-with-config.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
print('Duration ms:', data.get('metadata', {}).get('duration_ms', 'N/A'))
for domain, count in data.get('metadata', {}).get('issues_by_domain', {}).items():
    print(f'  {domain}: {count}')
"
```

**Verify:**
- [ ] ALL domains executed: linting, type_checking, formatting, testing, coverage, duplication, sca, sast
- [ ] Issues found in each applicable domain
- [ ] Duration is non-zero
- [ ] `enabled_domains` populated
- [ ] `scanners_used` populated

#### 4.9.2 CLI — `--all` WITHOUT Config
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --all --all-files --format json > /tmp/full-scan-go-no-config.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/full-scan-go-no-config.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] How many domains execute without config?
- [ ] Go auto-detected via `go.mod` presence and `.go` file extensions
- [ ] Compare with `--all` WITH config — are the same domains covered?
- [ ] If not all domains run, document which are missing

### 4.10 Output Formats

Run a scan and test each output format:

```bash
lucidshark scan --linting --all-files --format json > /tmp/go-out-json.json
lucidshark scan --linting --all-files --format summary > /tmp/go-out-summary.txt
lucidshark scan --linting --all-files --format table > /tmp/go-out-table.txt
lucidshark scan --linting --all-files --format ai > /tmp/go-out-ai.txt
lucidshark scan --linting --all-files --format sarif > /tmp/go-out-sarif.json
```

**Verify each format:**
- [ ] **json**: Valid JSON, has `issues` array and `metadata` object
- [ ] **summary**: Human-readable text with severity counts and domain breakdown
- [ ] **table**: Tabular output with columns
- [ ] **ai**: Rich structured output with priorities, fix steps, instructions
- [ ] **sarif**: Valid SARIF 2.1.0 schema with `runs`, `results`, `rules`

### 4.11 CLI Flags & Features

#### 4.11.1 `--dry-run`
```bash
lucidshark scan --all --all-files --dry-run
```

**Verify:**
- [ ] Shows planned domains, tools, file targeting
- [ ] Does NOT actually execute scans
- [ ] Lists Go-specific tools (golangci-lint, go vet, gofmt, go test)

#### 4.11.2 `--fail-on`
```bash
lucidshark scan --linting --all-files --fail-on medium
echo "Exit code for medium: $?"

lucidshark scan --linting --all-files --fail-on critical
echo "Exit code for critical: $?"
```

**Verify:**
- [ ] `--fail-on medium`: exit code 1 (there are medium+ issues)
- [ ] `--fail-on critical`: exit code 0 (if no critical issues) or 1 (if there are)

#### 4.11.3 `--base-branch`
```bash
# Create a branch with changes
git checkout -b test-branch
echo "// new issue" >> cmd/myapp/main.go
git add -A && git commit -m "add change"

lucidshark scan --linting --all-files --base-branch main --format json
echo "Exit code: $?"

git checkout main
git branch -D test-branch
```

**Verify:**
- [ ] Only reports issues from files changed since `main`

#### 4.11.4 `--debug` and `--verbose`
```bash
lucidshark --debug scan --linting --all-files --format summary 2>&1 | head -50
lucidshark --verbose scan --linting --all-files --format summary 2>&1 | head -50
```

**Verify:**
- [ ] `--debug` shows detailed debug logs (tool commands, paths, etc.)
- [ ] `--verbose` shows info-level logs
- [ ] Shows golangci-lint command being executed
- [ ] Note: `--debug` must come BEFORE `scan` subcommand

#### 4.11.5 `--stream`
```bash
lucidshark scan --linting --all-files --stream 2>&1 | head -30
```

**Verify:**
- [ ] Produces streaming output
- [ ] Check if output is raw JSON or parsed

#### 4.11.6 Incremental Scanning (Default)
```bash
# With no uncommitted changes
lucidshark scan --linting --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Scans only uncommitted/changed files (not `--all-files`)
- [ ] If no changes, may report 0 issues

### 4.12 Other CLI Commands

#### 4.12.1 `lucidshark status`
```bash
lucidshark status
```

**Verify:**
- [ ] Shows version, platform
- [ ] Shows available plugins/tools — Go tools listed
- [ ] Shows scanner versions (golangci-lint, go version, gofmt)

#### 4.12.2 `lucidshark doctor`
```bash
lucidshark doctor
```

**Verify:**
- [ ] Checks config validity
- [ ] Checks Go tool availability (golangci-lint, go, gofmt)
- [ ] Checks environment (GOPATH, GOROOT)
- [ ] Reports any issues/warnings

#### 4.12.3 `lucidshark help`
```bash
lucidshark help | head -100
```

**Verify:**
- [ ] Outputs comprehensive markdown reference
- [ ] Documents all subcommands and flags

#### 4.12.4 `lucidshark overview --update`
```bash
lucidshark overview --update
cat QUALITY.md | head -50
```

**Verify:**
- [ ] Generates `QUALITY.md` file
- [ ] Contains health score, issue counts
- [ ] Contains domain breakdown for Go domains

#### 4.12.5 `lucidshark serve --mcp`
```bash
timeout 5 lucidshark serve --mcp 2>&1 || true
```

**Verify:**
- [ ] MCP server starts without crash
- [ ] Outputs MCP protocol initialization

---

## Phase 5: MCP Tool Testing

**🚨 CRITICAL: This ENTIRE PHASE Was SKIPPED in a Previous Test Run 🚨**

**In a previous Python E2E test, this ENTIRE phase was skipped with the excuse:**
> "⏳ Not tested in this session due to context/time constraints"

**This is COMPLETELY UNACCEPTABLE.**

**Why this phase is CRITICAL:**
- **MCP integration is THE PRIMARY WAY users interact with LucidShark via Claude Code**
- Skipping MCP testing means you didn't test the main product feature
- MCP tools must have exact parity with CLI commands — discrepancies are critical bugs
- Many users will NEVER use the CLI — they only use MCP through Claude Code

**You MUST test ALL MCP tools listed below:**
1. `mcp__lucidshark__scan()` — for every domain (linting, type_checking, formatting, testing, coverage, duplication, sast, sca)
2. `mcp__lucidshark__check_file()` — verify it works on Go files
3. `mcp__lucidshark__get_fix_instructions()` — verify it returns actionable fix instructions
4. `mcp__lucidshark__apply_fix()` — verify it actually fixes issues (and ONLY the intended issues)
5. `mcp__lucidshark__get_status()` — verify it returns valid status
6. `mcp__lucidshark__get_help()` — verify it returns help text
7. `mcp__lucidshark__autoconfigure()` — verify it detects Go project and generates correct config
8. `mcp__lucidshark__validate_config()` — verify it validates lucidshark.yml correctly

**For EACH MCP tool, you must:**
- Execute it with valid inputs
- Record exact output
- Compare with equivalent CLI command (where applicable)
- Verify exit codes/status
- Document any discrepancies as bugs

**NO SHORTCUTS. NO EXCUSES. TEST EVERYTHING.**

---

All MCP tests use the test-project with `lucidshark.yml` in place.

```bash
cd "$TEST_WORKSPACE/test-project"
```

### 5.1 `mcp__lucidshark__scan()`

#### 5.1.1 Scan — Individual Domains

Test each domain individually via MCP:

```
mcp__lucidshark__scan(domains=["linting"], all_files=true)
mcp__lucidshark__scan(domains=["type_checking"], all_files=true)
mcp__lucidshark__scan(domains=["formatting"], all_files=true)
mcp__lucidshark__scan(domains=["testing"], all_files=true)
mcp__lucidshark__scan(domains=["testing", "coverage"], all_files=true)
mcp__lucidshark__scan(domains=["duplication"], all_files=true)
mcp__lucidshark__scan(domains=["sca"], all_files=true)
mcp__lucidshark__scan(domains=["sast"], all_files=true)
```

For EACH call, verify:
- [ ] Correct domain executed
- [ ] Issues returned with proper structure (file_path, line, severity, message)
- [ ] No errors or crashes
- [ ] Results consistent with CLI results for same domain
- [ ] Go tools used (golangci_lint, go_vet, gofmt, go_test, go_cover, gosec)

**Additional verification for testing + coverage MCP call:**
```bash
# Verify coverage data was produced by the MCP scan
rm -f coverage.out
```
```
mcp__lucidshark__scan(domains=["testing", "coverage"], all_files=true)
```
```bash
ls -la coverage.out
echo "coverage.out exists after MCP scan: $?"
head -3 coverage.out
```

**Verify:**
- [ ] `coverage.out` file exists on disk after MCP scan
- [ ] File contains valid Go coverprofile data (starts with `mode:`)
- [ ] Coverage percentage in MCP result matches CLI result
- [ ] Coverage data was produced by the scan itself, not leftover from a previous run

#### 5.1.2 Scan — All Domains
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] All 8 domains execute
- [ ] Compare total issue counts with CLI `--all` results

#### 5.1.3 Scan — Specific Files
```
mcp__lucidshark__scan(files=["internal/handlers/handler.go"], domains=["linting", "sast"])
```

**Verify:**
- [ ] Only `handler.go` scanned
- [ ] Linting and SAST issues for that file only

#### 5.1.4 Scan — Auto-Fix
```
mcp__lucidshark__scan(domains=["linting"], all_files=true, fix=true)
```

**Verify:**
- [ ] Issues auto-fixed via golangci-lint --fix
- [ ] Fewer/zero linting issues in result
- [ ] Files modified on disk

Restore files after: `git checkout -- .`

#### 5.1.5 Scan — Formatting Fix via MCP
```
mcp__lucidshark__scan(domains=["formatting"], all_files=true, fix=true)
```

**Verify:**
- [ ] Formatting issues fixed via `gofmt -w`
- [ ] `main.go` reformatted
- [ ] Re-scan shows zero formatting issues

Restore: `git checkout -- .`

### 5.2 `mcp__lucidshark__check_file()`

```
mcp__lucidshark__check_file(file_path="cmd/myapp/main.go")
```

**Verify:**
- [ ] Returns issues for `main.go`
- [ ] Check which domains run (does it run ALL domains?)
- [ ] Returns domain_status, issues_by_domain, instructions
- [ ] Response time reasonable for single-file check

```
mcp__lucidshark__check_file(file_path="internal/handlers/handler.go")
```

**Verify:**
- [ ] Returns security-related issues
- [ ] SAST issues included
- [ ] Linting issues included

### 5.3 `mcp__lucidshark__get_fix_instructions()`

First, run a scan to get issue IDs:
```
mcp__lucidshark__scan(domains=["linting", "sast", "sca"], all_files=true)
```

Then for each type of issue, get fix instructions:

```
mcp__lucidshark__get_fix_instructions(issue_id="<linting-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sast-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sca-issue-id>")
```

**Verify for each:**
- [ ] Returns priority, fix_steps, suggested_fix
- [ ] Returns documentation_url where applicable
- [ ] Guidance is specific and actionable for Go code

**Test with nonexistent ID:**
```
mcp__lucidshark__get_fix_instructions(issue_id="nonexistent-id-12345")
```

**Verify:**
- [ ] Returns "Issue not found" error

### 5.4 `mcp__lucidshark__apply_fix()`

```
mcp__lucidshark__apply_fix(issue_id="<linting-issue-id>")
```

**Verify:**
- [ ] Fix applied to file on disk
- [ ] Check: does it fix ONLY the targeted issue or ALL auto-fixable issues in the file?
- [ ] Return message indicates success

**Test with non-linting issue:**
```
mcp__lucidshark__apply_fix(issue_id="<sast-issue-id>")
```

**Verify:**
- [ ] Correctly rejects with "Only linting issues support auto-fix" or similar

Restore: `git checkout -- .`

### 5.5 `mcp__lucidshark__get_status()`

```
mcp__lucidshark__get_status()
```

**Verify:**
- [ ] Returns tool inventory including Go tools
- [ ] Returns scanner versions (golangci-lint version, go version)
- [ ] Check: does `enabled_domains` show all configured domains?

### 5.6 `mcp__lucidshark__get_help()`

```
mcp__lucidshark__get_help()
```

**Verify:**
- [ ] Returns comprehensive documentation
- [ ] Covers all domains, CLI flags, MCP tools
- [ ] Mentions Go-specific tools and configuration
- [ ] Response size is reasonable (not truncated)

### 5.7 `mcp__lucidshark__autoconfigure()`

```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Detects Go language from `go.mod`
- [ ] Detects Go test files (`_test.go`)
- [ ] Provides example configs for Go
- [ ] Mentions golangci-lint installation

### 5.8 `mcp__lucidshark__validate_config()`

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Reports valid config as valid
- [ ] Check with intentionally broken configs (same as Phase 3.4)

### 5.9 MCP vs CLI Parity

For each domain, compare MCP and CLI results:

| Domain | CLI Issues | MCP Issues | Match? |
|--------|-----------|------------|--------|
| linting | | | |
| type_checking | | | |
| formatting | | | |
| testing | | | |
| coverage | | | |
| duplication | | | |
| sca | | | |
| sast | | | |

Document any discrepancies.

---

## Phase 6: Real-World Project Testing

### 6.1 Gin

```bash
cd "$TEST_WORKSPACE/gin"
```

#### 6.1.1 Create lucidshark.yml for Gin
Use autoconfigure or manually create a config appropriate for Gin.

#### 6.1.2 Full Scan
```bash
lucidshark scan --all --all-files --format json > /tmp/gin-scan.json
```
Also via MCP:
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] Scan completes without errors
- [ ] Record issue counts per domain
- [ ] No false positives on well-maintained code (especially linting, type checking)
- [ ] SCA finds known CVEs if any in Gin's deps
- [ ] Record scan duration
- [ ] golangci-lint handles Gin's codebase size within timeout (600s)

### 6.2 Cobra

```bash
cd "$TEST_WORKSPACE/cobra"
```

#### 6.2.1 Full Scan (CLI + MCP)
Same process as Gin.

**Verify:**
- [ ] Scan completes
- [ ] Handles CLI-specific code patterns (code generation, templates)
- [ ] Record results

### 6.3 GoFiber

```bash
cd "$TEST_WORKSPACE/fiber"
```

#### 6.3.1 Full Scan
Same process.

**Additional checks:**
- [ ] Handles modern Go patterns correctly
- [ ] Test suite runs and coverage collected
- [ ] Record pass/fail/skip counts

### 6.4 Hugo

```bash
cd "$TEST_WORKSPACE/hugo"
```

#### 6.4.1 Full Scan
Same process.

**Additional checks:**
- [ ] Large codebase doesn't cause timeout/OOM
- [ ] golangci-lint timeout (default 300s) sufficient for Hugo
- [ ] go test timeout (default 600s) sufficient
- [ ] Record scan duration — Hugo is very large
- [ ] If timeout occurs, document the timeout and which tool timed out

---

## Phase 7: Edge Case Testing

### 7.1 Empty Go File
```bash
cat > "$TEST_WORKSPACE/test-project/internal/empty.go" << 'EOF'
package internal
EOF
lucidshark scan --linting --files internal/empty.go --format json
```

**Verify:**
- [ ] No crash on minimal file
- [ ] Zero issues reported

### 7.2 Syntax Error File
```bash
cat > "$TEST_WORKSPACE/test-project/internal/broken.go" << 'EOF'
package internal

func broken( {
    // missing closing paren
    return
}
EOF
lucidshark scan --linting --files internal/broken.go --format json
lucidshark scan --type-checking --files internal/broken.go --format json
```

**Verify:**
- [ ] Handles syntax errors gracefully
- [ ] Reports syntax error as an issue (golangci-lint "typecheck" linter)
- [ ] Does not crash

### 7.3 Very Large File
```bash
python3 -c "
print('package internal')
print()
for i in range(5000):
    print(f'func Func{i}(x int) int {{ return x + {i} }}')
" > "$TEST_WORKSPACE/test-project/internal/large.go"
lucidshark scan --linting --files internal/large.go --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Handles large file without OOM or timeout
- [ ] Results returned in reasonable time

### 7.4 Non-ASCII / Unicode File
```bash
cat > "$TEST_WORKSPACE/test-project/internal/unicode.go" << 'EOF'
package internal

// Grüße — Unicode in comments and identifiers
func Grüße(name string) string {
	return "Hallo, " + name + "! 👋"
}

var 変数 = "日本語テスト"
EOF
lucidshark scan --linting --files internal/unicode.go --format json
```

**Verify:**
- [ ] Handles Unicode content
- [ ] No encoding errors
- [ ] Note: Go allows Unicode identifiers

### 7.5 No Go Project (Wrong Language Detection)
```bash
mkdir -p "$TEST_WORKSPACE/not-go"
cd "$TEST_WORKSPACE/not-go"
git init
echo "console.log('hello')" > index.js
echo '{"name": "test"}' > package.json
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Does NOT try to run Go tools on JavaScript project (no `go.mod`)
- [ ] Auto-detects JavaScript/TypeScript instead, or reports no applicable tools

### 7.6 Mixed Language Project
```bash
mkdir -p "$TEST_WORKSPACE/mixed-lang"
cd "$TEST_WORKSPACE/mixed-lang"
git init
echo "package main" > main.go
echo "module example.com/mixed" > go.mod
echo "import os" > app.py
echo "console.log('hello')" > app.js
lucidshark scan --linting --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Handles multiple languages
- [ ] Runs golangci-lint for `.go` files
- [ ] Runs appropriate linters for other languages

### 7.7 Go Project Without Tests
```bash
mkdir -p "$TEST_WORKSPACE/no-tests"
cd "$TEST_WORKSPACE/no-tests"
git init
echo "module example.com/notests" > go.mod
cat > main.go << 'EOF'
package main

import "fmt"

func main() {
	fmt.Println("no tests here")
}
EOF
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Handles project with no test files gracefully
- [ ] Reports 0 tests or "no test files" message
- [ ] Does not crash

### 7.8 Go Project with Build Tags
```bash
cat > "$TEST_WORKSPACE/test-project/internal/buildtag.go" << 'EOF'
//go:build linux
// +build linux

package internal

func LinuxOnly() string {
	return "linux only"
}
EOF
lucidshark scan --linting --files internal/buildtag.go --format json
```

**Verify:**
- [ ] Handles build tags without errors
- [ ] File is either scanned or properly skipped based on build tags

### 7.9 Go Module with Vendor Directory
```bash
mkdir -p "$TEST_WORKSPACE/test-project/vendor"
echo "This simulates vendored deps" > "$TEST_WORKSPACE/test-project/vendor/README"
lucidshark scan --linting --all-files --format json
```

**Verify:**
- [ ] Vendor directory excluded via exclude_patterns
- [ ] golangci-lint does not lint vendored code

Clean up edge case files:
```bash
cd "$TEST_WORKSPACE/test-project"
rm -f internal/empty.go internal/broken.go internal/large.go internal/unicode.go internal/buildtag.go
rm -rf vendor
```

---

## Phase 8: Installation Method Comparison

Compare the binary and pip installations (both in test-project root):

### 8.1 Feature Parity

Run the same scan with BOTH installation methods and compare:

```bash
cd "$TEST_WORKSPACE/test-project"

# Test with binary
./lucidshark scan --linting --all-files --format json > /tmp/go-binary-results.json
BINARY_EXIT=$?
echo "Binary exit code: $BINARY_EXIT"

# Test with pip (activate venv)
source .venv/bin/activate
lucidshark scan --linting --all-files --format json > /tmp/go-pip-results.json
PIP_EXIT=$?
echo "Pip exit code: $PIP_EXIT"

# Compare results
echo "Comparing issue counts..."
BINARY_ISSUES=$(python3 -c "import json; print(json.load(open('/tmp/go-binary-results.json')).get('metadata', {}).get('total_issues', 0))")
PIP_ISSUES=$(python3 -c "import json; print(json.load(open('/tmp/go-pip-results.json')).get('metadata', {}).get('total_issues', 0))")

echo "Binary found: $BINARY_ISSUES issues"
echo "Pip found: $PIP_ISSUES issues"
```

**Compare:**
- [ ] Same exit codes? Binary: _______, Pip: _______
- [ ] Same issue count? Binary: _______, Pip: _______
- [ ] Same issue IDs and messages? (manually inspect the JSON files)
- [ ] Same scanners used?
- [ ] Same execution time (roughly)?

**Expected:** Results should be IDENTICAL since both use the same source code.

**If there are differences:** This is a BUG - report as critical issue.

### 8.2 Tool Availability

```bash
cd "$TEST_WORKSPACE/test-project"

# Binary doctor
./lucidshark doctor > /tmp/binary-doctor.txt 2>&1

# Pip doctor
source .venv/bin/activate
lucidshark doctor > /tmp/pip-doctor.txt 2>&1

# Compare
diff /tmp/binary-doctor.txt /tmp/pip-doctor.txt
```

**Expected:** Both should report the same tool availability since they're the same source code.

**If there are differences:** Document them - this could indicate packaging issues (e.g., binary missing embedded files).

---

## Phase 9: Regression Checks for Known Bugs

Check whether these previously reported bugs (from Python E2E) also affect Go:

| Bug | Test | Status |
|-----|------|--------|
| BUG-001: `--formatting` CLI flag broken | Run `lucidshark scan --formatting --all-files` without config on Go project | |
| BUG-002: `--all` without config only runs limited domains | Run `lucidshark scan --all --all-files` without config on Go project, check executed_domains | |
| BUG-003: Ghost issues in formatting | Run formatting scan, check for issue with incorrect file_path | |
| BUG-004: Duration always 0ms | Check `duration_ms` in any scan metadata | |
| BUG-005: `enabled_domains` empty without config | Check metadata when scanning without config | |
| BUG-006: `scanners_used` empty for non-security | Check metadata when running linting only | |
| BUG-007: MCP coverage "no data" after testing | Run `mcp__lucidshark__scan(domains=["testing", "coverage"])` on Go project | |
| BUG-008: `apply_fix` fixes ALL issues | Fix one issue, check if other issues also fixed | |

---

## Test Report Template

Write the report with this structure:

```markdown
# LucidShark Go Support — E2E Test Report

**Date:** YYYY-MM-DD
**Tester:** Claude (model version)
**LucidShark Version:** (from `lucidshark --version`)
**Installation Methods Tested:** install.sh, pip
**Go Version:** (from `go version`)
**Platform:** (from `uname -a`)
**Tool Versions:** golangci-lint X.Y.Z, gofmt (bundled with Go), go vet (bundled with Go), gosec X.Y.Z, OpenGrep X.Y.Z, Trivy X.Y.Z, Duplo X.Y.Z

---

## Executive Summary
(2-3 paragraph overview: what works, what's broken, overall assessment)

## Installation Testing Results
### install.sh
### pip
### Go Tool Installation
### Comparison

## Init & Configuration Results
### lucidshark init
### Autoconfigure (Go detection)
### Config Validation

## CLI Scan Results by Domain
### Linting (golangci-lint)
### Type Checking (go vet)
### Formatting (gofmt)
### Testing (go test)
### Coverage (go cover)
### Duplication (Duplo)
### SAST — gosec (Go-specific)
### SAST — OpenGrep (cross-language)
### gosec vs OpenGrep Overlap Analysis
### SCA (Trivy)

## MCP Tool Results
### scan()
### check_file()
### get_fix_instructions()
### apply_fix()
### get_status()
### get_help()
### autoconfigure()
### validate_config()

## MCP vs CLI Parity
(Table comparing issue counts and behavior differences)

## Real-World Project Results
### Gin
### Cobra
### GoFiber
### Hugo

## Edge Case Results

## Output Format Results
(json, summary, table, ai, sarif)

## Regression Check Results
(Status of each previously reported bug)

## New Bugs Found
### BUG-XXX: Title
**Severity:** Critical/Moderate/Minor
**Reproducibility:** X%
**Description:** ...
**Expected:** ...
**Actual:** ...

## New UX Issues Found

## Recommendations (Priority Order)
### P0 — Must Fix
### P1 — Should Fix
### P2 — Nice to Have

## Conclusion
(Overall assessment with score out of 10)

## Cleanup

After completing the test, remove all test artifacts:

```bash
# If you still have the TEST_WORKSPACE variable:
rm -rf "$TEST_WORKSPACE"

# Or if the variable is lost:
rm -rf /tmp/lucidshark-go-e2e-*

# Verify cleanup:
ls /tmp/lucidshark-go-e2e-* 2>/dev/null || echo "✓ All test artifacts removed"
```

**What gets deleted:**
- All cloned projects (gin, cobra, fiber, hugo)
- The artificial test-project
- All installation test directories
- Any generated coverage reports, test artifacts, and go module caches

**Safe to delete:** Everything was isolated in `/tmp` — no files in your actual workspace were touched.
```

---

## Important Notes for the Tester

1. **🚨 VERIFY LOCAL VERSION FIRST!** Before starting ANY tests, verify that you installed the LOCAL development version, not the published version. Check Phase 1.3 verification steps. If versions don't match, STOP and fix installation.
2. **Execute every command.** Do not skip steps even if you think you know the outcome.
3. **Capture actual output.** Include relevant snippets in the report, not just pass/fail.
4. **Record exit codes** for every `lucidshark scan` command.
5. **Measure wall-clock time** for scans on large projects (Gin, Hugo).
6. **Compare MCP vs CLI** results for the same operation — discrepancies are bugs.
7. **Check for regressions** against all previously reported bugs (BUG-001 through BUG-008).
8. **Test BOTH with and without `lucidshark.yml`** to verify config-less experience.
9. **Clean up** between tests that modify files (`git checkout -- .`).
10. **If disk space is limited**, skip Hugo clone and note it — Hugo is very large (~100MB).
11. **If a tool is not installed** (e.g., opengrep, duplo, golangci-lint), document it — don't skip the test.
12. **Go-specific:** Ensure `go mod tidy` succeeds before running tests that need compilation.
13. **Go-specific:** If `go test` fails due to missing dependencies, run `go mod download` first.
14. **If you find the same bugs that were supposedly "fixed"**, double-check that you're testing the LOCAL version, not the published one.

---

## 🎯 FINAL COMPLETION CHECKLIST 🎯

Before you claim this test is complete, answer EVERY question below with specific data:

### Installation & Setup (LOCAL VERSION VERIFICATION)
- [ ] Local development version from pyproject.toml: ________________
- [ ] Binary built with PyInstaller in Phase 0.3: Version? ________________ (must match local!)
- [ ] Binary copied to test-project root in Phase 2.3.1: Version? ________________ (must match local!)
- [ ] Venv created in test-project/.venv in Phase 2.3.2: (yes/no) ________________
- [ ] Pip editable install in test-project/.venv: Version? ________________ (must match local!)
- [ ] ✅ VERIFIED: All versions match the local development version? (yes/no) ________________
- [ ] Pip shows editable install location (local source path)? (yes/no) ________________
- [ ] If versions DON'T match local, did you STOP and fix installation? (yes/no) ________________
- [ ] `lucidshark doctor` output: Which Go tools detected? ________________
- [ ] golangci-lint version: ________________
- [ ] go version: ________________

### Test Projects
- [ ] Gin cloned successfully? (yes/no) Commit hash: ________________
- [ ] Cobra cloned successfully? (yes/no) Commit hash: ________________
- [ ] GoFiber cloned successfully? (yes/no) Commit hash: ________________
- [ ] Hugo cloned successfully? (yes/no) Commit hash: ________________ (or "skipped due to disk space")
- [ ] Custom test-project created? (yes/no) All 4 source files written? ________________
- [ ] `go mod tidy` succeeded on test-project? (yes/no) ________________

### CLI Scans — Custom Test Project
- [ ] Linting (golangci-lint): How many issues? ________ Exit code? ________ Runtime? ________
- [ ] Type checking (go vet): How many issues? ________ Exit code? ________ Runtime? ________
- [ ] Formatting (gofmt): How many files need formatting? ________ Exit code? ________
- [ ] Testing (go test): How many tests run? ________ Passed? ________ Failed? ________ Exit code? ________
- [ ] Coverage: Overall coverage percentage? ________% Exit code? ________
- [ ] Duplication: Duplicated lines found? ________ Exit code? ________
- [ ] SAST — gosec: How many issues? ________ Exit code? ________ Runtime? ________
- [ ] SAST — OpenGrep: How many issues? ________ Exit code? ________ Runtime? ________
- [ ] gosec vs OpenGrep: How many overlapping issues? ________ How many gosec-only? ________ How many OpenGrep-only? ________
- [ ] SCA (Trivy): How many CVEs? ________ (Critical/High/Medium/Low breakdown: ____/____/____/____) Exit code? ________ Runtime? ________

### Real-World Projects (Pick at least 2)
- [ ] Project 1 (________): Linting issues? ________ Type errors? ________ Test results? ________ Runtime for full scan? ________
- [ ] Project 2 (________): Linting issues? ________ Type errors? ________ Test results? ________ Runtime for full scan? ________

### MCP Tools
- [ ] `mcp__lucidshark__scan()` on test-project: How many issues? ________ Exit code? ________ Matches CLI? (yes/no) ________
- [ ] `mcp__lucidshark__check_file()` on `cmd/myapp/main.go`: How many issues? ________ Exit code? ________
- [ ] `mcp__lucidshark__get_fix_instructions()` for one linting issue: Did it return fix instructions? (yes/no) ________
- [ ] `mcp__lucidshark__apply_fix()` for one linting issue: Fixed? (yes/no) ________ Verified by re-scanning? (yes/no) ________
- [ ] `mcp__lucidshark__get_status()`: Did it return valid status? (yes/no) ________
- [ ] `mcp__lucidshark__get_help()`: Did it return help text? (yes/no) ________
- [ ] `mcp__lucidshark__autoconfigure()`: Generated valid lucidshark.yml? (yes/no) ________ Detected Go correctly? (yes/no) ________
- [ ] `mcp__lucidshark__validate_config()`: Validated config without errors? (yes/no) ________

### MCP vs CLI Parity
- [ ] Same issue count for linting? (yes/no) If no, explain: ________________
- [ ] Same issue count for type checking? (yes/no) If no, explain: ________________
- [ ] Same exit codes? (yes/no) If no, explain: ________________

### Output Formats
- [ ] `--format json`: Valid JSON? (yes/no) ________ Can be parsed with `jq`? (yes/no) ________
- [ ] `--format summary`: Human-readable summary? (yes/no) ________
- [ ] `--format table`: Table formatted correctly? (yes/no) ________
- [ ] `--format ai`: AI-friendly format? (yes/no) ________
- [ ] `--format sarif`: Valid SARIF? (yes/no) ________

### Regression Testing
- [ ] BUG-001: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________
- [ ] BUG-002: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________
- [ ] BUG-003: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________
- [ ] BUG-004: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________
- [ ] BUG-005: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________
- [ ] BUG-006: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________
- [ ] BUG-007: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________
- [ ] BUG-008: Status (✅ FIXED / ❌ STILL BROKEN / ⏭️ NOT APPLICABLE TO GO) ________

### New Bugs Found
- [ ] Total new bugs found: ________ (P0: ________, P1: ________, P2: ________)
- [ ] Each bug has: Title, Severity, Reproducibility %, Description, Expected vs Actual, Reproduction steps? (yes/no) ________

### Edge Cases
- [ ] Empty Go file: Handled correctly? (yes/no) ________
- [ ] Syntax error in Go file: Error message helpful? (yes/no) ________
- [ ] Very large Go project (if Hugo tested): Scan completed? (yes/no) ________ Runtime: ________ Issues found: ________
- [ ] Go project with no go.mod: Handled gracefully? (yes/no) ________
- [ ] Scanning outside project root: Error message clear? (yes/no) ________

### Go-Specific Verification
- [ ] Tested BOTH gosec AND OpenGrep? (yes/no) ________
- [ ] Compared gosec vs OpenGrep results? (yes/no) ________ Overlap count: ________
- [ ] Verified gofmt formatting fixes? (yes/no) ________ Number of files formatted: ________
- [ ] Verified go test runs actual tests? (yes/no) ________ Test count: ________
- [ ] Verified go vet catches real issues? (yes/no) ________ Issue count: ________
- [ ] Tested with vendor/ directory if present? (yes/no) ________

---

## 📜 TEST COMPLETION CERTIFICATE 📜

**I hereby certify that I have:**

✅ **VERIFIED LOCAL VERSION:** Tested the LOCAL development version (from source), NOT the published PyPI/GitHub version
✅ **VERIFIED VERSION MATCH:** Confirmed all installations (binary, pip) match the version in pyproject.toml
✅ Executed EVERY step in this test document without shortcuts
✅ Run ALL commands and captured actual output (not placeholders or summaries)
✅ Tested BOTH CLI and MCP interfaces for every domain
✅ Tested BOTH gosec (Go-specific SAST) AND OpenGrep (cross-language SAST)
✅ Compared MCP vs CLI results for parity
✅ Verified ALL previously reported bugs (BUG-001 through BUG-008)
✅ Created detailed reproduction steps for every new bug found
✅ Tested on real-world Go projects (Gin, Cobra, GoFiber, and/or Hugo)
✅ Verified output formats (json, summary, table, ai, sarif)
✅ Documented exit codes, timings, and exact issue counts
✅ Investigated every failure, error, or unexpected result

**Test Report Location:** ________________

**Tester Name/ID:** ________________

**Test Date:** ________________

**LucidShark Version Tested:** ________________

**Final Verdict:**
- [ ] ✅ **APPROVED** — LucidShark Go support is production-ready (score ≥9/10)
- [ ] ⚠️ **APPROVED WITH RESERVATIONS** — Works but has minor issues (score 7-8.9/10)
- [ ] ❌ **NOT APPROVED** — Critical bugs found, not ready for production (score <7/10)

**Overall Score: ________ / 10**

**Critical Issues Found (P0):** ________ (list IDs: ________________)

**Major Issues Found (P1):** ________ (list IDs: ________________)

**Minor Issues Found (P2):** ________ (list IDs: ________________)

**Summary Statement (1-2 sentences):**
________________________________________________________________________________
________________________________________________________________________________

**I would/would not trust this software in production because:**
________________________________________________________________________________
________________________________________________________________________________

---

**Signature:** _________________________ **Date:** _________________________
