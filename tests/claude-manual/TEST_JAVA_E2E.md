# LucidShark Java Support  -  End-to-End Test Instructions

## 🚨🚨🚨 CRITICAL INSTALLATION REQUIREMENT 🚨🚨🚨

**YOU MUST TEST THE LOCAL DEVELOPMENT VERSION, NOT THE PUBLISHED VERSION!**

**USE THE UNIVERSAL SETUP SCRIPT:**
```bash
/Users/toniantunovic/dev/voldeq/lucidshark-code/lucidshark/tests/claude-manual/setup-test-installation.sh <project-path>
```

This script is the **SOURCE OF TRUTH** for all E2E tests. It automatically:
- ✅ Builds PyInstaller binary from local source
- ✅ Installs lucidshark from local source in editable mode
- ✅ Verifies ALL versions match your local development version
- ✅ Fails if testing wrong version (e.g., 0.6.4 from PyPI instead of 0.6.5 local)

**See `tests/claude-manual/README.md` for details and `TEST_GO_E2E.md` Phase 2.3 for usage examples.**

---

## 🚨 CRITICAL TESTING PHILOSOPHY 🚨

**YOU ARE A QUALITY ASSURANCE ENGINEER, NOT A CHEERLEADER.**

Your job is to **FIND BUGS**, not to confirm that things work. Approach every test with skepticism and rigor.

### Non-Negotiable Testing Rules

1. **EXECUTE EVERY SINGLE STEP** - No exceptions. No shortcuts.
2. **TRY TO BREAK THINGS** - Find edge cases, bugs, and failures
3. **BE DEEPLY SKEPTICAL** - Question everything, verify everything
4. **DOCUMENT EVERYTHING IN EXTREME DETAIL** - Other engineers must reproduce your findings
5. **IF SOMETHING SEEMS OFF, INVESTIGATE RUTHLESSLY** - Don't make excuses
6. **COMPARE ACTUAL VS EXPECTED** - State both explicitly
7. **NO PARTIAL CREDIT** - Either you completed the test or you didn't

**See the Python E2E test file for the complete testing philosophy and standards. The same rules apply here.**

### Success Criteria
- ✅ Every step executed and documented
- ✅ Every bug found and reported with reproduction steps
- ✅ Every discrepancy investigated and explained
- ✅ Detailed test report with actual data, not summaries
- ✅ Clear verdict: PASS (ready for production) or FAIL (blocking issues found)

### Failure Criteria
- ❌ Any step skipped without documented reason
- ❌ Any "seems to work" or "probably correct" statements
- ❌ Any bugs found but not thoroughly documented
- ❌ Test report with vague summaries instead of concrete data

---

**Purpose:** You are performing a comprehensive end-to-end test of LucidShark's Java support. You will test both the CLI and MCP interfaces across all domains, using real open-source Java projects checked out from GitHub. You will test installation via both the install script and pip, run `lucidshark init`, `autoconfigure`, and exercise every scan domain and MCP tool. At the end, write a detailed test report that another engineer could use to reproduce your findings.

**Java Tools Under Test:**

| Domain | Tool | Version | Type |
|--------|------|---------|------|
| Linting | Checkstyle | 13.3.0 | Managed (auto-download JAR) |
| Linting | PMD | 7.23.0 | Managed (auto-download JAR) |
| Type Checking | SpotBugs | 4.9.8 | Managed (auto-download JAR) |
| Testing | Maven / Gradle |  -  | System (build tool) |
| Coverage | JaCoCo |  -  | Integrated (parses XML reports) |
| Duplication | Duplo |  -  | System (language-agnostic) |
| SAST | OpenGrep |  -  | System (language-agnostic) |
| SCA | Trivy |  -  | System (scans pom.xml, build.gradle) |

---

## Phase 0: Environment Setup

### 0.1 Record Environment Info

```bash
uname -a
java -version 2>&1
javac -version 2>&1
mvn --version 2>&1 || echo "Maven not installed"
gradle --version 2>&1 || echo "Gradle not installed"
python3 --version
pip3 --version
git --version
echo "Disk space:" && df -h .
echo "Working directory:" && pwd
```

Record all output in the test report under "Environment".

### 0.2 Create Clean Test Workspace

```bash
export TEST_WORKSPACE="/tmp/lucidshark-java-e2e-$(date +%s)"
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

### 0.3 Verify Java Toolchain

```bash
# Ensure JDK is available (required for Checkstyle, PMD, SpotBugs)
java -version 2>&1 | head -1
javac -version 2>&1 | head -1

# Check JAVA_HOME
echo "JAVA_HOME: ${JAVA_HOME:-not set}"
```

**Verify:**
- [ ] JDK 11+ is available (minimum for all managed tools)
- [ ] `javac` is available (needed for SpotBugs compilation)
- [ ] `JAVA_HOME` is set or `java`/`javac` are on PATH

If JDK is not available, install it:
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk
# or use sdkman
curl -s "https://get.sdkman.io" | bash && sdk install java 17.0.9-tem
```

---

## Phase 1: Installation Testing

### 1.1 Install via install.sh (Binary)

```bash
cd "$TEST_WORKSPACE"
mkdir install-script-test && cd install-script-test
git init  # install.sh expects to be in a project root
curl -fsSL https://raw.githubusercontent.com/toniantunovi/lucidshark/main/install.sh | bash
```

**Verify:**
- [ ] Binary downloaded successfully to `./lucidshark`
- [ ] `./lucidshark --version` outputs a version string
- [ ] `./lucidshark --help` shows help text with all subcommands (scan, init, status, doctor, help, validate, overview, serve)
- [ ] `./lucidshark status` runs without error
- [ ] `./lucidshark doctor` runs and shows tool availability

Record the version number and which tools `doctor` reports as available/missing. Pay special attention to Java-specific tools: Checkstyle, PMD, SpotBugs.

### 1.2 Install via install.sh with Specific Version

```bash
cd "$TEST_WORKSPACE"
mkdir install-version-test && cd install-version-test
git init
curl -fsSL https://raw.githubusercontent.com/toniantunovi/lucidshark/main/install.sh | bash -s -- --version v0.5.63
```

**Verify:**
- [ ] Correct version installed (check `./lucidshark --version`)
- [ ] The binary works (`./lucidshark status`)


---

## Phase 2: Test Project Setup

### 2.1 Clone Test Projects from GitHub

Clone these real-world Java projects. Each serves a different test purpose:

```bash
cd "$TEST_WORKSPACE"

# Project 1: Spring PetClinic  -  Spring Boot, Maven, JPA, JUnit 5, typical enterprise app
git clone --depth 1 https://github.com/spring-projects/spring-petclinic.git

# Project 2: Google Gson  -  Pure library, Maven, clean code, comprehensive tests
git clone --depth 1 https://github.com/google/gson.git

# Project 3: Square OkHttp  -  Gradle-based, modern Java, HTTP client library
git clone --depth 1 https://github.com/square/okhttp.git

# Project 4: Apache Commons Lang  -  Maven, classic library structure, multi-module
git clone --depth 1 https://github.com/apache/commons-lang.git
```

**Verify all projects cloned successfully:**
```bash
ls -la "$TEST_WORKSPACE"
echo ""
echo "Expected directories:"
echo "  - spring-petclinic/"
echo "  - gson/"
echo "  - okhttp/"
echo "  - commons-lang/"
```

**Verify:**
- [ ] All four project directories exist in `$TEST_WORKSPACE`
- [ ] Each directory contains a git repository (`.git/` folder)
- [ ] Each directory is inside `/tmp/lucidshark-java-e2e-*/`

**Why these projects:**
- **spring-petclinic**: Covers Spring Boot (60%+ of enterprise Java), Maven, JPA, JUnit 5, typical package layout
- **gson**: Pure Java library, Maven, clean code baseline, serialization domain
- **okhttp**: Gradle-based (covers Gradle build system detection), modern Java patterns
- **commons-lang**: Apache Maven project, utility library, mature codebase with extensive tests

### 2.2 Create Custom Vulnerable Test Project

This project has intentional issues across ALL domains for comprehensive testing:

```bash
mkdir -p "$TEST_WORKSPACE/test-project/src/main/java/com/example/app"
mkdir -p "$TEST_WORKSPACE/test-project/src/test/java/com/example/app"
cd "$TEST_WORKSPACE/test-project"
git init
```

**Create `pom.xml`** (Maven project with JUnit 5, JaCoCo, vulnerable dependencies):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>test-project</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- JUnit 5 -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.0</version>
            <scope>test</scope>
        </dependency>

        <!-- Intentionally vulnerable dependencies for SCA testing -->
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.14.1</version> <!-- CVE-2021-44228 Log4Shell -->
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.9.8</version> <!-- Multiple CVEs -->
        </dependency>
        <dependency>
            <groupId>commons-collections</groupId>
            <artifactId>commons-collections</artifactId>
            <version>3.2.1</version> <!-- CVE-2015-7501 deserialization -->
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>5.2.0.RELEASE</version> <!-- Known CVEs -->
        </dependency>
        <dependency>
            <groupId>commons-io</groupId>
            <artifactId>commons-io</artifactId>
            <version>2.4</version> <!-- CVE-2021-29425 path traversal -->
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.10</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>prepare-agent</goal>
                        </goals>
                    </execution>
                    <execution>
                        <id>report</id>
                        <phase>test</phase>
                        <goals>
                            <goal>report</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Create `src/main/java/com/example/app/Main.java`** (Checkstyle + PMD issues):
```java
package com.example.app;

import java.util.List;
import java.util.ArrayList;
import java.util.Map;        // unused import  -  Checkstyle/PMD
import java.util.HashMap;    // unused import  -  Checkstyle/PMD
import java.io.*;             // star import  -  Checkstyle

public class Main {

    // Missing Javadoc  -  Checkstyle
    public static void main(String[] args) {
        System.out.println("Hello World");
    }

    // Naming violation: method should be camelCase  -  Checkstyle
    public void Do_Something() {
        int x = 10;
        // Empty if block  -  PMD
        if (x > 5) {
        }
    }

    // God method: too long and complex  -  PMD
    public String processData(String input, int mode) {
        String result = "";  // String concatenation in loop  -  PMD
        if (mode == 1) {
            for (int i = 0; i < input.length(); i++) {
                result = result + input.charAt(i);  // PMD: InefficientStringConcatenation
                if (input.charAt(i) == 'a') {
                    result = result + "A";
                } else if (input.charAt(i) == 'b') {
                    result = result + "B";
                } else if (input.charAt(i) == 'c') {
                    result = result + "C";
                } else if (input.charAt(i) == 'd') {
                    result = result + "D";
                }
            }
        } else if (mode == 2) {
            for (int i = input.length() - 1; i >= 0; i--) {
                result = result + input.charAt(i);
            }
        } else if (mode == 3) {
            result = input.toUpperCase();
        } else {
            result = input;
        }
        return result;
    }

    // Unused parameter  -  PMD
    public int calculate(int a, int b, int unusedParam) {
        return a + b;
    }

    // Missing braces on if  -  Checkstyle
    public void noBraces(boolean flag) {
        if (flag)
            System.out.println("true");
        else
            System.out.println("false");
    }

    // Magic numbers  -  Checkstyle/PMD
    public double computeArea(double radius) {
        return 3.14159 * radius * radius;
    }

    // Empty catch block  -  PMD
    public void riskyOperation() {
        try {
            int result = 10 / 0;
        } catch (ArithmeticException e) {
            // empty catch  -  PMD: EmptyCatchBlock
        }
    }

    // Too many parameters  -  PMD
    public void tooManyParams(int a, int b, int c, int d, int e, int f, int g) {
        System.out.println(a + b + c + d + e + f + g);
    }
}
```

**Create `src/main/java/com/example/app/SecurityIssues.java`** (SAST issues):
```java
package com.example.app;

import java.io.*;
import java.sql.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import javax.crypto.Cipher;
import javax.crypto.spec.SecretKeySpec;
import javax.crypto.spec.IvParameterSpec;

public class SecurityIssues {

    // Hardcoded credentials  -  SAST
    private static final String DB_PASSWORD = "super_secret_password_123";
    private static final String API_KEY = "sk-1234567890abcdef1234567890abcdef";
    private static final String SECRET_KEY = "MySecretEncryptionKey123";

    // SQL Injection  -  SAST
    public ResultSet getUser(Connection conn, String username) throws SQLException {
        Statement stmt = conn.createStatement();
        String query = "SELECT * FROM users WHERE name = '" + username + "'";
        return stmt.executeQuery(query);
    }

    // SQL Injection (format string variant)  -  SAST
    public ResultSet getUserById(Connection conn, int userId) throws SQLException {
        Statement stmt = conn.createStatement();
        return stmt.executeQuery(String.format("SELECT * FROM users WHERE id = %d", userId));
    }

    // Command Injection  -  SAST
    public String runCommand(String userInput) throws IOException {
        Runtime rt = Runtime.getRuntime();
        Process proc = rt.exec("cmd /c " + userInput);  // command injection
        BufferedReader reader = new BufferedReader(new InputStreamReader(proc.getInputStream()));
        return reader.readLine();
    }

    // Command Injection via ProcessBuilder  -  SAST
    public Process executeCommand(String command) throws IOException {
        ProcessBuilder pb = new ProcessBuilder("sh", "-c", command);
        return pb.start();
    }

    // Insecure deserialization  -  SAST
    public Object deserialize(byte[] data) throws IOException, ClassNotFoundException {
        ObjectInputStream ois = new ObjectInputStream(new ByteArrayInputStream(data));
        return ois.readObject();  // unsafe deserialization
    }

    // Weak cryptography (MD5)  -  SAST
    public String hashPassword(String password) throws NoSuchAlgorithmException {
        MessageDigest md = MessageDigest.getInstance("MD5");
        byte[] digest = md.digest(password.getBytes());
        StringBuilder sb = new StringBuilder();
        for (byte b : digest) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    // Weak cryptography (DES)  -  SAST
    public byte[] encryptData(String data) throws Exception {
        SecretKeySpec key = new SecretKeySpec(SECRET_KEY.getBytes(), "DES");
        Cipher cipher = Cipher.getInstance("DES/ECB/PKCS5Padding");  // weak cipher + ECB mode
        cipher.init(Cipher.ENCRYPT_MODE, key);
        return cipher.doFinal(data.getBytes());
    }

    // Path traversal  -  SAST
    public String readFile(String baseDir, String fileName) throws IOException {
        File file = new File(baseDir + "/" + fileName);  // no path validation
        BufferedReader reader = new BufferedReader(new FileReader(file));
        StringBuilder content = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            content.append(line).append("\n");
        }
        reader.close();  // should use try-with-resources
        return content.toString();
    }

    // XXE vulnerability  -  SAST
    public void parseXml(String xmlInput) throws Exception {
        javax.xml.parsers.DocumentBuilderFactory dbf =
            javax.xml.parsers.DocumentBuilderFactory.newInstance();
        // Not disabling external entities = XXE vulnerability
        javax.xml.parsers.DocumentBuilder db = dbf.newDocumentBuilder();
        db.parse(new java.io.ByteArrayInputStream(xmlInput.getBytes()));
    }

    // LDAP Injection  -  SAST
    public void searchLdap(String userInput) throws Exception {
        javax.naming.directory.DirContext ctx = null;  // simplified for testing
        String filter = "(uid=" + userInput + ")";  // LDAP injection
    }

    // Insecure random  -  SAST
    public int generateToken() {
        java.util.Random random = new java.util.Random();  // insecure random
        return random.nextInt(1000000);
    }
}
```

**Create `src/main/java/com/example/app/UserService.java`** (SpotBugs / type checking issues):
```java
package com.example.app;

import java.util.ArrayList;
import java.util.List;

public class UserService {

    private List<String> users = new ArrayList<>();

    // Null dereference  -  SpotBugs
    public String getFirstUser() {
        String user = null;
        if (users.isEmpty()) {
            // user remains null
        }
        return user.toUpperCase();  // NullPointerException  -  SpotBugs NP_ALWAYS_NULL
    }

    // Equals without hashCode  -  SpotBugs HE_EQUALS_NO_HASHCODE
    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (obj == null || getClass() != obj.getClass()) return false;
        UserService that = (UserService) obj;
        return users.equals(that.users);
    }
    // missing hashCode() override

    // Returning mutable internal state  -  SpotBugs EI_EXPOSE_REP
    public List<String> getUsers() {
        return users;  // exposes internal representation
    }

    // Comparison using == on Strings  -  SpotBugs ES_COMPARING_STRINGS_WITH_EQ
    public boolean isAdmin(String username) {
        return username == "admin";  // should use .equals()
    }

    // Inefficient use of keySet  -  SpotBugs WMI_WRONG_MAP_ITERATOR
    public void printMap(java.util.Map<String, String> map) {
        for (String key : map.keySet()) {
            System.out.println(key + " = " + map.get(key));
        }
    }

    // Unused field  -  SpotBugs URF_UNREAD_FIELD
    private int unusedCounter = 0;

    // Resource leak  -  SpotBugs
    public void readConfig(String path) throws java.io.IOException {
        java.io.FileInputStream fis = new java.io.FileInputStream(path);
        byte[] data = fis.readAllBytes();
        // fis never closed  -  resource leak
    }
}
```

**Create `src/main/java/com/example/app/DuplicateA.java`** (duplication detection):
```java
package com.example.app;

import java.util.List;

public class DuplicateA {

    public double calculateStatistics(List<Double> numbers) {
        if (numbers == null || numbers.isEmpty()) {
            return 0.0;
        }
        double total = 0.0;
        for (Double num : numbers) {
            total += num;
        }
        double mean = total / numbers.size();
        double variance = 0.0;
        for (Double num : numbers) {
            variance += Math.pow(num - mean, 2);
        }
        variance = variance / numbers.size();
        double stdDev = Math.sqrt(variance);
        double min = numbers.stream().mapToDouble(Double::doubleValue).min().orElse(0.0);
        double max = numbers.stream().mapToDouble(Double::doubleValue).max().orElse(0.0);
        System.out.println("Mean: " + mean);
        System.out.println("StdDev: " + stdDev);
        System.out.println("Min: " + min);
        System.out.println("Max: " + max);
        return mean;
    }
}
```

**Create `src/main/java/com/example/app/DuplicateB.java`** (near-duplicate of DuplicateA):
```java
package com.example.app;

import java.util.List;

public class DuplicateB {

    public double computeStatistics(List<Double> values) {
        if (values == null || values.isEmpty()) {
            return 0.0;
        }
        double total = 0.0;
        for (Double val : values) {
            total += val;
        }
        double mean = total / values.size();
        double variance = 0.0;
        for (Double val : values) {
            variance += Math.pow(val - mean, 2);
        }
        variance = variance / values.size();
        double stdDev = Math.sqrt(variance);
        double min = values.stream().mapToDouble(Double::doubleValue).min().orElse(0.0);
        double max = values.stream().mapToDouble(Double::doubleValue).max().orElse(0.0);
        System.out.println("Mean: " + mean);
        System.out.println("StdDev: " + stdDev);
        System.out.println("Min: " + min);
        System.out.println("Max: " + max);
        return mean;
    }
}
```

**Create `src/main/java/com/example/app/FormattingIssues.java`** (formatting issues):
```java
package com.example.app;

public class FormattingIssues {

    // Badly formatted method  -  google-java-format should flag
public void     badlyFormatted(  String a,String b  ,String c){
        if(a!=null){
System.out.println(a);
        }else{
            System.out.println(  b  );
}
    }

    // Inconsistent indentation
  public int compute(int x,
                            int y,
    int z) {
      return x+y+z;
  }

    // Long line
    public String buildMessage(String firstName, String lastName, String email, String phone, String address, String city, String state, String zip) {
        return firstName + " " + lastName + " " + email + " " + phone + " " + address + " " + city + " " + state + " " + zip;
    }

    // Missing space around operators, inconsistent bracing
    public void messyCode(){int a=1;int b=2;int c=a+b;if(c>2){System.out.println(c);}else{System.out.println("nope");}}
}
```

**Create `src/test/java/com/example/app/MainTest.java`:**
```java
package com.example.app;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MainTest {

    @Test
    void testProcessDataMode1() {
        Main main = new Main();
        String result = main.processData("abc", 1);
        // This test exercises mode 1 path
        assertNotNull(result);
    }

    @Test
    void testProcessDataMode2() {
        Main main = new Main();
        String result = main.processData("hello", 2);
        assertEquals("olleh", result);
    }

    @Test
    void testProcessDataMode3() {
        Main main = new Main();
        String result = main.processData("hello", 3);
        assertEquals("HELLO", result);
    }

    @Test
    void testCalculate() {
        Main main = new Main();
        assertEquals(5, main.calculate(2, 3, 999));
    }

    @Test
    void testComputeArea() {
        Main main = new Main();
        double area = main.computeArea(5.0);
        assertTrue(area > 78.0 && area < 79.0);
    }

    @Test
    void testNoBraces() {
        Main main = new Main();
        // Just verify no exception
        main.noBraces(true);
        main.noBraces(false);
    }
}
```

**Create `src/test/java/com/example/app/UserServiceTest.java`:**
```java
package com.example.app;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UserServiceTest {

    @Test
    void testGetFirstUserThrows() {
        UserService service = new UserService();
        // Should throw NullPointerException due to bug
        assertThrows(NullPointerException.class, () -> {
            service.getFirstUser();
        });
    }

    @Test
    void testIsAdmin() {
        UserService service = new UserService();
        // This will fail due to == comparison bug
        // Using .equals() would pass; == may or may not depending on string interning
        boolean result = service.isAdmin("admin");
        // Just record the result  -  may be false due to == comparison
        assertNotNull(result);
    }

    @Test
    void testGetUsers() {
        UserService service = new UserService();
        assertNotNull(service.getUsers());
        assertTrue(service.getUsers().isEmpty());
    }
}
```

Compile the project and commit:
```bash
cd "$TEST_WORKSPACE/test-project"

# Attempt to compile (needed for SpotBugs)
mvn compile -q 2>&1 || echo "Maven compile failed  -  SpotBugs will need compiled classes"

# Commit everything
git add -A && git commit -m "Initial commit with intentional Java issues"
```

### 2.3 Install LucidShark in Test Project Using Setup Script

**🚨 CRITICAL: Use the Universal Setup Script**

All E2E tests (Python, Java, JavaScript, Go, etc.) MUST use the universal setup script located at:
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
[INFO] Local development version: 0.6.X
[SUCCESS] Binary verified: version 0.6.X
[SUCCESS] Binary copied to .../test-project/lucidshark (version 0.6.X)
[SUCCESS] Pip installation verified: version 0.6.X
[SUCCESS] ✅ All versions match! Installation successful.
```

**Verify:**
- [ ] Script completes without errors
- [ ] All three versions (local, binary, pip) match
- [ ] Binary exists at `$TEST_WORKSPACE/test-project/lucidshark`
- [ ] Venv exists at `$TEST_WORKSPACE/test-project/.venv`

**If the script fails:** DO NOT PROCEED. Debug and fix the installation issue first.

---

## Phase 3: Init & Configuration Testing

### 3.1 Test `lucidshark init` on Test Project

```bash
cd "$TEST_WORKSPACE/test-project"
```

#### 3.1.1 Init Dry Run
```bash
./lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files WOULD be created without creating them
- [ ] Lists: `.mcp.json`, `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/skills/lucidshark/SKILL.md`
- [ ] No files actually created (check with `ls -la .mcp.json .claude/ 2>/dev/null`)

#### 3.1.2 Init (Full)
```bash
./lucidshark init
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
./lucidshark init
```

**Verify:**
- [ ] Detects existing configuration
- [ ] Suggests `--force` to overwrite
- [ ] Does NOT overwrite existing files

#### 3.1.4 Init Force
```bash
./lucidshark init --force
```

**Verify:**
- [ ] Overwrites all files successfully
- [ ] Files are identical or updated versions

#### 3.1.5 Init Remove
```bash
./lucidshark init --remove
```

**Verify:**
- [ ] All LucidShark artifacts removed
- [ ] `.mcp.json` is `{}` (empty object) or removed
- [ ] `.claude/CLAUDE.md` has lucidshark section removed
- [ ] `.claude/settings.json` has lucidshark hooks removed
- [ ] `.claude/skills/lucidshark/` removed

Re-run init for remaining tests:
```bash
./lucidshark init
```

### 3.2: End-to-End Autoconfiguration Testing

**CRITICAL:** Test complete autoconfiguration workflow from detection to validation to execution. Do NOT use pre-written configs.

---

### 3.2.1 Autoconfigure Real-World Project: Spring PetClinic (Maven)

**Objective:** Test autoconfiguration on Spring Boot Maven project.

#### Step 1: Call Autoconfigure MCP Tool
```bash
cd "$TEST_WORKSPACE/spring-petclinic"
```
```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Mentions detecting Java from pom.xml
- [ ] Mentions detecting Maven
- [ ] Mentions Checkstyle, PMD, SpotBugs, JaCoCo
- [ ] Includes example configs for Java/Maven projects
- [ ] Mentions integration test detection (*IT.java files)
- [ ] Includes exclusions (target/, .idea/, *.class)

#### Step 2: Detect Project Tools

```bash
# Check build system
ls -la pom.xml build.gradle 2>/dev/null
cat pom.xml | grep -E '<artifactId>(jacoco|checkstyle|pmd|spotbugs)' | head -10

# Check for integration tests (may require Docker)
find src/test -name '*IT.java' 2>/dev/null | head -5

# Check test directory structure
ls -la src/test/java/ 2>/dev/null | head -10
```

**Record findings:**
- [ ] Build system: _____________ (Maven or Gradle)
- [ ] Test framework: _____________ (JUnit)
- [ ] Has integration tests: _____________ (yes/no)
- [ ] Coverage plugin in pom.xml: _____________ (JaCoCo)
- [ ] Linter plugins in pom.xml: _____________

#### Step 3: Generate lucidshark.yml Based on Detection

**IMPORTANT:** Based on ACTUAL detected tools. Check if project has integration tests that need Docker.

```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: spring-petclinic
  languages: [java]

pipeline:
  linting:
    enabled: true
    tools: [checkstyle, pmd]

  testing:
    enabled: true
    tools: [maven]

  coverage:
    enabled: true
    tools: [jacoco]
    threshold: 70
    # Skip integration tests if they need Docker
    # extra_args: ["-DskipITs", "-Ddocker.skip=true"]

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
      - name: opengrep
        domains: [sast]

fail_on:
  linting: error
  testing: any
  coverage: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/target/**"
  - "**/.idea/**"
  - "**/.gradle/**"
  - "**/build/**"
  - "**/*.class"
EOF
```

#### Step 4: Validate Configuration

```bash
./lucidshark validate
echo "Validation exit code: $?"
```

**Verify:**
- [ ] Exit code 0 (valid)
- [ ] No validation errors

#### Step 5: Test Generated Config

**Test linting:**
```bash
./lucidshark scan --linting --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Checkstyle and/or PMD execute
- [ ] JAR files auto-downloaded to .lucidshark/bin/

**Test testing (may be slow for large project):**
```bash
./lucidshark scan --testing --format ai 2>&1 | tail -30
```

**Verify:**
- [ ] Maven tests run via `mvn test`
- [ ] JUnit tests execute

**Test exclusions:**
```bash
./lucidshark scan --duplication --all-files --format ai 2>&1 | grep -c 'target/'
echo "target/ files scanned (should be 0): $?"
```

**Verify:**
- [ ] target/, .class files NOT scanned

---

### 3.2.2 Autoconfigure Real-World Project: OkHttp (Gradle)

**Objective:** Test on Gradle-based project (if OkHttp uses Gradle).

```bash
cd "$TEST_WORKSPACE/okhttp"

# Detect build system
ls -la build.gradle build.gradle.kts pom.xml 2>/dev/null
cat build.gradle | grep -i 'jacoco\|checkstyle' | head -5 2>/dev/null
```

**Generate config based on Gradle detection:**
```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: okhttp
  languages: [java]

pipeline:
  linting:
    enabled: true
    tools: [checkstyle, pmd]

  testing:
    enabled: true
    tools: [maven]  # or configure for Gradle if needed

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

fail_on:
  linting: error
  testing: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/build/**"
  - "**/.gradle/**"
  - "**/target/**"
  - "**/*.class"
EOF
```

**Validate and test:**
```bash
./lucidshark validate
./lucidshark scan --linting --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Config valid
- [ ] Scans work on Gradle project

---

### 3.2.3 Autoconfigure Real-World Project: Gson (Google JSON library)

```bash
cd "$TEST_WORKSPACE/gson"

# Detect project structure
cat pom.xml | grep -E '<groupId>|<artifactId>' | head -10
find src/test -name '*.java' 2>/dev/null | wc -l
```

**Generate config:**
```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: gson
  languages: [java]

pipeline:
  linting:
    enabled: true
    tools: [checkstyle, pmd]

  testing:
    enabled: true
    tools: [maven]

  coverage:
    enabled: true
    tools: [jacoco]
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
      - name: opengrep
        domains: [sast]

fail_on:
  linting: error
  testing: any
  coverage: any
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/target/**"
  - "**/*.class"
EOF
```

**Validate and test:**
```bash
./lucidshark validate
./lucidshark scan --testing --format ai 2>&1 | head -40
```

**Verify:**
- [ ] Maven tests run
- [ ] Library project scans correctly

---

### 3.2.4 Summary Table: Autoconfiguration Results

| Project | Build System | Has Integration Tests? | Config Valid? | Scans Work? | Notes |
|---------|--------------|------------------------|---------------|-------------|-------|
| spring-petclinic | Maven/Gradle | | | | |
| okhttp | Maven/Gradle | | | | |
| gson | Maven | | | | |
| commons-lang | Maven | | | | |

**Autoconfiguration Test Verdict:**
- [ ] **PASS:** All Maven projects detected correctly
- [ ] **PASS:** Gradle projects detected correctly (if applicable)
- [ ] **PASS:** Configs validated successfully
- [ ] **PASS:** Scans executed successfully
- [ ] **PASS:** Exclusions prevented scanning target/, build/
- [ ] **FAIL:** <describe failure> _____________

---

### 3.3 Test Autoconfigure MCP Tool Directly

```
mcp__lucidshark__autoconfigure()
```

**Verify returns:**
- [ ] Java detection guidance
- [ ] Maven/Gradle detection steps
- [ ] Checkstyle, PMD, SpotBugs, JaCoCo tool info
- [ ] Integration test detection (*IT.java)
- [ ] Example lucidshark.yml for Java
- [ ] Docker skip guidance for integration tests

---

### 3.4 Validate Configuration via MCP

```bash
cd "$TEST_WORKSPACE/spring-petclinic"
```

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Reports config as valid
- [ ] Shows Maven tools

**Test invalid config:**
```bash
cp lucidshark.yml lucidshark.yml.backup
echo "bad: yaml: :" > lucidshark.yml
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
cd "$TEST_WORKSPACE/spring-petclinic"
./lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files would be created
- [ ] No conflict with pom.xml, src/

```bash
./lucidshark init
```

**Verify:**
- [ ] Creates .mcp.json, .claude/ files
- [ ] Project structure intact

---

## Phase 4: CLI Scan Testing

Use the test-project for all CLI tests unless otherwise noted.

```bash
cd "$TEST_WORKSPACE/test-project"
```

### 4.1 Linting  -  Checkstyle

#### 4.1.1 CLI  -  Checkstyle Only (No Config)
Remove or rename `lucidshark.yml` temporarily:
```bash
mv lucidshark.yml lucidshark.yml.bak
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] Checkstyle auto-detected for Java project
- [ ] Checkstyle JAR auto-downloaded to `.lucidshark/bin/checkstyle/13.3.0/`
- [ ] Finds unused imports in `Main.java`  -  `java.util.Map`, `java.util.HashMap`
- [ ] Finds star import in `Main.java`  -  `java.io.*`
- [ ] Finds naming violation: `Do_Something` method name
- [ ] Finds missing braces on if/else in `noBraces`
- [ ] Finds magic number 3.14159 in `computeArea`
- [ ] Each issue has: file_path, line, column, rule_id, message, severity
- [ ] Severity mapping: error→HIGH, warning→MEDIUM, info→LOW
- [ ] Exit code is non-zero (issues found)

#### 4.1.2 CLI  -  Checkstyle with Config
```bash
./lucidshark scan --linting --all-files --format json
```

**Verify:**
- [ ] Same issues detected as without config
- [ ] Exclude patterns applied (no `target/**` files scanned)
- [ ] Uses bundled `checkstyle-google.xml` configuration

#### 4.1.3 CLI  -  Linting Specific File
```bash
./lucidshark scan --linting --files src/main/java/com/example/app/SecurityIssues.java --format json
```

**Verify:**
- [ ] Only scans `SecurityIssues.java`
- [ ] Does NOT report issues from `Main.java`

### 4.2 Linting  -  PMD

#### 4.2.1 CLI  -  PMD Scan
```bash
./lucidshark scan --linting --all-files --format json 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
pmd_issues = [i for i in data.get('issues', []) if 'pmd' in i.get('tool', '').lower()]
print(f'PMD issues: {len(pmd_issues)}')
for i in pmd_issues[:10]:
    print(f'  {i.get(\"file_path\")}:{i.get(\"line\")} [{i.get(\"rule_id\")}] {i.get(\"message\")[:80]}')
"
```

**Verify:**
- [ ] PMD JAR auto-downloaded to `.lucidshark/bin/pmd/7.23.0/`
- [ ] Finds empty if block in `Main.java` (`Do_Something` method)
- [ ] Finds empty catch block in `Main.java` (`riskyOperation` method)
- [ ] Finds string concatenation in loop (InefficientStringConcatenation) in `processData`
- [ ] Finds unused parameter `unusedParam` in `calculate`
- [ ] Finds too many parameters (ExcessiveParameterList) in `tooManyParams`
- [ ] Severity mapping: priority 1→CRITICAL, 2→HIGH, 3→MEDIUM, 4→LOW, 5→INFO
- [ ] Uses bundled `pmd-ruleset.xml` configuration

#### 4.2.2 CLI  -  Linting on Spring PetClinic (Clean Project)
```bash
cd "$TEST_WORKSPACE/spring-petclinic"
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Zero or manageable number of linting issues on well-maintained project
- [ ] Checkstyle and PMD both auto-detected
- [ ] Scan completes without errors on larger codebase

#### 4.2.3 CLI  -  Checkstyle Auto-Fix
```bash
./lucidshark scan --linting --all-files --fix --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Checkstyle reports `auto_fix_supported: false` (Checkstyle does NOT support auto-fix)
- [ ] PMD reports `auto_fix_supported: false` (PMD does NOT support auto-fix)
- [ ] No files modified on disk
- [ ] Confirm: Java linting tools do not have auto-fix capability (unlike Python's Ruff)

### 4.3 Type Checking (SpotBugs)

#### 4.3.1 Pre-requisite: Compile Project
SpotBugs requires compiled `.class` files:
```bash
cd "$TEST_WORKSPACE/test-project"
mvn compile -q
ls target/classes/com/example/app/*.class
```

**Verify:**
- [ ] Maven compilation succeeds
- [ ] `.class` files exist in `target/classes/`

#### 4.3.2 CLI  -  SpotBugs Type Checking
```bash
./lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] SpotBugs JAR auto-downloaded to `.lucidshark/bin/spotbugs/4.9.8/`
- [ ] Detects compiled classes in `target/classes/`
- [ ] Finds null dereference in `UserService.getFirstUser()`  -  NP_ALWAYS_NULL
- [ ] Finds equals without hashCode in `UserService`  -  HE_EQUALS_NO_HASHCODE
- [ ] Finds mutable internal state exposure in `UserService.getUsers()`  -  EI_EXPOSE_REP
- [ ] Finds string comparison with == in `UserService.isAdmin()`  -  ES_COMPARING_STRINGS_WITH_EQ
- [ ] Finds resource leak in `UserService.readConfig()`  -  OBL_UNSATISFIED_OBLIGATION or similar
- [ ] Each issue has severity mapped: priority 1→HIGH, 2→MEDIUM, 3→LOW
- [ ] Category descriptions included (e.g., CORRECTNESS, STYLE, PERFORMANCE)

#### 4.3.3 CLI  -  SpotBugs Without Compiled Classes
```bash
rm -rf target/classes
./lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Handles missing compiled classes gracefully
- [ ] Reports error or warning that compilation is needed
- [ ] Does NOT crash

Restore: `mvn compile -q`

#### 4.3.4 CLI  -  SpotBugs on Gson (Compiled)
```bash
cd "$TEST_WORKSPACE/gson"
mvn compile -q -pl gson 2>&1 || echo "Compile status: $?"
./lucidshark scan --type-checking --all-files --format json 2>&1 | head -50
cd "$TEST_WORKSPACE/test-project"
```

**Record results.** Gson is well-maintained, so expect few findings.

### 4.4 Testing (Maven)

#### 4.5.1 CLI  -  Testing Domain
```bash
./lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Maven auto-detected (finds `pom.xml`)
- [ ] Runs `mvn test` (or `mvnw test` if wrapper present)
- [ ] Reports test results (pass/fail counts)
- [ ] Parses JUnit XML from `target/surefire-reports/`
- [ ] `testGetFirstUserThrows` should PASS (expects NPE)
- [ ] Other tests should pass
- [ ] Reports total tests, passed, failed, errors, duration

#### 4.5.2 CLI  -  Testing with Failing Test
Add an intentionally failing test:
```bash
cat >> src/test/java/com/example/app/FailingTest.java << 'EOF'
package com.example.app;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FailingTest {
    @Test
    void testThatWillFail() {
        assertEquals(1, 2, "Intentionally failing test");
    }
}
EOF

mvn compile -q 2>&1 || true
./lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Reports test failure with clear message
- [ ] Includes stack trace with line numbers
- [ ] Reports correct pass/fail counts
- [ ] Exit code is non-zero

Restore: `rm src/test/java/com/example/app/FailingTest.java`

#### 4.5.3 CLI  -  Testing on Spring PetClinic
```bash
cd "$TEST_WORKSPACE/spring-petclinic"
./lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Runs Spring Boot test suite
- [ ] Parses JUnit XML results correctly
- [ ] Reports pass/fail counts

### 4.6 Testing (Gradle)  -  OkHttp

#### 4.6.1 Gradle Build System Detection
```bash
cd "$TEST_WORKSPACE/okhttp"
ls gradlew build.gradle.kts 2>/dev/null || ls gradlew build.gradle 2>/dev/null
./lucidshark scan --testing --all-files --format json 2>&1 | head -30
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Gradle wrapper (`gradlew`) auto-detected
- [ ] Uses `./gradlew test` instead of `mvn test`
- [ ] Build system detection works correctly (not trying to use Maven on Gradle project)
- [ ] Reports test results from Gradle's JUnit XML output

### 4.7 Coverage (JaCoCo)

#### 4.7.1 CLI  -  Coverage Without Testing (Should Error)
```bash
# Clean slate  -  ensure no leftover coverage data from previous runs
rm -rf target/site/jacoco
./lucidshark scan --coverage --all-files --format json
echo "Exit code: $?"
ls target/site/jacoco/jacoco.xml 2>/dev/null
echo "jacoco.xml exists after coverage-only scan: $?"
```

**Verify:**
- [ ] No `target/site/jacoco/jacoco.xml` produced (testing didn't run)
- [ ] Reports error or "no coverage data" (JaCoCo requires test execution first)
- [ ] Exit code is non-zero
- [ ] Does not crash

#### 4.7.2 CLI  -  Testing + Coverage Together
```bash
# Clean slate  -  remove any pre-existing coverage data
rm -rf target/site/jacoco
./lucidshark scan --testing --coverage --all-files --format json
echo "Exit code: $?"
# Prove the testing step produced coverage data
ls -la target/site/jacoco/jacoco.xml
echo "jacoco.xml exists: $?"
python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('target/site/jacoco/jacoco.xml')
root = tree.getroot()
for counter in root.findall('.//counter[@type=\"LINE\"]'):
    missed = int(counter.get('missed', 0))
    covered = int(counter.get('covered', 0))
    total = missed + covered
    if total > 0:
        print(f'Line coverage: {covered}/{total} = {100*covered/total:.1f}%')
        break
"
```

**Verify:**
- [ ] Tests run first, then coverage parsed
- [ ] `target/site/jacoco/jacoco.xml` exists on disk after scan (verified with `ls`)
- [ ] JaCoCo XML contains valid coverage counters (non-zero line coverage)
- [ ] Coverage percentage in scan output matches the JaCoCo XML data
- [ ] Coverage threshold comparison works (below 80% → issue)
- [ ] Per-file coverage data available
- [ ] Gap percentage reported

#### 4.7.3 CLI  -  Coverage Threshold
```bash
# Low threshold (should pass)
./lucidshark scan --testing --coverage --all-files --coverage-threshold 10 --format json
echo "Exit code with low threshold: $?"

# High threshold (should fail)
./lucidshark scan --testing --coverage --all-files --coverage-threshold 95 --format json
echo "Exit code with high threshold: $?"
```

**Verify:**
- [ ] With 10% threshold: no coverage issue
- [ ] With 95% threshold: coverage issue reported with gap percentage

#### 4.7.4 Coverage on Spring PetClinic
```bash
cd "$TEST_WORKSPACE/spring-petclinic"
./lucidshark scan --testing --coverage --all-files --format json 2>&1 | head -30
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] JaCoCo report found (PetClinic uses JaCoCo by default)
- [ ] Coverage percentage reported for real project

### 4.8 Duplication (Duplo)

#### 4.8.1 CLI  -  Duplication Domain
```bash
./lucidshark scan --duplication --all-files --format json
```

**Verify:**
- [ ] Duplo detects duplicates between `DuplicateA.java` and `DuplicateB.java`
- [ ] Reports duplication percentage
- [ ] Reports file locations of duplicate blocks
- [ ] Respects `min_lines: 4` config
- [ ] Scans `.java` files correctly

### 4.9 SAST (OpenGrep)

#### 4.9.1 CLI  -  SAST Domain
```bash
./lucidshark scan --sast --all-files --format json
```

**Verify and record which of these are detected in `SecurityIssues.java`:**
- [ ] SQL injection (string concatenation in SQL query)
- [ ] SQL injection (String.format variant)
- [ ] Command injection via `Runtime.exec()`
- [ ] Command injection via `ProcessBuilder`
- [ ] Insecure deserialization via `ObjectInputStream.readObject()`
- [ ] Weak cryptography: MD5 password hashing
- [ ] Weak cryptography: DES encryption with ECB mode
- [ ] Hardcoded credentials (`DB_PASSWORD`, `API_KEY`, `SECRET_KEY`)
- [ ] Path traversal (string concatenation for file paths)
- [ ] XXE vulnerability (DocumentBuilderFactory without disabling external entities)
- [ ] LDAP injection
- [ ] Insecure random (`java.util.Random` instead of `SecureRandom`)
- [ ] Each SAST issue has CWE and/or OWASP references
- [ ] Severity levels are appropriate (SQL injection = CRITICAL/HIGH, weak crypto = MEDIUM/HIGH)

### 4.10 SCA (Trivy)

#### 4.10.1 CLI  -  SCA Domain
```bash
./lucidshark scan --sca --all-files --format json
```

**Verify:**
- [ ] Trivy scans `pom.xml`
- [ ] Finds CVE-2021-44228 (Log4Shell) in log4j-core 2.14.1  -  CRITICAL
- [ ] Finds CVEs in jackson-databind 2.9.8  -  multiple HIGH/CRITICAL
- [ ] Finds CVE-2015-7501 in commons-collections 3.2.1  -  HIGH
- [ ] Finds CVEs in spring-web 5.2.0.RELEASE
- [ ] Finds CVE-2021-29425 in commons-io 2.4
- [ ] Each CVE has: CVE ID, severity, affected package, fixed version
- [ ] If Trivy DB download fails, document the error handling behavior

#### 4.10.2 SCA on Spring PetClinic
```bash
cd "$TEST_WORKSPACE/spring-petclinic"
./lucidshark scan --sca --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Scans Spring Boot's dependency tree
- [ ] Reports any known CVEs in transitive dependencies

#### 4.10.3 SCA on OkHttp (Gradle)
```bash
cd "$TEST_WORKSPACE/okhttp"
./lucidshark scan --sca --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Trivy scans `build.gradle` or `build.gradle.kts`
- [ ] Handles Gradle dependency format correctly

### 4.11 Full Scan (`--all`)

#### 4.11.1 CLI  -  `--all` with Config
```bash
./lucidshark scan --all --all-files --format json > /tmp/java-full-scan-with-config.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/java-full-scan-with-config.json') as f:
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

#### 4.11.2 CLI  -  `--all` WITHOUT Config
```bash
mv lucidshark.yml lucidshark.yml.bak
./lucidshark scan --all --all-files --format json > /tmp/java-full-scan-no-config.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/java-full-scan-no-config.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] How many domains execute without config? Document which ones auto-detect.
- [ ] Compare with `--all` WITH config  -  are the same domains covered?
- [ ] Checkstyle and PMD should auto-detect from `.java` files
- [ ] Maven should auto-detect from `pom.xml`

### 4.12 Output Formats

Run a scan and test each output format:

```bash
./lucidshark scan --linting --all-files --format json > /tmp/java-out-json.json
./lucidshark scan --linting --all-files --format summary > /tmp/java-out-summary.txt
./lucidshark scan --linting --all-files --format table > /tmp/java-out-table.txt
./lucidshark scan --linting --all-files --format ai > /tmp/java-out-ai.txt
./lucidshark scan --linting --all-files --format sarif > /tmp/java-out-sarif.json
```

**Verify each format:**
- [ ] **json**: Valid JSON, has `issues` array and `metadata` object
- [ ] **summary**: Human-readable text with severity counts and domain breakdown
- [ ] **table**: Tabular output with columns
- [ ] **ai**: Rich structured output with priorities, fix steps, instructions
- [ ] **sarif**: Valid SARIF 2.1.0 schema with `runs`, `results`, `rules`

### 4.13 CLI Flags & Features

#### 4.13.1 `--dry-run`
```bash
./lucidshark scan --all --all-files --dry-run
```

**Verify:**
- [ ] Shows planned domains, tools, file targeting
- [ ] Does NOT actually execute scans
- [ ] Lists Checkstyle, PMD, SpotBugs, etc. as planned tools

#### 4.13.2 `--fail-on`
```bash
./lucidshark scan --linting --all-files --fail-on medium
echo "Exit code for medium: $?"

./lucidshark scan --linting --all-files --fail-on critical
echo "Exit code for critical: $?"
```

**Verify:**
- [ ] `--fail-on medium`: exit code 1 (there are medium+ issues)
- [ ] `--fail-on critical`: exit code 0 (if no critical issues) or 1 (if there are)

#### 4.13.3 `--base-branch`
```bash
git checkout -b test-branch
echo "// new issue" >> src/main/java/com/example/app/Main.java
git add -A && git commit -m "add change"

./lucidshark scan --linting --all-files --base-branch main --format json
echo "Exit code: $?"

git checkout main
git branch -D test-branch
```

**Verify:**
- [ ] Only reports issues from files changed since `main`

#### 4.13.4 `--debug` and `--verbose`
```bash
./lucidshark --debug scan --linting --all-files --format summary 2>&1 | head -50
./lucidshark --verbose scan --linting --all-files --format summary 2>&1 | head -50
```

**Verify:**
- [ ] `--debug` shows detailed debug logs (JAR download URLs, Java commands, paths)
- [ ] `--verbose` shows info-level logs
- [ ] Note: `--debug` must come BEFORE `scan` subcommand

#### 4.13.5 `--stream`
```bash
./lucidshark scan --linting --all-files --stream 2>&1 | head -30
```

**Verify:**
- [ ] Produces streaming output
- [ ] Check if output is raw JSON or parsed

#### 4.13.6 Incremental Scanning (Default)
```bash
# With no uncommitted changes
./lucidshark scan --linting --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Scans only uncommitted/changed files (not `--all-files`)
- [ ] If no changes, may report 0 issues

### 4.14 Other CLI Commands

#### 4.14.1 `lucidshark status`
```bash
./lucidshark status
```

**Verify:**
- [ ] Shows version, platform
- [ ] Shows available plugins/tools including Java tools
- [ ] Shows Checkstyle, PMD, SpotBugs versions
- [ ] Shows google-java-format availability

#### 4.14.2 `lucidshark doctor`
```bash
./lucidshark doctor
```

**Verify:**
- [ ] Checks config validity
- [ ] Checks Java tool availability (JDK, Maven, etc.)
- [ ] Reports managed tool download status (Checkstyle, PMD, SpotBugs JARs)
- [ ] Reports any issues/warnings

#### 4.14.3 `lucidshark help`
```bash
./lucidshark help | head -100
```

**Verify:**
- [ ] Outputs comprehensive markdown reference
- [ ] Documents all subcommands and flags

#### 4.14.4 `lucidshark overview --update`
```bash
./lucidshark overview --update
cat QUALITY.md | head -50
```

**Verify:**
- [ ] Generates `QUALITY.md` file
- [ ] Contains health score, issue counts
- [ ] Contains domain breakdown

#### 4.14.5 `lucidshark serve --mcp`
```bash
timeout 5 lucidshark serve --mcp 2>&1 || true
```

**Verify:**
- [ ] MCP server starts without crash
- [ ] Outputs MCP protocol initialization

---

## Phase 5: MCP Tool Testing

All MCP tests use the test-project with `lucidshark.yml` in place.

```bash
cd "$TEST_WORKSPACE/test-project"
```

### 5.1 `mcp__lucidshark__scan()`

#### 5.1.1 Scan  -  Individual Domains

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
- [ ] Java-specific tools used (Checkstyle/PMD for linting, SpotBugs for type_checking, etc.)

**Additional verification for testing + coverage MCP call:**
```bash
# Verify coverage data was produced by the MCP scan
rm -rf target/site/jacoco
```
```
mcp__lucidshark__scan(domains=["testing", "coverage"], all_files=true)
```
```bash
ls -la target/site/jacoco/jacoco.xml
echo "jacoco.xml exists after MCP scan: $?"
```

**Verify:**
- [ ] `target/site/jacoco/jacoco.xml` exists on disk after MCP scan
- [ ] Coverage percentage in MCP result matches CLI result
- [ ] Coverage data was produced by the scan itself, not leftover from a previous run

#### 5.1.2 Scan  -  All Domains
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] All 8 domains execute
- [ ] Compare total issue counts with CLI `--all` results

#### 5.1.3 Scan  -  Specific Files
```
mcp__lucidshark__scan(files=["src/main/java/com/example/app/SecurityIssues.java"], domains=["linting", "sast"])
```

**Verify:**
- [ ] Only `SecurityIssues.java` scanned
- [ ] Linting and SAST issues for that file only

#### 5.1.4 Scan  -  Auto-Fix (Linting)
```
mcp__lucidshark__scan(domains=["linting"], all_files=true, fix=true)
```

**Verify:**
- [ ] Reports that Checkstyle and PMD do NOT support auto-fix
- [ ] No files modified

#### 5.1.5 Scan  -  Formatting Fix via MCP
```
mcp__lucidshark__scan(domains=["formatting"], all_files=true, fix=true)
```

**Verify:**
- [ ] Formatting issues fixed (if google-java-format available)
- [ ] `FormattingIssues.java` reformatted

Restore: `git checkout -- .`

### 5.2 `mcp__lucidshark__check_file()`

```
mcp__lucidshark__check_file(file_path="src/main/java/com/example/app/Main.java")
```

**Verify:**
- [ ] Returns issues for `Main.java`
- [ ] Includes Checkstyle + PMD linting issues
- [ ] Returns domain_status, issues_by_domain, instructions
- [ ] Response time reasonable for single-file check

```
mcp__lucidshark__check_file(file_path="src/main/java/com/example/app/SecurityIssues.java")
```

**Verify:**
- [ ] Returns security-related issues
- [ ] SAST issues included

### 5.3 `mcp__lucidshark__get_fix_instructions()`

First, run a scan to get issue IDs:
```
mcp__lucidshark__scan(domains=["linting", "sast", "sca"], all_files=true)
```

Then for each type of issue, get fix instructions:

```
mcp__lucidshark__get_fix_instructions(issue_id="<checkstyle-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<pmd-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sast-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sca-issue-id>")
```

**Verify for each:**
- [ ] Returns priority, fix_steps, suggested_fix
- [ ] Returns documentation_url where applicable
- [ ] Guidance is specific and actionable for Java

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
- [ ] Correctly reports that Checkstyle/PMD do not support auto-fix
- [ ] Or applies fix if the tool supports it

**Test with SAST issue:**
```
mcp__lucidshark__apply_fix(issue_id="<sast-issue-id>")
```

**Verify:**
- [ ] Correctly rejects with appropriate message

Restore: `git checkout -- .`

### 5.5 `mcp__lucidshark__get_status()`

```
mcp__lucidshark__get_status()
```

**Verify:**
- [ ] Returns tool inventory including Java tools
- [ ] Returns scanner versions (Checkstyle 13.3.0, PMD 7.23.0, SpotBugs 4.9.8)
- [ ] Shows managed tool download status

### 5.6 `mcp__lucidshark__get_help()`

```
mcp__lucidshark__get_help()
```

**Verify:**
- [ ] Returns comprehensive documentation
- [ ] Covers all domains, CLI flags, MCP tools
- [ ] Mentions Java-specific tools and configuration

### 5.7 `mcp__lucidshark__autoconfigure()`

```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Detects Java language
- [ ] Detects Maven build system
- [ ] Provides Java-specific config examples
- [ ] Mentions Checkstyle, PMD, SpotBugs, JaCoCo

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
| linting (Checkstyle) | | | |
| linting (PMD) | | | |
| type_checking (SpotBugs) | | | |
| formatting (google-java-format) | | | |
| testing (Maven) | | | |
| coverage (JaCoCo) | | | |
| duplication (Duplo) | | | |
| sca (Trivy) | | | |
| sast (OpenGrep) | | | |

Document any discrepancies.

---

## Phase 6: Real-World Project Testing

### 6.1 Spring PetClinic

```bash
cd "$TEST_WORKSPACE/spring-petclinic"
```

#### 6.1.1 Create lucidshark.yml for Spring PetClinic
Use autoconfigure or manually create a config appropriate for Spring PetClinic:
```yaml
version: 1
languages: [java]
domains:
  linting:
    enabled: true
    tools: [checkstyle, pmd]
  type_checking:
    enabled: true
    tools: [spotbugs]
  formatting:
    enabled: true
    tools: [google_java_format]
  testing:
    enabled: true
    tools: [maven]
  coverage:
    enabled: true
    tools: [jacoco]
    threshold: 50
  duplication:
    enabled: true
    tools: [duplo]
  sca:
    enabled: true
    tools: [trivy]
  sast:
    enabled: true
    tools: [opengrep]
exclude_patterns:
  - "target/**"
  - ".mvn/**"
```

#### 6.1.2 Full Scan
```bash
mvn compile -q 2>&1 || echo "Compile needed for SpotBugs"
./lucidshark scan --all --all-files --format json > /tmp/petclinic-scan.json
echo "Exit code: $?"
```
Also via MCP:
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] Scan completes without errors
- [ ] Record issue counts per domain
- [ ] Spring Boot annotations handled correctly by linters
- [ ] SCA finds known CVEs in Spring Boot dependency tree
- [ ] Record scan duration
- [ ] JaCoCo coverage data parsed (if PetClinic has JaCoCo configured)

### 6.2 Google Gson

```bash
cd "$TEST_WORKSPACE/gson"
```

#### 6.2.1 Full Scan (CLI + MCP)
```bash
./lucidshark scan --all --all-files --format json > /tmp/gson-scan.json
echo "Exit code: $?"
```

**Verify:**
- [ ] Scan completes on multi-module Maven project
- [ ] Handles `gson/` submodule structure
- [ ] Checkstyle/PMD run on clean, well-maintained code
- [ ] Record results

### 6.3 OkHttp (Gradle)

```bash
cd "$TEST_WORKSPACE/okhttp"
```

#### 6.3.1 Full Scan
```bash
./lucidshark scan --all --all-files --format json > /tmp/okhttp-scan.json
echo "Exit code: $?"
```

**Additional Gradle-specific checks:**
- [ ] Gradle wrapper (`gradlew`) correctly detected
- [ ] Uses `./gradlew test` for testing (not `mvn test`)
- [ ] JaCoCo report path: `build/reports/jacoco/test/jacoco.xml` (Gradle convention)
- [ ] SpotBugs looks for classes in `build/classes/java/main/` (Gradle convention)
- [ ] SCA scans `build.gradle.kts` or `build.gradle`
- [ ] Handles Kotlin/Java mixed source sets

### 6.4 Apache Commons Lang

```bash
cd "$TEST_WORKSPACE/commons-lang"
```

#### 6.4.1 Full Scan
```bash
./lucidshark scan --all --all-files --format json > /tmp/commons-lang-scan.json
echo "Exit code: $?"
```

**Additional checks:**
- [ ] Handles large, mature codebase
- [ ] No crashes on edge cases in utility code
- [ ] SpotBugs handles extensive test suite
- [ ] Record scan duration (large project performance)

---

## Phase 7: Edge Case Testing

### 7.1 Empty Java File
```bash
cd "$TEST_WORKSPACE/test-project"
touch src/main/java/com/example/app/Empty.java
./lucidshark scan --linting --files src/main/java/com/example/app/Empty.java --format json
```

**Verify:**
- [ ] No crash on empty file
- [ ] Zero or minimal issues reported (may flag missing package declaration)

### 7.2 Syntax Error File
```bash
cat > src/main/java/com/example/app/Broken.java << 'EOF'
package com.example.app;

public class Broken {
    // Missing closing brace
    public void broken() {
        System.out.println("broken"
EOF
./lucidshark scan --linting --files src/main/java/com/example/app/Broken.java --format json
./lucidshark scan --type-checking --files src/main/java/com/example/app/Broken.java --format json
```

**Verify:**
- [ ] Handles syntax errors gracefully
- [ ] Reports syntax error as an issue
- [ ] Does not crash
- [ ] SpotBugs handles uncompilable file gracefully

### 7.3 Very Large File
```bash
python3 -c "
print('package com.example.app;')
print('public class LargeFile {')
for i in range(5000):
    print(f'    public int method_{i}(int x) {{ return x + {i}; }}')
print('}')
" > src/main/java/com/example/app/LargeFile.java
./lucidshark scan --linting --files src/main/java/com/example/app/LargeFile.java --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Handles large file without OOM or timeout
- [ ] Results returned in reasonable time
- [ ] Checkstyle and PMD handle 5000+ methods

### 7.4 Non-ASCII / Unicode File
```bash
cat > src/main/java/com/example/app/Unicode.java << 'EOF'
package com.example.app;

/**
 * Klasse mit deutschen Umlauten: äöü ÄÖÜ ß
 * 日本語コメント
 * Émoji test: 🎉 👋
 */
public class Unicode {

    private String grüße = "Hallo Welt!";
    private String 変数 = "テスト";

    public String getGreeting() {
        return grüße;
    }
}
EOF
./lucidshark scan --linting --files src/main/java/com/example/app/Unicode.java --format json
```

**Verify:**
- [ ] Handles Unicode content
- [ ] No encoding errors from Checkstyle/PMD
- [ ] Java allows Unicode identifiers  -  verify tool handles them

### 7.5 No Java Project (Wrong Language Detection)
```bash
mkdir -p "$TEST_WORKSPACE/not-java"
cd "$TEST_WORKSPACE/not-java"
git init
echo "print('hello')" > app.py
echo 'flask==2.0.0' > requirements.txt
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Does NOT try to run Checkstyle/PMD/SpotBugs on Python project
- [ ] Auto-detects Python instead, or reports no applicable Java tools

### 7.6 Mixed Language Project
```bash
mkdir -p "$TEST_WORKSPACE/mixed-lang/src/main/java/com/example"
cd "$TEST_WORKSPACE/mixed-lang"
git init
echo "package com.example; public class App { }" > src/main/java/com/example/App.java
echo "import os" > app.py
echo "console.log('hello')" > app.js
./lucidshark scan --linting --all-files --format json
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Handles multiple languages
- [ ] Runs Checkstyle/PMD for `.java` files
- [ ] Runs appropriate linter for `.py` and `.js` files
- [ ] No cross-language tool confusion

### 7.7 Multi-Module Maven Project
```bash
mkdir -p "$TEST_WORKSPACE/multi-module/module-a/src/main/java/com/example"
mkdir -p "$TEST_WORKSPACE/multi-module/module-b/src/main/java/com/example"
cd "$TEST_WORKSPACE/multi-module"
git init

cat > pom.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>pom</packaging>
    <modules>
        <module>module-a</module>
        <module>module-b</module>
    </modules>
</project>
EOF

cat > module-a/pom.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent><groupId>com.example</groupId><artifactId>parent</artifactId><version>1.0-SNAPSHOT</version></parent>
    <artifactId>module-a</artifactId>
</project>
EOF

cat > module-b/pom.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent><groupId>com.example</groupId><artifactId>parent</artifactId><version>1.0-SNAPSHOT</version></parent>
    <artifactId>module-b</artifactId>
</project>
EOF

echo "package com.example; public class ModuleA { }" > module-a/src/main/java/com/example/ModuleA.java
echo "package com.example; public class ModuleB { }" > module-b/src/main/java/com/example/ModuleB.java

./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project"
```

**Verify:**
- [ ] Scans Java files across ALL modules
- [ ] Checkstyle/PMD find files in both `module-a/` and `module-b/`
- [ ] SpotBugs detects classes in both module `target/classes/` directories

Clean up edge case files:
```bash
cd "$TEST_WORKSPACE/test-project"
rm -f src/main/java/com/example/app/Empty.java src/main/java/com/example/app/Broken.java src/main/java/com/example/app/LargeFile.java src/main/java/com/example/app/Unicode.java
```

---

## Phase 8: Installation Method Comparison

Compare the binary (from install.sh in Phase 1.1) and pip installation (from setup script in Phase 2.3):

### 8.1 Feature Parity
Run a subset of scans with BOTH installation methods and compare:

```bash
cd "$TEST_WORKSPACE/test-project"

# Test with binary (CLI tests use this)
./lucidshark scan --linting --all-files --format json > /tmp/binary-java-results.json
echo "Binary exit code: $?"

# Test with pip (from venv created by setup script)
source .venv/bin/activate
lucidshark scan --linting --all-files --format json > /tmp/pip-java-results.json
echo "Pip exit code: $?"
deactivate
```

**Compare:**
- [ ] Same issues detected?
- [ ] Same output format?
- [ ] Same exit codes?
- [ ] Same managed tool download behavior (Checkstyle, PMD, SpotBugs JARs)?
- [ ] Any behavioral differences?

**Note:** Both installations (binary and pip) are from the same local source (installed by setup script in Phase 2.3), so they MUST match.

### 8.2 Tool Availability
```bash
cd "$TEST_WORKSPACE/test-project"

# Binary
./lucidshark doctor

# Pip (from venv)
source .venv/bin/activate
lucidshark doctor
deactivate
```

**Compare which tools are bundled vs. required externally for each method.**

---

## Phase 9: Managed Tool Download Testing

This is Java-specific: Checkstyle, PMD, and SpotBugs are auto-downloaded JARs.

### 9.1 First-Run Download
```bash
# Clear cached tools
rm -rf .lucidshark/bin/

# Run scan  -  should trigger downloads
./lucidshark --debug scan --linting --type-checking --all-files --format json 2>&1 | grep -i "download\|cache\|jar"
```

**Verify:**
- [ ] Checkstyle JAR downloaded from `https://github.com/checkstyle/checkstyle/releases/`
- [ ] PMD ZIP downloaded from `https://github.com/pmd/pmd/releases/`
- [ ] SpotBugs ZIP downloaded from `https://github.com/spotbugs/spotbugs/releases/`
- [ ] All downloads use HTTPS
- [ ] Files cached in `.lucidshark/bin/{tool}/{version}/`
- [ ] Download progress/status shown

### 9.2 Cached Run
```bash
# Run again  -  should use cached JARs
./lucidshark --debug scan --linting --type-checking --all-files --format json 2>&1 | grep -i "download\|cache\|jar"
```

**Verify:**
- [ ] No re-download on second run
- [ ] JARs loaded from cache
- [ ] Faster execution time than first run

### 9.3 Corrupted Cache
```bash
# Corrupt a cached JAR
echo "corrupted" > .lucidshark/bin/checkstyle/13.3.0/checkstyle-13.3.0-all.jar 2>/dev/null || true
./lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Handles corrupted JAR gracefully
- [ ] Either re-downloads or reports clear error
- [ ] Does not crash with cryptic Java error

Restore: `rm -rf .lucidshark/bin/`

---

## Phase 10: Regression Checks for Known Bugs

Check whether these previously reported bugs (from Python testing) also affect Java:

| Bug | Test | Status |
|-----|------|--------|
| BUG-001: `--formatting` CLI flag broken | Run `lucidshark scan --formatting --all-files` without config | |
| BUG-002: `--all` without config only runs limited domains | Run `lucidshark scan --all --all-files` without config, check executed_domains | |
| BUG-003: Ghost formatting issue | Run formatting scan, check for issue with tool output in file_path | |
| BUG-004: Duration always 0ms | Check `duration_ms` in any scan metadata | |
| BUG-005: `enabled_domains` empty without config | Check metadata when scanning without config | |
| BUG-006: `scanners_used` empty for non-security | Check metadata when running linting only | |
| BUG-007: MCP coverage "no data" after testing | Run `mcp__lucidshark__scan(domains=["testing", "coverage"])` | |
| BUG-008: `apply_fix` fixes ALL issues | Test if applicable (Java linters may not support auto-fix) | |

---

## Test Report Template

Write the report with this structure:

```markdown
# LucidShark Java Support  -  E2E Test Report

**Date:** YYYY-MM-DD
**Tester:** Claude (model version)
**LucidShark Version:** (from `lucidshark --version`)
**Installation Method:** Universal setup script (installed both binary and pip from local source)
**Java Version:** (from `java -version`)
**Maven Version:** (from `mvn --version`)
**Platform:** (from `uname -a`)
**Tool Versions:** Checkstyle 13.3.0, PMD 7.23.0, SpotBugs 4.9.8, google-java-format X.Y.Z, Trivy X.Y.Z, OpenGrep X.Y.Z, Duplo X.Y.Z

---

## Executive Summary
(2-3 paragraph overview: what works, what's broken, overall assessment)

## Environment
(Full environment info from Phase 0)

## Installation Testing Results
### install.sh (Binary)
### Setup Script Installation (Binary + Pip Editable)
### Binary vs Pip Comparison

## Init & Configuration Results
### lucidshark init
### Autoconfigure
### Config Validation

## CLI Scan Results by Domain
### Linting  -  Checkstyle
### Linting  -  PMD
### Type Checking  -  SpotBugs
### Formatting  -  google-java-format
### Testing  -  Maven
### Testing  -  Gradle
### Coverage  -  JaCoCo
### Duplication  -  Duplo
### SAST  -  OpenGrep
### SCA  -  Trivy

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
### Spring PetClinic (Maven, Spring Boot)
### Google Gson (Maven, library)
### OkHttp (Gradle, modern Java)
### Apache Commons Lang (Maven, utility library)

## Managed Tool Download Results
### First-run download behavior
### Cache behavior
### Corrupted cache handling

## Edge Case Results

## Output Format Results
(json, summary, table, ai, sarif)

## Build System Comparison
### Maven vs Gradle
(Document differences in detection, test execution, coverage report paths, SpotBugs class paths)

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
### P0  -  Must Fix
### P1  -  Should Fix
### P2  -  Nice to Have

## Conclusion
(Overall assessment with score out of 10)

## Cleanup

After completing the test, remove all test artifacts:

```bash
# If you still have the TEST_WORKSPACE variable:
rm -rf "$TEST_WORKSPACE"

# Or if the variable is lost:
rm -rf /tmp/lucidshark-java-e2e-*

# Verify cleanup:
ls /tmp/lucidshark-java-e2e-* 2>/dev/null || echo "✓ All test artifacts removed"
```

**What gets deleted:**
- All cloned projects (spring-petclinic, gson, okhttp, commons-lang)
- The artificial test-project
- All installation test directories
- Any generated coverage reports, build artifacts, and cached JARs

**Safe to delete:** Everything was isolated in `/tmp`  -  no files in your actual workspace were touched.
```

---

## Important Notes for the Tester

1. **Execute every command.** Do not skip steps even if you think you know the outcome.
2. **Capture actual output.** Include relevant snippets in the report, not just pass/fail.
3. **Record exit codes** for every `lucidshark scan` command.
4. **Measure wall-clock time** for scans on large projects (Spring PetClinic, OkHttp).
5. **Compare MCP vs CLI** results for the same operation  -  discrepancies are bugs.
6. **Check for regressions** against all previously reported bugs.
7. **Test BOTH with and without `lucidshark.yml`** to verify config-less experience.
8. **Clean up** between tests that modify files (`git checkout -- .`).
9. **Compile before SpotBugs**  -  SpotBugs requires `.class` files. Run `mvn compile` or `./gradlew classes` first.
10. **If a tool is not installed** (e.g., google-java-format, opengrep, duplo), document it  -  don't skip the test.
11. **Maven/Gradle may need internet** to download dependencies. If offline, document which tests are affected.
12. **Managed tool JARs require JDK**  -  if JDK is not available, Checkstyle/PMD/SpotBugs will all fail. Document this clearly.
13. **Test both Maven and Gradle paths**  -  use test-project for Maven, OkHttp for Gradle.
