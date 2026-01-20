/**
 * Helpers with linting issues for testing.
 */

import _ from "lodash"; // Unused import

// ESLint: unused variable
const DEBUG = true;

// ESLint: any type usage
function formatData(data: any): any {
  return JSON.stringify(data);
}

// Missing return type annotation
function calculateSum(a: number, b: number) {
  return a + b;
}

// Unused function
function deprecatedHelper(): void {
  console.log("This is deprecated");
}

// SAST: Hardcoded credentials
const API_KEY = "sk-1234567890abcdef";
const DB_PASSWORD = "super_secret_password";

// Type error: implicit any in callback
function processItems(items: string[], callback): string[] {
  return items.map(callback);
}

export {
  formatData,
  calculateSum,
  deprecatedHelper,
  API_KEY,
  DB_PASSWORD,
  processItems,
};
