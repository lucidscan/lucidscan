# LucidShark JavaScript/TypeScript Support — End-to-End Test Instructions

**Purpose:** You are performing a comprehensive end-to-end test of LucidShark's JavaScript/TypeScript support. You will test both the CLI and MCP interfaces across all applicable domains, using real open-source JS/TS projects checked out from GitHub. You will test installation via both the install script and pip, run `lucidshark init`, `autoconfigure`, and exercise every scan domain and MCP tool. At the end, write a detailed test report.

**IMPORTANT:** Execute every step below. Do not skip steps or summarize without actually running the commands. Capture actual output, exit codes, and timings. If a step fails, document the failure in detail and continue with the next step.

---

## Tools Under Test

| Domain | Tools | File Types |
|--------|-------|------------|
| Linting | ESLint, Biome | `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`, `.cts` |
| Type Checking | TypeScript (tsc) | `.ts`, `.tsx`, `.mts`, `.cts` |
| Formatting | Prettier, Biome | `.js`, `.jsx`, `.ts`, `.tsx`, `.css`, `.json`, `.md` |
| Testing | Jest, Vitest, Mocha, Karma, Playwright | `.test.ts`, `.spec.ts`, `.test.js`, `.spec.js` |
| Coverage | Istanbul/NYC, Vitest Coverage | via test runners |
| Duplication | Duplo | `.js`, `.jsx`, `.ts`, `.tsx` |
| SAST | OpenGrep | `.js`, `.jsx`, `.ts`, `.tsx` |
| SCA | Trivy | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |

---

## Phase 0: Environment Setup

### 0.1 Record Environment Info

```bash
uname -a
node --version
npm --version
npx --version
python3 --version
pip3 --version
git --version
echo "Disk space:" && df -h .
echo "Working directory:" && pwd
```

Record all output in the test report under "Environment".

### 0.2 Create Clean Test Workspace

```bash
export TEST_WORKSPACE="/tmp/lucidshark-js-e2e-$(date +%s)"
mkdir -p "$TEST_WORKSPACE"
cd "$TEST_WORKSPACE"
```

All subsequent work happens inside `$TEST_WORKSPACE`. Do NOT use any pre-existing LucidShark installation.

### 0.3 Record Tool Versions (After Installation)

Run after completing Phase 1 (installation) and Phase 2 (project setup with `node_modules`):

```bash
cd "$TEST_WORKSPACE/test-project-jest"
npx eslint --version 2>/dev/null || echo "ESLint not installed"
npx tsc --version 2>/dev/null || echo "TypeScript not installed"
npx prettier --version 2>/dev/null || echo "Prettier not installed"
npx jest --version 2>/dev/null || echo "Jest not installed"
npx mocha --version 2>/dev/null || echo "Mocha not installed"

cd "$TEST_WORKSPACE/test-project-vitest"
npx vitest --version 2>/dev/null || echo "Vitest not installed"
npx biome --version 2>/dev/null || echo "Biome not installed"

# System-level tools
lucidshark doctor 2>/dev/null | head -30
```

Record all versions in the test report.

---

## Phase 1: Installation Testing

### 1.1 Install via install.sh (Binary)

```bash
cd "$TEST_WORKSPACE"
mkdir install-script-test && cd install-script-test
git init
curl -fsSL https://raw.githubusercontent.com/toniantunovi/lucidshark/main/install.sh | bash
```

**Verify:**
- [ ] Binary downloaded successfully to `./lucidshark`
- [ ] `./lucidshark --version` outputs a version string
- [ ] `./lucidshark --help` shows help text with all subcommands (scan, init, status, doctor, help, validate, overview, serve)
- [ ] `./lucidshark status` runs without error
- [ ] `./lucidshark doctor` runs and shows tool availability

Record the version number and which tools `doctor` reports as available/missing.

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

### 1.3 Install via pip

```bash
cd "$TEST_WORKSPACE"
python3 -m venv pip-install-test
source pip-install-test/bin/activate
pip install lucidshark
```

**Verify:**
- [ ] `pip install lucidshark` succeeds without errors
- [ ] `lucidshark --version` outputs a version string
- [ ] `lucidshark --help` shows all subcommands
- [ ] `lucidshark status` works
- [ ] `lucidshark doctor` works
- [ ] Compare: does the pip version match the install.sh latest version? Document any differences.

### 1.4 Install via pip with Specific Version

```bash
pip install lucidshark==0.5.63
lucidshark --version
```

**Verify:**
- [ ] Correct version installed
- [ ] Downgrade/upgrade worked cleanly

### 1.5 Install from Source (Development)

```bash
cd "$TEST_WORKSPACE"
git clone https://github.com/toniantunovi/lucidshark.git lucidshark-source
cd lucidshark-source
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
lucidshark --version
```

**Verify:**
- [ ] Editable install succeeds
- [ ] `lucidshark` command is available
- [ ] Version matches source

**Decide which installation to use for remaining tests.** Prefer the pip install (1.3) for consistency. Keep the venv activated.

---

## Phase 2: Test Project Setup

### 2.1 Clone Test Projects from GitHub

Clone these real-world JavaScript/TypeScript projects. Each serves a different test purpose:

```bash
cd "$TEST_WORKSPACE"

# Project 1: Express — classic Node.js, plain JS, ESLint, Mocha tests
# Represents: vanilla JS backend projects (~30% of Node ecosystem)
git clone --depth 1 https://github.com/expressjs/express.git

# Project 2: Axios — JS/TS HTTP client, Jest tests, widely used
# Represents: npm libraries, mixed JS/TS, Jest ecosystem
git clone --depth 1 https://github.com/axios/axios.git

# Project 3: Zustand — TypeScript, Vitest, modern React state management
# Represents: modern TS + Vite ecosystem, React libraries
git clone --depth 1 https://github.com/pmndrs/zustand.git

# Project 4: Playwright — TypeScript, Playwright tests, large project
# Represents: E2E testing projects, monorepo structures
git clone --depth 1 https://github.com/microsoft/playwright.git

# Project 5: Sinon — JS test spy/stub library, Mocha tests, .mocharc.yml config
# Represents: widely-used test utility, Mocha with structured config
git clone --depth 1 https://github.com/sinonjs/sinon.git

# Project 6: Hexo — Blog framework, plain JS, Mocha tests, large test suite
# Represents: medium-sized Mocha project with many test files
git clone --depth 1 https://github.com/hexojs/hexo.git

# Project 7: Socket.IO — Real-time framework, TypeScript, Mocha tests
# Represents: TS project using Mocha (not Jest/Vitest), monorepo
git clone --depth 1 https://github.com/socketio/socket.io.git
```

Install dependencies for each:
```bash
cd "$TEST_WORKSPACE/express" && npm install --ignore-scripts 2>&1 | tail -5
cd "$TEST_WORKSPACE/axios" && npm install --ignore-scripts 2>&1 | tail -5
cd "$TEST_WORKSPACE/zustand" && npm install --ignore-scripts 2>&1 | tail -5
cd "$TEST_WORKSPACE/sinon" && npm install --ignore-scripts 2>&1 | tail -5
cd "$TEST_WORKSPACE/hexo" && npm install --ignore-scripts 2>&1 | tail -5
cd "$TEST_WORKSPACE/socket.io" && npm install --ignore-scripts 2>&1 | tail -5
# Playwright is large — skip full install, just test scanning source files
```

### 2.2 Create Custom Vulnerable Test Project (Jest variant)

This project has intentional issues across ALL domains for comprehensive testing with **Jest**:

```bash
mkdir -p "$TEST_WORKSPACE/test-project-jest/src"
mkdir -p "$TEST_WORKSPACE/test-project-jest/tests"
cd "$TEST_WORKSPACE/test-project-jest"
git init
npm init -y
```

**Create `tsconfig.json`:**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": false,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

**Create `.eslintrc.json`:**
```json
{
  "env": {
    "node": true,
    "es2020": true,
    "jest": true
  },
  "parser": "@typescript-eslint/parser",
  "parserOptions": {
    "ecmaVersion": 2020,
    "sourceType": "module"
  },
  "plugins": ["@typescript-eslint"],
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended"
  ],
  "rules": {
    "no-unused-vars": "off",
    "@typescript-eslint/no-unused-vars": "error",
    "@typescript-eslint/no-explicit-any": "warn",
    "no-eval": "error",
    "no-implied-eval": "error"
  }
}
```

**Create `.prettierrc`:**
```json
{
  "semi": true,
  "trailingComma": "all",
  "singleQuote": true,
  "printWidth": 80,
  "tabWidth": 2
}
```

**Install dev dependencies:**
```bash
npm install --save-dev typescript @typescript-eslint/parser @typescript-eslint/eslint-plugin eslint prettier jest ts-jest @types/jest @types/node
```

**Create `jest.config.ts`:**
```typescript
import type { Config } from 'jest';

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/tests'],
  testMatch: ['**/*.test.ts'],
  collectCoverageFrom: ['src/**/*.ts', '!src/**/*.d.ts'],
  coverageDirectory: 'coverage',
  coverageReporters: ['json-summary', 'json', 'text', 'lcov'],
};

export default config;
```

**Create `src/main.ts`** (linting + formatting + type errors):
```typescript
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { EventEmitter } from 'events';

// Unused variable
const unusedConfig = { debug: true, verbose: false };

// Type error: number assigned to string
const userName: string = 42;

// Badly formatted function (Prettier violations)
function   processData(  data: string,    count:number  ):    string {
    const    x:string = 123;  // type error: number to string
    const unused = "never used";
    const result = data.toUpperCase(  );
    return 42;  // type error: returning number from string function
}

function    badlyFormatted(   a:boolean,b:number,c:number   ) {
  if(a){
          return b
    }
      else {
              return c
      }
}

interface UserData {
  name: string;
  age: number;
  email: string;
}

class UserManager {
  private users: Map<string, UserData> = new Map();

  addUser(name: string, age: number): void {
    // Type error: age is number but UserData.name expects string
    this.users.set(name, { name: age, age: name, email: 123 });
  }

  getUser(name: string): UserData | undefined {
    return this.users.get(name);
  }

  // Missing return in some paths
  findUser(predicate: (u: UserData) => boolean): UserData {
    for (const [, user] of this.users) {
      if (predicate(user)) {
        return user;
      }
    }
    // Missing return — violates noImplicitReturns
  }
}

export { processData, badlyFormatted, UserManager };
export type { UserData };
```

**Create `src/security.ts`** (SAST issues):
```typescript
import { execSync, exec } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';

// Command Injection via exec
export function runCommand(userInput: string): string {
  return execSync(userInput).toString();
}

// Command Injection via template literal
export function runShellCommand(cmd: string): void {
  exec(`bash -c "${cmd}"`, (error, stdout) => {
    console.log(stdout);
  });
}

// Eval usage — code injection
export function evaluate(expression: string): unknown {
  return eval(expression);
}

// SQL Injection (raw string concatenation)
export function getUser(db: any, username: string): any {
  const query = "SELECT * FROM users WHERE name = '" + username + "'";
  return db.query(query);
}

// SQL Injection via template literal
export function getUserById(db: any, id: string): any {
  return db.query(`SELECT * FROM users WHERE id = ${id}`);
}

// Path Traversal
export function readFile(baseDir: string, filename: string): string {
  const filepath = baseDir + '/' + filename;
  return fs.readFileSync(filepath, 'utf-8');
}

// Path Traversal via path.join (still vulnerable if filename has ../)
export function readUserFile(filename: string): string {
  return fs.readFileSync(path.join('/uploads', filename), 'utf-8');
}

// Weak Crypto — MD5 for password
export function hashPassword(password: string): string {
  return crypto.createHash('md5').update(password).digest('hex');
}

// Hardcoded Secrets
export const API_KEY = 'sk-1234567890abcdef1234567890abcdef';
export const DATABASE_URL = 'postgresql://admin:super_secret_password@localhost:5432/mydb';
export const JWT_SECRET = 'my-super-secret-jwt-key-dont-share';

// Insecure Deserialization (JSON.parse from untrusted input used in eval-like context)
export function deserializePayload(data: string): unknown {
  const parsed = JSON.parse(data);
  // Using Function constructor as eval alternative
  return new Function('return ' + parsed.code)();
}

// Prototype Pollution
export function merge(target: any, source: any): any {
  for (const key in source) {
    if (typeof source[key] === 'object') {
      target[key] = merge(target[key] || {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

// ReDoS vulnerable regex
export function validateEmail(email: string): boolean {
  const regex = /^([a-zA-Z0-9_\.\-])+\@(([a-zA-Z0-9\-])+\.)+([a-zA-Z0-9]{2,4})+$/;
  return regex.test(email);
}
```

**Create `src/duplicate1.ts`** (duplication detection):
```typescript
export interface Statistics {
  mean: number;
  total: number;
  count: number;
  min: number;
  max: number;
  variance: number;
  stdDev: number;
}

export function calculateStatistics(numbers: number[]): Statistics {
  const total = numbers.reduce((sum, n) => sum + n, 0);
  const count = numbers.length;
  if (count === 0) {
    return { mean: 0, total: 0, count: 0, min: 0, max: 0, variance: 0, stdDev: 0 };
  }
  const mean = total / count;
  const minimum = Math.min(...numbers);
  const maximum = Math.max(...numbers);
  const variance = numbers.reduce((sum, x) => sum + Math.pow(x - mean, 2), 0) / count;
  const stdDev = Math.sqrt(variance);
  return {
    mean,
    total,
    count,
    min: minimum,
    max: maximum,
    variance,
    stdDev,
  };
}
```

**Create `src/duplicate2.ts`** (near-duplicate of duplicate1.ts):
```typescript
export interface MetricResult {
  mean: number;
  total: number;
  count: number;
  min: number;
  max: number;
  variance: number;
  stdDev: number;
}

export function computeMetrics(values: number[]): MetricResult {
  const total = values.reduce((sum, n) => sum + n, 0);
  const count = values.length;
  if (count === 0) {
    return { mean: 0, total: 0, count: 0, min: 0, max: 0, variance: 0, stdDev: 0 };
  }
  const mean = total / count;
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const variance = values.reduce((sum, x) => sum + Math.pow(x - mean, 2), 0) / count;
  const stdDev = Math.sqrt(variance);
  return {
    mean,
    total,
    count,
    min: minimum,
    max: maximum,
    variance,
    stdDev,
  };
}
```

**Create `tests/main.test.ts`:**
```typescript
import { processData, badlyFormatted, UserManager } from '../src/main';

describe('processData', () => {
  it('should uppercase the input string', () => {
    // This will fail because processData returns 42, not a string
    const result = processData('hello', 1);
    expect(result).toBe('HELLO');
  });

  it('should handle empty string', () => {
    const result = processData('', 0);
    expect(result).toBe('');
  });
});

describe('badlyFormatted', () => {
  it('should return b when a is true', () => {
    expect(badlyFormatted(true, 1, 2)).toBe(1);
  });

  it('should return c when a is false', () => {
    expect(badlyFormatted(false, 1, 2)).toBe(2);
  });
});

describe('UserManager', () => {
  it('should add and retrieve a user', () => {
    const mgr = new UserManager();
    mgr.addUser('alice', 30);
    const user = mgr.getUser('alice');
    expect(user).toBeDefined();
    expect(user?.name).toBe('alice');
  });
});

describe('basic passing tests', () => {
  it('adds numbers correctly', () => {
    expect(1 + 1).toBe(2);
  });

  it('uppercases strings', () => {
    expect('hello'.toUpperCase()).toBe('HELLO');
  });
});
```

**Create `package.json`** (with known vulnerable packages):
```json
{
  "name": "test-project-jest",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "build": "tsc",
    "test": "jest",
    "test:coverage": "jest --coverage",
    "lint": "eslint src/ tests/",
    "format": "prettier --check .",
    "format:fix": "prettier --write ."
  },
  "dependencies": {
    "express": "4.17.1",
    "lodash": "4.17.20",
    "jsonwebtoken": "8.5.1",
    "axios": "0.21.1",
    "minimist": "1.2.5",
    "node-fetch": "2.6.1",
    "tar": "6.1.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "@typescript-eslint/parser": "^6.0.0",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "eslint": "^8.0.0",
    "prettier": "^3.0.0",
    "jest": "^29.0.0",
    "ts-jest": "^29.0.0",
    "@types/jest": "^29.0.0",
    "@types/node": "^20.0.0"
  }
}
```

Commit everything:
```bash
cd "$TEST_WORKSPACE/test-project-jest"
npm install --ignore-scripts 2>&1 | tail -5
git add -A && git commit -m "Initial commit with intentional issues"
```

### 2.3 Create Custom Vulnerable Test Project (Vitest variant)

This project tests the Vitest + Biome + Prettier + Vite ecosystem:

```bash
mkdir -p "$TEST_WORKSPACE/test-project-vitest/src"
mkdir -p "$TEST_WORKSPACE/test-project-vitest/tests"
cd "$TEST_WORKSPACE/test-project-vitest"
git init
npm init -y
```

**Create `tsconfig.json`:**
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": false,
    "forceConsistentCasingInFileNames": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

**Create `biome.json`:**
```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "organizeImports": {
    "enabled": true
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "suspicious": {
        "noExplicitAny": "warn"
      },
      "complexity": {
        "noUselessFragments": "error"
      }
    }
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 80
  }
}
```

**Create `vitest.config.ts`:**
```typescript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['json-summary', 'json', 'text', 'lcov'],
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.d.ts'],
    },
  },
});
```

**Install dev dependencies:**
```bash
npm install --save-dev typescript vitest @vitest/coverage-v8 @biomejs/biome prettier @types/node
```

**Create `src/main.ts`** (same intentional issues as Jest variant):
```typescript
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

const unusedConfig = { debug: true };

const userName: string = 42;  // type error

function   processData(  data: string,    count:number  ):    string {
    const    x:string = 123;
    const unused = "never used";
    return 42;
}

export { processData };
```

**Create `src/duplicate1.ts`** (identical to Jest variant):
```typescript
export function calculateStatistics(numbers: number[]): { mean: number; total: number } {
  const total = numbers.reduce((sum, n) => sum + n, 0);
  const count = numbers.length;
  if (count === 0) {
    return { mean: 0, total: 0 };
  }
  const mean = total / count;
  const minimum = Math.min(...numbers);
  const maximum = Math.max(...numbers);
  const variance = numbers.reduce((sum, x) => sum + Math.pow(x - mean, 2), 0) / count;
  const stdDev = Math.sqrt(variance);
  return { mean, total };
}
```

**Create `src/duplicate2.ts`** (near-duplicate):
```typescript
export function computeMetrics(values: number[]): { mean: number; total: number } {
  const total = values.reduce((sum, n) => sum + n, 0);
  const count = values.length;
  if (count === 0) {
    return { mean: 0, total: 0 };
  }
  const mean = total / count;
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const variance = values.reduce((sum, x) => sum + Math.pow(x - mean, 2), 0) / count;
  const stdDev = Math.sqrt(variance);
  return { mean, total };
}
```

**Create `tests/main.test.ts`:**
```typescript
import { describe, it, expect } from 'vitest';
import { processData } from '../src/main';

describe('processData', () => {
  it('should uppercase the input string', () => {
    const result = processData('hello', 1);
    expect(result).toBe('HELLO');
  });
});

describe('basic tests', () => {
  it('adds numbers', () => {
    expect(1 + 1).toBe(2);
  });

  it('passes always', () => {
    expect(true).toBe(true);
  });
});
```

**Create `package.json`:**
```json
{
  "name": "test-project-vitest",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "tsc",
    "test": "vitest run",
    "test:coverage": "vitest run --coverage",
    "lint": "biome check src/",
    "format": "prettier --check ."
  },
  "dependencies": {
    "express": "4.17.1",
    "lodash": "4.17.20",
    "axios": "0.21.1"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "vitest": "^1.0.0",
    "@vitest/coverage-v8": "^1.0.0",
    "@biomejs/biome": "^1.9.0",
    "prettier": "^3.0.0",
    "@types/node": "^20.0.0"
  }
}
```

Commit:
```bash
cd "$TEST_WORKSPACE/test-project-vitest"
npm install --ignore-scripts 2>&1 | tail -5
git add -A && git commit -m "Initial commit with intentional issues"
```

### 2.4 Create Mocha Test Project

This tests the Mocha ecosystem (used by Express, many classic Node.js projects):

```bash
mkdir -p "$TEST_WORKSPACE/test-project-mocha/src"
mkdir -p "$TEST_WORKSPACE/test-project-mocha/test"
cd "$TEST_WORKSPACE/test-project-mocha"
git init
npm init -y
```

**Create `.mocharc.yml`:**
```yaml
spec: "test/**/*.test.{js,ts}"
timeout: 5000
exit: true
```

**Create `src/math.js`:**
```javascript
function add(a, b) {
  return a + b;
}

function divide(a, b) {
  return a / b;  // no zero check — intentional bug
}

function multiply(a, b) {
  return a * b;
}

module.exports = { add, divide, multiply };
```

**Create `src/string-utils.js`:**
```javascript
function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function reverse(str) {
  return str.split('').reverse().join('');
}

module.exports = { capitalize, reverse };
```

**Create `test/math.test.js`:**
```javascript
const assert = require('assert');
const { add, divide, multiply } = require('../src/math');

describe('Math functions', function() {
  describe('add', function() {
    it('should add two positive numbers', function() {
      assert.strictEqual(add(1, 2), 3);
    });

    it('should add negative numbers', function() {
      assert.strictEqual(add(-1, -2), -3);
    });

    it('should add zero', function() {
      assert.strictEqual(add(0, 5), 5);
    });
  });

  describe('divide', function() {
    it('should divide two numbers', function() {
      assert.strictEqual(divide(10, 2), 5);
    });

    it('should return Infinity for divide by zero', function() {
      // This tests the intentional bug — no zero check
      assert.strictEqual(divide(10, 0), Infinity);
    });
  });

  describe('multiply', function() {
    it('should multiply two numbers', function() {
      assert.strictEqual(multiply(3, 4), 12);
    });
  });
});
```

**Create `test/string-utils.test.js`:**
```javascript
const assert = require('assert');
const { capitalize, reverse } = require('../src/string-utils');

describe('String utils', function() {
  describe('capitalize', function() {
    it('should capitalize first letter', function() {
      assert.strictEqual(capitalize('hello'), 'Hello');
    });

    it('should handle empty string', function() {
      assert.strictEqual(capitalize(''), '');
    });

    it('should intentionally fail', function() {
      // Intentional failure for testing
      assert.strictEqual(capitalize('hello'), 'hello');
    });
  });

  describe('reverse', function() {
    it('should reverse a string', function() {
      assert.strictEqual(reverse('abc'), 'cba');
    });
  });
});
```

**Create `package.json`:**
```json
{
  "name": "test-project-mocha",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "test": "mocha",
    "test:coverage": "nyc mocha"
  },
  "devDependencies": {
    "mocha": "^10.0.0",
    "nyc": "^15.0.0"
  }
}
```

**Install and commit:**
```bash
npm install --ignore-scripts 2>&1 | tail -5
git add -A && git commit -m "Initial Mocha test project"
```

### 2.5 Create Minimal Karma Test Project

This tests the Karma/Angular ecosystem:

```bash
mkdir -p "$TEST_WORKSPACE/test-project-karma/src"
mkdir -p "$TEST_WORKSPACE/test-project-karma/tests"
cd "$TEST_WORKSPACE/test-project-karma"
git init
npm init -y
```

**Create `karma.conf.js`:**
```javascript
module.exports = function(config) {
  config.set({
    frameworks: ['jasmine'],
    files: ['tests/**/*.spec.js'],
    reporters: ['progress', 'json'],
    browsers: ['ChromeHeadless'],
    singleRun: true,
    jsonReporter: {
      stdout: true
    }
  });
};
```

**Create `tests/basic.spec.js`:**
```javascript
describe('Basic suite', function() {
  it('should add numbers', function() {
    expect(1 + 1).toBe(2);
  });

  it('should concatenate strings', function() {
    expect('hello' + ' ' + 'world').toBe('hello world');
  });
});
```

**Install deps:**
```bash
npm install --save-dev karma karma-jasmine karma-chrome-launcher karma-json-reporter jasmine-core
```

Commit:
```bash
git add -A && git commit -m "Initial Karma test project"
```

---

## Phase 3: Init & Configuration Testing

### 3.1 Test `lucidshark init` on Jest Test Project

```bash
cd "$TEST_WORKSPACE/test-project-jest"
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

**CRITICAL:** This phase tests the complete autoconfiguration workflow from detection to validation to execution. Do NOT skip steps or use pre-written configs. The goal is to verify that LucidShark can automatically configure itself for real-world projects.

---

### 3.2.1 Autoconfigure Real-World Project: axios (Vitest)

**Objective:** Test autoconfiguration on a real Vitest project without using templates.

#### Step 1: Call Autoconfigure MCP Tool
```bash
cd "$TEST_WORKSPACE/axios"
```
```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Mentions detecting JavaScript/TypeScript from package.json
- [ ] Mentions detecting test frameworks (Jest, Mocha, Vitest, Karma, Playwright)
- [ ] Mentions detecting ESLint/Biome
- [ ] Mentions detecting TypeScript
- [ ] Includes example configs for TypeScript projects
- [ ] Includes common exclusion patterns (node_modules, dist, coverage, etc.)

#### Step 2: Detect Project Tools

```bash
# Check package manager and language
cat package.json | jq '.name, .scripts.test'

# Check for test framework config
ls -la vitest.config.* jest.config.* karma.conf.* .mocharc.* playwright.config.* 2>/dev/null

# Check for linter config
ls -la .eslintrc* eslint.config.* biome.json 2>/dev/null

# Check for TypeScript
ls -la tsconfig.json 2>/dev/null

# Check installed tools
npm list eslint typescript vitest jest mocha 2>/dev/null | grep -v 'UNMET' | head -20
```

**Record findings:**
- [ ] Test framework detected: _____________ (should be Vitest based on vitest.config.js)
- [ ] Linter detected: _____________ (should be ESLint based on eslint.config.js)
- [ ] Type checker: _____________ (should be TypeScript based on tsconfig.json)
- [ ] Package manager: npm
- [ ] Language: TypeScript + JavaScript

#### Step 3: Check Current Tool Installation

```bash
npm list eslint typescript vitest 2>&1 | grep -E '^[├└]' | head -10
```

**Record which tools are already installed:** _____________

**If any tools are missing, install them:**
```bash
# Only if needed - axios should have all tools already
npm install --save-dev eslint typescript vitest
```

#### Step 4: Generate lucidshark.yml Based on Detection

**IMPORTANT:** Based on the ACTUAL tools detected (Vitest, ESLint, TypeScript), create a config. Do NOT copy-paste a generic template.

```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: axios
  languages: [typescript, javascript]

pipeline:
  linting:
    enabled: true
    tools: [eslint]

  type_checking:
    enabled: true
    tools: [typescript]

  testing:
    enabled: true
    tools: [vitest]

  coverage:
    enabled: true
    tools: [vitest_coverage]
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
      - name: opengrep
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
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/coverage/**"
  - "**/.next/**"
  - "**/.nuxt/**"
EOF
```

#### Step 5: Validate Configuration

```bash
lucidshark validate
echo "Validation exit code: $?"
```

**Verify:**
- [ ] Exit code 0 (valid config)
- [ ] No validation errors
- [ ] Config correctly specifies vitest (not jest)

**If validation fails:**
- [ ] Record error message: _____________
- [ ] Fix the config
- [ ] Re-validate

#### Step 6: Test Generated Config with Scans

**Test linting:**
```bash
lucidshark scan --linting --format ai 2>&1 | head -30
```

**Verify:**
- [ ] ESLint executes successfully
- [ ] Output shows domain_status.linting
- [ ] No errors about missing tools

**Test type checking:**
```bash
lucidshark scan --type-checking --format ai 2>&1 | head -30
```

**Verify:**
- [ ] TypeScript executes successfully
- [ ] May find type errors (expected in test files)

**Test testing:**
```bash
lucidshark scan --testing --format ai 2>&1 | head -30
```

**Verify:**
- [ ] **CRITICAL: Vitest runs, NOT Jest**
- [ ] Tests execute successfully
- [ ] Output shows test results

**Test exclusions work:**
```bash
lucidshark scan --duplication --all-files --format ai 2>&1 | grep -c 'node_modules'
echo "node_modules files scanned (should be 0): $?"
```

**Verify:**
- [ ] node_modules NOT scanned (grep count should be 0 or very low)
- [ ] Only source files scanned

---

### 3.2.2 Autoconfigure Real-World Project: sinon (Mocha)

**Objective:** Verify autoconfiguration correctly detects Mocha (not Jest/Vitest).

#### Step 1: Detect Tools in sinon

```bash
cd "$TEST_WORKSPACE/sinon"

# Check test framework
cat package.json | jq '.scripts.test, .scripts["test-node"]'
ls -la .mocharc.* mocha.opts 2>/dev/null
npm list mocha 2>&1 | grep mocha

# Check for configs
ls -la .eslintrc* eslint.config.* 2>/dev/null
```

**Record findings:**
- [ ] Test framework: _____________ (should be Mocha)
- [ ] Test command: _____________ (should reference mocha)
- [ ] Linter: _____________

#### Step 2: Generate lucidshark.yml for Mocha Project

```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: sinon
  languages: [javascript]

pipeline:
  linting:
    enabled: true
    tools: [eslint]

  testing:
    enabled: true
    tools: [mocha]

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
  security: high
  duplication: any

exclude:
  - "**/.git/**"
  - "**/.lucidshark/**"
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/coverage/**"
EOF
```

#### Step 3: Validate and Test

```bash
lucidshark validate
echo "Validation exit code: $?"

# Test that Mocha runs
lucidshark scan --testing --format ai 2>&1 | head -40
```

**Verify:**
- [ ] Config validates successfully
- [ ] **CRITICAL: Mocha runs, NOT Jest or Vitest**
- [ ] Tests execute successfully
- [ ] Output shows Mocha test results

---

### 3.2.3 Autoconfigure Real-World Project: zustand (Vitest + React)

**Objective:** Test autoconfiguration on modern React + Vitest project.

```bash
cd "$TEST_WORKSPACE/zustand"

# Detect tools
cat package.json | jq '.scripts.test'
ls -la vitest.config.* 2>/dev/null
npm list vitest biome 2>&1 | grep -E '^[├└]'
```

**Generate config:**
```bash
cat > lucidshark.yml << 'EOF'
version: 1

project:
  name: zustand
  languages: [typescript, javascript]

pipeline:
  linting:
    enabled: true
    tools: [eslint]  # or [biome] if zustand uses biome

  type_checking:
    enabled: true
    tools: [typescript]

  testing:
    enabled: true
    tools: [vitest]

  coverage:
    enabled: true
    tools: [vitest_coverage]
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
  - "**/node_modules/**"
  - "**/dist/**"
  - "**/coverage/**"
EOF
```

**Validate and test:**
```bash
lucidshark validate
lucidshark scan --testing --format ai 2>&1 | head -30
```

**Verify:**
- [ ] Vitest detected and runs successfully
- [ ] TypeScript type checking works
- [ ] Config is appropriate for React library

---

### 3.2.4 Summary Table: Autoconfiguration Results

**For each project, verify detection was correct:**

| Project | Expected Test Framework | Detected Framework | Expected Linter | Detected Linter | Config Valid? | Scans Work? | Notes |
|---------|-------------------------|-------------------|-----------------|-----------------|---------------|-------------|-------|
| axios | Vitest | | ESLint | | | | |
| sinon | Mocha | | ESLint | | | | |
| zustand | Vitest | | ESLint/Biome | | | | |

**Autoconfiguration Test Verdict:**
- [ ] **PASS:** All projects correctly detected test frameworks (Vitest for axios/zustand, Mocha for sinon)
- [ ] **PASS:** Generated configs validated successfully
- [ ] **PASS:** Scans executed successfully with generated configs
- [ ] **PASS:** Exclusions prevented scanning node_modules
- [ ] **FAIL:** <describe what failed> _____________

---

### 3.3 Test Autoconfigure MCP Tool Directly

```
mcp__lucidshark__autoconfigure()
```

**Verify the MCP tool returns:**
- [ ] Step-by-step instructions for analyzing projects
- [ ] Detection steps for package.json, test configs, linter configs
- [ ] Tool installation guidance
- [ ] Example lucidshark.yml templates
- [ ] Common exclusion patterns
- [ ] Threshold recommendations
- [ ] Instructions to call validate_config() after generation

---

### 3.4 Validate Configuration via MCP

```bash
cd "$TEST_WORKSPACE/axios"
```

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Reports axios config as valid
- [ ] Shows parsed domains and tools
- [ ] Lists enabled domains

**Test with invalid config:**
```bash
# Temporarily break the config
cp lucidshark.yml lucidshark.yml.backup
echo "invalid: yaml: syntax:" > lucidshark.yml
```

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Returns validation error
- [ ] Error message is clear

```bash
# Restore
mv lucidshark.yml.backup lucidshark.yml
```

---

### 3.5 Test Invalid Configurations

Return to a test project and test validation error handling:

```bash
cd "$TEST_WORKSPACE/axios"
```

**Test each invalid config scenario:**

#### 1. Missing version field
```bash
cp lucidshark.yml lucidshark.yml.backup
sed '/^version:/d' lucidshark.yml > lucidshark.yml.tmp && mv lucidshark.yml.tmp lucidshark.yml
lucidshark validate
echo "Exit code (should be non-zero): $?"
mv lucidshark.yml.backup lucidshark.yml
```

**Verify:** [ ] Validation fails with clear error about missing version

#### 2. Invalid tool name
```bash
cp lucidshark.yml lucidshark.yml.backup
sed 's/tools: \[eslint\]/tools: [fake_nonexistent_linter]/' lucidshark.yml > lucidshark.yml.tmp && mv lucidshark.yml.tmp lucidshark.yml
lucidshark validate
echo "Exit code (should be non-zero): $?"
mv lucidshark.yml.backup lucidshark.yml
```

**Verify:** [ ] Validation fails or warns about unknown tool

#### 3. Coverage without testing enabled
```bash
cp lucidshark.yml lucidshark.yml.backup
# Manually edit to disable testing but keep coverage
cat > lucidshark.yml << 'EOF'
version: 1
pipeline:
  testing:
    enabled: false
  coverage:
    enabled: true
    tools: [vitest_coverage]
EOF
lucidshark validate
echo "Exit code: $?"
mv lucidshark.yml.backup lucidshark.yml
```

**Verify:** [ ] Validation fails or warns (coverage requires testing)

---

### 3.6 Test lucidshark init on Real Projects

```bash
cd "$TEST_WORKSPACE/axios"
lucidshark init --dry-run
```

**Verify:**
- [ ] Shows what files would be created
- [ ] Does not conflict with existing package.json, tsconfig.json, etc.

```bash
lucidshark init
```

**Verify:**
- [ ] Creates .mcp.json, .claude/CLAUDE.md, .claude/settings.json, .claude/skills/lucidshark/
- [ ] Does not break existing project structure

### 3.6 Test `lucidshark init` on GitHub Projects

Run init on each cloned project:
```bash
cd "$TEST_WORKSPACE/express" && lucidshark init --dry-run
cd "$TEST_WORKSPACE/axios" && lucidshark init --dry-run
cd "$TEST_WORKSPACE/zustand" && lucidshark init --dry-run
```

**Verify:**
- [ ] Init works on projects with existing `.eslintrc`, `tsconfig.json`, `package.json`, etc.
- [ ] Does not conflict with existing project configs

---

## Phase 4: CLI Scan Testing — Jest Project

Use the test-project-jest for all CLI tests unless otherwise noted.

```bash
cd "$TEST_WORKSPACE/test-project-jest"
```

### 4.1 Linting (ESLint)

#### 4.1.1 CLI — Linting Only (No Config)
Remove or rename `lucidshark.yml` temporarily:
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] ESLint auto-detected for JS/TS project (looks for `.eslintrc.*` or `eslint.config.*`)
- [ ] Finds `@typescript-eslint/no-unused-vars` errors in `main.ts` — `unusedConfig`, `unused`, `os`, `path`, `fs`, `EventEmitter`
- [ ] Finds type annotation issues via `@typescript-eslint` rules
- [ ] Each issue has: file_path, line, column, rule_id, message, severity
- [ ] Exit code is non-zero (issues found)
- [ ] Security-related ESLint rules triggered (e.g., `no-eval` in `security.ts`)

#### 4.1.2 CLI — Linting with Config
```bash
lucidshark scan --linting --all-files --format json
```

**Verify:**
- [ ] Same issues detected as without config
- [ ] Exclude patterns applied (no `node_modules/**` files scanned)
- [ ] No `dist/**` or `coverage/**` files scanned

#### 4.1.3 CLI — Linting Auto-Fix
```bash
cp -r src src.backup
lucidshark scan --linting --all-files --fix --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Auto-fixable issues fixed (e.g., unused imports removed if `--fix` triggers ESLint fix)
- [ ] Files actually modified on disk (diff `src/main.ts` vs backup)
- [ ] Issues that can't be auto-fixed remain
- [ ] Re-scan shows fewer issues

Restore: `rm -rf src && mv src.backup src`

#### 4.1.4 CLI — Linting Specific File
```bash
lucidshark scan --linting --files src/security.ts --format json
```

**Verify:**
- [ ] Only scans `security.ts`
- [ ] Does NOT report issues from `main.ts`

#### 4.1.5 CLI — Linting on Express (Clean Project)
```bash
cd "$TEST_WORKSPACE/express"
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify:**
- [ ] Zero or very few linting issues on well-maintained project
- [ ] ESLint auto-detected (Express uses `.eslintrc.yml`)
- [ ] Handles plain JS files (`.js`) correctly

#### 4.1.6 CLI — Linting on Axios
```bash
cd "$TEST_WORKSPACE/axios"
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify and record issue count.**

### 4.2 Type Checking (TypeScript / tsc)

#### 4.2.1 CLI — Type Checking Only (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] TypeScript compiler (tsc) auto-detected via `tsconfig.json`
- [ ] Finds type error: `const userName: string = 42` in `main.ts`
- [ ] Finds type error: `const x: string = 123` in `processData`
- [ ] Finds type error: `return 42` in `-> string` function
- [ ] Finds type error: wrong types in `addUser` (name/age swapped)
- [ ] Finds `noImplicitReturns` error in `findUser`
- [ ] Finds `noUnusedLocals` / `noUnusedParameters` errors
- [ ] Each issue has severity mapped (expect HIGH)
- [ ] Error codes are TS format (e.g., TS2322, TS7030)

#### 4.2.2 CLI — Type Checking with Config
```bash
lucidshark scan --type-checking --all-files --format json
```

**Verify:**
- [ ] TypeScript tool runs per config
- [ ] Same type errors detected
- [ ] Exclude patterns respected

#### 4.2.3 CLI — Type Checking on Zustand (Well-Typed Project)
```bash
cd "$TEST_WORKSPACE/zustand"
lucidshark scan --type-checking --all-files --format json 2>&1 | head -100
cd "$TEST_WORKSPACE/test-project-jest"
```

**Record results.** Zustand is well-typed, so expect few/zero errors.

#### 4.2.4 CLI — Type Checking on Express (Plain JS — No tsconfig)
```bash
cd "$TEST_WORKSPACE/express"
lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify:**
- [ ] Handles project with no `tsconfig.json` gracefully
- [ ] Either skips type checking or reports "no tsconfig.json found"
- [ ] Does NOT crash

### 4.3 Formatting (Prettier)

#### 4.3.1 CLI — `--formatting` Flag (No Config)
```bash
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --formatting --all-files --format json
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] Does the `--formatting` flag work without config?
- [ ] Prettier auto-detected via `.prettierrc`
- [ ] If it fails, record the exact error message

#### 4.3.2 CLI — Formatting with Config
```bash
lucidshark scan --formatting --all-files --format json
```

**Verify:**
- [ ] Formatting issues detected in `main.ts` (extra spaces, inconsistent indentation)
- [ ] Prettier-specific issues (semicolons, quotes, trailing commas)
- [ ] Check for ghost issue: is there an issue with file_path containing "files" in the message?

#### 4.3.3 CLI — Formatting Auto-Fix
```bash
cp -r src src.backup
lucidshark scan --formatting --all-files --fix --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] `main.ts` reformatted on disk
- [ ] `security.ts` reformatted if needed
- [ ] Re-scan shows zero formatting issues

Restore: `rm -rf src && mv src.backup src`

### 4.4 Testing (Jest)

#### 4.4.1 CLI — Testing Domain
```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Jest auto-detected via `jest.config.ts` and executed
- [ ] Reports test results (pass/fail counts)
- [ ] `processData should uppercase the input string` should FAIL (returns 42)
- [ ] `processData should handle empty string` should FAIL
- [ ] `addUser` test should FAIL (types are wrong — name/age swapped)
- [ ] `basic passing tests` should PASS
- [ ] `badlyFormatted` tests should PASS
- [ ] Reports: passed count, failed count, total count

#### 4.4.2 CLI — Testing + Coverage Together
```bash
# Clean slate — remove any pre-existing coverage data
rm -rf coverage .nyc_output
lucidshark scan --testing --coverage --all-files --format json
echo "Exit code: $?"
# Prove the testing step produced coverage data
ls -la coverage/coverage-summary.json
echo "coverage-summary.json exists: $?"
cat coverage/coverage-summary.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('Line coverage:', d.get('total',{}).get('lines',{}).get('pct','MISSING'))"
```

**Verify:**
- [ ] Jest runs with `--coverage` flag
- [ ] Tests run (pass/fail counts reported)
- [ ] `coverage/coverage-summary.json` exists on disk after scan (verified with `ls`)
- [ ] Coverage percentage in the file is non-zero
- [ ] Coverage percentage in scan output matches the file on disk
- [ ] Coverage threshold comparison works (below 80% → issue)
- [ ] Gap percentage reported

#### 4.4.3 CLI — Testing Specific File
```bash
lucidshark scan --testing --files tests/main.test.ts --format json
```

**Verify:**
- [ ] Only runs tests in `main.test.ts`
- [ ] Jest receives file targeting correctly

### 4.5 Coverage (Istanbul/NYC)

#### 4.5.1 CLI — Coverage Without Testing (Should Error)
```bash
# Clean slate — ensure no leftover coverage data from previous runs
rm -rf coverage .nyc_output
lucidshark scan --coverage --all-files --format json
echo "Exit code: $?"
ls coverage/coverage-summary.json 2>/dev/null
echo "coverage-summary.json exists after coverage-only scan: $?"
```

**Verify:**
- [ ] No `coverage/coverage-summary.json` produced (testing didn't run)
- [ ] Reports error or "no coverage data" (coverage requires testing to run first)
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

### 4.6 Duplication (Duplo)

#### 4.6.1 CLI — Duplication Domain
```bash
lucidshark scan --duplication --all-files --format json
```

**Verify:**
- [ ] Duplo detects duplicates between `duplicate1.ts` and `duplicate2.ts`
- [ ] Reports duplication percentage
- [ ] Reports file locations of duplicate blocks
- [ ] Respects `min_lines: 4` config
- [ ] Handles TypeScript files correctly (not just `.js`)

### 4.7 SAST (OpenGrep)

#### 4.7.1 CLI — SAST Domain
```bash
lucidshark scan --sast --all-files --format json
```

**Verify and record which of these are detected:**
- [ ] Command injection via `execSync(userInput)` in `security.ts`
- [ ] Command injection via `exec(template literal)` in `security.ts`
- [ ] `eval()` usage in `security.ts`
- [ ] SQL injection (string concatenation in query) in `security.ts`
- [ ] SQL injection via template literal in `security.ts`
- [ ] Path traversal (string concat in file path) in `security.ts`
- [ ] Weak crypto via `crypto.createHash('md5')` for password in `security.ts`
- [ ] Hardcoded secrets (`API_KEY`, `DATABASE_URL`, `JWT_SECRET`) in `security.ts`
- [ ] `new Function()` constructor (eval alternative) in `security.ts`
- [ ] Prototype pollution in `merge()` in `security.ts`
- [ ] ReDoS vulnerable regex in `security.ts`
- [ ] Each SAST issue has CWE and/or OWASP references

### 4.8 SCA (Trivy)

#### 4.8.1 CLI — SCA Domain
```bash
lucidshark scan --sca --all-files --format json
```

**Verify:**
- [ ] Trivy scans `package.json` and/or `package-lock.json`
- [ ] Finds known CVEs in old package versions:
  - `express@4.17.1` — known vulnerabilities
  - `lodash@4.17.20` — prototype pollution (CVE-2021-23337)
  - `jsonwebtoken@8.5.1` — known issues
  - `axios@0.21.1` — SSRF vulnerability (CVE-2021-3749)
  - `minimist@1.2.5` — prototype pollution
  - `node-fetch@2.6.1` — known vulnerabilities
  - `tar@6.1.0` — path traversal
- [ ] Each CVE has: CVE ID, severity, affected package, fixed version
- [ ] If Trivy DB download fails, document the error handling behavior

#### 4.8.2 SCA on Axios
```bash
cd "$TEST_WORKSPACE/axios"
lucidshark scan --sca --all-files --format json
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify and record results.**

### 4.9 Full Scan (`--all`)

#### 4.9.1 CLI — `--all` with Config
```bash
lucidshark scan --all --all-files --format json > /tmp/full-scan-jest.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/full-scan-jest.json') as f:
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
lucidshark scan --all --all-files --format json > /tmp/full-scan-jest-no-config.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/full-scan-jest-no-config.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
"
mv lucidshark.yml.bak lucidshark.yml
```

**Verify:**
- [ ] How many domains execute without config?
- [ ] Does it auto-detect ESLint, TypeScript, Prettier, Jest?
- [ ] Compare with `--all` WITH config — are the same domains covered?
- [ ] If not all domains run, document it

### 4.10 Output Formats

Run a scan and test each output format:

```bash
lucidshark scan --linting --all-files --format json > /tmp/out-json.json
lucidshark scan --linting --all-files --format summary > /tmp/out-summary.txt
lucidshark scan --linting --all-files --format table > /tmp/out-table.txt
lucidshark scan --linting --all-files --format ai > /tmp/out-ai.txt
lucidshark scan --linting --all-files --format sarif > /tmp/out-sarif.json
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
git checkout -b test-branch
echo "// new issue" >> src/main.ts
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
- [ ] `--debug` shows detailed debug logs (tool commands, paths, node_modules resolution, etc.)
- [ ] `--verbose` shows info-level logs
- [ ] Note: `--debug` must come BEFORE `scan` subcommand

#### 4.11.5 `--stream`
```bash
lucidshark scan --linting --all-files --stream 2>&1 | head -30
```

**Verify:**
- [ ] Produces streaming output

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
- [ ] Shows available plugins/tools
- [ ] Shows scanner versions (eslint, typescript, prettier, etc.)
- [ ] Shows detected languages (javascript, typescript)
- [ ] Check: does it show configured domains from `lucidshark.yml`?

#### 4.12.2 `lucidshark doctor`
```bash
lucidshark doctor
```

**Verify:**
- [ ] Checks config validity
- [ ] Checks tool availability (eslint, tsc, prettier, jest)
- [ ] Checks node_modules resolution
- [ ] Checks environment (Node.js version, npm)
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
- [ ] Contains domain breakdown

#### 4.12.5 `lucidshark serve --mcp`
```bash
timeout 5 lucidshark serve --mcp 2>&1 || true
```

**Verify:**
- [ ] MCP server starts without crash
- [ ] Outputs MCP protocol initialization

---

## Phase 5: CLI Scan Testing — Vitest Project

Switch to the Vitest test project to test the Biome + Vitest + Vitest Coverage toolchain:

```bash
cd "$TEST_WORKSPACE/test-project-vitest"
```

### 5.1 Linting (Biome)

#### 5.1.1 CLI — Biome Linting
```bash
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Biome auto-detected via `biome.json`
- [ ] Finds unused variable issues
- [ ] Finds any issues via Biome's recommended rules
- [ ] Each issue has: file_path, line, column, rule_id, message, severity
- [ ] Biome rule IDs are in correct format (e.g., `lint/suspicious/noExplicitAny`)

#### 5.1.2 CLI — Biome Auto-Fix
```bash
cp -r src src.backup
lucidshark scan --linting --all-files --fix --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Biome `check --apply` invoked
- [ ] Auto-fixable issues fixed
- [ ] Re-scan shows fewer issues

Restore: `rm -rf src && mv src.backup src`

### 5.2 Testing (Vitest)

#### 5.2.1 CLI — Vitest Testing
```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Vitest auto-detected via `vitest.config.ts`
- [ ] Vitest executed (not Jest!)
- [ ] Reports test results (pass/fail counts)
- [ ] `processData` test should FAIL (returns 42)
- [ ] Basic tests should PASS
- [ ] JSON reporter output parsed correctly

#### 5.2.2 CLI — Vitest + Coverage
```bash
# Clean slate — remove any pre-existing coverage data
rm -rf coverage
lucidshark scan --testing --coverage --all-files --format json
echo "Exit code: $?"
# Prove the testing step produced coverage data
ls -la coverage/coverage-summary.json
echo "coverage-summary.json exists: $?"
cat coverage/coverage-summary.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('Line coverage:', d.get('total',{}).get('lines',{}).get('pct','MISSING'))"
```

**Verify:**
- [ ] Vitest runs with `--coverage` flag
- [ ] Coverage generated via `@vitest/coverage-v8`
- [ ] `coverage/coverage-summary.json` exists on disk after scan (verified with `ls`)
- [ ] Coverage percentage in the file is non-zero
- [ ] Coverage percentage in scan output matches the file on disk
- [ ] Coverage threshold comparison works

### 5.3 Coverage (Vitest Coverage)

#### 5.3.1 CLI — Vitest Coverage Provider
```bash
lucidshark scan --testing --coverage --all-files --coverage-threshold 10 --format json
echo "Exit code: $?"

lucidshark scan --testing --coverage --all-files --coverage-threshold 90 --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] With 10% threshold: no coverage issue
- [ ] With 90% threshold: coverage issue with gap
- [ ] Vitest coverage properly parsed (Istanbul-compatible format)

### 5.4 Full Scan — Vitest Project
```bash
lucidshark scan --all --all-files --format json > /tmp/full-scan-vitest.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/full-scan-vitest.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
for domain, count in data.get('metadata', {}).get('issues_by_domain', {}).items():
    print(f'  {domain}: {count}')
"
```

**Verify:**
- [ ] Biome used for linting (not ESLint)
- [ ] Vitest used for testing (not Jest)
- [ ] Vitest Coverage used (not Istanbul/NYC)
- [ ] All domains executed

---

## Phase 6: CLI Scan Testing — Mocha Project

```bash
cd "$TEST_WORKSPACE/test-project-mocha"
```

### 6.1 Mocha Detection & Execution

#### 6.1.1 CLI — Mocha Testing (No Config)
```bash
mv .mocharc.yml .mocharc.yml.bak 2>/dev/null
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
mv .mocharc.yml.bak .mocharc.yml 2>/dev/null
```

**Verify:**
- [ ] Mocha auto-detected (found in `node_modules/.bin/mocha`)
- [ ] Tests executed successfully
- [ ] Reports test results (pass/fail counts)
- [ ] `capitalize should intentionally fail` test should FAIL
- [ ] Other tests should PASS
- [ ] Exit code non-zero (failures detected)

#### 6.1.2 CLI — Mocha with Config
```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] `.mocharc.yml` detected and used
- [ ] Same test results as without config
- [ ] Test spec pattern from config respected (`test/**/*.test.{js,ts}`)

#### 6.1.3 CLI — Mocha Config File Variants

Test each config format detection:
```bash
# Test .mocharc.json
mv .mocharc.yml .mocharc.yml.bak
echo '{"spec": "test/**/*.test.js", "exit": true}' > .mocharc.json
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
rm .mocharc.json
mv .mocharc.yml.bak .mocharc.yml
```

**Verify:**
- [ ] `.mocharc.json` detected
- [ ] Tests still run correctly

#### 6.1.4 CLI — Mocha JSON Report Parsing
```bash
lucidshark scan --testing --all-files --format json > /tmp/mocha-scan.json
python3 -c "
import json
with open('/tmp/mocha-scan.json') as f:
    data = json.load(f)
issues = [i for i in data.get('issues', []) if i.get('source_tool') == 'mocha']
print(f'Mocha issues: {len(issues)}')
for i in issues:
    print(f'  {i.get(\"title\", \"\")}')
    print(f'    file: {i.get(\"file_path\")}, line: {i.get(\"line_start\")}')
"
```

**Verify:**
- [ ] Failed test converted to UnifiedIssue
- [ ] Issue has file_path extracted from stack trace
- [ ] Issue has line_number extracted from stack trace
- [ ] Issue title includes test name and failure message
- [ ] Issue severity is HIGH
- [ ] Issue has `source_tool: "mocha"`
- [ ] Issue has deterministic ID (re-running produces same ID)

#### 6.1.5 Mocha Config via `package.json`

Many projects (including Express) configure Mocha in `package.json` rather than `.mocharc.*`:

```bash
mv .mocharc.yml .mocharc.yml.bak
# Add mocha config to package.json
python3 -c "
import json
with open('package.json') as f:
    pkg = json.load(f)
pkg['mocha'] = {'spec': 'test/**/*.test.js', 'exit': True, 'recursive': True}
with open('package.json', 'w') as f:
    json.dump(pkg, f, indent=2)
"
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
# Restore
python3 -c "
import json
with open('package.json') as f:
    pkg = json.load(f)
del pkg['mocha']
with open('package.json', 'w') as f:
    json.dump(pkg, f, indent=2)
"
mv .mocharc.yml.bak .mocharc.yml
```

**Verify:**
- [ ] Mocha detects config from `package.json` "mocha" key
- [ ] Tests still run correctly

#### 6.1.6 Create `lucidshark.yml` for Mocha Project

```yaml
version: 1
languages: [javascript]
domains:
  testing:
    enabled: true
    tools: [mocha]
  coverage:
    enabled: true
    tools: [istanbul]
    threshold: 50
exclude_patterns:
  - "node_modules/**"
```

```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Mocha explicitly selected via config
- [ ] Only Mocha runs (not Jest, Vitest, etc.)
- [ ] Results match previous runs

#### 6.1.7 Mocha + NYC/Istanbul Coverage

This is critical — Mocha is the only supported test runner that lacks built-in coverage. It relies on NYC/Istanbul as an external wrapper. LucidShark must invoke NYC to wrap Mocha automatically.

```bash
# Clean slate — no pre-existing coverage data
cd "$TEST_WORKSPACE/test-project-mocha"
rm -rf coverage .nyc_output
ls coverage/coverage-summary.json 2>/dev/null && echo "FAIL: stale coverage data exists" || echo "OK: clean slate"

# LucidShark must produce coverage data itself — no manual npx nyc step
lucidshark scan --testing --coverage --all-files --format json
echo "Exit code: $?"

# Prove the testing step produced coverage data
ls -la coverage/coverage-summary.json 2>/dev/null || ls -la .nyc_output/ 2>/dev/null
echo "Coverage data exists: $?"
cat coverage/coverage-summary.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('Line coverage:', d.get('total',{}).get('lines',{}).get('pct','MISSING'))" 2>/dev/null || echo "No coverage-summary.json found"
```

**Verify:**
- [ ] No pre-existing coverage data before scan (clean slate confirmed)
- [ ] Mocha tests execute
- [ ] LucidShark's testing step itself produces coverage output (NYC wraps Mocha automatically)
- [ ] `coverage/coverage-summary.json` or `.nyc_output/` exists on disk after scan
- [ ] Coverage percentage is non-zero
- [ ] Istanbul plugin finds and parses the coverage data it produced
- [ ] Coverage threshold comparison works (below 50% → issue)
- [ ] Gap percentage reported

Via MCP:
```bash
rm -rf coverage .nyc_output
```
```
mcp__lucidshark__scan(domains=["testing", "coverage"], all_files=true)
```

**Verify:**
- [ ] Same behavior as CLI — coverage data produced by the scan itself
- [ ] `coverage/coverage-summary.json` or `.nyc_output/` exists after MCP scan
- [ ] Coverage data parsed correctly
- [ ] Coverage percentage matches CLI result

#### 6.1.8 Mocha Coverage Threshold Levels
```bash
lucidshark scan --testing --coverage --all-files --coverage-threshold 10 --format json
echo "Exit code: $?"

lucidshark scan --testing --coverage --all-files --coverage-threshold 95 --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] With 10% threshold: no coverage issue
- [ ] With 95% threshold: coverage issue reported with gap

#### 6.1.9 Mocha Test Runner Deduplication

Verify that when multiple JS test runners are available but no config specifies which to use, LucidShark picks only one:

```bash
# Install Jest alongside Mocha (simulating a project with both)
npm install --save-dev jest 2>&1 | tail -3
mv lucidshark.yml lucidshark.yml.bak
lucidshark scan --testing --all-files --format json 2>&1 | head -50
echo "Exit code: $?"
mv lucidshark.yml.bak lucidshark.yml
npm uninstall jest 2>&1 | tail -3
```

**Verify:**
- [ ] Only ONE test runner executed (not both Jest and Mocha)
- [ ] Mocha selected because `.mocharc.yml` exists (config-based priority)
- [ ] No duplicate test results

#### 6.1.10 Mocha on Real-World GitHub Projects

Test Mocha integration against multiple real open-source projects that use Mocha.

**6.1.10a — Express (Plain JS, Mocha)**
```bash
cd "$TEST_WORKSPACE/express"
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Mocha detected for Express project
- [ ] Tests execute (or document if deps are missing)
- [ ] Results reported correctly (pass/fail counts)
- [ ] No crashes on real-world test suite
- [ ] JSON output parseable

**6.1.10b — Sinon (JS, Mocha + .mocharc.yml)**
```bash
cd "$TEST_WORKSPACE/sinon"
# Check what Mocha config format Sinon uses
ls .mocharc.* 2>/dev/null; cat package.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('mocha key:', 'mocha' in d)" 2>/dev/null
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Mocha detected via Sinon's config (`.mocharc.yml` or `package.json`)
- [ ] Tests execute
- [ ] Sinon's test patterns (stubs, spies, mocks) don't confuse the runner
- [ ] Results reported correctly

**6.1.10c — Hexo (JS, Mocha, large test suite)**
```bash
cd "$TEST_WORKSPACE/hexo"
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Mocha detected
- [ ] Large test suite handled (100+ tests) without timeout
- [ ] Results reported correctly
- [ ] Duration reasonable (<600s)

**6.1.10d — Socket.IO (TypeScript, Mocha)**
```bash
cd "$TEST_WORKSPACE/socket.io"
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Mocha detected in TypeScript project
- [ ] Handles Mocha + TypeScript (ts-node/tsx require hooks)
- [ ] If TS compilation fails, error is clear and documented
- [ ] Monorepo structure handled correctly
- [ ] Results reported correctly

**Summary table for real-world Mocha projects:**

| Project | Language | Config Format | Tests Run? | Pass/Fail | Issues |
|---------|----------|--------------|------------|-----------|--------|
| Express | JS | (default) | | | |
| Sinon | JS | .mocharc.yml | | | |
| Hexo | JS | (check) | | | |
| Socket.IO | TS | (check) | | | |

Record any projects where Mocha fails to run and document the root cause.

---

## Phase 7: CLI Scan Testing — Karma Project

```bash
cd "$TEST_WORKSPACE/test-project-karma"
```

### 7.1 Karma Detection

#### 7.1.1 CLI — Testing Domain with Karma
```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Karma auto-detected via `karma.conf.js`
- [ ] Karma executed with `--single-run` flag
- [ ] If ChromeHeadless not available, document the error handling
- [ ] If Karma runs, test results reported (pass/fail)

**Note:** Karma requires a browser environment (ChromeHeadless). If not available in the test environment:
- [ ] Error message clearly mentions missing browser / ChromeHeadless
- [ ] Exit code is non-zero
- [ ] No raw stack trace exposed to user (clean error message)
- [ ] LucidShark records skip with reason (check `--debug` output)
- [ ] Other domains (linting, type_checking) are not affected by Karma failure

---

## Phase 8: MCP Tool Testing

All MCP tests use the Jest test-project with `lucidshark.yml` in place.

```bash
cd "$TEST_WORKSPACE/test-project-jest"
```

### 8.1 `mcp__lucidshark__scan()`

#### 8.1.1 Scan — Individual Domains

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
- [ ] Correct JS/TS tool used (ESLint not Ruff, TypeScript not mypy, Jest not pytest, etc.)
- [ ] Issues returned with proper structure (file_path, line, severity, message)
- [ ] No errors or crashes
- [ ] Results consistent with CLI results for same domain

#### 8.1.2 Scan — All Domains
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] All 8 domains execute
- [ ] Compare total issue counts with CLI `--all` results

#### 8.1.3 Scan — Specific Files
```
mcp__lucidshark__scan(files=["src/security.ts"], domains=["linting", "sast"])
```

**Verify:**
- [ ] Only `security.ts` scanned
- [ ] Linting and SAST issues for that file only

#### 8.1.4 Scan — Auto-Fix
```
mcp__lucidshark__scan(domains=["linting"], all_files=true, fix=true)
```

**Verify:**
- [ ] ESLint `--fix` invoked
- [ ] Issues auto-fixed
- [ ] Fewer/zero linting issues in result
- [ ] Files modified on disk

Restore files after: `git checkout -- .`

#### 8.1.5 Scan — Formatting Fix via MCP
```
mcp__lucidshark__scan(domains=["formatting"], all_files=true, fix=true)
```

**Verify:**
- [ ] Prettier `--write` invoked
- [ ] Formatting issues fixed
- [ ] `main.ts` reformatted

Restore: `git checkout -- .`

### 8.2 `mcp__lucidshark__check_file()`

```
mcp__lucidshark__check_file(file_path="src/main.ts")
```

**Verify:**
- [ ] Returns issues for `main.ts`
- [ ] Check which domains run (does it run ALL domains including SCA?)
- [ ] Returns domain_status, issues_by_domain, instructions
- [ ] Response time reasonable for single-file check

```
mcp__lucidshark__check_file(file_path="src/security.ts")
```

**Verify:**
- [ ] Returns security-related issues
- [ ] SAST issues included
- [ ] ESLint `no-eval` rule triggered

### 8.3 `mcp__lucidshark__get_fix_instructions()`

First, run a scan to get issue IDs:
```
mcp__lucidshark__scan(domains=["linting", "sast", "sca", "type_checking"], all_files=true)
```

Then for each type of issue, get fix instructions:

```
mcp__lucidshark__get_fix_instructions(issue_id="<eslint-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<typescript-error-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sast-issue-id>")
mcp__lucidshark__get_fix_instructions(issue_id="<sca-issue-id>")
```

**Verify for each:**
- [ ] Returns priority, fix_steps, suggested_fix
- [ ] Returns documentation_url where applicable
- [ ] Guidance is specific and actionable
- [ ] ESLint fix instructions reference the correct rule
- [ ] TypeScript fix instructions reference the TS error code

**Test with nonexistent ID:**
```
mcp__lucidshark__get_fix_instructions(issue_id="nonexistent-id-12345")
```

**Verify:**
- [ ] Returns "Issue not found" error

### 8.4 `mcp__lucidshark__apply_fix()`

```
mcp__lucidshark__apply_fix(issue_id="<eslint-auto-fixable-issue-id>")
```

**Verify:**
- [ ] Fix applied to file on disk
- [ ] Check: does it fix ONLY the targeted issue or ALL auto-fixable issues in the file?
- [ ] Return message indicates success

**Test with non-linting issue (e.g., TypeScript error):**
```
mcp__lucidshark__apply_fix(issue_id="<typescript-error-id>")
```

**Verify:**
- [ ] Correctly rejects with "Only linting issues support auto-fix" or similar

**Test with SAST issue:**
```
mcp__lucidshark__apply_fix(issue_id="<sast-issue-id>")
```

**Verify:**
- [ ] Correctly rejects

**Test formatting auto-fix via apply_fix:**

First get a formatting issue ID:
```
mcp__lucidshark__scan(domains=["formatting"], all_files=true)
```

Then try to apply fix:
```
mcp__lucidshark__apply_fix(issue_id="<prettier-formatting-issue-id>")
```

**Verify:**
- [ ] Either applies Prettier `--write` fix, or correctly indicates formatting fixes require scan with `fix=true`
- [ ] Document the behavior — does `apply_fix` support formatting issues or only linting?

Restore: `git checkout -- .`

### 8.5 `mcp__lucidshark__get_status()`

```
mcp__lucidshark__get_status()
```

**Verify:**
- [ ] Returns tool inventory
- [ ] Returns scanner versions (eslint, tsc, prettier, jest versions)
- [ ] Shows detected languages: javascript, typescript
- [ ] Check: does `enabled_domains` show all configured domains?

### 8.6 `mcp__lucidshark__get_help()`

```
mcp__lucidshark__get_help()
```

**Verify:**
- [ ] Returns comprehensive documentation
- [ ] Covers all domains, CLI flags, MCP tools
- [ ] Mentions JavaScript/TypeScript support
- [ ] Response size is reasonable (not truncated)

### 8.7 `mcp__lucidshark__autoconfigure()`

```
mcp__lucidshark__autoconfigure()
```

**Verify:**
- [ ] Returns step-by-step analysis instructions
- [ ] Detects JavaScript/TypeScript languages
- [ ] Detects Jest for testing
- [ ] Detects ESLint for linting
- [ ] Provides example configs for JS/TS projects

### 8.8 `mcp__lucidshark__validate_config()`

```
mcp__lucidshark__validate_config()
```

**Verify:**
- [ ] Reports valid config as valid
- [ ] Check with intentionally broken configs (same as Phase 3.5)

### 8.9 MCP Scan on Mocha Project

Switch to Mocha project and verify MCP works:

```bash
cd "$TEST_WORKSPACE/test-project-mocha"
```

```
mcp__lucidshark__scan(domains=["testing"], all_files=true)
```

**Verify:**
- [ ] Mocha used per config (not Jest or Vitest)
- [ ] Test results include pass/fail counts
- [ ] Failed test issues returned with correct structure

### 8.10 MCP Scan on Vitest Project

Switch to Vitest project and verify MCP works with different toolchains:

```bash
cd "$TEST_WORKSPACE/test-project-vitest"
```

```
mcp__lucidshark__scan(domains=["linting"], all_files=true)
```

**Verify:**
- [ ] Biome used (not ESLint) per config

```
mcp__lucidshark__scan(domains=["testing", "coverage"], all_files=true)
```

**Verify:**
- [ ] Vitest used (not Jest) per config
- [ ] Vitest coverage generated

### 8.11 MCP vs CLI Parity

For each domain, compare MCP and CLI results on the Jest test project:

| Domain | CLI Issues | MCP Issues | Match? |
|--------|-----------|------------|--------|
| linting (ESLint) | | | |
| type_checking (tsc) | | | |
| formatting (Prettier) | | | |
| testing (Jest) | | | |
| coverage (Istanbul) | | | |
| duplication (Duplo) | | | |
| sca (Trivy) | | | |
| sast (OpenGrep) | | | |

Document any discrepancies.

---

## Phase 9: Real-World Project Testing

### 9.1 Express

```bash
cd "$TEST_WORKSPACE/express"
```

#### 9.1.1 Create lucidshark.yml for Express
Use autoconfigure or manually create a config appropriate for Express (plain JS, ESLint, Mocha):

```yaml
version: 1
languages: [javascript]
domains:
  linting:
    enabled: true
    tools: [eslint]
  formatting:
    enabled: true
    tools: [prettier]
  testing:
    enabled: true
    tools: [mocha]
  coverage:
    enabled: true
    tools: [istanbul]
    threshold: 50
  sca:
    enabled: true
    tools: [trivy]
  sast:
    enabled: true
    tools: [opengrep]
  duplication:
    enabled: true
    tools: [duplo]
exclude_patterns:
  - "node_modules/**"
```

**Note:** Express uses plain JS (no TypeScript), so type_checking is not applicable. Express uses Mocha for testing with NYC for coverage.

#### 9.1.2 Full Scan
```bash
lucidshark scan --all --all-files --format json > /tmp/express-scan.json
```
Also via MCP:
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] Scan completes without errors
- [ ] Record issue counts per domain
- [ ] No false positives on well-maintained code (especially linting)
- [ ] SCA finds known CVEs if any in Express's deps
- [ ] Record scan duration
- [ ] Handles `.js` files correctly (no TypeScript errors reported for plain JS)

### 9.2 Axios

```bash
cd "$TEST_WORKSPACE/axios"
```

#### 9.2.1 Full Scan (CLI + MCP)
Create config and run full scan.

**Verify:**
- [ ] Scan completes
- [ ] Handles mixed JS/TS codebase correctly
- [ ] Jest tests detected (Axios uses Jest)
- [ ] Record results

### 9.3 Zustand

```bash
cd "$TEST_WORKSPACE/zustand"
```

#### 9.3.1 Full Scan
Create config and run full scan.

**Additional checks:**
- [ ] Type checking works well (Zustand is well-typed)
- [ ] Vitest detected (Zustand uses Vitest)
- [ ] Handles monorepo/workspace structure if applicable
- [ ] Record results

### 9.4 Playwright

```bash
cd "$TEST_WORKSPACE/playwright"
```

#### 9.4.1 Linting + Type Checking Scan (Skip Testing)
Playwright is large; focus on static analysis:

```bash
lucidshark scan --linting --type-checking --all-files --format json 2>&1 | head -200
```

**Additional checks:**
- [ ] Large codebase doesn't cause timeout/OOM
- [ ] Handles monorepo structure
- [ ] Record scan duration and issue count

### 9.5 Sinon (Mocha — JS, .mocharc.yml)

```bash
cd "$TEST_WORKSPACE/sinon"
```

#### 9.5.1 Detect Configuration
```bash
ls -la .mocharc.* .eslintrc* package.json 2>/dev/null
cat .mocharc.yml 2>/dev/null || cat .mocharc.json 2>/dev/null || echo "No standalone mocharc"
```

#### 9.5.2 Create lucidshark.yml for Sinon
```yaml
version: 1
languages: [javascript]
domains:
  linting:
    enabled: true
    tools: [eslint]
  testing:
    enabled: true
    tools: [mocha]
  coverage:
    enabled: true
    tools: [istanbul]
    threshold: 50
  sca:
    enabled: true
    tools: [trivy]
  sast:
    enabled: true
    tools: [opengrep]
  duplication:
    enabled: true
    tools: [duplo]
exclude_patterns:
  - "node_modules/**"
  - "pkg/**"
```

#### 9.5.3 Full Scan
```bash
lucidshark scan --all --all-files --format json > /tmp/sinon-scan.json
echo "Exit code: $?"
python3 -c "
import json
with open('/tmp/sinon-scan.json') as f:
    data = json.load(f)
print('Executed domains:', data.get('metadata', {}).get('executed_domains', []))
print('Total issues:', data.get('metadata', {}).get('total_issues', 0))
for domain, count in data.get('metadata', {}).get('issues_by_domain', {}).items():
    print(f'  {domain}: {count}')
"
```

Also via MCP:
```
mcp__lucidshark__scan(domains=["all"], all_files=true)
```

**Verify:**
- [ ] Scan completes without errors
- [ ] Mocha tests detected and executed
- [ ] `.mocharc.yml` config respected (spec patterns, require hooks)
- [ ] Test results include pass/fail counts
- [ ] ESLint linting runs on JS source files
- [ ] Record issue counts per domain
- [ ] Record scan duration

#### 9.5.4 Mocha Testing Only
```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Only Mocha runs (deduplication works — no Jest/Vitest)
- [ ] Test count matches `npx mocha --recursive` output
- [ ] Failed tests (if any) produce correct UnifiedIssue structure

### 9.6 Hexo (Mocha — JS, large test suite)

```bash
cd "$TEST_WORKSPACE/hexo"
```

#### 9.6.1 Detect Configuration
```bash
ls -la .mocharc.* .eslintrc* package.json 2>/dev/null
python3 -c "import json; d=json.load(open('package.json')); print('scripts.test:', d.get('scripts',{}).get('test','N/A')); print('mocha config:', 'mocha' in d)"
```

#### 9.6.2 Create lucidshark.yml for Hexo
```yaml
version: 1
languages: [javascript]
domains:
  linting:
    enabled: true
    tools: [eslint]
  testing:
    enabled: true
    tools: [mocha]
  coverage:
    enabled: true
    tools: [istanbul]
    threshold: 30
  sca:
    enabled: true
    tools: [trivy]
  duplication:
    enabled: true
    tools: [duplo]
exclude_patterns:
  - "node_modules/**"
  - "tmp/**"
```

#### 9.6.3 Full Scan
```bash
lucidshark scan --all --all-files --format json > /tmp/hexo-scan.json
echo "Exit code: $?"
```

**Verify:**
- [ ] Scan completes without errors
- [ ] Mocha tests executed — large test suite (100+ tests)
- [ ] No timeout (600s limit)
- [ ] Test results accurate (compare with `npx mocha --recursive` output)
- [ ] ESLint handles Hexo's JS codebase
- [ ] Record issue counts and scan duration

#### 9.6.4 Mocha Performance on Large Suite
```bash
time lucidshark scan --testing --all-files --format json > /dev/null
```

**Verify:**
- [ ] Mocha completes within reasonable time (<120s)
- [ ] No memory issues with large result set
- [ ] JSON parsing handles large output

### 9.7 Socket.IO (Mocha — TypeScript, monorepo)

```bash
cd "$TEST_WORKSPACE/socket.io"
```

#### 9.7.1 Detect Configuration
```bash
ls -la .mocharc.* tsconfig*.json package.json 2>/dev/null
python3 -c "import json; d=json.load(open('package.json')); print('scripts.test:', d.get('scripts',{}).get('test','N/A')); print('workspaces:', d.get('workspaces','N/A'))"
```

#### 9.7.2 Create lucidshark.yml for Socket.IO
```yaml
version: 1
languages: [typescript, javascript]
domains:
  linting:
    enabled: true
    tools: [eslint]
  type_checking:
    enabled: true
    tools: [typescript]
  testing:
    enabled: true
    tools: [mocha]
  sca:
    enabled: true
    tools: [trivy]
  sast:
    enabled: true
    tools: [opengrep]
exclude_patterns:
  - "node_modules/**"
  - "dist/**"
  - "build/**"
```

#### 9.7.3 Full Scan
```bash
lucidshark scan --all --all-files --format json > /tmp/socketio-scan.json
echo "Exit code: $?"
```

**Verify:**
- [ ] Scan completes without errors
- [ ] TypeScript type checking runs on `.ts` source files
- [ ] Mocha detects and attempts to run tests
- [ ] Handles TS tests requiring compilation/transpilation (ts-node, tsx)
- [ ] If Mocha fails on TS files without require hooks, document the error clearly
- [ ] Monorepo/workspace structure handled
- [ ] Record issue counts per domain

#### 9.7.4 Mocha + TypeScript Interaction
```bash
lucidshark scan --testing --all-files --format json
echo "Exit code: $?"
lucidshark --debug scan --testing --all-files --format summary 2>&1 | grep -i "mocha\|require\|ts-node\|tsx\|typescript"
```

**Verify:**
- [ ] Debug output shows which Mocha binary is used
- [ ] If `.mocharc.*` contains `--require ts-node/register` or similar, it's respected
- [ ] If no TS transpilation is configured, Mocha fails gracefully with clear message
- [ ] No silent empty results (the no-tests-found detection should trigger)

### Real-World Mocha Summary

Fill in after testing all projects:

| Project | Config Format | Language | Test Count | Pass | Fail | Errors | Duration | Notes |
|---------|--------------|----------|------------|------|------|--------|----------|-------|
| Express | default | JS | | | | | | |
| Sinon | .mocharc.yml | JS | | | | | | |
| Hexo | (check) | JS | | | | | | |
| Socket.IO | (check) | TS | | | | | | |

**Key questions to answer:**
- [ ] Do ALL four Mocha projects produce valid test results?
- [ ] Are there any projects where Mocha is detected but tests fail to run?
- [ ] Is the JSON report correctly parsed for all projects?
- [ ] Does the no-tests-found detection trigger for any project?
- [ ] Is the test runner deduplication correct (Mocha selected over Jest/Vitest where appropriate)?

---

## Phase 10: Edge Case Testing

### 10.1 Empty TypeScript File
```bash
cd "$TEST_WORKSPACE/test-project-jest"
touch src/empty.ts
lucidshark scan --linting --files src/empty.ts --format json
lucidshark scan --type-checking --files src/empty.ts --format json
```

**Verify:**
- [ ] No crash on empty file
- [ ] Zero issues reported

### 10.2 Syntax Error File
```bash
cat > src/broken.ts << 'EOF'
function broken(
    // missing closing paren and colon
    console.log("hello")
EOF
lucidshark scan --linting --files src/broken.ts --format json
lucidshark scan --type-checking --files src/broken.ts --format json
```

**Verify:**
- [ ] Handles syntax errors gracefully
- [ ] Reports syntax error as an issue
- [ ] Does not crash

### 10.3 JSX / TSX File
```bash
cat > src/component.tsx << 'EOF'
import React from 'react';

interface Props {
  name: string;
  count: number;
}

const MyComponent: React.FC<Props> = ({ name, count }) => {
  const unused = "not used";
  return (
    <div>
      <h1>Hello, {name}!</h1>
      <p>Count: {count}</p>
    </div>
  );
};

export default MyComponent;
EOF
lucidshark scan --linting --files src/component.tsx --format json
lucidshark scan --type-checking --files src/component.tsx --format json
```

**Verify:**
- [ ] Handles `.tsx` files correctly
- [ ] ESLint parses JSX without errors
- [ ] TypeScript handles JSX (may need `jsx` compiler option)
- [ ] Unused variable detected

### 10.4 Very Large File
```bash
python3 -c "
for i in range(10000):
    print(f'export function func_{i}(x: number): number {{ return x + {i}; }}')
" > src/large.ts
lucidshark scan --linting --files src/large.ts --format json
echo "Exit code: $?"
```

**Verify:**
- [ ] Handles large file without OOM or timeout
- [ ] Results returned in reasonable time

### 10.5 Non-ASCII / Unicode File
```bash
cat > src/unicode.ts << 'EOF'
/**
 * Módulo con caracteres españoles y emojis
 */

export function grüße(name: string): string {
  return `Hallo, ${name}! 👋`;
}

export const 変数 = "日本語テスト";
EOF
lucidshark scan --linting --files src/unicode.ts --format json
```

**Verify:**
- [ ] Handles Unicode content correctly
- [ ] No encoding errors
- [ ] ESLint/TypeScript processes file without issues

### 10.6 CommonJS vs ESM
```bash
cat > src/cjs.cjs << 'EOF'
const fs = require('fs');
const unused = 'test';
module.exports = { hello: () => 'world' };
EOF

cat > src/esm.mjs << 'EOF'
import fs from 'fs';
const unused = 'test';
export const hello = () => 'world';
EOF

lucidshark scan --linting --files src/cjs.cjs --format json
lucidshark scan --linting --files src/esm.mjs --format json
```

**Verify:**
- [ ] Handles `.cjs` (CommonJS) files
- [ ] Handles `.mjs` (ESM) files
- [ ] Correct module type detection
- [ ] Unused variables detected in both

### 10.7 JavaScript-Only Project (No TypeScript)
```bash
mkdir -p "$TEST_WORKSPACE/js-only"
cd "$TEST_WORKSPACE/js-only"
git init
echo '{"name": "js-only"}' > package.json
cat > index.js << 'EOF'
const unused = 'test';
function hello(name) {
    return 'Hello, ' + name;
}
module.exports = { hello };
EOF
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"

lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify:**
- [ ] ESLint works on plain JS files without TypeScript config
- [ ] Type checking gracefully handles no `tsconfig.json`
- [ ] Does NOT crash on JS-only project

### 10.8 Mixed Language Project
```bash
mkdir -p "$TEST_WORKSPACE/mixed-lang"
cd "$TEST_WORKSPACE/mixed-lang"
git init
mkdir src
echo "import os" > src/app.py
echo "console.log('hello')" > src/app.js
echo "export const x: number = 1;" > src/app.ts
echo "package main" > src/main.go
lucidshark scan --linting --all-files --format json
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify:**
- [ ] Handles multiple languages
- [ ] Runs appropriate linter for each (Ruff for Python, ESLint for JS/TS)
- [ ] No cross-contamination of results

### 10.9 Monorepo / Workspaces with Project References

Test the standard TypeScript monorepo pattern with project references and path aliases:

```bash
mkdir -p "$TEST_WORKSPACE/monorepo/packages/api/src"
mkdir -p "$TEST_WORKSPACE/monorepo/packages/web/src"
mkdir -p "$TEST_WORKSPACE/monorepo/packages/shared/src"
cd "$TEST_WORKSPACE/monorepo"
git init

cat > package.json << 'EOF'
{
  "name": "monorepo",
  "private": true,
  "workspaces": ["packages/*"]
}
EOF

# Root tsconfig with project references
cat > tsconfig.json << 'EOF'
{
  "files": [],
  "references": [
    { "path": "packages/shared" },
    { "path": "packages/api" },
    { "path": "packages/web" }
  ]
}
EOF

# Shared package
cat > packages/shared/tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "strict": true,
    "composite": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "declaration": true
  },
  "include": ["src/**/*"]
}
EOF
cat > packages/shared/src/types.ts << 'EOF'
export interface User {
  id: number;
  name: string;
  email: string;
}

export function validateUser(user: User): boolean {
  const unused = "test";
  return user.id > 0 && user.name.length > 0;
}

// Type error: returning string from boolean function
export function isActive(user: User): boolean {
  return user.name;
}
EOF

# API package with path aliases
cat > packages/api/tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "strict": true,
    "composite": true,
    "outDir": "./dist",
    "rootDir": "./src",
    "paths": {
      "@shared/*": ["../shared/src/*"]
    },
    "baseUrl": "."
  },
  "references": [{ "path": "../shared" }],
  "include": ["src/**/*"]
}
EOF
cat > packages/api/src/index.ts << 'EOF'
import { User, validateUser } from '@shared/types';

export function createUser(name: string, email: string): User {
  const user: User = { id: 1, name, email };
  validateUser(user);
  return user;
}

// Type error: number assigned to string
export const apiVersion: string = 42;
EOF

# Web package
cat > packages/web/tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "strict": true,
    "composite": true,
    "outDir": "./dist",
    "rootDir": "./src"
  },
  "references": [{ "path": "../shared" }],
  "include": ["src/**/*"]
}
EOF
echo "export const y: number = 'hello';" > packages/web/src/index.ts

lucidshark scan --type-checking --all-files --format json
echo "Exit code: $?"
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify:**
- [ ] TypeScript handles project references (`"references"` in tsconfig)
- [ ] Path aliases (`@shared/*`) resolved correctly (or document if unsupported)
- [ ] `composite: true` projects processed correctly
- [ ] Issues reported for all three packages (shared, api, web)
- [ ] File paths are correct (relative to monorepo root)
- [ ] Linting handles multiple packages without cross-contamination

### 10.10 Yarn / pnpm Lockfile SCA Scanning

Test that Trivy handles non-npm lockfile formats:

```bash
mkdir -p "$TEST_WORKSPACE/yarn-project"
cd "$TEST_WORKSPACE/yarn-project"
git init
cat > package.json << 'EOF'
{
  "name": "yarn-test",
  "dependencies": {
    "lodash": "4.17.20",
    "axios": "0.21.1"
  }
}
EOF

# Create a minimal yarn.lock with known vulnerable packages
cat > yarn.lock << 'EOF'
# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
# yarn lockance v1

axios@0.21.1:
  version "0.21.1"
  resolved "https://registry.yarnpkg.com/axios/-/axios-0.21.1.tgz"

lodash@4.17.20:
  version "4.17.20"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.20.tgz"
EOF

lucidshark scan --sca --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify:**
- [ ] Trivy scans `yarn.lock` file
- [ ] Finds CVEs in lodash 4.17.20 and axios 0.21.1
- [ ] Lockfile format correctly detected

```bash
mkdir -p "$TEST_WORKSPACE/pnpm-project"
cd "$TEST_WORKSPACE/pnpm-project"
git init
cat > package.json << 'EOF'
{
  "name": "pnpm-test",
  "dependencies": {
    "lodash": "4.17.20"
  }
}
EOF

cat > pnpm-lock.yaml << 'EOF'
lockfileVersion: '6.0'
settings:
  autoInstallPeers: true
dependencies:
  lodash:
    specifier: 4.17.20
    version: 4.17.20
packages:
  /lodash@4.17.20:
    resolution: {integrity: sha512-PlhdFcillOINfeV7Ni6oF1TAEayyZBoZ8bcshTHqOYJYlrqzRDxOtxQ}
    dev: false
EOF

lucidshark scan --sca --all-files --format json
echo "Exit code: $?"
cd "$TEST_WORKSPACE/test-project-jest"
```

**Verify:**
- [ ] Trivy scans `pnpm-lock.yaml` file
- [ ] Finds CVEs in lodash 4.17.20
- [ ] pnpm lockfile format correctly detected

### 10.11 `.d.ts` Declaration File Exclusion

Verify that declaration files are correctly excluded when configured:

```bash
cd "$TEST_WORKSPACE/test-project-jest"
cat > src/types.d.ts << 'EOF'
// This declaration file has intentional issues
declare const unusedGlobal: any;
declare function badFunction(x: string): number;
EOF
lucidshark scan --linting --all-files --format json 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
dts_issues = [i for i in data.get('issues', []) if '.d.ts' in str(i.get('file_path', ''))]
print(f'.d.ts issues: {len(dts_issues)}')
"
rm -f src/types.d.ts
```

**Verify:**
- [ ] `.d.ts` files excluded per `exclude_patterns` in `lucidshark.yml`
- [ ] Zero issues from `.d.ts` files

Clean up edge case files:
```bash
cd "$TEST_WORKSPACE/test-project-jest"
rm -f src/empty.ts src/broken.ts src/large.ts src/unicode.ts src/component.tsx src/cjs.cjs src/esm.mjs
```

---

## Phase 11: Installation Method Comparison

If you completed both install.sh (1.1) and pip (1.3) installations, compare them:

### 11.1 Feature Parity
Run a subset of scans with BOTH installation methods and compare:

```bash
# With install.sh binary:
cd "$TEST_WORKSPACE/install-script-test"
cp -r "$TEST_WORKSPACE/test-project-jest/src" .
cp "$TEST_WORKSPACE/test-project-jest/lucidshark.yml" .
cp "$TEST_WORKSPACE/test-project-jest/tsconfig.json" .
cp -r "$TEST_WORKSPACE/test-project-jest/node_modules" . 2>/dev/null || true
./lucidshark scan --linting --all-files --format json > /tmp/install-sh-results.json

# With pip:
source "$TEST_WORKSPACE/pip-install-test/bin/activate"
cd "$TEST_WORKSPACE/test-project-jest"
lucidshark scan --linting --all-files --format json > /tmp/pip-results.json
```

**Compare:**
- [ ] Same issues detected?
- [ ] Same output format?
- [ ] Same exit codes?
- [ ] Any behavioral differences?

### 11.2 Tool Availability
```bash
# install.sh binary
cd "$TEST_WORKSPACE/install-script-test"
./lucidshark doctor

# pip install
cd "$TEST_WORKSPACE/test-project-jest"
lucidshark doctor
```

**Compare which tools are bundled vs. required externally for each method.**
**Note especially:** Does the binary find `node_modules/.bin/eslint`, `tsc`, `prettier`, `jest` correctly?

---

## Phase 12: Regression Checks for Known Bugs (from Python E2E)

Check whether these previously reported bugs also affect JavaScript/TypeScript scanning:

| Bug | Test | Status |
|-----|------|--------|
| BUG-001: `--formatting` CLI flag broken | Run `lucidshark scan --formatting --all-files` without config | |
| BUG-002: `--all` without config only runs 2 domains | Run `lucidshark scan --all --all-files` without config, check executed_domains | |
| BUG-003: formatter ghost issue | Run formatting scan, check for issue with tool output in file_path | |
| BUG-004: Duration always 0ms | Check `duration_ms` in any scan metadata | |
| BUG-005: `enabled_domains` empty without config | Check metadata when scanning without config | |
| BUG-006: `scanners_used` empty for non-security | Check metadata when running linting only | |
| BUG-007: MCP coverage "no data" after testing | Run `mcp__lucidshark__scan(domains=["testing", "coverage"])` | |
| BUG-008: `apply_fix` fixes ALL issues | Fix one ESLint issue, check if other ESLint issues also fixed | |

---

## Phase 13: Tool-Specific Deep Dives

### 13.1 ESLint Configuration Variants

Test ESLint with different config formats:

```bash
cd "$TEST_WORKSPACE/test-project-jest"
```

#### 13.1.1 `.eslintrc.json` (already tested)
Already in place — baseline results.

#### 13.1.2 Flat Config (`eslint.config.js`)
```bash
mv .eslintrc.json .eslintrc.json.bak
cat > eslint.config.js << 'EOF'
import tseslint from '@typescript-eslint/eslint-plugin';

export default [
  {
    files: ['**/*.ts', '**/*.tsx'],
    plugins: { '@typescript-eslint': tseslint },
    rules: {
      '@typescript-eslint/no-unused-vars': 'error',
      'no-eval': 'error',
    },
  },
];
EOF
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
rm eslint.config.js
mv .eslintrc.json.bak .eslintrc.json
```

**Verify:**
- [ ] LucidShark detects flat config
- [ ] ESLint 9+ flat config format works
- [ ] Same issues detected (or document differences)

#### 13.1.3 Flat Config ESM (`eslint.config.mjs`)

ESM projects require `.mjs` config when `"type": "module"` is set:

```bash
mv .eslintrc.json .eslintrc.json.bak
cat > eslint.config.mjs << 'EOF'
import tseslint from '@typescript-eslint/eslint-plugin';
import tsparser from '@typescript-eslint/parser';

export default [
  {
    files: ['**/*.ts', '**/*.tsx'],
    languageOptions: {
      parser: tsparser,
    },
    plugins: { '@typescript-eslint': tseslint },
    rules: {
      '@typescript-eslint/no-unused-vars': 'error',
      'no-eval': 'error',
    },
  },
];
EOF
lucidshark scan --linting --all-files --format json
echo "Exit code: $?"
rm eslint.config.mjs
mv .eslintrc.json.bak .eslintrc.json
```

**Verify:**
- [ ] LucidShark detects `eslint.config.mjs`
- [ ] ESLint processes the ESM config correctly
- [ ] Issues detected

### 13.2 Biome vs ESLint Comparison

Run linting on the same project with both tools:

```bash
cd "$TEST_WORKSPACE/test-project-jest"

# ESLint (already configured)
lucidshark scan --linting --all-files --format json > /tmp/eslint-results.json

# Temporarily switch to Biome
npm install --save-dev @biomejs/biome
cat > biome.json << 'EOF'
{ "linter": { "enabled": true, "rules": { "recommended": true } } }
EOF
# Edit lucidshark.yml to use biome instead of eslint
sed 's/tools: \[eslint\]/tools: [biome]/' lucidshark.yml > lucidshark.yml.tmp && mv lucidshark.yml.tmp lucidshark.yml
lucidshark scan --linting --all-files --format json > /tmp/biome-results.json
# Restore
sed 's/tools: \[biome\]/tools: [eslint]/' lucidshark.yml > lucidshark.yml.tmp && mv lucidshark.yml.tmp lucidshark.yml
rm biome.json
```

**Compare:**
- [ ] How many issues each finds
- [ ] Rule ID formats (ESLint vs Biome)
- [ ] Severity mapping consistency
- [ ] Auto-fix behavior differences

### 13.3 Prettier vs Biome Formatting

Compare formatting tools:

```bash
# Prettier (already configured)
lucidshark scan --formatting --all-files --format json > /tmp/prettier-results.json

# Temporarily switch to Biome formatting
sed 's/tools: \[prettier\]/tools: [biome]/' lucidshark.yml > lucidshark.yml.tmp && mv lucidshark.yml.tmp lucidshark.yml
lucidshark scan --formatting --all-files --format json > /tmp/biome-fmt-results.json
# Restore
sed 's/tools: \[biome\]/tools: [prettier]/' lucidshark.yml > lucidshark.yml.tmp && mv lucidshark.yml.tmp lucidshark.yml
```

**Compare:**
- [ ] Same files flagged as needing formatting?
- [ ] Both fix modes work?

### 13.4 Jest vs Vitest vs Mocha Comparison

Compare test runners using the same test logic:

From Phase 4.4 (Jest), Phase 5.2 (Vitest), and Phase 6 (Mocha), compare:
- [ ] Test discovery behavior
- [ ] Pass/fail reporting format
- [ ] Coverage output compatibility (Jest=Istanbul, Vitest=V8, Mocha=NYC)
- [ ] Timeout handling
- [ ] File targeting behavior
- [ ] Config file detection
- [ ] JSON report format differences (Jest/Vitest use same format, Mocha uses its own)

### 13.5 Node Module Resolution

Verify LucidShark finds tools in `node_modules/.bin/`:

```bash
cd "$TEST_WORKSPACE/test-project-jest"

# Check which binary paths are resolved
lucidshark --debug scan --linting --all-files --format summary 2>&1 | grep -i "eslint\|node_modules\|binary\|command"
lucidshark --debug scan --type-checking --all-files --format summary 2>&1 | grep -i "tsc\|typescript\|node_modules\|binary\|command"
lucidshark --debug scan --formatting --all-files --format summary 2>&1 | grep -i "prettier\|node_modules\|binary\|command"
lucidshark --debug scan --testing --all-files --format summary 2>&1 | grep -i "jest\|node_modules\|binary\|command"
```

**Verify:**
- [ ] ESLint resolved from `node_modules/.bin/eslint`
- [ ] tsc resolved from `node_modules/.bin/tsc`
- [ ] Prettier resolved from `node_modules/.bin/prettier`
- [ ] Jest resolved from `node_modules/.bin/jest`
- [ ] Falls back to global if not in node_modules

---

## Phase 14: Playwright E2E Detection (Bonus)

If the test project has Playwright configured:

```bash
cd "$TEST_WORKSPACE/test-project-jest"
npm install --save-dev @playwright/test
cat > playwright.config.ts << 'EOF'
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  reporter: 'json',
});
EOF
mkdir -p e2e
cat > e2e/example.spec.ts << 'EOF'
import { test, expect } from '@playwright/test';

test('basic test', async ({ page }) => {
  expect(1 + 1).toBe(2);
});
EOF
```

Update `lucidshark.yml` to include Playwright:
```yaml
testing:
  enabled: true
  tools: [jest, playwright]
```

```bash
lucidshark scan --testing --all-files --format json
```

**Verify:**
- [ ] Playwright detected alongside Jest
- [ ] Playwright tests attempted (may fail without browser install)
- [ ] Document error handling if browsers not installed
- [ ] Jest tests still run correctly alongside Playwright

Clean up:
```bash
rm -rf e2e playwright.config.ts
# Restore lucidshark.yml testing to just jest
```

---

## Test Report Template

Write the report with this structure:

```markdown
# LucidShark JavaScript/TypeScript Support — E2E Test Report

**Date:** YYYY-MM-DD
**Tester:** Claude (model version)
**LucidShark Version:** (from `lucidshark --version`)
**Installation Methods Tested:** install.sh, pip
**Node.js Version:** (from `node --version`)
**npm Version:** (from `npm --version`)
**Platform:** (from `uname -a`)
**Tool Versions:** ESLint X.Y.Z, Biome X.Y.Z, TypeScript X.Y.Z, Prettier X.Y.Z, Jest X.Y.Z, Vitest X.Y.Z, OpenGrep X.Y.Z, Trivy X.Y.Z, Duplo X.Y.Z

---

## Executive Summary
(2-3 paragraph overview: what works, what's broken, overall assessment)

## Installation Testing Results
### install.sh
### pip
### Source Install
### Comparison

## Init & Configuration Results
### lucidshark init
### Autoconfigure
### Config Validation

## CLI Scan Results — Jest Project
### Linting (ESLint)
### Type Checking (TypeScript / tsc)
### Formatting (Prettier)
### Testing (Jest)
### Coverage (Istanbul / NYC)
### Duplication (Duplo)
### SAST (OpenGrep)
### SCA (Trivy)

## CLI Scan Results — Vitest Project
### Linting (Biome)
### Testing (Vitest)
### Coverage (Vitest Coverage)
### Full Scan Comparison

## CLI Scan Results — Mocha Project
### Testing (Mocha)
### Mocha Config Detection (standalone, package.json)
### Mocha + NYC/Istanbul Coverage
### Mocha Coverage Threshold
### Mocha Test Runner Deduplication
### Mocha on Express (Real-World)

## CLI Scan Results — Karma Project
### Testing (Karma)

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
### Express (Plain JS, Mocha)
### Axios (JS/TS, Jest)
### Zustand (TypeScript, Vitest)
### Playwright (TypeScript, Large Monorepo)
### Sinon (JS, Mocha, .mocharc.yml)
### Hexo (JS, Mocha, Large Test Suite)
### Socket.IO (TypeScript, Mocha, Monorepo)
### Real-World Mocha Summary Table

## Edge Case Results
### Empty File
### Syntax Error
### JSX/TSX
### Large File
### Unicode
### CommonJS vs ESM
### JS-Only Project
### Mixed Language
### Monorepo / Project References / Path Aliases
### Yarn / pnpm Lockfile SCA
### .d.ts Declaration File Exclusion

## Tool-Specific Results
### ESLint Config Variants
### Biome vs ESLint Comparison
### Prettier vs Biome Formatting
### Jest vs Vitest vs Mocha Comparison
### Node Module Resolution

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

## Missing Tool Support
(Document any JS/TS ecosystem tools not currently supported that would improve coverage)

## Recommendations (Priority Order)
### P0 — Must Fix
### P1 — Should Fix
### P2 — Nice to Have

## Conclusion
(Overall assessment with score out of 10)
```

---

## Important Notes for the Tester

1. **Execute every command.** Do not skip steps even if you think you know the outcome.
2. **Capture actual output.** Include relevant snippets in the report, not just pass/fail.
3. **Record exit codes** for every `lucidshark scan` command.
4. **Measure wall-clock time** for scans on large projects (Playwright, Axios).
5. **Compare MCP vs CLI** results for the same operation — discrepancies are bugs.
6. **Check for regressions** against all previously reported bugs (BUG-001 through BUG-008).
7. **Test BOTH with and without `lucidshark.yml`** to verify config-less experience.
8. **Clean up** between tests that modify files (`git checkout -- .`).
9. **If disk space is limited**, skip Trivy/SCA tests and note it.
10. **If a tool is not installed** (e.g., opengrep, duplo, biome), document it — don't skip the test.
11. **Verify node_modules resolution** — JS/TS tools must be found in local `node_modules/.bin/` first.
12. **Test both ESLint and Biome** — they are the two supported linters, projects use one or the other.
13. **Test Jest, Vitest, and Mocha** — they are the three main supported test runners, covering ~90% of JS/TS projects.
14. **Pay attention to `.js` vs `.ts` handling** — LucidShark must handle both correctly.
15. **Document Karma behavior** — Karma requires browser binaries which may not be available in CI.
