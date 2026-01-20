/**
 * Routes with type errors for testing.
 */

interface User {
  id: number;
  name: string;
  email: string;
}

// Type error: parameter type mismatch
function createUser(id: string, name: number): User {
  return {
    id: id, // Type error: string assigned to number
    name: name, // Type error: number assigned to string
    email: "test@example.com",
  };
}

// Type error: missing return in some paths
function findUser(id: number): User {
  if (id > 0) {
    return {
      id: id,
      name: "Test User",
      email: "test@example.com",
    };
  }
  // Missing return - type error
}

// Unsafe type assertion
function processUserInput(input: unknown): string {
  // Type error: unsafe assertion
  return (input as User).name;
}

// Loose equality - ESLint issue
function checkId(a: number, b: string): boolean {
  return a == b; // Should use ===
}

export { createUser, findUser, processUserInput, checkId };
