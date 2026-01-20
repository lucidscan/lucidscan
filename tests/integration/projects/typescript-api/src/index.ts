/**
 * Main entry point with intentional issues for testing.
 */

import express from "express";
import { processUserInput } from "./routes";
import { formatData } from "./helpers"; // Unused import - ESLint issue

const app = express();

// ESLint: using any type
function handleRequest(data: any): any {
  return data;
}

// Type error: wrong return type
function getPort(): string {
  return 3000; // Returns number instead of string
}

// SAST: Prototype pollution vulnerability
function merge(target: object, source: object): object {
  for (const key in source) {
    if (key === "__proto__" || key === "constructor") {
      // Vulnerable: should skip these
    }
    (target as any)[key] = (source as any)[key];
  }
  return target;
}

app.get("/", (req, res) => {
  res.send("Hello World");
});

// Unused variable - ESLint issue
const unusedConfig = {
  debug: true,
};

export { app, handleRequest, getPort, merge };
